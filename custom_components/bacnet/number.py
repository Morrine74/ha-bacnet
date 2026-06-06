"""Number platform for BACnet (writable analog outputs/values)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BACnetConfigEntry
from .const import ANALOG_OUTPUT, ANALOG_VALUE
from .entity import BACnetEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BACnetConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BACnet number entities from a config entry."""
    coordinator = entry.runtime_data.coordinator
    entities = [
        BACnetNumber(coordinator, device, point)
        for device, point in coordinator.iter_points()
        if point.object_type in (ANALOG_OUTPUT, ANALOG_VALUE)
    ]
    async_add_entities(entities)


class BACnetNumber(BACnetEntity, NumberEntity):
    """A writable BACnet analog output or value."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -1000000.0
    _attr_native_max_value = 1000000.0
    _attr_native_step = 0.1

    @property
    def native_value(self) -> float | None:
        """Return the present value as a float."""
        value = self.native_raw_value
        if value is None:
            return None
        try:
            return round(float(value), 3)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Write a new value to the BACnet object."""
        await self.coordinator.async_write_point(self._device, self._point, value)
