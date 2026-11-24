"""Data update coordinator for ParentAdmin."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
import time

from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ParentAdminAuthError, ParentAdminClient, ParentAdminConnectionError
from .const import (
    BASE_URL,
    DOMAIN,
    LOGGER,
    PHOTO_CACHE_SIZE,
    PHOTO_LINK_RESIGN,
    PHOTO_LINK_VALID,
    PHOTO_PATH,
    QUIET_END_HOUR,
    QUIET_START_HOUR,
    SCAN_INTERVAL,
)
from .parser import DiaryEntry, parse_diary

type ParentAdminConfigEntry = ConfigEntry[ParentAdminCoordinator]


@dataclass
class DiaryData:
    """Today's diary."""

    day: date
    child_name: str | None
    entries: list[DiaryEntry]
    fetched: datetime
    # nursery photo URL -> signed Home Assistant path that serves it
    photo_links: dict[str, str] = field(default_factory=dict)


class ParentAdminCoordinator(DataUpdateCoordinator[DiaryData]):
    """Polls today's diary page and serves its photos."""

    config_entry: ParentAdminConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ParentAdminConfigEntry, client: ParentAdminClient
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        self._photo_urls: dict[str, str] = {}  # key -> nursery URL
        self._signed: dict[str, tuple[str, float]] = {}  # key -> (signed path, expiry)
        self._photo_cache: OrderedDict[str, tuple[bytes, str]] = OrderedDict()

    async def _async_update_data(self) -> DiaryData:
        now = dt_util.now()
        today = now.date()

        # Overnight: keep what we have, but always fetch once for a new day.
        quiet = now.hour >= QUIET_START_HOUR or now.hour < QUIET_END_HOUR
        if quiet and self.data is not None and self.data.day == today:
            data = self.data
        else:
            try:
                html = await self.client.async_get_diary_html(today)
            except ParentAdminAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except ParentAdminConnectionError as err:
                raise UpdateFailed(str(err)) from err

            child_name, entries = await self.hass.async_add_executor_job(
                parse_diary, html, BASE_URL
            )
            if child_name is None and self.data is not None:
                child_name = self.data.child_name
            data = DiaryData(day=today, child_name=child_name, entries=entries, fetched=now)

        data.photo_links = self._build_photo_links(data)
        return data

    def _build_photo_links(self, data: DiaryData) -> dict[str, str]:
        links: dict[str, str] = {}
        urls: dict[str, str] = {}
        signed: dict[str, tuple[str, float]] = {}
        now = time.time()
        for entry in data.entries:
            for url in entry.photos:
                key = sha256(url.encode()).hexdigest()[:24]
                urls[key] = url
                current = self._signed.get(key)
                if current is None or current[1] - now < PHOTO_LINK_RESIGN.total_seconds():
                    path = PHOTO_PATH.format(entry_id=self.config_entry.entry_id, key=key)
                    current = (
                        async_sign_path(
                            self.hass, path, PHOTO_LINK_VALID, use_content_user=True
                        ),
                        now + PHOTO_LINK_VALID.total_seconds(),
                    )
                signed[key] = current
                links[url] = current[0]
        self._photo_urls = urls
        self._signed = signed
        return links

    async def async_get_photo(self, url: str) -> tuple[bytes, str]:
        """Return (bytes, content type) for a nursery photo URL, cached."""
        if (cached := self._photo_cache.get(url)) is not None:
            self._photo_cache.move_to_end(url)
            return cached
        result = await self.client.async_get_photo(url)
        self._photo_cache[url] = result
        while len(self._photo_cache) > PHOTO_CACHE_SIZE:
            self._photo_cache.popitem(last=False)
        return result

    async def async_get_photo_by_key(self, key: str) -> tuple[bytes, str]:
        """Photo for a key from a signed link. Raises KeyError if unknown."""
        return await self.async_get_photo(self._photo_urls[key])
