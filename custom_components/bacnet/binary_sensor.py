"""Binary sensor platform for BACnet (read-only binary inputs)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BACnetConfigEntry
from .const import BINARY_INPUT
from .entity import BACnetEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BACnetConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BACnet binary sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    entities = [
        BACnetBinarySensor(coordinator, device, point)
        for device, point in coordinator.iter_points()
        if point.object_type == BINARY_INPUT
    ]
    async_add_entities(entities)


class BACnetBinarySensor(BACnetEntity, BinarySensorEntity):
    """A read-only BACnet binary input."""

    @property
    def is_on(self) -> bool | None:
        """Return True when the present value is active."""
        value = self.native_raw_value
        if value is None:
            return None
        return _as_bool(value)


def _as_bool(value) -> bool:
    """Interpret a BACnet binary present-value as a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).lower() in ("1", "active", "on", "true")
