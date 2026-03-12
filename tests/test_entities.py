"""Tests for YouTube Chat entity platforms."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.youtube_chat.binary_sensor import YouTubeChatIsLiveSensor
from custom_components.youtube_chat.const import (
    ALLOWED_ROLES,
    DOMAIN,
    ROLE_EVERYONE,
    ROLE_OWNER_ONLY,
    MONITOR_MODE_OWN,
)
from custom_components.youtube_chat.coordinator import YouTubeChatCoordinator
from custom_components.youtube_chat.select import YouTubeChatAllowedRolesSelect
from custom_components.youtube_chat.sensor import (
    KeywordSensor,
    LastSuperChatSensor,
    LastSuperStickerSensor,
    ViewerCountSensor,
)
from custom_components.youtube_chat.text import YouTubeChatKeywordsText

from .conftest import MOCK_ENTRY_ID


def _make_coordinator(
    hass: HomeAssistant, mock_youtube_api: MagicMock
) -> YouTubeChatCoordinator:
    """Create a coordinator for entity tests."""
    return YouTubeChatCoordinator(
        hass, mock_youtube_api, MOCK_ENTRY_ID, MONITOR_MODE_OWN
    )


def _make_mock_entry() -> MagicMock:
    """Create a mock ConfigEntry for entity constructors."""
    entry = MagicMock()
    entry.entry_id = MOCK_ENTRY_ID
    entry.title = "TestChannel"
    entry.data = {"channel_id": "UCtest123"}
    return entry


# ---------- Binary sensor ----------


class TestIsLiveBinarySensor:
    """Tests for the is_live binary sensor."""

    def test_is_on_when_live(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Binary sensor is on when live."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = {"is_live": True, "viewer_count": 42, "keywords": {}}
        entry = _make_mock_entry()

        sensor = YouTubeChatIsLiveSensor(coord, entry)
        assert sensor.is_on is True

    def test_is_off_when_not_live(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Binary sensor is off when not live."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = {"is_live": False, "viewer_count": None, "keywords": {}}
        entry = _make_mock_entry()

        sensor = YouTubeChatIsLiveSensor(coord, entry)
        assert sensor.is_on is False

    def test_is_none_when_no_data(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Binary sensor returns None when coordinator has no data."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = None
        entry = _make_mock_entry()

        sensor = YouTubeChatIsLiveSensor(coord, entry)
        assert sensor.is_on is None

    def test_unique_id(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Binary sensor has correct unique_id."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = YouTubeChatIsLiveSensor(coord, entry)
        assert sensor.unique_id == f"{MOCK_ENTRY_ID}_is_live"

    def test_entity_name(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Binary sensor has correct name."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = YouTubeChatIsLiveSensor(coord, entry)
        assert sensor.name == "yt_chat_is_live"


# ---------- Viewer count sensor ----------


class TestViewerCountSensor:
    """Tests for the viewer count sensor."""

    def test_returns_viewer_count(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor returns viewer count when live."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = {"is_live": True, "viewer_count": 123, "keywords": {}}
        entry = _make_mock_entry()

        sensor = ViewerCountSensor(coord, entry)
        assert sensor.native_value == 123
        assert sensor.available is True

    def test_unavailable_when_not_live(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Sensor is unavailable when not live."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = {"is_live": False, "viewer_count": None, "keywords": {}}
        entry = _make_mock_entry()

        sensor = ViewerCountSensor(coord, entry)
        assert sensor.available is False

    def test_unavailable_when_no_data(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Sensor is unavailable when coordinator has no data."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = None
        entry = _make_mock_entry()

        sensor = ViewerCountSensor(coord, entry)
        assert sensor.available is False

    def test_returns_none_when_no_data(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Sensor returns None when no data."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = None
        entry = _make_mock_entry()

        sensor = ViewerCountSensor(coord, entry)
        assert sensor.native_value is None

    def test_unique_id(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Viewer count sensor has correct unique_id."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = ViewerCountSensor(coord, entry)
        assert sensor.unique_id == f"{MOCK_ENTRY_ID}_viewer_count"

    def test_unit_of_measurement(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor reports viewers as unit."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = ViewerCountSensor(coord, entry)
        assert sensor.native_unit_of_measurement == "viewers"


# ---------- Keyword sensor ----------


class TestKeywordSensor:
    """Tests for the keyword sensor."""

    def test_returns_parameter_from_coordinator(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Sensor returns the parameter from coordinator data."""
        coord = _make_coordinator(hass, mock_youtube_api)
        now = datetime.now(timezone.utc)
        coord.data = {
            "is_live": True,
            "viewer_count": 10,
            "keywords": {
                "lights": {
                    "parameter": "off",
                    "author": "TestViewer",
                    "message": "!lights off",
                    "matched_at": now,
                    "is_chat_owner": False,
                    "is_chat_sponsor": True,
                    "is_chat_moderator": False,
                }
            },
        }
        entry = _make_mock_entry()

        sensor = KeywordSensor(coord, entry, "lights")
        assert sensor.native_value == "off"

    def test_extra_attributes(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor exposes extra state attributes."""
        coord = _make_coordinator(hass, mock_youtube_api)
        now = datetime.now(timezone.utc)
        coord.data = {
            "is_live": True,
            "viewer_count": 10,
            "keywords": {
                "color": {
                    "parameter": "red",
                    "author": "ArtistViewer",
                    "message": "!color red",
                    "matched_at": now,
                    "is_chat_owner": True,
                    "is_chat_sponsor": False,
                    "is_chat_moderator": True,
                }
            },
        }
        entry = _make_mock_entry()

        sensor = KeywordSensor(coord, entry, "color")
        attrs = sensor.extra_state_attributes

        assert attrs["author"] == "ArtistViewer"
        assert attrs["message"] == "!color red"
        assert attrs["matched_at"] == now.isoformat()
        assert attrs["is_chat_owner"] is True
        assert attrs["is_chat_sponsor"] is False
        assert attrs["is_chat_moderator"] is True

    def test_returns_none_when_no_keyword_data(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Sensor returns None when keyword has not been triggered yet."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = {"is_live": True, "viewer_count": 10, "keywords": {}}
        entry = _make_mock_entry()

        sensor = KeywordSensor(coord, entry, "lights")
        assert sensor.native_value is None

    def test_returns_restored_value_when_no_coordinator_data(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Sensor falls back to restored value."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = {"is_live": False, "viewer_count": None, "keywords": {}}
        entry = _make_mock_entry()

        sensor = KeywordSensor(coord, entry, "lights")
        sensor._restored_value = "on"
        assert sensor.native_value == "on"

    def test_unique_id_includes_keyword(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Keyword sensor unique_id includes the keyword."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = KeywordSensor(coord, entry, "lights")
        assert sensor.unique_id == f"{MOCK_ENTRY_ID}_keyword_lights"

    def test_name_includes_keyword(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Keyword sensor name includes the keyword."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = KeywordSensor(coord, entry, "color")
        assert sensor.name == "yt_chat_keyword_color"


# ---------- Text entity ----------


class TestKeywordsText:
    """Tests for the keywords text entity."""

    def test_initial_state(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Text entity starts with empty value."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        text = YouTubeChatKeywordsText(coord, entry)
        assert text.native_value == ""

    async def test_set_value_updates_coordinator(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Setting text value updates the coordinator keywords."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        text = YouTubeChatKeywordsText(coord, entry)
        # Patch async_write_ha_state since entity isn't fully registered
        text.async_write_ha_state = MagicMock()

        await text.async_set_value("lights,color")

        assert text.native_value == "lights,color"
        assert coord.keywords == "lights,color"

    def test_unique_id(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Text entity has correct unique_id."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        text = YouTubeChatKeywordsText(coord, entry)
        assert text.unique_id == f"{MOCK_ENTRY_ID}_keywords"

    def test_name(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Text entity has correct name."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        text = YouTubeChatKeywordsText(coord, entry)
        assert text.name == "yt_chat_keywords"

    def test_max_length(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Text entity has max length set."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        text = YouTubeChatKeywordsText(coord, entry)
        assert text.native_max == 1000


# ---------- Select entity ----------


class TestAllowedRolesSelect:
    """Tests for the allowed roles select entity."""

    def test_default_option(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Select entity defaults to owner only."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        select = YouTubeChatAllowedRolesSelect(coord, entry)
        assert select.current_option == ROLE_OWNER_ONLY

    def test_options_list(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Select entity has all role options."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        select = YouTubeChatAllowedRolesSelect(coord, entry)
        assert select.options == ALLOWED_ROLES

    async def test_select_option_updates_coordinator(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Selecting an option updates the coordinator."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        select = YouTubeChatAllowedRolesSelect(coord, entry)
        select.async_write_ha_state = MagicMock()

        await select.async_select_option(ROLE_EVERYONE)

        assert select.current_option == ROLE_EVERYONE
        assert coord.allowed_role == ROLE_EVERYONE

    def test_unique_id(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Select entity has correct unique_id."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        select = YouTubeChatAllowedRolesSelect(coord, entry)
        assert select.unique_id == f"{MOCK_ENTRY_ID}_allowed_roles"

    def test_name(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Select entity has correct name."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        select = YouTubeChatAllowedRolesSelect(coord, entry)
        assert select.name == "yt_chat_allowed_roles"


# ---------- Last Super Chat sensor ----------


def _make_data_with_super_chat(now=None):
    """Build coordinator data with a Super Chat."""
    if now is None:
        now = datetime.now(timezone.utc)
    return {
        "is_live": True,
        "viewer_count": 10,
        "keywords": {},
        "last_super_chat": {
            "amount_display_string": "$5.00",
            "amount_micros": 5000000,
            "currency": "USD",
            "tier": 2,
            "comment": "Great stream!",
            "author": "BigDonor",
            "author_channel_id": "UCdonor123",
            "received_at": now,
            "is_chat_owner": False,
            "is_chat_sponsor": True,
            "is_chat_moderator": False,
        },
        "last_super_sticker": None,
    }


def _make_data_with_super_sticker(now=None):
    """Build coordinator data with a Super Sticker."""
    if now is None:
        now = datetime.now(timezone.utc)
    return {
        "is_live": True,
        "viewer_count": 10,
        "keywords": {},
        "last_super_chat": None,
        "last_super_sticker": {
            "amount_display_string": "$2.00",
            "amount_micros": 2000000,
            "currency": "USD",
            "tier": 1,
            "sticker_id": "sticker_xyz",
            "sticker_alt_text": "Party hat",
            "author": "StickerFan",
            "author_channel_id": "UCsticker456",
            "received_at": now,
            "is_chat_owner": True,
            "is_chat_sponsor": False,
            "is_chat_moderator": True,
        },
    }


class TestLastSuperChatSensor:
    """Tests for the last Super Chat sensor."""

    def test_returns_amount(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor returns amount display string."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = _make_data_with_super_chat()
        entry = _make_mock_entry()

        sensor = LastSuperChatSensor(coord, entry)
        assert sensor.native_value == "$5.00"

    def test_extra_attributes(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor exposes all Super Chat attributes."""
        now = datetime.now(timezone.utc)
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = _make_data_with_super_chat(now)
        entry = _make_mock_entry()

        sensor = LastSuperChatSensor(coord, entry)
        attrs = sensor.extra_state_attributes

        assert attrs["amount_micros"] == 5000000
        assert attrs["currency"] == "USD"
        assert attrs["tier"] == 2
        assert attrs["comment"] == "Great stream!"
        assert attrs["author"] == "BigDonor"
        assert attrs["received_at"] == now.isoformat()
        assert attrs["is_chat_owner"] is False
        assert attrs["is_chat_sponsor"] is True
        assert attrs["is_chat_moderator"] is False

    def test_returns_none_when_no_super_chat(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Sensor returns None when no Super Chat received yet."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = {
            "is_live": True, "viewer_count": 10, "keywords": {},
            "last_super_chat": None, "last_super_sticker": None,
        }
        entry = _make_mock_entry()

        sensor = LastSuperChatSensor(coord, entry)
        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None

    def test_falls_back_to_restored_value(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Sensor falls back to restored value."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = {
            "is_live": False, "viewer_count": None, "keywords": {},
            "last_super_chat": None, "last_super_sticker": None,
        }
        entry = _make_mock_entry()

        sensor = LastSuperChatSensor(coord, entry)
        sensor._restored_value = "$10.00"
        assert sensor.native_value == "$10.00"

    def test_unique_id(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor has correct unique_id."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = LastSuperChatSensor(coord, entry)
        assert sensor.unique_id == f"{MOCK_ENTRY_ID}_last_super_chat"

    def test_name(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor has correct name."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = LastSuperChatSensor(coord, entry)
        assert sensor.name == "yt_chat_last_super_chat"


# ---------- Last Super Sticker sensor ----------


class TestLastSuperStickerSensor:
    """Tests for the last Super Sticker sensor."""

    def test_returns_amount(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor returns amount display string."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = _make_data_with_super_sticker()
        entry = _make_mock_entry()

        sensor = LastSuperStickerSensor(coord, entry)
        assert sensor.native_value == "$2.00"

    def test_extra_attributes(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor exposes all Super Sticker attributes including sticker info."""
        now = datetime.now(timezone.utc)
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = _make_data_with_super_sticker(now)
        entry = _make_mock_entry()

        sensor = LastSuperStickerSensor(coord, entry)
        attrs = sensor.extra_state_attributes

        assert attrs["amount_micros"] == 2000000
        assert attrs["currency"] == "USD"
        assert attrs["tier"] == 1
        assert attrs["sticker_id"] == "sticker_xyz"
        assert attrs["sticker_alt_text"] == "Party hat"
        assert attrs["author"] == "StickerFan"
        assert attrs["received_at"] == now.isoformat()
        assert attrs["is_chat_owner"] is True
        assert attrs["is_chat_moderator"] is True

    def test_returns_none_when_no_super_sticker(
        self, hass: HomeAssistant, mock_youtube_api: MagicMock
    ):
        """Sensor returns None when no Super Sticker received."""
        coord = _make_coordinator(hass, mock_youtube_api)
        coord.data = {
            "is_live": True, "viewer_count": 10, "keywords": {},
            "last_super_chat": None, "last_super_sticker": None,
        }
        entry = _make_mock_entry()

        sensor = LastSuperStickerSensor(coord, entry)
        assert sensor.native_value is None

    def test_unique_id(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor has correct unique_id."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = LastSuperStickerSensor(coord, entry)
        assert sensor.unique_id == f"{MOCK_ENTRY_ID}_last_super_sticker"

    def test_name(self, hass: HomeAssistant, mock_youtube_api: MagicMock):
        """Sensor has correct name."""
        coord = _make_coordinator(hass, mock_youtube_api)
        entry = _make_mock_entry()

        sensor = LastSuperStickerSensor(coord, entry)
        assert sensor.name == "yt_chat_last_super_sticker"
