"""Constants for the YouTube Chat integration."""

DOMAIN = "youtube_chat"
EVENT_KEYWORD_DETECTED = "youtube_chat_keyword_detected"
CONF_CHANNEL_ID = "channel_id"
CONF_MONITOR_MODE = "monitor_mode"
CONF_TARGET_CHANNEL_ID = "target_channel_id"
MONITOR_MODE_OWN = "own"
MONITOR_MODE_OTHER = "other"
DEFAULT_POLL_INTERVAL = 10  # seconds, overridden by API response
BROADCAST_CHECK_INTERVAL = 60  # seconds when not live
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

ROLE_EVERYONE = "Everyone"
ROLE_MODERATORS_AND_OWNER = "Moderators and owner"
ROLE_OWNER_ONLY = "Owner only"
ALLOWED_ROLES = [ROLE_EVERYONE, ROLE_MODERATORS_AND_OWNER, ROLE_OWNER_ONLY]


def get_device_info(entry) -> dict:
    """Return device info for grouping entities under the channel device."""
    return {
        "identifiers": {(DOMAIN, entry.data.get(CONF_CHANNEL_ID, entry.entry_id))},
        "name": entry.title,
        "manufacturer": "YouTube",
    }
