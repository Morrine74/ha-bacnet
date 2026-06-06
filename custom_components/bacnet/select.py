"""Select platform for BACnet (writable multi-state outputs/values)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BACnetConfigEntry
from .const import MULTI_STATE_OUTPUT, MULTI_STATE_VALUE
from .entity import BACnetEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BACnetConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BACnet select entities from a config entry."""
    coordinator = entry.runtime_data.coordinator
    entities = [
        BACnetSelect(coordinator, device, point)
        for device, point in coordinator.iter_points()
        if point.object_type in (MULTI_STATE_OUTPUT, MULTI_STATE_VALUE)
    ]
    async_add_entities(entities)


class BACnetSelect(BACnetEntity, SelectEntity):
    """A writable BACnet multi-state output or value.

    Multi-state values are 1-based integers in BACnet. Until state-text is
    discovered, options are presented as ``State N`` labels.
    """

    _attr_options: list[str] = [f"State {i}" for i in range(1, 33)]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected state label."""
        value = self.native_raw_value
        if value is None:
            return None
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        return f"State {index}"

    async def async_select_option(self, option: str) -> None:
        """Write the selected multi-state value."""
        try:
            index = int(option.split(" ", 1)[1])
        except (IndexError, ValueError):
            return
        await self.coordinator.async_write_point(self._device, self._point, index)
