"""Data update coordinator for the BACnet integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .hub import BACnetHub, BACnetHubError
from .models import DeviceConfig, PointConfig

_LOGGER = logging.getLogger(__name__)


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
        self._cov_values: dict[str, Any] = {}

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
                self._cov_values[key] = payload["value"]
                data = dict(self.data or {})
                data[key] = payload["value"]
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
        """Read the present-value of every polled point."""
        data: dict[str, Any] = dict(self.data or {})

        async def _read(device: DeviceConfig, point: PointConfig) -> None:
            key = point_key(device.address, point.object_id)
            if point.use_cov and key in self._cov_values:
                # COV-driven points keep their pushed value between polls but we
                # still refresh occasionally to recover from missed messages.
                data[key] = self._cov_values[key]
                return
            try:
                value = await self.hub.async_read_present_value(
                    device.address, point.object_id
                )
                data[key] = _normalize_value(value)
            except BACnetHubError as err:
                _LOGGER.debug("Read failed for %s: %s", point.object_id, err)
                data.setdefault(key, None)

        tasks = [
            _read(device, point) for device, point in self.iter_points()
        ]
        if not tasks:
            return data
        try:
            await asyncio.gather(*tasks)
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"BACnet polling failed: {err}") from err
        return data

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
        data = dict(self.data or {})
        data[key] = value
        self.async_set_updated_data(data)


def _normalize_value(value: Any) -> Any:
    """Convert bacpypes primitives to plain Python values for HA state."""
    if value is None or isinstance(value, (int, float, bool, str)):
        return value

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

