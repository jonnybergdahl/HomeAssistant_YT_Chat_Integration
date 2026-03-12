"""Select platform for YouTube Chat integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import ALLOWED_ROLES, DOMAIN, ROLE_OWNER_ONLY, get_device_info
from .coordinator import YouTubeChatCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator: YouTubeChatCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities([YouTubeChatAllowedRolesSelect(coordinator, entry)])


class YouTubeChatAllowedRolesSelect(RestoreEntity, SelectEntity):
    """Select entity for choosing the allowed roles filter."""

    _attr_has_entity_name = True
    _attr_translation_key = "allowed_roles"
    _attr_options = ALLOWED_ROLES
    _attr_current_option = ROLE_OWNER_ONLY

    def __init__(
        self, coordinator: YouTubeChatCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the select entity."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_allowed_roles"
        self._attr_device_info = get_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Restore last state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if (
            last_state
            and last_state.state not in (None, "unknown", "unavailable")
            and last_state.state in ALLOWED_ROLES
        ):
            self._attr_current_option = last_state.state
        # Push initial value to coordinator
        self._coordinator.set_allowed_role(self._attr_current_option)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self._attr_current_option = option
        self._coordinator.set_allowed_role(option)
        self.async_write_ha_state()
