"""Data models shared across the BACnet integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import (
    CONF_ACTIVE_TEXT,
    CONF_COV_LIFETIME,
    CONF_DESCRIPTION,
    CONF_DEVICE_ADDRESS,
    CONF_EQUIPMENT_INDEX,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_INACTIVE_TEXT,
    CONF_OBJECT_INSTANCE,
    CONF_OBJECT_NAME,
    CONF_OBJECT_TYPE,
    CONF_OBJECTS,
    CONF_STATE_TEXT,
    CONF_TREE_PATH,
    CONF_UNITS,
    CONF_USE_COV,
    CONF_WRITE_PRIORITY,
    DEFAULT_COV_LIFETIME,
    DEFAULT_WRITE_PRIORITY,
    WRITABLE_TYPES,
)


@dataclass(slots=True)
class PointConfig:
    """Configuration for a single monitored BACnet object (point)."""

    object_type: str
    instance: int
    name: str
    use_cov: bool = False
    cov_lifetime: int = DEFAULT_COV_LIFETIME
    write_priority: int = DEFAULT_WRITE_PRIORITY
    units: str | None = None
    description: str | None = None
    state_text: list[str] | None = None
    active_text: str | None = None
    inactive_text: str | None = None
    tree_path: list[str] | None = None
    equipment_index: int | None = None

    @property
    def object_id(self) -> str:
        """Return the ``type,instance`` identifier."""
        return f"{self.object_type},{self.instance}"

    @property
    def writable(self) -> bool:
        """Return whether this object type accepts writes."""
        return self.object_type in WRITABLE_TYPES

    def to_dict(self) -> dict[str, Any]:
        """Serialise for storage in the config entry options."""
        return {
            CONF_OBJECT_TYPE: self.object_type,
            CONF_OBJECT_INSTANCE: self.instance,
            CONF_OBJECT_NAME: self.name,
            CONF_USE_COV: self.use_cov,
            CONF_COV_LIFETIME: self.cov_lifetime,
            CONF_WRITE_PRIORITY: self.write_priority,
            CONF_UNITS: self.units,
            CONF_DESCRIPTION: self.description,
            CONF_STATE_TEXT: self.state_text,
            CONF_ACTIVE_TEXT: self.active_text,
            CONF_INACTIVE_TEXT: self.inactive_text,
            CONF_TREE_PATH: self.tree_path,
            CONF_EQUIPMENT_INDEX: self.equipment_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PointConfig":
        """Deserialise from config entry options."""
        return cls(
            object_type=data[CONF_OBJECT_TYPE],
            instance=int(data[CONF_OBJECT_INSTANCE]),
            name=data.get(CONF_OBJECT_NAME, ""),
            use_cov=bool(data.get(CONF_USE_COV, False)),
            cov_lifetime=int(data.get(CONF_COV_LIFETIME, DEFAULT_COV_LIFETIME)),
            write_priority=int(
                data.get(CONF_WRITE_PRIORITY, DEFAULT_WRITE_PRIORITY)
            ),
            units=data.get(CONF_UNITS),
            description=data.get(CONF_DESCRIPTION),
            state_text=data.get(CONF_STATE_TEXT),
            active_text=data.get(CONF_ACTIVE_TEXT),
            inactive_text=data.get(CONF_INACTIVE_TEXT),
            tree_path=data.get(CONF_TREE_PATH),
            equipment_index=data.get(CONF_EQUIPMENT_INDEX),
        )


@dataclass(slots=True)
class DeviceConfig:
    """Configuration for a remote BACnet device and its monitored points."""

    device_id: int
    address: str
    name: str
    points: list[PointConfig] = field(default_factory=list)

    @property
    def unique_id(self) -> str:
        """Return a stable identifier for this device."""
        return str(self.device_id)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for storage in the config entry options."""
        return {
            CONF_DEVICE_ID: self.device_id,
            CONF_DEVICE_ADDRESS: self.address,
            CONF_DEVICE_NAME: self.name,
            CONF_OBJECTS: [point.to_dict() for point in self.points],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceConfig":
        """Deserialise from config entry options."""
        return cls(
            device_id=int(data[CONF_DEVICE_ID]),
            address=data[CONF_DEVICE_ADDRESS],
            name=data.get(CONF_DEVICE_NAME, f"Device {data[CONF_DEVICE_ID]}"),
            points=[
                PointConfig.from_dict(item)
                for item in data.get(CONF_OBJECTS, [])
            ],
        )


def devices_from_options(options: dict[str, Any]) -> list[DeviceConfig]:
    """Build the list of configured devices from entry options."""
    from .const import CONF_DEVICES

    return [
        DeviceConfig.from_dict(item) for item in options.get(CONF_DEVICES, [])
    ]
