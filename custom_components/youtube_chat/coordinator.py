"""DataUpdateCoordinator for YouTube Chat integration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging
import re

from googleapiclient.errors import HttpError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ACTIVE_WINDOW_MINUTES,
    BROADCAST_CHECK_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_KEYWORD_DETECTED,
    EVENT_SUPER_CHAT,
    EVENT_SUPER_STICKER,
    MONITOR_MODE_OTHER,
    ROLE_EVERYONE,
    ROLE_MEMBERS_AND_ABOVE,
    ROLE_MODERATORS_AND_OWNER,
    ROLE_OWNER_ONLY,
    SCHEDULE_CHECK_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

COMMAND_RE = re.compile(r"^!(\w+)\s+(.+)$")

# Shared quota backoff: when any coordinator hits quotaExceeded,
# all coordinators skip API calls until this time passes.
# Keyed by hass id so multiple HA instances don't interfere.
_quota_backoff_until: dict[int, datetime] = {}
QUOTA_BACKOFF_MINUTES = 5

MSG_TYPE_TEXT = "textMessageEvent"
MSG_TYPE_SUPER_CHAT = "superChatEvent"
MSG_TYPE_SUPER_STICKER = "superStickerEvent"


def is_author_allowed(author_details: dict, role: str) -> bool:
    """Check if the message author is allowed based on the selected role."""
    if role == ROLE_EVERYONE:
        return True
    if role == ROLE_MEMBERS_AND_ABOVE:
        return (
            author_details.get("isChatSponsor", False)
            or author_details.get("isChatModerator", False)
            or author_details.get("isChatOwner", False)
        )
    if role == ROLE_MODERATORS_AND_OWNER:
        return author_details.get("isChatModerator", False) or author_details.get(
            "isChatOwner", False
        )
    if role == ROLE_OWNER_ONLY:
        return author_details.get("isChatOwner", False)
    return False


class YouTubeChatCoordinator(DataUpdateCoordinator):
    """Coordinator that polls YouTube Live Chat."""

    def __init__(
        self,
        hass: HomeAssistant,
        youtube,
        entry_id: str,
        monitor_mode: str,
        target_channel_id: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        initial_interval = (
            SCHEDULE_CHECK_INTERVAL
            if monitor_mode == MONITOR_MODE_OTHER
            else BROADCAST_CHECK_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=initial_interval),
        )
        self.youtube = youtube
        self.entry_id = entry_id
        self._monitor_mode = monitor_mode
        self._target_channel_id = target_channel_id
        self._uploads_playlist_id: str | None = None
        self._scheduled_start: datetime | None = None
        self._live_chat_id: str | None = None
        self._next_page_token: str | None = None
        self._is_live = False
        self._viewer_count: int | None = None
        # Per-keyword last received data
        self._keyword_data: dict[str, dict] = {}
        # Last Super Chat / Super Sticker data
        self._last_super_chat: dict | None = None
        self._last_super_sticker: dict | None = None

        # State pushed by text/select entities — no entity ID guessing
        self.keywords: str = ""
        self.allowed_role: str = ROLE_OWNER_ONLY

        # Callback for keyword list changes (set by sensor platform)
        self.on_keywords_changed: Callable[[set[str]], None] | None = None

    def set_keywords(self, value: str) -> None:
        """Called by the text entity when keywords change."""
        self.keywords = value
        # Notify sensor platform to reconcile keyword sensors
        if self.on_keywords_changed is not None:
            parsed = {
                k.strip().lower() for k in value.split(",") if k.strip()
            } if value else set()
            self.on_keywords_changed(parsed)

    def set_allowed_role(self, value: str) -> None:
        """Called by the select entity when the role changes."""
        self.allowed_role = value

    async def _async_update_data(self) -> dict:
        """Fetch data from YouTube API."""
        hass_id = id(self.hass)
        now = datetime.now(timezone.utc)

        # If another coordinator already hit quota, skip the API call
        backoff_until = _quota_backoff_until.get(hass_id)
        if backoff_until and now < backoff_until:
            _LOGGER.debug(
                "Skipping API call, quota backoff active until %s",
                backoff_until.isoformat(),
            )
            self.update_interval = timedelta(
                seconds=max(1, (backoff_until - now).total_seconds())
            )
            return self._build_data()

        try:
            if not self._is_live or self._live_chat_id is None:
                await self._check_for_broadcast()
            else:
                await self._poll_chat()
        except HttpError as err:
            if err.resp.status == 403:
                backoff_until = now + timedelta(minutes=QUOTA_BACKOFF_MINUTES)
                _quota_backoff_until[hass_id] = backoff_until
                _LOGGER.warning(
                    "YouTube API quota exceeded, all coordinators backing off for %d minutes",
                    QUOTA_BACKOFF_MINUTES,
                )
                self.update_interval = timedelta(minutes=QUOTA_BACKOFF_MINUTES)
                return self._build_data()
            if err.resp.status == 404:
                _LOGGER.info("Broadcast ended (404), resetting to not live")
                self._reset_live_state()
                return self._build_data()
            raise UpdateFailed(f"YouTube API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with YouTube API: {err}") from err

        return self._build_data()

    async def _check_for_broadcast(self) -> None:
        """Check if there is an active live broadcast."""
        if self._monitor_mode == MONITOR_MODE_OTHER:
            await self._check_for_broadcast_other()
        else:
            await self._check_for_broadcast_own()

    async def _check_for_broadcast_own(self) -> None:
        """Check for own active live broadcast."""
        response = await self.hass.async_add_executor_job(
            self._api_check_broadcast_own
        )

        # Filter for active/live broadcasts (mine=True returns all statuses)
        items = response.get("items", [])
        broadcast = None
        for item in items:
            status = item.get("status", {}).get("lifeCycleStatus")
            if status in ("live", "liveStarting"):
                broadcast = item
                break

        if broadcast is None:
            self._reset_live_state()
            return

        snippet = broadcast.get("snippet", {})
        self._live_chat_id = snippet.get("liveChatId")

        if not self._live_chat_id:
            self._reset_live_state()
            return

        self._is_live = True
        self._next_page_token = None

        # Get viewer count from videos.list (liveBroadcasts doesn't have it)
        video_id = broadcast.get("id")
        if video_id:
            video_response = await self.hass.async_add_executor_job(
                self._api_get_video_details, video_id
            )
            video_items = video_response.get("items", [])
            if video_items:
                details = video_items[0].get("liveStreamingDetails", {})
                viewer_count = details.get("concurrentViewers")
                if viewer_count is not None:
                    self._viewer_count = int(viewer_count)

        self.update_interval = timedelta(seconds=DEFAULT_POLL_INTERVAL)
        _LOGGER.info("Active broadcast found, live chat ID: %s", self._live_chat_id)

    async def _check_for_broadcast_other(self) -> None:
        """Check for another channel's active live broadcast.

        Uses channels.list + playlistItems.list + videos.list (3 units total)
        instead of search.list (100 units) to stay within API quota.

        Polling strategy:
        - No scheduled stream: check every SCHEDULE_CHECK_INTERVAL (15 min)
        - Stream scheduled within ACTIVE_WINDOW_MINUTES: check every
          BROADCAST_CHECK_INTERVAL (60s)
        - Stream is live: switch to chat polling at DEFAULT_POLL_INTERVAL
        """
        # Step 1: Get the uploads playlist ID (cached after first call, 1 unit)
        if self._uploads_playlist_id is None:
            channel_response = await self.hass.async_add_executor_job(
                self._api_get_channel_uploads_playlist
            )
            items = channel_response.get("items", [])
            if not items:
                self._set_idle_state()
                return
            self._uploads_playlist_id = (
                items[0].get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads")
            )
            if not self._uploads_playlist_id:
                self._set_idle_state()
                return

        # Step 2: Get recent videos from the uploads playlist (1 unit)
        playlist_response = await self.hass.async_add_executor_job(
            self._api_get_recent_uploads
        )
        playlist_items = playlist_response.get("items", [])
        if not playlist_items:
            self._set_idle_state()
            return

        # Collect video IDs to check in a single batch
        video_ids = [
            item["contentDetails"]["videoId"]
            for item in playlist_items
            if "contentDetails" in item
        ]
        if not video_ids:
            self._set_idle_state()
            return

        # Step 3: Check liveStreamingDetails for these videos (1 unit)
        video_response = await self.hass.async_add_executor_job(
            self._api_get_video_details, ",".join(video_ids)
        )

        now = datetime.now(timezone.utc)
        earliest_scheduled: datetime | None = None

        for video in video_response.get("items", []):
            details = video.get("liveStreamingDetails", {})

            # Already live — start chat polling
            live_chat_id = details.get("activeLiveChatId")
            if live_chat_id:
                self._live_chat_id = live_chat_id
                self._is_live = True
                self._scheduled_start = None
                self._next_page_token = None

                viewer_count = details.get("concurrentViewers")
                if viewer_count is not None:
                    self._viewer_count = int(viewer_count)

                self.update_interval = timedelta(seconds=DEFAULT_POLL_INTERVAL)
                _LOGGER.info(
                    "Active broadcast found for channel %s, live chat ID: %s",
                    self._target_channel_id,
                    self._live_chat_id,
                )
                return

            # Check for a scheduled (upcoming) stream
            scheduled_str = details.get("scheduledStartTime")
            if scheduled_str:
                try:
                    scheduled = datetime.fromisoformat(
                        scheduled_str.replace("Z", "+00:00")
                    )
                    if scheduled > now and (
                        earliest_scheduled is None or scheduled < earliest_scheduled
                    ):
                        earliest_scheduled = scheduled
                except (ValueError, TypeError):
                    pass

        # No live stream found — adjust interval based on schedule
        self._is_live = False
        self._live_chat_id = None
        self._next_page_token = None
        self._viewer_count = None
        self._scheduled_start = earliest_scheduled

        if earliest_scheduled is not None:
            minutes_until = (earliest_scheduled - now).total_seconds() / 60
            if minutes_until <= ACTIVE_WINDOW_MINUTES:
                self.update_interval = timedelta(seconds=BROADCAST_CHECK_INTERVAL)
                _LOGGER.debug(
                    "Stream on %s scheduled in %.0f minutes, polling every %ds",
                    self._target_channel_id,
                    minutes_until,
                    BROADCAST_CHECK_INTERVAL,
                )
            else:
                # Check again closer to the scheduled time
                seconds_until_active = (
                    (earliest_scheduled - now).total_seconds()
                    - ACTIVE_WINDOW_MINUTES * 60
                )
                self.update_interval = timedelta(
                    seconds=min(SCHEDULE_CHECK_INTERVAL, max(60, seconds_until_active))
                )
                _LOGGER.debug(
                    "Stream on %s scheduled in %.0f minutes, next check in %ds",
                    self._target_channel_id,
                    minutes_until,
                    self.update_interval.total_seconds(),
                )
        else:
            self.update_interval = timedelta(seconds=SCHEDULE_CHECK_INTERVAL)
            _LOGGER.debug(
                "No scheduled streams for %s, checking every %ds",
                self._target_channel_id,
                SCHEDULE_CHECK_INTERVAL,
            )

    def _api_check_broadcast_own(self) -> dict:
        """Call the YouTube API to check for own broadcasts (sync)."""
        return (
            self.youtube.liveBroadcasts()
            .list(
                part="snippet,status",
                mine=True,
            )
            .execute()
        )

    def _api_get_channel_uploads_playlist(self) -> dict:
        """Get the uploads playlist ID for the target channel (sync, 1 unit)."""
        return (
            self.youtube.channels()
            .list(
                part="contentDetails",
                id=self._target_channel_id,
            )
            .execute()
        )

    def _api_get_recent_uploads(self) -> dict:
        """Get recent videos from the uploads playlist (sync, 1 unit)."""
        return (
            self.youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=self._uploads_playlist_id,
                maxResults=5,
            )
            .execute()
        )

    def _api_get_video_details(self, video_id: str) -> dict:
        """Get video details including liveStreamingDetails (sync)."""
        return (
            self.youtube.videos()
            .list(
                part="liveStreamingDetails",
                id=video_id,
            )
            .execute()
        )

    async def _poll_chat(self) -> None:
        """Poll live chat messages."""
        response = await self.hass.async_add_executor_job(self._api_poll_chat)

        # Update polling interval from API response
        polling_interval_ms = response.get("pollingIntervalMillis", DEFAULT_POLL_INTERVAL * 1000)
        self.update_interval = timedelta(milliseconds=polling_interval_ms)

        self._next_page_token = response.get("nextPageToken")

        # Process messages
        messages = response.get("items", [])
        for message in messages:
            self._process_message(message)

    def _api_poll_chat(self) -> dict:
        """Call the YouTube API to poll chat messages (sync)."""
        request_kwargs = {
            "liveChatId": self._live_chat_id,
            "part": "snippet,authorDetails",
        }
        if self._next_page_token:
            request_kwargs["pageToken"] = self._next_page_token

        return self.youtube.liveChatMessages().list(**request_kwargs).execute()

    def _process_message(self, message: dict) -> None:
        """Process a single chat message."""
        snippet = message.get("snippet", {})
        msg_type = snippet.get("type", MSG_TYPE_TEXT)

        if msg_type == MSG_TYPE_SUPER_CHAT:
            self._process_super_chat(message)
        elif msg_type == MSG_TYPE_SUPER_STICKER:
            self._process_super_sticker(message)
        elif msg_type == MSG_TYPE_TEXT:
            self._process_text_message(message)

    def _process_super_chat(self, message: dict) -> None:
        """Process a Super Chat message."""
        snippet = message.get("snippet", {})
        author_details = message.get("authorDetails", {})
        details = snippet.get("superChatDetails", {})

        now = datetime.now(timezone.utc)
        author_name = author_details.get("displayName", "Unknown")

        self._last_super_chat = {
            "amount_display_string": details.get("amountDisplayString", ""),
            "amount_micros": details.get("amountMicros", 0),
            "currency": details.get("currency", ""),
            "tier": details.get("tier", 0),
            "comment": details.get("userComment", ""),
            "author": author_name,
            "author_channel_id": author_details.get("channelId", ""),
            "received_at": now,
            "is_chat_owner": author_details.get("isChatOwner", False),
            "is_chat_sponsor": author_details.get("isChatSponsor", False),
            "is_chat_moderator": author_details.get("isChatModerator", False),
        }

        event_data = {
            "amount": details.get("amountDisplayString", ""),
            "amount_micros": details.get("amountMicros", 0),
            "currency": details.get("currency", ""),
            "tier": details.get("tier", 0),
            "comment": details.get("userComment", ""),
            "author": author_name,
            "author_channel_id": author_details.get("channelId", ""),
            "received_at": now.isoformat(),
        }
        self.hass.bus.async_fire(EVENT_SUPER_CHAT, event_data)
        _LOGGER.debug("Super Chat received: %s from %s", details.get("amountDisplayString"), author_name)

    def _process_super_sticker(self, message: dict) -> None:
        """Process a Super Sticker message."""
        snippet = message.get("snippet", {})
        author_details = message.get("authorDetails", {})
        details = snippet.get("superStickerDetails", {})
        sticker_meta = details.get("superStickerMetadata", {})

        now = datetime.now(timezone.utc)
        author_name = author_details.get("displayName", "Unknown")

        self._last_super_sticker = {
            "amount_display_string": details.get("amountDisplayString", ""),
            "amount_micros": details.get("amountMicros", 0),
            "currency": details.get("currency", ""),
            "tier": details.get("tier", 0),
            "sticker_id": sticker_meta.get("stickerId", ""),
            "sticker_alt_text": sticker_meta.get("altText", ""),
            "author": author_name,
            "author_channel_id": author_details.get("channelId", ""),
            "received_at": now,
            "is_chat_owner": author_details.get("isChatOwner", False),
            "is_chat_sponsor": author_details.get("isChatSponsor", False),
            "is_chat_moderator": author_details.get("isChatModerator", False),
        }

        event_data = {
            "amount": details.get("amountDisplayString", ""),
            "amount_micros": details.get("amountMicros", 0),
            "currency": details.get("currency", ""),
            "tier": details.get("tier", 0),
            "sticker_id": sticker_meta.get("stickerId", ""),
            "sticker_alt_text": sticker_meta.get("altText", ""),
            "author": author_name,
            "author_channel_id": author_details.get("channelId", ""),
            "received_at": now.isoformat(),
        }
        self.hass.bus.async_fire(EVENT_SUPER_STICKER, event_data)
        _LOGGER.debug("Super Sticker received: %s from %s", details.get("amountDisplayString"), author_name)

    def _process_text_message(self, message: dict) -> None:
        """Process a regular text chat message for command matching."""
        snippet = message.get("snippet", {})
        author_details = message.get("authorDetails", {})
        display_message = snippet.get("displayMessage", "")

        # Check role filter
        if not is_author_allowed(author_details, self.allowed_role):
            return

        # Check for command pattern
        match = COMMAND_RE.match(display_message)
        if not match:
            return

        command = match.group(1).lower()
        parameter = match.group(2)

        # Check keyword filter
        if self.keywords:
            allowed_commands = [
                k.strip().lower() for k in self.keywords.split(",") if k.strip()
            ]
            if allowed_commands and command not in allowed_commands:
                return

        # Match found — update per-keyword state and fire event
        now = datetime.now(timezone.utc)
        author_name = author_details.get("displayName", "Unknown")

        self._keyword_data[command] = {
            "parameter": parameter,
            "author": author_name,
            "author_channel_id": author_details.get("channelId", ""),
            "message": display_message,
            "matched_at": now,
            "is_chat_owner": author_details.get("isChatOwner", False),
            "is_chat_sponsor": author_details.get("isChatSponsor", False),
            "is_chat_moderator": author_details.get("isChatModerator", False),
        }

        event_data = {
            "keyword": command,
            "parameter": parameter,
            "author": author_name,
            "author_channel_id": author_details.get("channelId", ""),
            "message": display_message,
            "matched_at": now.isoformat(),
        }
        self.hass.bus.async_fire(EVENT_KEYWORD_DETECTED, event_data)
        _LOGGER.debug("Keyword detected: %s from %s", command, author_name)

    def _set_idle_state(self) -> None:
        """Reset state when no stream is found or scheduled."""
        self._is_live = False
        self._live_chat_id = None
        self._next_page_token = None
        self._viewer_count = None
        self._scheduled_start = None
        self.update_interval = timedelta(seconds=SCHEDULE_CHECK_INTERVAL)

    def _reset_live_state(self) -> None:
        """Reset state when not live (used by own-channel path)."""
        self._is_live = False
        self._live_chat_id = None
        self._next_page_token = None
        self._viewer_count = None
        self.update_interval = timedelta(seconds=BROADCAST_CHECK_INTERVAL)

    def _build_data(self) -> dict:
        """Build the data dict returned to entities."""
        return {
            "is_live": self._is_live,
            "viewer_count": self._viewer_count,
            "keywords": dict(self._keyword_data),
            "last_super_chat": self._last_super_chat,
            "last_super_sticker": self._last_super_sticker,
        }
