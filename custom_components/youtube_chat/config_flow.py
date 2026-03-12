"""Config flow for YouTube Chat integration."""

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow

from .const import (
    CONF_CHANNEL_ID,
    CONF_MONITOR_MODE,
    CONF_TARGET_CHANNEL_ID,
    DOMAIN,
    MONITOR_MODE_OTHER,
    MONITOR_MODE_OWN,
    SCOPES,
)

_LOGGER = logging.getLogger(__name__)


class YouTubeChatOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle a config flow for YouTube Chat."""

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize the flow handler."""
        super().__init__()
        self._channels: dict[str, str] = {}
        self._data: dict = {}
        self._youtube = None

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle user-initiated flow, reusing token if an entry already exists."""
        # Check for existing entries we can reuse the token from
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        if existing_entries:
            existing_entry = existing_entries[0]
            # Reuse the existing entry's token data
            token_data = existing_entry.data.get("token")
            if token_data:
                _LOGGER.info("Reusing existing OAuth token for new entry")
                data = dict(existing_entry.data)
                # Remove entry-specific fields so we start fresh
                data.pop(CONF_CHANNEL_ID, None)
                data.pop(CONF_MONITOR_MODE, None)
                data.pop(CONF_TARGET_CHANNEL_ID, None)
                return await self._setup_youtube_and_proceed(data)

        # No existing entry — go through OAuth
        return await super().async_step_user(user_input)

    async def async_oauth_create_entry(self, data: dict) -> ConfigFlowResult:
        """Create an entry for the flow after OAuth completes."""
        _LOGGER.info("Successfully authenticated")
        return await self._setup_youtube_and_proceed(data)

    async def _setup_youtube_and_proceed(self, data: dict) -> ConfigFlowResult:
        """Build YouTube client, fetch channels, and proceed to configuration."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token_data = data["token"]
        credentials = Credentials(
            token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
        )

        try:
            self._youtube = await self.hass.async_add_executor_job(
                lambda: build("youtube", "v3", credentials=credentials)
            )
            response = await self.hass.async_add_executor_job(
                lambda: self._youtube.channels()
                .list(part="snippet", mine=True)
                .execute()
            )
        except Exception:
            _LOGGER.exception("Failed to fetch YouTube channels")
            return self.async_abort(reason="api_error")

        items = response.get("items", [])
        _LOGGER.debug(
            "channels.list(mine=True) returned %d items: %s", len(items), items
        )

        self._data = data

        if not items:
            # No own channels found — skip straight to "Other channel" mode
            return await self.async_step_enter_channel_id()

        # Build channel_id -> title mapping
        self._channels = {ch["id"]: ch["snippet"]["title"] for ch in items}

        if len(self._channels) == 1:
            channel_id = next(iter(self._channels))
            self._data[CONF_CHANNEL_ID] = channel_id
        else:
            return await self.async_step_select_channel()

        # Proceed to monitor mode selection
        return await self.async_step_select_monitor_mode()

    async def async_step_select_channel(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Let the user pick which YouTube channel to use."""
        if user_input is not None:
            self._data[CONF_CHANNEL_ID] = user_input[CONF_CHANNEL_ID]
            return await self.async_step_select_monitor_mode()

        channel_options = {cid: title for cid, title in self._channels.items()}

        return self.async_show_form(
            step_id="select_channel",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CHANNEL_ID): vol.In(channel_options),
                }
            ),
        )

    async def async_step_select_monitor_mode(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Let the user choose to monitor own channel or another channel."""
        if user_input is not None:
            mode = user_input[CONF_MONITOR_MODE]
            if mode == MONITOR_MODE_OTHER:
                return await self.async_step_enter_channel_id()

            # Own channel mode
            self._data[CONF_MONITOR_MODE] = MONITOR_MODE_OWN
            channel_id = self._data[CONF_CHANNEL_ID]
            channel_title = self._channels[channel_id]
            return await self._create_entry(channel_id, channel_title)

        return self.async_show_form(
            step_id="select_monitor_mode",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MONITOR_MODE, default=MONITOR_MODE_OWN
                    ): vol.In(
                        {
                            MONITOR_MODE_OWN: "My channel",
                            MONITOR_MODE_OTHER: "Other channel",
                        }
                    ),
                }
            ),
        )

    async def async_step_enter_channel_id(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Let the user enter a target channel handle or ID to monitor."""
        errors = {}

        if user_input is not None:
            channel_input = user_input[CONF_TARGET_CHANNEL_ID].strip()

            # Detect @handle vs UC... channel ID
            if channel_input.startswith("@"):
                lookup_params = {"part": "snippet", "forHandle": channel_input}
            else:
                lookup_params = {"part": "snippet", "id": channel_input}

            # Validate the channel exists
            try:
                response = await self.hass.async_add_executor_job(
                    lambda: self._youtube.channels()
                    .list(**lookup_params)
                    .execute()
                )
            except Exception:
                _LOGGER.exception("Failed to look up channel %s", channel_input)
                errors["base"] = "channel_not_found"
            else:
                items = response.get("items", [])
                if not items:
                    errors["base"] = "channel_not_found"
                else:
                    # Always store the resolved UC... channel ID
                    resolved_channel_id = items[0]["id"]
                    channel_title = items[0]["snippet"]["title"]
                    self._data[CONF_MONITOR_MODE] = MONITOR_MODE_OTHER
                    self._data[CONF_TARGET_CHANNEL_ID] = resolved_channel_id
                    return await self._create_entry(
                        resolved_channel_id, channel_title
                    )

        return self.async_show_form(
            step_id="enter_channel_id",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARGET_CHANNEL_ID): str,
                }
            ),
            errors=errors,
        )

    async def _create_entry(
        self, unique_channel_id: str, title: str
    ) -> ConfigFlowResult:
        """Create a config entry for the selected channel."""
        await self.async_set_unique_id(unique_channel_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=title, data=self._data)
