"""Base entity for ParentAdmin."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BASE_URL, DIARY_PATH, DOMAIN
from .coordinator import ParentAdminCoordinator


class ParentAdminEntity(CoordinatorEntity[ParentAdminCoordinator]):
    """Common device info and unique IDs."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ParentAdminCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        full_name = coordinator.data.child_name or "Child"
        first_name = full_name.split()[0]
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=f"{first_name} nursery",
            manufacturer="Nursery In a Box",
            model=f"ParentAdmin diary ({full_name})",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=BASE_URL + DIARY_PATH,
        )
