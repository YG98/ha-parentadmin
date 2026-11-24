"""Config flow for ParentAdmin."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import ParentAdminAuthError, ParentAdminClient, ParentAdminConnectionError
from .const import DOMAIN, LOGGER

USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


async def _try_login(hass: HomeAssistant, email: str, password: str) -> str | None:
    """Return an error key, or None if the login worked."""
    session = async_create_clientsession(
        hass, auto_cleanup=False, cookie_jar=aiohttp.CookieJar()
    )
    try:
        await ParentAdminClient(session, email, password).async_login()
    except ParentAdminAuthError:
        return "invalid_auth"
    except ParentAdminConnectionError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        LOGGER.exception("Unexpected error during ParentAdmin login")
        return "unknown"
    finally:
        await session.close()
    return None


class ParentAdminConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ParentAdmin."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()
            error = await _try_login(self.hass, email, user_input[CONF_PASSWORD])
            if error is None:
                return self.async_create_entry(
                    title=email,
                    data={CONF_EMAIL: email, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
            errors["base"] = error
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            error = await _try_login(
                self.hass, entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
