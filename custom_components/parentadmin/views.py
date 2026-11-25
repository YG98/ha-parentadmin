"""HTTP endpoint that serves diary photos to the Home Assistant frontend."""
from __future__ import annotations

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.http import KEY_HASS

from .api import ParentAdminError
from .const import DOMAIN, LOGGER


class ParentAdminPhotoView(HomeAssistantView):
    """Serve a diary photo. Needs HA auth or a signed URL (authSig)."""

    url = "/api/parentadmin/{entry_id}/photo/{key}"
    name = "api:parentadmin:photo"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, key: str) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise web.HTTPNotFound
        try:
            body, content_type = await entry.runtime_data.diary.async_get_photo_by_key(key)
        except KeyError:
            raise web.HTTPNotFound from None
        except ParentAdminError as err:
            LOGGER.warning("Could not fetch diary photo: %s", err)
            raise web.HTTPBadGateway from err
        return web.Response(
            body=body,
            content_type=content_type,
            headers={"Cache-Control": "private, max-age=86400"},
        )
