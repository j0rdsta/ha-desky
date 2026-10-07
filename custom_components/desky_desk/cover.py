"""Cover platform for Desky Desk."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COVER_CLOSED_POSITION, MAX_HEIGHT, MIN_HEIGHT
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity

_LOGGER = logging.getLogger(__name__)

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky Desk cover based on a config entry."""
    async_add_entities([DeskyCover(entry.runtime_data)])


class DeskyCover(DeskEntity, CoverEntity):
    """Representation of a Desky Desk as a cover."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )
    # The desk is the device's main feature, so the cover takes the device name
    _attr_name = None
    _attr_translation_key = "desk"

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the cover."""
        super().__init__(coordinator, "cover")

    @property
    def current_cover_position(self) -> int:
        """Return current position of cover.

        0 is closed (desk at minimum height)
        100 is open (desk at maximum height)
        """
        height = self.coordinator.data.height_cm

        # Calculate position based on height range
        position = int((height - MIN_HEIGHT) / (MAX_HEIGHT - MIN_HEIGHT) * 100)

        # Ensure position is within 0-100 range
        return max(0, min(100, position))

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed (desk at minimum height)."""
        return self.current_cover_position <= COVER_CLOSED_POSITION

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening (desk moving up)."""
        data = self.coordinator.data
        return data.is_moving and data.movement_direction == "up"

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing (desk moving down)."""
        data = self.coordinator.data
        return data.is_moving and data.movement_direction == "down"

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover (raise the desk)."""
        if self._device:
            await self._device.move_up()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover (lower the desk)."""
        if self._device:
            await self._device.move_down()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover (stop desk movement)."""
        if self._device:
            await self._device.stop()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        if not self._device:
            return

        # Convert position (0-100) to height (MIN_HEIGHT-MAX_HEIGHT)
        position = kwargs[ATTR_POSITION]
        target_height = MIN_HEIGHT + (position / 100) * (MAX_HEIGHT - MIN_HEIGHT)

        # Use the move_to_height method for precise positioning
        await self._device.move_to_height(target_height)

        # Request coordinator update to track movement
        await self.coordinator.async_request_refresh()
