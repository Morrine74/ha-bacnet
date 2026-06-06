"""Switch platform for BACnet (writable binary outputs/values)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BACnetConfigEntry
from .const import BINARY_OUTPUT, BINARY_VALUE
from .entity import BACnetEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BACnetConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BACnet switches from a config entry."""
    coordinator = entry.runtime_data.coordinator
    entities = [
        BACnetSwitch(coordinator, device, point)
        for device, point in coordinator.iter_points()
        if point.object_type in (BINARY_OUTPUT, BINARY_VALUE)
    ]
    async_add_entities(entities)


class BACnetSwitch(BACnetEntity, SwitchEntity):
    """A writable BACnet binary output or value."""

    @property
    def is_on(self) -> bool | None:
        """Return True when the present value is active."""
        value = self.native_raw_value
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).lower() in ("1", "active", "on", "true")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the binary point to active."""
        await self.coordinator.async_write_point(self._device, self._point, "active")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set the binary point to inactive."""
        await self.coordinator.async_write_point(
            self._device, self._point, "inactive"
        )
