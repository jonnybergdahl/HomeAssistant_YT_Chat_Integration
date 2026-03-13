"""Constants for the YouTube Chat integration."""

DOMAIN = "youtube_chat"
EVENT_KEYWORD_DETECTED = "youtube_chat_keyword_detected"
EVENT_SUPER_CHAT = "youtube_chat_super_chat"
EVENT_SUPER_STICKER = "youtube_chat_super_sticker"
CONF_CHANNEL_ID = "channel_id"
CONF_MONITOR_MODE = "monitor_mode"
CONF_TARGET_CHANNEL_ID = "target_channel_id"
MONITOR_MODE_OWN = "own"
MONITOR_MODE_OTHER = "other"
DEFAULT_POLL_INTERVAL = 10  # seconds, overridden by API response
BROADCAST_CHECK_INTERVAL = 60  # seconds when approaching scheduled start
SCHEDULE_CHECK_INTERVAL = 900  # 15 minutes, when no stream is imminent
ACTIVE_WINDOW_MINUTES = 15  # start frequent polling this many minutes before scheduled start
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

ROLE_EVERYONE = "Everyone"
ROLE_MEMBERS_AND_ABOVE = "Members, moderators, and owner"
ROLE_MODERATORS_AND_OWNER = "Moderators and owner"
ROLE_OWNER_ONLY = "Owner only"
ALLOWED_ROLES = [
    ROLE_EVERYONE,
    ROLE_MEMBERS_AND_ABOVE,
    ROLE_MODERATORS_AND_OWNER,
    ROLE_OWNER_ONLY,
]


def get_device_info(entry) -> dict:
    """Return device info for grouping entities under the channel device."""
    # Use target channel ID for "other" mode, own channel ID for "own" mode
    monitor_mode = entry.data.get(CONF_MONITOR_MODE, MONITOR_MODE_OWN)
    if monitor_mode == MONITOR_MODE_OTHER:
        channel_id = entry.data.get(CONF_TARGET_CHANNEL_ID, entry.entry_id)
    else:
        channel_id = entry.data.get(CONF_CHANNEL_ID, entry.entry_id)

    return {
        "identifiers": {(DOMAIN, channel_id)},
        "name": entry.title,
        "manufacturer": "YouTube",
    }
