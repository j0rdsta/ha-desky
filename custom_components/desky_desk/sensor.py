"""Sensor platform for Desky Desk."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import time

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import Posture, height_known
from .coordinator import DeskData, DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity

# State comes from the coordinator, so there are no updates to limit
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class DeskSensorEntityDescription(SensorEntityDescription):
    """A desk sensor and how to read its value from the desk data."""

    value_fn: Callable[[DeskData], StateType]


SENSOR_DESCRIPTIONS = [
    # Always cm; Home Assistant converts it to the unit the user picks. Unknown
    # until the desk reports a height, so the placeholder is not recorded
    DeskSensorEntityDescription(
        key="height_display",
        translation_key="height_display",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        suggested_display_precision=1,
        value_fn=lambda data: (
            round(data.height_cm, 1) if height_known(data.height_cm) else None
        ),
    ),
    DeskSensorEntityDescription(
        key="posture",
        translation_key="posture",
        device_class=SensorDeviceClass.ENUM,
        options=[posture.value for posture in Posture],
        value_fn=lambda data: data.posture,
    ),
]


# How often the time today sensors update while nothing else changes
POSTURE_TIME_INTERVAL = timedelta(minutes=1)

POSTURE_TIME_DESCRIPTIONS = {
    posture: SensorEntityDescription(
        key=f"{posture}_time_today",
        translation_key=f"{posture}_time_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
    )
    for posture in (Posture.STANDING, Posture.SITTING)
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky sensor platform."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        DeskSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.extend(
        PostureTimeSensor(coordinator, posture, description)
        for posture, description in POSTURE_TIME_DESCRIPTIONS.items()
    )
    async_add_entities(entities)


class DeskSensor(DeskEntity, SensorEntity):
    """Representation of a Desky desk sensor."""

    entity_description: DeskSensorEntityDescription

    def __init__(
        self,
        coordinator: DeskUpdateCoordinator,
        description: DeskSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)


class PostureTimeSensor(DeskEntity, RestoreSensor):
    """Minutes spent in one posture today, counted while the desk is connected.

    The total resets at local midnight and is restored after a restart on the
    same day.
    """

    def __init__(
        self,
        coordinator: DeskUpdateCoordinator,
        posture: Posture,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._posture = posture
        self._minutes = 0.0
        self._day: date = dt_util.now().date()
        self._attr_last_reset = dt_util.start_of_local_day(self._day)
        # time.monotonic() up to which the time in the posture is counted, or
        # None while the desk is not in it; nothing earlier than _not_before
        # belongs to this total
        self._counting_since: float | None = None
        self._not_before = time.monotonic()

    @property
    def native_value(self) -> float:
        """Return the minutes counted today."""
        return round(self._minutes, 1)

    async def async_added_to_hass(self) -> None:
        """Restore today's total, then count every minute and reset at midnight."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        last_data = await self.async_get_last_sensor_data()
        if (
            last_state is not None
            and last_data is not None
            and isinstance(last_data.native_value, int | float | Decimal)
            and (last_reset := last_state.attributes.get("last_reset"))
            and (reset_at := dt_util.parse_datetime(str(last_reset)))
            and dt_util.as_local(reset_at).date() == self._day
        ):
            self._minutes = float(last_data.native_value)

        self._not_before = now = time.monotonic()
        self._count(now)
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._async_on_time, hour=0, minute=0, second=0
            )
        )
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_on_time, POSTURE_TIME_INTERVAL
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Count the time up to this update, which may change the posture."""
        self._update()
        super()._handle_coordinator_update()

    @callback
    def _async_on_time(self, _now: datetime) -> None:
        """Count the time so far, and start a new day after midnight."""
        self._update()
        self.async_write_ha_state()

    @callback
    def _update(self) -> None:
        """Count the time so far, resetting the total on a new local day.

        The day is compared on every update, not only at the midnight
        callback, so a day whose midnight is skipped by a clock change resets
        too.
        """
        now = time.monotonic()
        self._count(now)
        if (today := dt_util.now().date()) != self._day:
            self._day = today
            self._attr_last_reset = dt_util.start_of_local_day(today)
            self._minutes = 0.0
            self._not_before = now
            if self._counting_since is not None:
                self._counting_since = now

    @callback
    def _count(self, now: float) -> None:
        """Add the time spent in the posture up to now."""
        data = self.coordinator.data
        in_posture = data.is_connected and data.posture == self._posture
        changed_at = data.posture_changed_at

        if self._counting_since is not None:
            # Time up to a change of posture belongs to the old posture
            end = now
            if not in_posture and changed_at is not None:
                end = min(now, max(self._counting_since, changed_at))
            self._minutes += (end - self._counting_since) / 60
            self._counting_since = now if in_posture else None
        elif in_posture:
            # The new posture counts from when the desk stopped in it
            start = now if changed_at is None else max(self._not_before, changed_at)
            self._counting_since = min(now, start)
