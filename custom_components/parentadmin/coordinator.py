"""Data update coordinators for ParentAdmin."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from hashlib import sha256
import time
from typing import Any

from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ParentAdminAuthError, ParentAdminClient, ParentAdminConnectionError, ParentAdminError
from .const import (
    ACCOUNT_PATH,
    ACCOUNT_SCAN_INTERVAL,
    BASE_URL,
    BOOKING_PATH,
    CURRENCY,
    DOMAIN,
    EVENT_NEW_INCIDENT,
    EVENT_NEW_INVOICE,
    EVENT_NEW_MESSAGE,
    FALLBACK_LOOKBACK_DAYS,
    INBOX_PATH,
    INCIDENTS_PATH,
    INVOICE_PATH,
    LOGGER,
    PHOTO_CACHE_SIZE,
    PHOTO_LINK_RESIGN,
    PHOTO_LINK_VALID,
    PHOTO_PATH,
    QUIET_END_HOUR,
    QUIET_START_HOUR,
    SCAN_INTERVAL,
    STORAGE_VERSION,
    UNBOOKED_REFRESH,
)
from .parser import (
    Account,
    BookingDay,
    DiaryEntry,
    FormsPage,
    Inbox,
    Invoice,
    parse_account,
    parse_booking,
    parse_diary,
    parse_forms,
    parse_inbox,
    parse_invoices,
)

type ParentAdminConfigEntry = ConfigEntry[ParentAdminRuntime]


class SeenState:
    """Remembers what we've already notified about, across restarts."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self.data: dict[str, Any] = {}

    async def async_load(self) -> None:
        self.data = await self._store.async_load() or {}

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self._store.async_delay_save(lambda: self.data, 5)


@dataclass
class DiaryData:
    """The diary being shown (today, or the last nursery day) plus inbox/incidents."""

    day: date
    child_name: str | None
    entries: list[DiaryEntry]
    fetched: datetime
    is_today: bool = True
    booked_today: BookingDay | None = None
    incidents: FormsPage | None = None
    inbox: Inbox | None = None
    # nursery photo URL -> signed Home Assistant path that serves it
    photo_links: dict[str, str] = field(default_factory=dict)


@dataclass
class AccountData:
    """Invoices, balance and booking pattern."""

    invoices: list[Invoice]
    account: Account | None
    booking: dict[date, BookingDay]
    fetched: datetime

    @property
    def latest_invoice(self) -> Invoice | None:
        return self.invoices[0] if self.invoices else None


class ParentAdminAccountCoordinator(DataUpdateCoordinator[AccountData]):
    """Polls the slow-changing pages every few hours."""

    config_entry: ParentAdminConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: ParentAdminClient, seen: SeenState
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_account",
            update_interval=ACCOUNT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        self.seen = seen

    async def _async_update_data(self) -> AccountData:
        try:
            invoices_html = await self.client.async_get_page(INVOICE_PATH)
            account_html = await self.client.async_get_page(ACCOUNT_PATH)
            booking_html = await self.client.async_get_page(BOOKING_PATH)
        except ParentAdminAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ParentAdminConnectionError as err:
            raise UpdateFailed(str(err)) from err

        def _parse() -> AccountData:
            return AccountData(
                invoices=parse_invoices(invoices_html),
                account=parse_account(account_html),
                booking=parse_booking(booking_html),
                fetched=dt_util.now(),
            )

        data = await self.hass.async_add_executor_job(_parse)
        self._check_new_invoice(data)
        return data

    def _check_new_invoice(self, data: AccountData) -> None:
        latest = data.latest_invoice
        if latest is None:
            return
        last_seen = self.seen.data.get("invoice")
        if last_seen is not None and last_seen != latest.number:
            self.hass.bus.async_fire(
                EVENT_NEW_INVOICE,
                {
                    "number": latest.number,
                    "period": latest.period,
                    "issue_date": latest.issue_date.isoformat() if latest.issue_date else None,
                    "total": latest.total,
                    "currency": CURRENCY,
                    "balance": data.account.balance if data.account else None,
                },
            )
        if last_seen != latest.number:
            self.seen.set("invoice", latest.number)


