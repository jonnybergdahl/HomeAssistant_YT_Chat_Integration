"""Binary sensor platform for YouTube Chat integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, get_device_info
from .coordinator import YouTubeChatCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: YouTubeChatCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities([YouTubeChatIsLiveSensor(coordinator, entry)])


class YouTubeChatIsLiveSensor(CoordinatorEntity[YouTubeChatCoordinator], BinarySensorEntity):
    """Binary sensor that indicates if the YouTube channel is currently live."""

    _attr_has_entity_name = True
    _attr_name = "yt_chat_is_live"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: YouTubeChatCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_is_live"
        self._attr_device_info = get_device_info(entry)

    @property
    def is_on(self) -> bool | None:
        """Return true if the channel is live."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("is_live", False)
