"""Latest diary photo, served through Home Assistant's authenticated image proxy."""
from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import ParentAdminError
from .const import LOGGER
from .coordinator import ParentAdminConfigEntry, ParentAdminCoordinator
from .entity import ParentAdminEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentAdminConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the image entity."""
    async_add_entities([ParentAdminLatestPhoto(entry.runtime_data)])


class ParentAdminLatestPhoto(ParentAdminEntity, ImageEntity):
    """Most recent photo from today's diary."""

    _attr_name = "Latest photo"
    _attr_content_type = "image/jpeg"

    def __init__(self, coordinator: ParentAdminCoordinator) -> None:
        ParentAdminEntity.__init__(self, coordinator, "latest_photo")
        ImageEntity.__init__(self, coordinator.hass)
        self._url: str | None = None
        self._cached: bytes | None = None
        self._caption: str | None = None
        self._time: str | None = None
        self._count = 0
        self._refresh_from_data()

    def _refresh_from_data(self) -> None:
        photo_entries = [e for e in self.coordinator.data.entries if e.photos]
        self._count = sum(len(e.photos) for e in photo_entries)
        if not photo_entries:
            # Keep showing the last photo we had (e.g. yesterday's) rather than going blank.
            return
        last = photo_entries[-1]
        url = last.photos[-1]
        self._caption = last.detail or None
        self._time = last.start.strftime("%H:%M") if last.start else None
        if url != self._url:
            self._url = url
            self._cached = None
            self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_from_data()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return super().available and self._url is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"caption": self._caption, "time": self._time, "photos_today": self._count}

    async def async_image(self) -> bytes | None:
        if self._url is None:
            return None
        if self._cached is None:
            try:
                body, content_type = await self.coordinator.async_get_photo(self._url)
            except ParentAdminError as err:
                LOGGER.warning("Could not download diary photo: %s", err)
                return None
            self._cached = body
            self._attr_content_type = content_type
        return self._cached