class ParentAdminCoordinator(DataUpdateCoordinator[DiaryData]):
    """Polls the diary, incidents and inbox, and serves diary photos."""

    config_entry: ParentAdminConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ParentAdminClient,
        seen: SeenState,
        account: ParentAdminAccountCoordinator,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        self.seen = seen
        self.account = account
        self._fallback: tuple[date, date, list[DiaryEntry]] | None = None  # (computed on, day, entries)
        self._photo_urls: dict[str, str] = {}  # key -> nursery URL
        self._signed: dict[str, tuple[str, float]] = {}  # key -> (signed path, expiry)
        self._photo_cache: OrderedDict[str, tuple[bytes, str]] = OrderedDict()

    def _booking(self, day: date) -> BookingDay | None:
        data = self.account.data
        return data.booking.get(day) if data else None

    async def _async_update_data(self) -> DiaryData:
        now = dt_util.now()
        today = now.date()
        booked = self._booking(today)
        previous = self.data
        fresh_today = previous is not None and previous.fetched.date() == today

        # Overnight, or on a day she isn't booked in: don't hammer the site.
        quiet = now.hour >= QUIET_START_HOUR or now.hour < QUIET_END_HOUR
        not_booked = booked is not None and booked.status != "booked"
        if fresh_today and (
            quiet or (not_booked and now - previous.fetched < UNBOOKED_REFRESH)
        ):
            previous.booked_today = booked
            previous.photo_links = self._build_photo_links(previous)
            return previous

        try:
            html = await self.client.async_get_diary_html(today)
            child_name, entries = await self.hass.async_add_executor_job(
                parse_diary, html, BASE_URL
            )
            day, is_today = today, True
            if not entries:
                day, entries = await self._async_last_nursery_day(today)
                is_today = day == today
            incidents = await self._async_optional(INCIDENTS_PATH, parse_forms)
            inbox = await self._async_optional(INBOX_PATH, parse_inbox)
        except ParentAdminAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ParentAdminConnectionError as err:
            raise UpdateFailed(str(err)) from err

        if child_name is None and previous is not None:
            child_name = previous.child_name
        data = DiaryData(
            day=day,
            child_name=child_name,
            entries=entries,
            fetched=now,
            is_today=is_today,
            booked_today=booked,
            incidents=incidents if incidents is not None else (previous.incidents if previous else None),
            inbox=inbox if inbox is not None else (previous.inbox if previous else None),
        )
        data.photo_links = self._build_photo_links(data)
        self._check_new_incident(data.incidents)
        self._check_new_messages(data.inbox)
        return data

    async def _async_optional(self, path: str, parser) -> Any:
        """Fetch a secondary page; a failure there must not break the diary."""
        try:
            html = await self.client.async_get_page(path)
            return await self.hass.async_add_executor_job(parser, html)
        except ParentAdminAuthError:
            raise
        except (ParentAdminError, Exception) as err:  # noqa: BLE001
            LOGGER.warning("Could not read %s: %s", path, err)
            return None

    async def _async_last_nursery_day(self, today: date) -> tuple[date, list[DiaryEntry]]:
        """Most recent day with diary entries, looked up once per day."""
        if self._fallback is not None and self._fallback[0] == today:
            return self._fallback[1], self._fallback[2]
        result: tuple[date, list[DiaryEntry]] = (today, [])
        for back in range(1, FALLBACK_LOOKBACK_DAYS + 1):
            day = today - timedelta(days=back)
            booking = self._booking(day)
            if booking is not None and booking.status != "booked":
                continue
            html = await self.client.async_get_diary_html(day)
            _, entries = await self.hass.async_add_executor_job(parse_diary, html, BASE_URL)
            if entries:
                result = (day, entries)
                break
        self._fallback = (today, result[0], result[1])
        return result

    def _check_new_incident(self, forms: FormsPage | None) -> None:
        if forms is None:
            return
        last = self.seen.data.get("incidents")
        if last is not None and last != forms.signature and forms.count != 0:
            self.hass.bus.async_fire(EVENT_NEW_INCIDENT, {"count": forms.count})
        if last != forms.signature:
            self.seen.set("incidents", forms.signature)

    def _check_new_messages(self, inbox: Inbox | None) -> None:
        if inbox is None:
            return
        known = self.seen.data.get("messages")
        current = [m.key for m in inbox.unread]
        if known is not None:
            for message in inbox.unread:
                if message.key not in known:
                    self.hass.bus.async_fire(
                        EVENT_NEW_MESSAGE,
                        {
                            "sender": message.sender,
                            "subject": message.subject,
                            "preview": message.preview,
                            "received": message.received,
                        },
                    )
        if known is None or set(known) != set(current):
            # keep a bounded history so a re-shown message doesn't notify twice
            merged = list(dict.fromkeys(current + (known or [])))[:100]
            self.seen.set("messages", merged)

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
                        async_sign_path(self.hass, path, PHOTO_LINK_VALID, use_content_user=True),
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


@dataclass
class ParentAdminRuntime:
    """Everything a config entry holds at runtime."""

    diary: ParentAdminCoordinator
    account: ParentAdminAccountCoordinator
