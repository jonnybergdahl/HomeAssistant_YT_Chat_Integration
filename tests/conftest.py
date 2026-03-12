"""Fixtures for YouTube Chat tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.youtube_chat.const import (
    CONF_CHANNEL_ID,
    CONF_MONITOR_MODE,
    CONF_TARGET_CHANNEL_ID,
    DOMAIN,
    MONITOR_MODE_OTHER,
    MONITOR_MODE_OWN,
)
from custom_components.youtube_chat.coordinator import YouTubeChatCoordinator

MOCK_CHANNEL_ID = "UCtest1234567890"
MOCK_TARGET_CHANNEL_ID = "UCother1234567890"
MOCK_ENTRY_ID = "test_entry_id_123"
MOCK_CHANNEL_TITLE = "TestChannel"
MOCK_TARGET_CHANNEL_TITLE = "OtherChannel"
MOCK_LIVE_CHAT_ID = "live_chat_abc123"
MOCK_VIDEO_ID = "dQw4w9WgXcQ"


@pytest.fixture
def mock_config_entry_own() -> ConfigEntry:
    """Create a mock config entry for own channel monitoring."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title=MOCK_CHANNEL_TITLE,
        data={
            CONF_CHANNEL_ID: MOCK_CHANNEL_ID,
            CONF_MONITOR_MODE: MONITOR_MODE_OWN,
            "token": {
                "access_token": "mock_access_token",
                "refresh_token": "mock_refresh_token",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        },
        source="user",
        unique_id=MOCK_CHANNEL_ID,
    )
    return entry


@pytest.fixture
def mock_config_entry_other() -> ConfigEntry:
    """Create a mock config entry for other channel monitoring."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title=MOCK_TARGET_CHANNEL_TITLE,
        data={
            CONF_CHANNEL_ID: MOCK_CHANNEL_ID,
            CONF_MONITOR_MODE: MONITOR_MODE_OTHER,
            CONF_TARGET_CHANNEL_ID: MOCK_TARGET_CHANNEL_ID,
            "token": {
                "access_token": "mock_access_token",
                "refresh_token": "mock_refresh_token",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        },
        source="user",
        unique_id=MOCK_TARGET_CHANNEL_ID,
    )
    return entry


@pytest.fixture
def mock_youtube_api() -> MagicMock:
    """Create a mock YouTube API client."""
    return _build_mock_youtube()


def _build_mock_youtube() -> MagicMock:
    """Build a mock YouTube API client with chained method mocking."""
    youtube = MagicMock()

    # liveBroadcasts().list().execute()
    broadcasts_list = MagicMock()
    youtube.liveBroadcasts.return_value.list.return_value = broadcasts_list
    broadcasts_list.execute.return_value = {"items": []}

    # search().list().execute()
    search_list = MagicMock()
    youtube.search.return_value.list.return_value = search_list
    search_list.execute.return_value = {"items": []}

    # videos().list().execute()
    videos_list = MagicMock()
    youtube.videos.return_value.list.return_value = videos_list
    videos_list.execute.return_value = {"items": []}

    # liveChatMessages().list().execute()
    chat_list = MagicMock()
    youtube.liveChatMessages.return_value.list.return_value = chat_list
    chat_list.execute.return_value = {
        "items": [],
        "nextPageToken": None,
        "pollingIntervalMillis": 10000,
    }

    # channels().list().execute()
    channels_list = MagicMock()
    youtube.channels.return_value.list.return_value = channels_list
    channels_list.execute.return_value = {"items": []}

    return youtube


def make_broadcast_response(
    live_chat_id: str = MOCK_LIVE_CHAT_ID,
    video_id: str = MOCK_VIDEO_ID,
) -> dict:
    """Build a mock liveBroadcasts.list response."""
    return {
        "items": [
            {
                "id": video_id,
                "snippet": {"liveChatId": live_chat_id},
                "status": {"lifeCycleStatus": "live"},
            }
        ]
    }


def make_search_response(video_id: str = MOCK_VIDEO_ID) -> dict:
    """Build a mock search.list response for a live video."""
    return {
        "items": [
            {
                "id": {"videoId": video_id},
            }
        ]
    }


def make_video_details_response(
    live_chat_id: str = MOCK_LIVE_CHAT_ID,
    viewer_count: int = 42,
) -> dict:
    """Build a mock videos.list response with liveStreamingDetails."""
    return {
        "items": [
            {
                "liveStreamingDetails": {
                    "activeLiveChatId": live_chat_id,
                    "concurrentViewers": str(viewer_count),
                },
            }
        ]
    }


def make_chat_message(
    display_message: str,
    author_name: str = "TestViewer",
    author_channel_id: str = "UCviewer123",
    is_owner: bool = False,
    is_moderator: bool = False,
    is_sponsor: bool = False,
) -> dict:
    """Build a single mock text chat message."""
    return {
        "snippet": {
            "type": "textMessageEvent",
            "displayMessage": display_message,
            "publishedAt": datetime.now(timezone.utc).isoformat(),
        },
        "authorDetails": {
            "displayName": author_name,
            "channelId": author_channel_id,
            "isChatOwner": is_owner,
            "isChatModerator": is_moderator,
            "isChatSponsor": is_sponsor,
        },
    }


def make_super_chat_message(
    amount_display: str = "$5.00",
    amount_micros: int = 5000000,
    currency: str = "USD",
    tier: int = 2,
    comment: str = "Great stream!",
    author_name: str = "GenerousViewer",
    author_channel_id: str = "UCdonor123",
    is_owner: bool = False,
    is_moderator: bool = False,
    is_sponsor: bool = False,
) -> dict:
    """Build a mock Super Chat message."""
    return {
        "snippet": {
            "type": "superChatEvent",
            "publishedAt": datetime.now(timezone.utc).isoformat(),
            "superChatDetails": {
                "amountDisplayString": amount_display,
                "amountMicros": amount_micros,
                "currency": currency,
                "tier": tier,
                "userComment": comment,
            },
        },
        "authorDetails": {
            "displayName": author_name,
            "channelId": author_channel_id,
            "isChatOwner": is_owner,
            "isChatModerator": is_moderator,
            "isChatSponsor": is_sponsor,
        },
    }


def make_super_sticker_message(
    amount_display: str = "$2.00",
    amount_micros: int = 2000000,
    currency: str = "USD",
    tier: int = 1,
    sticker_id: str = "sticker_abc123",
    alt_text: str = "Hype train",
    author_name: str = "StickerFan",
    author_channel_id: str = "UCsticker123",
    is_owner: bool = False,
    is_moderator: bool = False,
    is_sponsor: bool = False,
) -> dict:
    """Build a mock Super Sticker message."""
    return {
        "snippet": {
            "type": "superStickerEvent",
            "publishedAt": datetime.now(timezone.utc).isoformat(),
            "superStickerDetails": {
                "amountDisplayString": amount_display,
                "amountMicros": amount_micros,
                "currency": currency,
                "tier": tier,
                "superStickerMetadata": {
                    "stickerId": sticker_id,
                    "altText": alt_text,
                },
            },
        },
        "authorDetails": {
            "displayName": author_name,
            "channelId": author_channel_id,
            "isChatOwner": is_owner,
            "isChatModerator": is_moderator,
            "isChatSponsor": is_sponsor,
        },
    }


def make_chat_response(
    messages: list[dict] | None = None,
    next_page_token: str | None = "next_token",
    polling_interval_ms: int = 10000,
) -> dict:
    """Build a mock liveChatMessages.list response."""
    return {
        "items": messages or [],
        "nextPageToken": next_page_token,
        "pollingIntervalMillis": polling_interval_ms,
    }
