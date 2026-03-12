"""Text platform for YouTube Chat integration."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, get_device_info
from .coordinator import YouTubeChatCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up text entities."""
    coordinator: YouTubeChatCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities([YouTubeChatKeywordsText(coordinator, entry)])


class YouTubeChatKeywordsText(RestoreEntity, TextEntity):
    """Text entity for managing the keyword list."""

    _attr_has_entity_name = True
    _attr_translation_key = "keywords"
    _attr_mode = TextMode.TEXT
    _attr_native_max = 1000
    _attr_native_value = ""

    def __init__(
        self, coordinator: YouTubeChatCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the text entity."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_keywords"
        self._attr_device_info = get_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Restore last state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = last_state.state
        # Push initial value to coordinator
        self._coordinator.set_keywords(self._attr_native_value)

    async def async_set_value(self, value: str) -> None:
        """Set the keyword list value."""
        self._attr_native_value = value
        self._coordinator.set_keywords(value)
        self.async_write_ha_state()
