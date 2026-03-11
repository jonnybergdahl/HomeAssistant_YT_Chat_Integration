"""Application credentials for YouTube Chat integration."""

from homeassistant.components.application_credentials import AuthorizationServer
from homeassistant.core import HomeAssistant


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return the authorization server."""
    return AuthorizationServer(
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
    )
