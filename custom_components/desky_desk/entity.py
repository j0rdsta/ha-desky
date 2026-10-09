"""Base entity for Desky Desk integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, Concatenate

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .bluetooth import DeskBLEDevice
from .const import DOMAIN
from .coordinator import DeskUpdateCoordinator
from .errors import DeskCommandError, DeskNotConnectedError


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
    def _device(self) -> DeskBLEDevice:
        """Return the BLE device."""
        return self.coordinator.device


@contextmanager
def translate_desk_errors() -> Iterator[None]:
    """Turn a command that does not reach the desk into a translated error."""
    try:
        yield
    except DeskNotConnectedError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="not_connected"
        ) from err
    except DeskCommandError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"error": str(err)},
        ) from err


def desk_command[EntityT: DeskEntity, **P](
    func: Callable[Concatenate[EntityT, P], Coroutine[Any, Any, None]],
) -> Callable[Concatenate[EntityT, P], Coroutine[Any, Any, None]]:
    """Raise a translated error when a command does not reach the desk.

    Home Assistant skips unavailable entities, but the connection can drop
    before the entity hears about it, and a write can fail on its own.
    """

    @wraps(func)
    async def wrapper(self: EntityT, *args: P.args, **kwargs: P.kwargs) -> None:
        with translate_desk_errors():
            await func(self, *args, **kwargs)

    return wrapper
