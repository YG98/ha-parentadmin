"""The ParentAdmin nursery diary integration."""
from __future__ import annotations

from pathlib import Path

import aiohttp

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import ParentAdminClient
from .const import CARD_FILE, CARD_URL, DOMAIN, VERSION
from .coordinator import (
    ParentAdminAccountCoordinator,
    ParentAdminConfigEntry,
    ParentAdminCoordinator,
    ParentAdminRuntime,
    SeenState,
)
from .views import ParentAdminPhotoView

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.IMAGE, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the photo endpoint and the timeline card (once per HA start)."""
    hass.http.register_view(ParentAdminPhotoView())
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "frontend" / CARD_FILE), False)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ParentAdminConfigEntry) -> bool:
    """Set up ParentAdmin from a config entry."""
    # Own session with its own cookie jar, so the PHPSESSID stays with us.
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    entry.async_on_unload(session.close)

    client = ParentAdminClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    seen = SeenState(hass, entry.entry_id)
    await seen.async_load()

    # Account first: the diary uses the booking pattern to know nursery days.
    account = ParentAdminAccountCoordinator(hass, entry, client, seen)
    await account.async_config_entry_first_refresh()
    diary = ParentAdminCoordinator(hass, entry, client, seen, account)
    await diary.async_config_entry_first_refresh()

    entry.runtime_data = ParentAdminRuntime(diary=diary, account=account)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParentAdminConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
