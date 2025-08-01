"""Cover platform for Desky Desk."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    COVER_CLOSED_POSITION,
    COVER_OPEN_POSITION,
    DOMAIN,
    MAX_HEIGHT,
    MIN_HEIGHT,
)
from .coordinator import DeskUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky Desk cover based on a config entry."""
    coordinator: DeskUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DeskyCover(coordinator)])


class DeskyCover(CoordinatorEntity[DeskUpdateCoordinator], CoverEntity):
    """Representation of a Desky Desk as a cover."""

    _attr_device_class = CoverDeviceClass.DAMPER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_cover"
        
    @property 
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return self.coordinator.get_device_info()

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover.
        
        0 is closed (desk at minimum height)
        100 is open (desk at maximum height)
        """
        if not self.coordinator.data:
            return None
        
        height = self.coordinator.data.get("height_cm", MIN_HEIGHT)
        
        # Calculate position based on height range
        position = int(
            (height - MIN_HEIGHT) / (MAX_HEIGHT - MIN_HEIGHT) * 100
        )
        
        # Ensure position is within 0-100 range
        return max(0, min(100, position))

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed (desk at minimum height)."""
        position = self.current_cover_position
        if position is None:
            return None
        return position <= COVER_CLOSED_POSITION

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening (desk moving up)."""
        if not self.coordinator.data:
            return False
        
        # Check if desk is moving up
        return (
            self.coordinator.data.get("is_moving", False) and 
            self.coordinator.data.get("movement_direction") == "up"
        )

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing (desk moving down)."""
        if not self.coordinator.data:
            return False
        
        # Check if desk is moving down
        return (
            self.coordinator.data.get("is_moving", False) and 
            self.coordinator.data.get("movement_direction") == "down"
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.data.get("is_connected", False) if self.coordinator.data else False

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover (raise the desk)."""
        if self.coordinator.device:
            await self.coordinator.device.move_up()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover (lower the desk)."""
        if self.coordinator.device:
            await self.coordinator.device.move_down()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover (stop desk movement)."""
        if self.coordinator.device:
            await self.coordinator.device.stop()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs.get(ATTR_POSITION)
        if position is None or not self.coordinator.device:
            return
        
        # Convert position (0-100) to height (MIN_HEIGHT-MAX_HEIGHT)
        target_height = MIN_HEIGHT + (position / 100) * (MAX_HEIGHT - MIN_HEIGHT)
        
        # Use the move_to_height method for precise positioning
        await self.coordinator.device.move_to_height(target_height)
        
        # Request coordinator update to track movement
        await self.coordinator.async_request_refresh()