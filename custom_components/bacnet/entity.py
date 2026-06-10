"""Base entity helpers for the BACnet integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import BACnetCoordinator, point_key
from .models import DeviceConfig, PointConfig
from .siemens import PathSplit, build_split, slugify_equipment


def point_grouping(
    device_id: int, point: PointConfig
) -> tuple[PathSplit, str | None]:
    """Compute the (path split, equipment sub-device key) for a point.

    Both the entity (for ``device_info``) and the setup code (for registering the
    equipment sub-devices) must agree on the same key, so the logic lives here.
    Returns an empty split and ``None`` key when the point has no Siemens path
    (the point then stays attached to its controller device).
    """
    split = build_split(point.tree_path, point.equipment_index)
    return split, slugify_equipment(device_id, split)


class BACnetEntity(CoordinatorEntity[BACnetCoordinator]):
    """Common base for entities backed by a single BACnet point."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BACnetCoordinator,
        device: DeviceConfig,
        point: PointConfig,
    ) -> None:
        """Initialise the entity from its device and point configuration."""
        super().__init__(coordinator)
        self._device = device
        self._point = point
        self._key = point_key(device.address, point.object_id)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{device.device_id}_{point.object_id}"
        )
        self._split, self._equipment_slug = point_grouping(
            device.device_id, point
        )
        # With a Siemens tree path, the equipment is the HA sub-device name, so
        # the entity keeps only the leaf (plus any breadcrumb) as its own name.
        self._attr_name = self._split.name or point.name or point.object_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for the entity's parent device.

        For a Siemens point with an equipment level, the parent is the equipment
        sub-device (grouping points like "Ballon d'eau chaude"), itself nested
        under the controller. Otherwise the parent is the controller directly.
        """
        entry_id = self.coordinator.entry.entry_id
        controller_id = (DOMAIN, f"{entry_id}_{self._device.device_id}")
        if self._equipment_slug:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_{self._equipment_slug}")},
                name=self._split.equipment,
                manufacturer=MANUFACTURER,
                model="Équipement",
                suggested_area=self._split.area,
                via_device=controller_id,
            )
        return DeviceInfo(
            identifiers={controller_id},
            name=self._device.name,
            manufacturer=MANUFACTURER,
            model=f"Device {self._device.device_id}",
            suggested_area=self._split.area,
            via_device=(DOMAIN, entry_id),
        )

    @property
    def native_raw_value(self) -> Any:
        """Return the raw present-value stored by the coordinator."""
        return (self.coordinator.data or {}).get(self._key)

    @property
    def available(self) -> bool:
        """Return whether the point currently has a known value."""
        return super().available and self.native_raw_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose BACnet metadata as entity attributes."""
        attrs: dict[str, Any] = {
            "device_id": self._device.device_id,
            "device_address": self._device.address,
            "object_id": self._point.object_id,
            "object_type": self._point.object_type,
            "cov": self._point.use_cov,
        }
        if self._point.description:
            attrs["description"] = self._point.description
        if self._point.tree_path:
            attrs["bacnet_path"] = self._point.tree_path
        if self._split.equipment:
            attrs["equipment"] = self._split.equipment
        if self._point.units:
            attrs["bacnet_units"] = self._point.units
        if self._point.state_text:
            attrs["state_text"] = self._point.state_text
        if self._point.active_text:
            attrs["active_text"] = self._point.active_text
        if self._point.inactive_text:
            attrs["inactive_text"] = self._point.inactive_text
        return attrs
