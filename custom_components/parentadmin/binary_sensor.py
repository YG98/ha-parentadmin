"""Binary sensors for ParentAdmin: nursery day and balance owed."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import AccountData, ParentAdminConfigEntry
from .entity import ParentAdminEntity


def _today(data: AccountData):
    return data.booking.get(dt_util.now().date())


@dataclass(frozen=True, kw_only=True)
class ParentAdminBinaryDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[AccountData], bool | None]
    attr_fn: Callable[[AccountData], dict[str, Any]] | None = None


BINARY_SENSORS: tuple[ParentAdminBinaryDescription, ...] = (
    ParentAdminBinaryDescription(
        key="nursery_today",
        name="Nursery today",
        icon="mdi:teddy-bear",
        is_on_fn=lambda d: (b.status == "booked") if (b := _today(d)) else False,
        attr_fn=lambda d: {
            "hours": b.hours if (b := _today(d)) else None,
            "status": b.status if b else "none",
        },
    ),
    ParentAdminBinaryDescription(
        key="balance_owed",
        name="Balance owed",
        icon="mdi:cash-clock",
        is_on_fn=lambda d: (d.account.balance < 0)
        if d.account and d.account.balance is not None
        else None,
        attr_fn=lambda d: {"balance": d.account.balance if d.account else None},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentAdminConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    rt = entry.runtime_data
    async_add_entities(
        ParentAdminBinarySensor(rt.account, d, rt.diary.data.child_name) for d in BINARY_SENSORS
    )


class ParentAdminBinarySensor(ParentAdminEntity, BinarySensorEntity):
    entity_description: ParentAdminBinaryDescription

    def __init__(self, coordinator, description: ParentAdminBinaryDescription, child: str | None) -> None:
        super().__init__(coordinator, description.key, child)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attr_fn
        return fn(self.coordinator.data) if fn else None
