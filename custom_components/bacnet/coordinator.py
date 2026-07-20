"""Data update coordinator for the BACnet integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ANALOG_TYPES,
    BINARY_TYPES,
    DOMAIN,
    MAX_POLL_FAILURES,
    MULTI_STATE_TYPES,
)
from .hub import BACnetHub, BACnetHubError, BACnetServiceUnsupported
from .models import DeviceConfig, PointConfig

_LOGGER = logging.getLogger(__name__)

# Object types safe to batch into a ReadPropertyMultiple request. Other types
# (e.g. schedule, whose present-value needs bacpypes3's AnyAtomic unwrapping on
# the single-read path) are polled individually.
_BATCHABLE_TYPES = ANALOG_TYPES | BINARY_TYPES | MULTI_STATE_TYPES


def point_key(address: str, object_id: str) -> str:
    """Return the dictionary key used to store a point value."""
    return f"{address}|{object_id}"


class BACnetCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll configured BACnet points and manage COV subscriptions."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        hub: BACnetHub,
        devices: list[DeviceConfig],
        scan_interval: int,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.hub = hub
        self.devices = devices
        self._cov_unsubscribers: list[Callable[[], None]] = []
        # Devices that rejected ReadPropertyMultiple; polled point by point.
        self._rpm_unsupported: set[str] = set()
        # Consecutive poll failures per point key; drives availability.
        self._fail_counts: dict[str, int] = {}

    def iter_points(self):
        """Yield (device, point) pairs for every configured point."""
        for device in self.devices:
            for point in device.points:
                yield device, point

    async def async_setup(self) -> None:
        """Start COV subscriptions for points that requested them."""
        for device, point in self.iter_points():
            if point.use_cov:
                await self._async_subscribe_point(device, point)

    async def _async_subscribe_point(
        self, device: DeviceConfig, point: PointConfig
    ) -> None:
        key = point_key(device.address, point.object_id)

        @callback
        def _handle_cov(payload: dict[str, Any]) -> None:
            if payload.get("property") in ("present-value", "presentValue"):
                # A push proves the device is alive.
                self._fail_counts.pop(key, None)
                data = dict(self.data or {})
                data[key] = _normalize_value(payload["value"])
                self.async_set_updated_data(data)

        try:
            unsub = await self.hub.async_subscribe_cov(
                device.address,
                point.object_id,
                _handle_cov,
                lifetime=point.cov_lifetime,
            )
            self._cov_unsubscribers.append(unsub)
        except BACnetHubError as err:
            _LOGGER.warning(
                "Could not subscribe to COV for %s: %s", point.object_id, err
            )

    async def async_shutdown(self) -> None:
        """Cancel COV subscriptions and stop polling."""
        for unsub in self._cov_unsubscribers:
            unsub()
        self._cov_unsubscribers.clear()
        await super().async_shutdown()

    async def _async_update_data(self) -> dict[str, Any]:
        """Read the present-value of every configured point.

        Points on the same device are batched into ReadPropertyMultiple
        requests (a handful of round-trips instead of one per point); devices
        that reject the service fall back to per-point ReadProperty reads.
        COV points are polled too: pushes stay authoritative between polls,
        the poll recovers from missed notifications and detects dead devices.
        """
        data: dict[str, Any] = dict(self.data or {})
        await asyncio.gather(
            *(self._async_poll_device(device, data) for device in self.devices)
        )
        return data

    async def _async_poll_device(
        self, device: DeviceConfig, data: dict[str, Any]
    ) -> None:
        """Refresh all points of one device, preferring one batched read."""
        batch: list[PointConfig] = []
        singles: list[PointConfig] = []
        for point in device.points:
            if (
                device.address not in self._rpm_unsupported
                and point.object_type in _BATCHABLE_TYPES
            ):
                batch.append(point)
            else:
                singles.append(point)
        if len(batch) < 2:
            # Batching a single point buys nothing.
            singles.extend(batch)
            batch = []

        if batch:
            try:
                values = await self.hub.async_read_present_values(
                    device.address, [point.object_id for point in batch]
                )
            except BACnetServiceUnsupported as err:
                _LOGGER.debug(
                    "%s does not support ReadPropertyMultiple (%s); "
                    "falling back to per-point reads",
                    device.address,
                    err,
                )
                self._rpm_unsupported.add(device.address)
                singles.extend(batch)
            except BACnetHubError as err:
                # Transient failure - keep trying RPM on the next poll.
                _LOGGER.debug(
                    "Batched read failed for %s: %s", device.address, err
                )
                for point in batch:
                    self._record_failure(device, point, data)
            else:
                for point in batch:
                    if point.object_id in values:
                        self._record_success(
                            device, point, values[point.object_id], data
                        )
                    else:
                        self._record_failure(device, point, data)

        if singles:
            await asyncio.gather(
                *(self._async_poll_point(device, point, data) for point in singles)
            )

    async def _async_poll_point(
        self, device: DeviceConfig, point: PointConfig, data: dict[str, Any]
    ) -> None:
        """Refresh a single point with an individual ReadProperty."""
        try:
            value = await self.hub.async_read_present_value(
                device.address, point.object_id
            )
        except BACnetHubError as err:
            _LOGGER.debug("Read failed for %s: %s", point.object_id, err)
            self._record_failure(device, point, data)
        else:
            self._record_success(device, point, value, data)

    def _record_success(
        self,
        device: DeviceConfig,
        point: PointConfig,
        value: Any,
        data: dict[str, Any],
    ) -> None:
        key = point_key(device.address, point.object_id)
        self._fail_counts.pop(key, None)
        data[key] = _normalize_value(value)

    def _record_failure(
        self, device: DeviceConfig, point: PointConfig, data: dict[str, Any]
    ) -> None:
        """Count a failed read; after enough misses the point goes unavailable.

        The last known value is kept for the first few failures so a one-off
        timeout does not flap the entity; a ``None`` value marks the entity
        unavailable (see ``BACnetEntity.available``).
        """
        key = point_key(device.address, point.object_id)
        count = self._fail_counts.get(key, 0) + 1
        self._fail_counts[key] = count
        if count < MAX_POLL_FAILURES:
            data.setdefault(key, None)
            return
        if data.get(key) is not None:
            _LOGGER.warning(
                "%s@%s unreachable for %d consecutive polls; "
                "marking its entity unavailable",
                point.object_id,
                device.address,
                count,
            )
        data[key] = None

    async def async_write_point(
        self, device: DeviceConfig, point: PointConfig, value: Any
    ) -> None:
        """Write a value to a point and refresh local state optimistically."""
        await self.hub.async_write_property(
            device.address,
            point.object_id,
            "present-value",
            value,
            priority=point.write_priority,
        )
        key = point_key(device.address, point.object_id)
        # A successful write proves the device is alive.
        self._fail_counts.pop(key, None)
        data = dict(self.data or {})
        data[key] = value
        self.async_set_updated_data(data)


def _normalize_value(value: Any) -> Any:
    """Convert bacpypes primitives to plain Python values for HA state."""
    if value is None or isinstance(value, (int, float, bool, str)):
        return value

    # BACnet Null (e.g. a relinquished/no-action value) maps to None.
    if type(value).__name__.lower() == "null":
        return None

    # AnyAtomic (e.g. a Schedule present-value) wraps the real atomic value and
    # exposes it through get_value()/get_value_type(); unwrap it first.
    getter = getattr(value, "get_value", None)
    if callable(getter):
        try:
            return _normalize_value(getter())
        except Exception:  # noqa: BLE001
            pass

    for attr in ("value", "realValue", "enumeratedValue", "booleanValue"):
        if hasattr(value, attr):
            inner = getattr(value, attr)
            return inner if not callable(inner) else _normalize_value(inner())

    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)

