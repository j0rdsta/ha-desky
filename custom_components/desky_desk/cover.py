"""Cover platform for Desky Desk."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COVER_CLOSED_POSITION, MAX_HEIGHT, MIN_HEIGHT
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity, desk_command
from .validation import allowed_move_range

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
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

    @desk_command
    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover (raise the desk)."""
        await self._device.move_up()

    @desk_command
    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover (lower the desk)."""
        await self._device.move_down()

    @desk_command
    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover (stop desk movement)."""
        await self._device.stop()

    @desk_command
    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        # Convert position (0-100) to height (MIN_HEIGHT-MAX_HEIGHT), to 0.1 cm
        position = kwargs[ATTR_POSITION]
        target_height = round(
            MIN_HEIGHT + (position / 100) * (MAX_HEIGHT - MIN_HEIGHT), 1
        )
        # A position outside the desk's limits moves to the nearest limit
        low, high = allowed_move_range(self.coordinator.data)
        target_height = min(max(target_height, low), high)

        await self._device.move_to_height(target_height)

        # Request coordinator update to track movement
        await self.coordinator.async_request_refresh()
