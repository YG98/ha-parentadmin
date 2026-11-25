"""Sensors for the ParentAdmin diary, inbox, incidents, invoices and account."""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import PERCENTAGE, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import CURRENCY
from .coordinator import AccountData, DiaryData, ParentAdminConfigEntry
from .entity import ParentAdminEntity
from .parser import DiaryEntry


def _at(data: DiaryData, value: time | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(data.day, value, tzinfo=dt_util.get_default_time_zone())


def _hhmm(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value else None


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _last(data: DiaryData, kind: str) -> DiaryEntry | None:
    return next((e for e in reversed(data.entries) if e.kind == kind), None)


def _first(data: DiaryData, kind: str) -> DiaryEntry | None:
    return next((e for e in data.entries if e.kind == kind), None)


def _of(data: DiaryData, kind: str) -> list[DiaryEntry]:
    return [e for e in data.entries if e.kind == kind]


def _timeline(data: DiaryData) -> dict[str, Any]:
    booked = data.booked_today
    return {
        "date": data.day.isoformat(),
        "is_today": data.is_today,
        "booked_today": None if booked is None else booked.status == "booked",
        "booked_hours": booked.hours if booked else None,
        "booking_status": booked.status if booked else None,
        "child": data.child_name,
        "entries": [
            {
                "time": _hhmm(e.start),
                "end": _hhmm(e.end),
                "type": e.kind,
                "title": e.title,
                "value": e.figure,
                "detail": e.detail,
                "photos": [data.photo_links[u] for u in e.photos if u in data.photo_links],
            }
            for e in data.entries
        ],
    }


def _latest_entry(data: DiaryData) -> str | None:
    if not data.entries:
        return None
    e = data.entries[-1]
    return f"{e.title}: {e.detail or e.figure}".strip(": ")[:255]


def _latest_attrs(data: DiaryData) -> dict[str, Any]:
    if not data.entries:
        return {"type": None, "time": None, "datetime": None, "date": data.day.isoformat()}
    e = data.entries[-1]
    return {
        "type": e.kind,
        "time": _hhmm(e.start),
        "datetime": _iso(_at(data, e.start)),
        "date": data.day.isoformat(),
        "is_today": data.is_today,
    }


def _last_meal_attrs(data: DiaryData) -> dict[str, Any]:
    e = _last(data, "food")
    return {"meal": e.title, "description": e.detail, "time": _hhmm(e.start)} if e else {}


def _nappy_attrs(data: DiaryData) -> dict[str, Any]:
    e = _last(data, "nappy")
    counts = Counter(n.figure.lower() for n in _of(data, "nappy"))
    return {"type": e.figure if e else None, **{f"{k}_today": v for k, v in counts.items()}}


def _inbox_attrs(data: DiaryData) -> dict[str, Any]:
    if data.inbox is None:
        return {}
    return {
        "messages": [
            {"sender": m.sender, "subject": m.subject, "preview": m.preview, "received": m.received}
            for m in data.inbox.unread[:5]
        ],
        "read_messages": data.inbox.read_count,
    }


def _balance_attrs(data: AccountData) -> dict[str, Any]:
    acct = data.account
    if acct is None:
        return {}
    bal = acct.balance
    pay = acct.last_payment
    return {
        "status": None if bal is None else "In debit" if bal < 0 else "In credit" if bal > 0 else "Settled",
        "last_payment_amount": pay.amount if pay else None,
        "last_payment_date": _iso(pay.date) if pay else None,
        "last_payment_description": pay.description if pay else None,
        "recent_transactions": [
            {"date": _iso(t.date), "description": t.description, "reference": t.reference, "amount": t.amount}
            for t in acct.transactions[:6]
        ],
    }


def _invoice_attrs(data: AccountData) -> dict[str, Any]:
    inv = data.latest_invoice
    if inv is None:
        return {}
    return {"period": inv.period, "number": inv.number, "issue_date": _iso(inv.issue_date)}


def _booking_today(data: AccountData):
    return data.booking.get(dt_util.now().date())


def _booking_value(data: AccountData) -> str:
    b = _booking_today(data)
    if b is None or b.status == "none":
        return "Not booked"
    if b.status == "booked":
        return b.hours or "Booked"
    return b.status.capitalize()


def _booking_attrs(data: AccountData) -> dict[str, Any]:
    today = dt_util.now().date()
    week = [data.booking.get(today + timedelta(days=i)) for i in range(7)]
    return {
        "status": (_booking_today(data).status if _booking_today(data) else "none"),
        "next_7_days": [
            {"date": b.date.isoformat(), "hours": b.hours, "status": b.status} for b in week if b
        ],
    }


@dataclass(frozen=True, kw_only=True)
class ParentAdminSensorDescription(SensorEntityDescription):
    """Sensor description with value and attribute callbacks."""

    source: str = "diary"  # which coordinator: "diary" or "account"
    value_fn: Callable[[Any], StateType | datetime]
    attr_fn: Callable[[Any], dict[str, Any]] | None = None


SENSORS: tuple[ParentAdminSensorDescription, ...] = (
    ParentAdminSensorDescription(
        key="timeline",
        name="Timeline",
        icon="mdi:notebook-outline",
        value_fn=lambda d: len(d.entries),
        attr_fn=_timeline,
    ),
    ParentAdminSensorDescription(
        key="latest_entry",
        name="Latest entry",
        icon="mdi:message-text-clock-outline",
        value_fn=_latest_entry,
        attr_fn=_latest_attrs,
    ),
    ParentAdminSensorDescription(
        key="checked_in",
        name="Checked in",
        icon="mdi:login",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _at(d, e.start) if (e := _first(d, "check-in")) else None,
    ),
    ParentAdminSensorDescription(
        key="last_nappy",
        name="Last nappy",
        icon="mdi:baby-face-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _at(d, e.start) if (e := _last(d, "nappy")) else None,
        attr_fn=_nappy_attrs,
    ),
    ParentAdminSensorDescription(
        key="nappy_changes",
        name="Nappy changes",
        icon="mdi:counter",
        value_fn=lambda d: len(_of(d, "nappy")),
    ),
    ParentAdminSensorDescription(
        key="sleep_total",
        name="Sleep today",
        icon="mdi:sleep",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: sum(e.minutes or 0 for e in _of(d, "sleep")),
    ),
    ParentAdminSensorDescription(
        key="water_total",
        name="Water today",
        icon="mdi:cup-water",
        device_class=SensorDeviceClass.VOLUME,
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        value_fn=lambda d: sum(e.millilitres or 0 for e in _of(d, "drink")),
    ),
    ParentAdminSensorDescription(
        key="last_meal",
        name="Last meal eaten",
        icon="mdi:food-apple",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: e.percent if (e := _last(d, "food")) else None,
        attr_fn=_last_meal_attrs,
    ),
    ParentAdminSensorDescription(
        key="unread_messages",
        name="Unread messages",
        icon="mdi:email-outline",
        value_fn=lambda d: len(d.inbox.unread) if d.inbox else None,
        attr_fn=_inbox_attrs,
    ),
    ParentAdminSensorDescription(
        key="incident_forms",
        name="Accident and incident forms",
        icon="mdi:bandage",
        value_fn=lambda d: d.incidents.count if d.incidents else None,
    ),
    ParentAdminSensorDescription(
        key="account_balance",
        name="Account balance",
        icon="mdi:cash",
        source="account",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        suggested_display_precision=2,
        value_fn=lambda d: d.account.balance if d.account else None,
        attr_fn=_balance_attrs,
    ),
    ParentAdminSensorDescription(
        key="latest_invoice",
        name="Latest invoice",
        icon="mdi:file-document-outline",
        source="account",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        suggested_display_precision=2,
        value_fn=lambda d: d.latest_invoice.total if d.latest_invoice else None,
        attr_fn=_invoice_attrs,
    ),
    ParentAdminSensorDescription(
        key="booked_hours_today",
        name="Booked hours today",
        icon="mdi:calendar-clock",
        source="account",
        value_fn=_booking_value,
        attr_fn=_booking_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentAdminConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    rt = entry.runtime_data
    child = rt.diary.data.child_name
    async_add_entities(
        ParentAdminSensor(rt.account if d.source == "account" else rt.diary, d, child)
        for d in SENSORS
    )


class ParentAdminSensor(ParentAdminEntity, SensorEntity):
    """A ParentAdmin sensor."""

    entity_description: ParentAdminSensorDescription
    # Large attributes stay out of the recorder database. (HA reads this at class level.)
    _unrecorded_attributes = frozenset({"entries", "recent_transactions"})

    def __init__(self, coordinator, description: ParentAdminSensorDescription, child: str | None) -> None:
        super().__init__(coordinator, description.key, child)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator.data)
