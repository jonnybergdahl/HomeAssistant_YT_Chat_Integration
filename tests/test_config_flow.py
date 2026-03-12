"""Tests for the YouTube Chat config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.youtube_chat.config_flow import YouTubeChatOAuth2FlowHandler
from custom_components.youtube_chat.const import (
    CONF_CHANNEL_ID,
    CONF_MONITOR_MODE,
    CONF_TARGET_CHANNEL_ID,
    DOMAIN,
    MONITOR_MODE_OTHER,
    MONITOR_MODE_OWN,
)

from .conftest import (
    MOCK_CHANNEL_ID,
    MOCK_CHANNEL_TITLE,
    MOCK_TARGET_CHANNEL_ID,
    MOCK_TARGET_CHANNEL_TITLE,
)


MOCK_TOKEN_DATA = {
    "access_token": "mock_access",
    "refresh_token": "mock_refresh",
    "token_type": "Bearer",
    "expires_in": 3600,
}

SINGLE_CHANNEL_RESPONSE = {
    "items": [
        {
            "id": MOCK_CHANNEL_ID,
            "snippet": {"title": MOCK_CHANNEL_TITLE},
        }
    ]
}

MULTI_CHANNEL_RESPONSE = {
    "items": [
        {
            "id": MOCK_CHANNEL_ID,
            "snippet": {"title": MOCK_CHANNEL_TITLE},
        },
        {
            "id": "UCsecond_channel",
            "snippet": {"title": "SecondChannel"},
        },
    ]
}

TARGET_CHANNEL_RESPONSE = {
    "items": [
        {
            "id": MOCK_TARGET_CHANNEL_ID,
            "snippet": {"title": MOCK_TARGET_CHANNEL_TITLE},
        }
    ]
}


def _build_mock_youtube(channels_response: dict) -> MagicMock:
    """Build a mock YouTube client for the config flow."""
    youtube = MagicMock()
    youtube.channels.return_value.list.return_value.execute.return_value = (
        channels_response
    )
    return youtube


def _patch_google(mock_yt: MagicMock):
    """Return context managers that patch google imports inside config_flow."""
    return (
        patch("googleapiclient.discovery.build", return_value=mock_yt),
        patch("google.oauth2.credentials.Credentials"),
    )


def _create_flow(hass: HomeAssistant) -> YouTubeChatOAuth2FlowHandler:
    """Create a flow handler with a mutable context."""
    flow = YouTubeChatOAuth2FlowHandler()
    flow.hass = hass
    flow.context = {"source": "user"}
    return flow


class TestConfigFlowOwnChannel:
    """Tests for the own-channel config flow path."""

    async def test_single_channel_own_mode(self, hass: HomeAssistant):
        """Single channel account skips channel selection, shows monitor mode."""
        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)
            result = await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_monitor_mode"

    async def test_single_channel_own_mode_creates_entry(self, hass: HomeAssistant):
        """Selecting own mode creates entry with channel title."""
        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)

            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})
            result = await flow.async_step_select_monitor_mode(
                {CONF_MONITOR_MODE: MONITOR_MODE_OWN}
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == MOCK_CHANNEL_TITLE
        assert result["data"][CONF_CHANNEL_ID] == MOCK_CHANNEL_ID
        assert result["data"][CONF_MONITOR_MODE] == MONITOR_MODE_OWN

    async def test_multi_channel_shows_selection(self, hass: HomeAssistant):
        """Multiple channels shows channel selection form."""
        mock_yt = _build_mock_youtube(MULTI_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)
            result = await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_channel"

    async def test_multi_channel_select_then_own(self, hass: HomeAssistant):
        """Multi-channel: select channel, then own mode creates entry."""
        mock_yt = _build_mock_youtube(MULTI_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)

            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})
            result = await flow.async_step_select_channel(
                {CONF_CHANNEL_ID: MOCK_CHANNEL_ID}
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_monitor_mode"


class TestConfigFlowOtherChannel:
    """Tests for the other-channel config flow path."""

    async def test_other_mode_shows_channel_id_form(self, hass: HomeAssistant):
        """Choosing other mode shows channel ID entry form."""
        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)

            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})
            result = await flow.async_step_select_monitor_mode(
                {CONF_MONITOR_MODE: MONITOR_MODE_OTHER}
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "enter_channel_id"

    async def test_valid_target_channel_creates_entry(self, hass: HomeAssistant):
        """Entering a valid channel ID creates entry with target channel title."""
        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)

            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})
            await flow.async_step_select_monitor_mode(
                {CONF_MONITOR_MODE: MONITOR_MODE_OTHER}
            )

            # Now return target channel for the lookup
            mock_yt.channels.return_value.list.return_value.execute.return_value = (
                TARGET_CHANNEL_RESPONSE
            )

            result = await flow.async_step_enter_channel_id(
                {CONF_TARGET_CHANNEL_ID: MOCK_TARGET_CHANNEL_ID}
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == MOCK_TARGET_CHANNEL_TITLE
        assert result["data"][CONF_MONITOR_MODE] == MONITOR_MODE_OTHER
        assert result["data"][CONF_TARGET_CHANNEL_ID] == MOCK_TARGET_CHANNEL_ID

    async def test_invalid_channel_id_shows_error(self, hass: HomeAssistant):
        """Entering an invalid channel ID shows error."""
        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)

            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})
            await flow.async_step_select_monitor_mode(
                {CONF_MONITOR_MODE: MONITOR_MODE_OTHER}
            )

            mock_yt.channels.return_value.list.return_value.execute.return_value = {
                "items": []
            }

            result = await flow.async_step_enter_channel_id(
                {CONF_TARGET_CHANNEL_ID: "UCinvalid"}
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "channel_not_found"}

    async def test_api_error_during_channel_lookup(self, hass: HomeAssistant):
        """API error during channel lookup shows error."""
        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)

            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})
            await flow.async_step_select_monitor_mode(
                {CONF_MONITOR_MODE: MONITOR_MODE_OTHER}
            )

            mock_yt.channels.return_value.list.return_value.execute.side_effect = (
                RuntimeError("API down")
            )

            result = await flow.async_step_enter_channel_id(
                {CONF_TARGET_CHANNEL_ID: MOCK_TARGET_CHANNEL_ID}
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "channel_not_found"}


class TestConfigFlowEdgeCases:
    """Tests for edge cases in the config flow."""

    async def test_no_channels_proceeds_to_enter_channel_id(self, hass: HomeAssistant):
        """No own channels skips to enter_channel_id for other-channel mode."""
        mock_yt = _build_mock_youtube({"items": []})
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)
            result = await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "enter_channel_id"

    async def test_no_channels_can_create_other_entry(self, hass: HomeAssistant):
        """No own channels → enter channel ID → creates entry successfully."""
        mock_yt = _build_mock_youtube({"items": []})
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)
            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})

            # Now return target channel for the lookup
            mock_yt.channels.return_value.list.return_value.execute.return_value = (
                TARGET_CHANNEL_RESPONSE
            )

            result = await flow.async_step_enter_channel_id(
                {CONF_TARGET_CHANNEL_ID: MOCK_TARGET_CHANNEL_ID}
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == MOCK_TARGET_CHANNEL_TITLE
        assert result["data"][CONF_MONITOR_MODE] == MONITOR_MODE_OTHER
        assert result["data"][CONF_TARGET_CHANNEL_ID] == MOCK_TARGET_CHANNEL_ID

    async def test_api_error_during_channel_fetch_aborts(self, hass: HomeAssistant):
        """API error fetching own channels aborts."""
        p1 = patch(
            "googleapiclient.discovery.build",
            side_effect=RuntimeError("Build failed"),
        )
        p2 = patch("google.oauth2.credentials.Credentials")

        with p1, p2:
            flow = _create_flow(hass)
            result = await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "api_error"

    async def test_channel_id_is_trimmed(self, hass: HomeAssistant):
        """Whitespace around channel ID is stripped."""
        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)

            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})
            await flow.async_step_select_monitor_mode(
                {CONF_MONITOR_MODE: MONITOR_MODE_OTHER}
            )

            mock_yt.channels.return_value.list.return_value.execute.return_value = (
                TARGET_CHANNEL_RESPONSE
            )

            result = await flow.async_step_enter_channel_id(
                {CONF_TARGET_CHANNEL_ID: f"  {MOCK_TARGET_CHANNEL_ID}  "}
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_TARGET_CHANNEL_ID] == MOCK_TARGET_CHANNEL_ID

    async def test_handle_lookup_uses_for_handle(self, hass: HomeAssistant):
        """@handle input uses forHandle API parameter and resolves to channel ID."""
        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)

            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})
            await flow.async_step_select_monitor_mode(
                {CONF_MONITOR_MODE: MONITOR_MODE_OTHER}
            )

            mock_yt.channels.return_value.list.return_value.execute.return_value = (
                TARGET_CHANNEL_RESPONSE
            )

            result = await flow.async_step_enter_channel_id(
                {CONF_TARGET_CHANNEL_ID: "@targetchannel"}
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Should resolve to the UC... ID from the API response
        assert result["data"][CONF_TARGET_CHANNEL_ID] == MOCK_TARGET_CHANNEL_ID
        assert result["title"] == MOCK_TARGET_CHANNEL_TITLE

        # Verify forHandle was used in the API call
        call_kwargs = mock_yt.channels.return_value.list.call_args.kwargs
        assert "forHandle" in call_kwargs
        assert call_kwargs["forHandle"] == "@targetchannel"
        assert "id" not in call_kwargs

    async def test_channel_id_lookup_uses_id_param(self, hass: HomeAssistant):
        """UC... channel ID input uses id API parameter."""
        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)

            await flow.async_oauth_create_entry({"token": MOCK_TOKEN_DATA})
            await flow.async_step_select_monitor_mode(
                {CONF_MONITOR_MODE: MONITOR_MODE_OTHER}
            )

            mock_yt.channels.return_value.list.return_value.execute.return_value = (
                TARGET_CHANNEL_RESPONSE
            )

            result = await flow.async_step_enter_channel_id(
                {CONF_TARGET_CHANNEL_ID: MOCK_TARGET_CHANNEL_ID}
            )

        # Verify id was used in the API call
        call_kwargs = mock_yt.channels.return_value.list.call_args.kwargs
        assert "id" in call_kwargs
        assert call_kwargs["id"] == MOCK_TARGET_CHANNEL_ID
        assert "forHandle" not in call_kwargs


class TestConfigFlowTokenReuse:
    """Tests for reusing existing OAuth tokens."""

    async def test_reuses_token_from_existing_entry(self, hass: HomeAssistant):
        """When an entry already exists, skip OAuth and reuse its token."""
        # Create a mock existing config entry
        existing_entry = MagicMock()
        existing_entry.data = {
            "token": MOCK_TOKEN_DATA,
            "auth_implementation": "test",
            CONF_CHANNEL_ID: MOCK_CHANNEL_ID,
            CONF_MONITOR_MODE: MONITOR_MODE_OWN,
        }
        hass.config_entries.async_entries = MagicMock(return_value=[existing_entry])

        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)
            result = await flow.async_step_user()

        # Should skip OAuth and go straight to monitor mode selection
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_monitor_mode"

    async def test_no_existing_entry_starts_oauth(self, hass: HomeAssistant):
        """When no entries exist, proceed with normal OAuth flow."""
        hass.config_entries.async_entries = MagicMock(return_value=[])

        flow = _create_flow(hass)
        # async_step_user with no existing entries should call super()
        # which triggers the OAuth flow — we just verify it doesn't
        # go to monitor mode selection
        result = await flow.async_step_user()

        # Should show the OAuth picker, not monitor mode
        assert result.get("step_id") != "select_monitor_mode"

    async def test_reused_token_clears_entry_specific_fields(
        self, hass: HomeAssistant
    ):
        """Reused token data should not carry over entry-specific fields."""
        existing_entry = MagicMock()
        existing_entry.data = {
            "token": MOCK_TOKEN_DATA,
            "auth_implementation": "test",
            CONF_CHANNEL_ID: MOCK_CHANNEL_ID,
            CONF_MONITOR_MODE: MONITOR_MODE_OWN,
            CONF_TARGET_CHANNEL_ID: "UCold_target",
        }
        hass.config_entries.async_entries = MagicMock(return_value=[existing_entry])

        mock_yt = _build_mock_youtube(SINGLE_CHANNEL_RESPONSE)
        p1, p2 = _patch_google(mock_yt)

        with p1, p2:
            flow = _create_flow(hass)
            await flow.async_step_user()

        # The internal data should not contain old entry-specific fields
        assert CONF_TARGET_CHANNEL_ID not in flow._data
        assert CONF_MONITOR_MODE not in flow._data
