"""YouTube Chat integration for Home Assistant."""

from __future__ import annotations

import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .const import CONF_MONITOR_MODE, CONF_TARGET_CHANNEL_ID, DOMAIN, MONITOR_MODE_OWN
from .coordinator import YouTubeChatCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.TEXT,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up YouTube Chat from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    await session.async_ensure_token_valid()

    token = session.token["access_token"]
    credentials = Credentials(token=token)

    youtube = await hass.async_add_executor_job(
        build, "youtube", "v3", credentials
    )

    monitor_mode = entry.data.get(CONF_MONITOR_MODE, MONITOR_MODE_OWN)
    target_channel_id = entry.data.get(CONF_TARGET_CHANNEL_ID)

    coordinator = YouTubeChatCoordinator(
        hass, youtube, entry.entry_id, monitor_mode, target_channel_id
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "session": session,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
