"""Sensor platform for BACnet (read-only analog/multi-state inputs)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BACnetConfigEntry
from .const import ANALOG_TYPES, MULTI_STATE_TYPES, WRITABLE_TYPES
from .entity import BACnetEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BACnetConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BACnet sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    entities: list[BACnetSensor] = []
    for device, point in coordinator.iter_points():
        is_analog = point.object_type in ANALOG_TYPES
        is_multistate = point.object_type in MULTI_STATE_TYPES
        # Read-only numeric points become sensors. Writable ones are handled by
        # number/switch/select platforms instead.
        if (is_analog or is_multistate) and point.object_type not in WRITABLE_TYPES:
            entities.append(BACnetSensor(coordinator, device, point))
    async_add_entities(entities)


class BACnetSensor(BACnetEntity, SensorEntity):
    """A read-only BACnet analog or multi-state input."""

    @property
    def native_value(self):
        """Return the present value."""
        value = self.native_raw_value
        if value is None:
            return None
        if self._point.object_type in ANALOG_TYPES:
            try:
                return round(float(value), 3)
            except (TypeError, ValueError):
                return value
        return value

    @property
    def state_class(self) -> SensorStateClass | None:
        """Analog inputs are continuous measurements."""
        if self._point.object_type in ANALOG_TYPES:
            return SensorStateClass.MEASUREMENT
        return None
