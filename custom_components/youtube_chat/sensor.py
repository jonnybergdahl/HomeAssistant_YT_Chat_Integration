"""Sensor platform for YouTube Chat integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, get_device_info
from .coordinator import YouTubeChatCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: YouTubeChatCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    # Always add the static sensors
    async_add_entities([
        ViewerCountSensor(coordinator, entry),
        LastSuperChatSensor(coordinator, entry),
        LastSuperStickerSensor(coordinator, entry),
    ])

    # Track keyword sensors so we can add/remove dynamically
    keyword_sensors: dict[str, KeywordSensor] = {}

    @callback
    def _reconcile_keyword_sensors(keywords: set[str]) -> None:
        """Add/remove keyword sensor entities to match the current keyword list."""
        current = set(keyword_sensors.keys())
        to_add = keywords - current
        to_remove = current - keywords

        # Remove entities for keywords no longer in the list
        if to_remove:
            entity_registry = async_get_entity_registry(hass)
            for keyword in to_remove:
                sensor = keyword_sensors.pop(keyword)
                entity_id = entity_registry.async_get_entity_id(
                    "sensor", DOMAIN, sensor.unique_id
                )
                if entity_id:
                    entity_registry.async_remove(entity_id)

        # Add entities for new keywords
        if to_add:
            new_sensors = []
            for keyword in to_add:
                sensor = KeywordSensor(coordinator, entry, keyword)
                keyword_sensors[keyword] = sensor
                new_sensors.append(sensor)
            async_add_entities(new_sensors)

    # Register callback on coordinator so text entity changes trigger reconciliation
    coordinator.on_keywords_changed = _reconcile_keyword_sensors

    # Create initial keyword sensors from coordinator's current keywords value
    if coordinator.keywords:
        initial = {
            k.strip().lower()
            for k in coordinator.keywords.split(",")
            if k.strip()
        }
        _reconcile_keyword_sensors(initial)

    hass.data[DOMAIN][entry.entry_id]["keyword_sensors"] = keyword_sensors


class ViewerCountSensor(CoordinatorEntity[YouTubeChatCoordinator], SensorEntity):
    """Sensor showing the current viewer count."""

    _attr_has_entity_name = True
    _attr_translation_key = "viewer_count"
    _attr_native_unit_of_measurement = "viewers"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: YouTubeChatCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_viewer_count"
        self._attr_device_info = get_device_info(entry)

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.get("is_live", False)

    @property
    def native_value(self) -> int | None:
        """Return the viewer count."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("viewer_count")


class KeywordSensor(
    CoordinatorEntity[YouTubeChatCoordinator], RestoreEntity, SensorEntity
):
    """Sensor showing the last received parameter for a specific keyword."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: YouTubeChatCoordinator,
        entry: ConfigEntry,
        keyword: str,
    ) -> None:
        """Initialize the keyword sensor."""
        super().__init__(coordinator)
        self._keyword = keyword
        self._attr_name = f"Keyword {keyword}"
        self._attr_unique_id = f"{entry.entry_id}_keyword_{keyword}"
        self._attr_device_info = get_device_info(entry)
        self._restored_value: str | None = None
        self._restored_attrs: dict | None = None

    async def async_added_to_hass(self) -> None:
        """Restore last state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            self._restored_value = last_state.state
            self._restored_attrs = dict(last_state.attributes)

    @property
    def native_value(self) -> str | None:
        """Return the last parameter received for this keyword."""
        if self.coordinator.data is not None:
            kw_data = self.coordinator.data.get("keywords", {}).get(self._keyword)
            if kw_data is not None:
                return kw_data["parameter"]
        return self._restored_value

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return extra attributes about the last match."""
        if self.coordinator.data is not None:
            kw_data = self.coordinator.data.get("keywords", {}).get(self._keyword)
            if kw_data is not None:
                return {
                    "author": kw_data["author"],
                    "message": kw_data["message"],
                    "matched_at": kw_data["matched_at"].isoformat(),
                    "is_chat_owner": kw_data["is_chat_owner"],
                    "is_chat_sponsor": kw_data["is_chat_sponsor"],
                    "is_chat_moderator": kw_data["is_chat_moderator"],
                }
        return self._restored_attrs


class LastSuperChatSensor(
    CoordinatorEntity[YouTubeChatCoordinator], RestoreEntity, SensorEntity
):
    """Sensor showing the last received Super Chat."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_super_chat"

    def __init__(
        self, coordinator: YouTubeChatCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_super_chat"
        self._attr_device_info = get_device_info(entry)
        self._restored_value: str | None = None
        self._restored_attrs: dict | None = None

    async def async_added_to_hass(self) -> None:
        """Restore last state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            self._restored_value = last_state.state
            self._restored_attrs = dict(last_state.attributes)

    @property
    def native_value(self) -> str | None:
        """Return the last Super Chat amount display string."""
        if self.coordinator.data is not None:
            sc_data = self.coordinator.data.get("last_super_chat")
            if sc_data is not None:
                return sc_data["amount_display_string"]
        return self._restored_value

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return extra attributes about the last Super Chat."""
        if self.coordinator.data is not None:
            sc_data = self.coordinator.data.get("last_super_chat")
            if sc_data is not None:
                return {
                    "amount_micros": sc_data["amount_micros"],
                    "currency": sc_data["currency"],
                    "tier": sc_data["tier"],
                    "comment": sc_data["comment"],
                    "author": sc_data["author"],
                    "author_channel_id": sc_data["author_channel_id"],
                    "received_at": sc_data["received_at"].isoformat(),
                    "is_chat_owner": sc_data["is_chat_owner"],
                    "is_chat_sponsor": sc_data["is_chat_sponsor"],
                    "is_chat_moderator": sc_data["is_chat_moderator"],
                }
        return self._restored_attrs


class LastSuperStickerSensor(
    CoordinatorEntity[YouTubeChatCoordinator], RestoreEntity, SensorEntity
):
    """Sensor showing the last received Super Sticker."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_super_sticker"

    def __init__(
        self, coordinator: YouTubeChatCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_super_sticker"
        self._attr_device_info = get_device_info(entry)
        self._restored_value: str | None = None
        self._restored_attrs: dict | None = None

    async def async_added_to_hass(self) -> None:
        """Restore last state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            self._restored_value = last_state.state
            self._restored_attrs = dict(last_state.attributes)

    @property
    def native_value(self) -> str | None:
        """Return the last Super Sticker amount display string."""
        if self.coordinator.data is not None:
            ss_data = self.coordinator.data.get("last_super_sticker")
            if ss_data is not None:
                return ss_data["amount_display_string"]
        return self._restored_value

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return extra attributes about the last Super Sticker."""
        if self.coordinator.data is not None:
            ss_data = self.coordinator.data.get("last_super_sticker")
            if ss_data is not None:
                return {
                    "amount_micros": ss_data["amount_micros"],
                    "currency": ss_data["currency"],
                    "tier": ss_data["tier"],
                    "sticker_id": ss_data["sticker_id"],
                    "sticker_alt_text": ss_data["sticker_alt_text"],
                    "author": ss_data["author"],
                    "author_channel_id": ss_data["author_channel_id"],
                    "received_at": ss_data["received_at"].isoformat(),
                    "is_chat_owner": ss_data["is_chat_owner"],
                    "is_chat_sponsor": ss_data["is_chat_sponsor"],
                    "is_chat_moderator": ss_data["is_chat_moderator"],
                }
        return self._restored_attrs
