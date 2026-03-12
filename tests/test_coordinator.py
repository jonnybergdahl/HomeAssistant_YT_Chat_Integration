"""Tests for the YouTube Chat coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.youtube_chat.const import (
    BROADCAST_CHECK_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    EVENT_KEYWORD_DETECTED,
    EVENT_SUPER_CHAT,
    EVENT_SUPER_STICKER,
    MONITOR_MODE_OTHER,
    MONITOR_MODE_OWN,
    ROLE_EVERYONE,
    ROLE_MODERATORS_AND_OWNER,
    ROLE_OWNER_ONLY,
)
from custom_components.youtube_chat.coordinator import (
    COMMAND_RE,
    YouTubeChatCoordinator,
    is_author_allowed,
)

from .conftest import (
    MOCK_ENTRY_ID,
    MOCK_LIVE_CHAT_ID,
    MOCK_TARGET_CHANNEL_ID,
    MOCK_VIDEO_ID,
    make_broadcast_response,
    make_chat_message,
    make_chat_response,
    make_search_response,
    make_super_chat_message,
    make_super_sticker_message,
    make_video_details_response,
)


# ---------- is_author_allowed ----------


class TestIsAuthorAllowed:
    """Tests for the is_author_allowed helper."""

    def test_everyone_allows_all(self):
        """Everyone role allows any author."""
        assert is_author_allowed({}, ROLE_EVERYONE) is True

    def test_owner_only_requires_owner(self):
        """Owner only role requires isChatOwner."""
        assert is_author_allowed({"isChatOwner": True}, ROLE_OWNER_ONLY) is True
        assert is_author_allowed({"isChatOwner": False}, ROLE_OWNER_ONLY) is False
        assert is_author_allowed({}, ROLE_OWNER_ONLY) is False

    def test_moderators_and_owner_allows_moderator(self):
        """Moderators and owner role allows mods and owner."""
        assert (
            is_author_allowed({"isChatModerator": True}, ROLE_MODERATORS_AND_OWNER)
            is True
        )
        assert (
            is_author_allowed({"isChatOwner": True}, ROLE_MODERATORS_AND_OWNER) is True
        )
        assert (
            is_author_allowed(
                {"isChatModerator": False, "isChatOwner": False},
                ROLE_MODERATORS_AND_OWNER,
            )
            is False
        )

    def test_unknown_role_denies(self):
        """Unknown role string denies everyone."""
        assert is_author_allowed({"isChatOwner": True}, "SomeUnknownRole") is False


# ---------- COMMAND_RE ----------


class TestCommandRegex:
    """Tests for the command regex pattern."""

    def test_valid_command(self):
        """Match a valid !command parameter message."""
        match = COMMAND_RE.match("!lights off")
        assert match is not None
        assert match.group(1) == "lights"
        assert match.group(2) == "off"

    def test_command_with_spaces_in_parameter(self):
        """Parameter can contain spaces."""
        match = COMMAND_RE.match("!scene cozy evening")
        assert match is not None
        assert match.group(1) == "scene"
        assert match.group(2) == "cozy evening"

    def test_no_exclamation_mark(self):
        """Messages without ! don't match."""
        assert COMMAND_RE.match("lights off") is None

    def test_no_parameter(self):
        """Messages with command but no parameter don't match."""
        assert COMMAND_RE.match("!lights") is None

    def test_empty_string(self):
        """Empty string doesn't match."""
        assert COMMAND_RE.match("") is None


# ---------- Coordinator init ----------


