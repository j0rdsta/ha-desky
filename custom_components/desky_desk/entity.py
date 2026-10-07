"""Base entity for Desky Desk integration."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .bluetooth import DeskBLEDevice
from .coordinator import DeskUpdateCoordinator


class DeskEntity(CoordinatorEntity[DeskUpdateCoordinator]):
    """Base entity for all Desky desk entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DeskUpdateCoordinator, key: str) -> None:
        """Initialize the entity.

        The unique ID is `<config entry unique ID>_<key>` and must never change.
        """
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{key}"
        self._attr_device_info = coordinator.get_device_info()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data.is_connected

    @property
    def _device(self) -> DeskBLEDevice | None:
        """Return the BLE device."""
        return self.coordinator.device
