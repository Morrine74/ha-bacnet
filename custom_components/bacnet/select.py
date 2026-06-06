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

    Multi-state values are 1-based integers in BACnet. When the object exposes
    ``state-text``, those labels are used as options; otherwise a generic
    ``State N`` list is presented.
    """

    def __init__(self, coordinator, device, point) -> None:
        """Build the option list from discovered state-text when available."""
        super().__init__(coordinator, device, point)
        if point.state_text:
            self._labels = list(point.state_text)
        else:
            self._labels = [f"State {i}" for i in range(1, 33)]
        self._attr_options = self._labels

    def _index_to_option(self, index: int) -> str | None:
        """Map a 1-based BACnet index to its option label."""
        pos = index - 1
        if 0 <= pos < len(self._labels):
            return self._labels[pos]
        return None

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
        return self._index_to_option(index)

    async def async_select_option(self, option: str) -> None:
        """Write the selected multi-state value (1-based index)."""
        try:
            index = self._labels.index(option) + 1
        except ValueError:
            return
        await self.coordinator.async_write_point(self._device, self._point, index)