class TestCoordinatorInit:
    """Tests for coordinator initialization."""

    def test_own_mode_defaults(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Coordinator initializes correctly in own mode."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        assert coord._monitor_mode == MONITOR_MODE_OWN
        assert coord._target_channel_id is None
        assert coord._is_live is False
        assert coord._viewer_count is None
        assert coord.keywords == ""
        assert coord.allowed_role == ROLE_OWNER_ONLY

    def test_other_mode_stores_target(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Coordinator stores target channel id in other mode."""
        coord = YouTubeChatCoordinator(
            hass,
            mock_youtube_api,
            MOCK_ENTRY_ID,
            MONITOR_MODE_OTHER,
            MOCK_TARGET_CHANNEL_ID,
        )
        assert coord._monitor_mode == MONITOR_MODE_OTHER
        assert coord._target_channel_id == MOCK_TARGET_CHANNEL_ID


# ---------- set_keywords ----------


class TestSetKeywords:
    """Tests for the set_keywords method."""

    def test_set_keywords_updates_value(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Setting keywords updates the coordinator state."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord.set_keywords("lights,color,scene")
        assert coord.keywords == "lights,color,scene"

    def test_set_keywords_triggers_callback(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Setting keywords triggers the on_keywords_changed callback."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        received = []
        coord.on_keywords_changed = lambda kws: received.append(kws)

        coord.set_keywords("lights, Color , SCENE")
        assert received == [{"lights", "color", "scene"}]

    def test_set_empty_keywords(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Setting empty keywords sends empty set via callback."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        received = []
        coord.on_keywords_changed = lambda kws: received.append(kws)

        coord.set_keywords("")
        assert received == [set()]


# ---------- Broadcast discovery (own) ----------


class TestBroadcastDiscoveryOwn:
    """Tests for own-channel broadcast discovery."""

    async def test_finds_active_broadcast(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Coordinator finds an active own broadcast."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        mock_youtube_api.liveBroadcasts.return_value.list.return_value.execute.return_value = (
            make_broadcast_response(viewer_count=100)
        )

        await coord._check_for_broadcast()

        assert coord._is_live is True
        assert coord._live_chat_id == MOCK_LIVE_CHAT_ID
        assert coord._viewer_count == 100
        assert coord.update_interval == timedelta(seconds=DEFAULT_POLL_INTERVAL)

    async def test_no_active_broadcast(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Coordinator resets when no broadcast is active."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        mock_youtube_api.liveBroadcasts.return_value.list.return_value.execute.return_value = {
            "items": []
        }

        await coord._check_for_broadcast()

        assert coord._is_live is False
        assert coord._live_chat_id is None
        assert coord.update_interval == timedelta(seconds=BROADCAST_CHECK_INTERVAL)

    async def test_broadcast_without_chat_id(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Broadcast without liveChatId resets state."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        mock_youtube_api.liveBroadcasts.return_value.list.return_value.execute.return_value = {
            "items": [{"snippet": {}, "liveStreamingDetails": {}}]
        }

        await coord._check_for_broadcast()

        assert coord._is_live is False


# ---------- Broadcast discovery (other) ----------


class TestBroadcastDiscoveryOther:
    """Tests for other-channel broadcast discovery."""

    async def test_finds_other_channel_broadcast(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Coordinator discovers another channel's live broadcast."""
        coord = YouTubeChatCoordinator(
            hass,
            mock_youtube_api,
            MOCK_ENTRY_ID,
            MONITOR_MODE_OTHER,
            MOCK_TARGET_CHANNEL_ID,
        )
        mock_youtube_api.search.return_value.list.return_value.execute.return_value = (
            make_search_response()
        )
        mock_youtube_api.videos.return_value.list.return_value.execute.return_value = (
            make_video_details_response(viewer_count=200)
        )

        await coord._check_for_broadcast()

        assert coord._is_live is True
        assert coord._live_chat_id == MOCK_LIVE_CHAT_ID
        assert coord._viewer_count == 200

    async def test_no_live_video_on_other_channel(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """No live video found on the other channel."""
        coord = YouTubeChatCoordinator(
            hass,
            mock_youtube_api,
            MOCK_ENTRY_ID,
            MONITOR_MODE_OTHER,
            MOCK_TARGET_CHANNEL_ID,
        )
        mock_youtube_api.search.return_value.list.return_value.execute.return_value = {
            "items": []
        }

        await coord._check_for_broadcast()

        assert coord._is_live is False

    async def test_video_without_active_chat(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Video exists but has no activeLiveChatId."""
        coord = YouTubeChatCoordinator(
            hass,
            mock_youtube_api,
            MOCK_ENTRY_ID,
            MONITOR_MODE_OTHER,
            MOCK_TARGET_CHANNEL_ID,
        )
        mock_youtube_api.search.return_value.list.return_value.execute.return_value = (
            make_search_response()
        )
        mock_youtube_api.videos.return_value.list.return_value.execute.return_value = {
            "items": [{"liveStreamingDetails": {}}]
        }

        await coord._check_for_broadcast()

        assert coord._is_live is False


# ---------- Chat polling ----------


class TestChatPolling:
    """Tests for chat message polling."""

    async def test_polls_chat_and_processes_messages(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Chat polling processes matching command messages."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID
        coord.allowed_role = ROLE_EVERYONE

        messages = [make_chat_message("!lights off", author_name="Viewer1")]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        # Track events
        events = []
        hass.bus.async_listen(EVENT_KEYWORD_DETECTED, lambda e: events.append(e))

        await coord._poll_chat()

        assert "lights" in coord._keyword_data
        assert coord._keyword_data["lights"]["parameter"] == "off"
        assert coord._keyword_data["lights"]["author"] == "Viewer1"

    async def test_keyword_filter(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Only messages matching keyword filter are processed."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID
        coord.allowed_role = ROLE_EVERYONE
        coord.keywords = "lights"

        messages = [
            make_chat_message("!lights off"),
            make_chat_message("!color red"),
        ]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        assert "lights" in coord._keyword_data
        assert "color" not in coord._keyword_data

    async def test_role_filter(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Only messages from allowed roles are processed."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID
        coord.allowed_role = ROLE_OWNER_ONLY

        messages = [
            make_chat_message("!lights off", is_owner=False),
            make_chat_message("!color red", is_owner=True, author_name="Owner"),
        ]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        assert "lights" not in coord._keyword_data
        assert "color" in coord._keyword_data
        assert coord._keyword_data["color"]["author"] == "Owner"

    async def test_non_command_messages_ignored(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Regular chat messages (no ! prefix) are ignored."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID
        coord.allowed_role = ROLE_EVERYONE

        messages = [
            make_chat_message("hello world"),
            make_chat_message("!noparams"),
        ]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        assert len(coord._keyword_data) == 0

    async def test_chat_message_stores_author_flags(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Chat messages store isChatOwner, isChatSponsor, isChatModerator."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID
        coord.allowed_role = ROLE_EVERYONE

        messages = [
            make_chat_message(
                "!test value",
                is_owner=True,
                is_moderator=True,
                is_sponsor=True,
            )
        ]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        data = coord._keyword_data["test"]
        assert data["is_chat_owner"] is True
        assert data["is_chat_moderator"] is True
        assert data["is_chat_sponsor"] is True

    async def test_updates_polling_interval(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Polling interval is updated from API response."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID

        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(polling_interval_ms=5000)
        )

        await coord._poll_chat()

        assert coord.update_interval == timedelta(milliseconds=5000)


# ---------- Error handling ----------


class TestErrorHandling:
    """Tests for API error handling in _async_update_data."""

    async def test_quota_exceeded_backs_off(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """403 quota error backs off to 5 minutes."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        resp = Response({"status": 403})
        mock_youtube_api.liveBroadcasts.return_value.list.return_value.execute.side_effect = (
            HttpError(resp, b"Quota exceeded")
        )

        result = await coord._async_update_data()

        assert coord.update_interval == timedelta(minutes=5)
        assert result["is_live"] is False

    async def test_404_resets_live_state(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """404 error resets live state (broadcast ended)."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID

        resp = Response({"status": 404})
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.side_effect = (
            HttpError(resp, b"Not found")
        )

        result = await coord._async_update_data()

        assert coord._is_live is False
        assert result["is_live"] is False

    async def test_other_http_error_raises(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Other HTTP errors raise UpdateFailed."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        resp = Response({"status": 500})
        mock_youtube_api.liveBroadcasts.return_value.list.return_value.execute.side_effect = (
            HttpError(resp, b"Server error")
        )

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

    async def test_generic_exception_raises(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Generic exceptions raise UpdateFailed."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        mock_youtube_api.liveBroadcasts.return_value.list.return_value.execute.side_effect = (
            RuntimeError("Connection lost")
        )

        with pytest.raises(UpdateFailed, match="Connection lost"):
            await coord._async_update_data()


# ---------- build_data ----------


class TestBuildData:
    """Tests for the _build_data method."""

    def test_not_live(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Data reflects not-live state."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        data = coord._build_data()
        assert data == {
            "is_live": False,
            "viewer_count": None,
            "keywords": {},
            "last_super_chat": None,
            "last_super_sticker": None,
        }

    def test_live_with_keywords(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Data includes keyword data when live."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._viewer_count = 50
        coord._keyword_data = {"lights": {"parameter": "off"}}

        data = coord._build_data()
        assert data["is_live"] is True
        assert data["viewer_count"] == 50
        assert data["keywords"] == {"lights": {"parameter": "off"}}


# ---------- Super Chat ----------


class TestSuperChat:
    """Tests for Super Chat processing."""

    async def test_processes_super_chat(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Super Chat messages are processed and stored."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID

        messages = [make_super_chat_message(
            amount_display="$10.00",
            amount_micros=10000000,
            currency="USD",
            tier=3,
            comment="Love the stream!",
            author_name="BigDonor",
        )]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        assert coord._last_super_chat is not None
        assert coord._last_super_chat["amount_display_string"] == "$10.00"
        assert coord._last_super_chat["amount_micros"] == 10000000
        assert coord._last_super_chat["currency"] == "USD"
        assert coord._last_super_chat["tier"] == 3
        assert coord._last_super_chat["comment"] == "Love the stream!"
        assert coord._last_super_chat["author"] == "BigDonor"

    async def test_super_chat_fires_event(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Super Chat fires a youtube_chat_super_chat event."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID

        events = []
        hass.bus.async_listen(EVENT_SUPER_CHAT, lambda e: events.append(e))

        messages = [make_super_chat_message(author_name="Donor")]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()
        await hass.async_block_till_done()

        assert len(events) == 1
        assert events[0].data["author"] == "Donor"
        assert events[0].data["amount"] == "$5.00"

    async def test_super_chat_does_not_trigger_keyword(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Super Chat messages don't trigger keyword matching."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID
        coord.allowed_role = ROLE_EVERYONE

        messages = [make_super_chat_message(comment="!lights off")]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        assert len(coord._keyword_data) == 0
        assert coord._last_super_chat is not None

    async def test_super_chat_stores_author_flags(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Super Chat stores isChatOwner, isChatSponsor, isChatModerator."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID

        messages = [make_super_chat_message(is_owner=True, is_sponsor=True)]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        assert coord._last_super_chat["is_chat_owner"] is True
        assert coord._last_super_chat["is_chat_sponsor"] is True
        assert coord._last_super_chat["is_chat_moderator"] is False

    async def test_super_chat_included_in_build_data(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Super Chat data appears in _build_data output."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._last_super_chat = {"amount_display_string": "$5.00"}

        data = coord._build_data()
        assert data["last_super_chat"] == {"amount_display_string": "$5.00"}


# ---------- Super Sticker ----------


class TestSuperSticker:
    """Tests for Super Sticker processing."""

    async def test_processes_super_sticker(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Super Sticker messages are processed and stored."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID

        messages = [make_super_sticker_message(
            amount_display="$2.00",
            sticker_id="sticker_xyz",
            alt_text="Party hat",
            author_name="StickerLover",
        )]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        assert coord._last_super_sticker is not None
        assert coord._last_super_sticker["amount_display_string"] == "$2.00"
        assert coord._last_super_sticker["sticker_id"] == "sticker_xyz"
        assert coord._last_super_sticker["sticker_alt_text"] == "Party hat"
        assert coord._last_super_sticker["author"] == "StickerLover"

    async def test_super_sticker_fires_event(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Super Sticker fires a youtube_chat_super_sticker event."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID

        events = []
        hass.bus.async_listen(EVENT_SUPER_STICKER, lambda e: events.append(e))

        messages = [make_super_sticker_message(author_name="StickerFan")]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()
        await hass.async_block_till_done()

        assert len(events) == 1
        assert events[0].data["author"] == "StickerFan"
        assert events[0].data["sticker_id"] == "sticker_abc123"

    async def test_super_sticker_does_not_trigger_keyword(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Super Sticker messages don't trigger keyword matching."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID
        coord.allowed_role = ROLE_EVERYONE

        messages = [make_super_sticker_message()]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        assert len(coord._keyword_data) == 0
        assert coord._last_super_sticker is not None

    async def test_mixed_messages(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Mixed message types are all processed correctly."""
        coord = YouTubeChatCoordinator(
            hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
        )
        coord._is_live = True
        coord._live_chat_id = MOCK_LIVE_CHAT_ID
        coord.allowed_role = ROLE_EVERYONE

        messages = [
            make_chat_message("!lights on"),
            make_super_chat_message(amount_display="$5.00"),
            make_super_sticker_message(amount_display="$2.00"),
        ]
        mock_youtube_api.liveChatMessages.return_value.list.return_value.execute.return_value = (
            make_chat_response(messages=messages)
        )

        await coord._poll_chat()

        assert "lights" in coord._keyword_data
        assert coord._last_super_chat is not None
        assert coord._last_super_chat["amount_display_string"] == "$5.00"
        assert coord._last_super_sticker is not None
        assert coord._last_super_sticker["amount_display_string"] == "$2.00"
