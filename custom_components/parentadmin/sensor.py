"""Sensors for the ParentAdmin diary."""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
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

from .coordinator import DiaryData, ParentAdminConfigEntry, ParentAdminCoordinator
from .entity import ParentAdminEntity
from .parser import DiaryEntry


def _at(data: DiaryData, value: time | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(data.day, value, tzinfo=dt_util.get_default_time_zone())


def _hhmm(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value else None


def _last(data: DiaryData, kind: str) -> DiaryEntry | None:
    return next((e for e in reversed(data.entries) if e.kind == kind), None)


def _first(data: DiaryData, kind: str) -> DiaryEntry | None:
    return next((e for e in data.entries if e.kind == kind), None)


def _of(data: DiaryData, kind: str) -> list[DiaryEntry]:
    return [e for e in data.entries if e.kind == kind]


def _timeline(data: DiaryData) -> dict[str, Any]:
    return {
        "date": data.day.isoformat(),
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


def _last_meal_attrs(data: DiaryData) -> dict[str, Any]:
    e = _last(data, "food")
    return {"meal": e.title, "description": e.detail, "time": _hhmm(e.start)} if e else {}


def _nappy_attrs(data: DiaryData) -> dict[str, Any]:
    e = _last(data, "nappy")
    counts = Counter(n.figure.lower() for n in _of(data, "nappy"))
    return {"type": e.figure if e else None, **{f"{k}_today": v for k, v in counts.items()}}


@dataclass(frozen=True, kw_only=True)
class ParentAdminSensorDescription(SensorEntityDescription):
    """Sensor description with value and attribute callbacks."""

    value_fn: Callable[[DiaryData], StateType | datetime]
    attr_fn: Callable[[DiaryData], dict[str, Any]] | None = None


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
        attr_fn=lambda d: {
            "type": d.entries[-1].kind if d.entries else None,
            "time": _hhmm(d.entries[-1].start) if d.entries else None,
        },
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
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentAdminConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(ParentAdminSensor(coordinator, desc) for desc in SENSORS)


class ParentAdminSensor(ParentAdminEntity, SensorEntity):
    """A diary sensor."""

    entity_description: ParentAdminSensorDescription
    # The full timeline can be large; keep it out of the recorder database.
    _unrecorded_attributes = frozenset({"entries"})

    def __init__(
        self, coordinator: ParentAdminCoordinator, description: ParentAdminSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator.data)
