"""BACnet network hub built on top of bacpypes3.

This module isolates every interaction with the bacpypes3 stack so the rest of
the integration only deals with plain Python data structures. All public methods
are coroutines that are safe to await from the Home Assistant event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DiscoveredDevice:
    """A device discovered on the network through a Who-Is / I-Am exchange."""

    device_id: int
    address: str
    name: str | None = None
    vendor_id: int | None = None
    max_apdu_length: int | None = None
    segmentation_supported: str | None = None


@dataclass(slots=True)
class DiscoveredObject:
    """A single BACnet object discovered on a device."""

    object_type: str
    instance: int
    name: str | None = None
    description: str | None = None
    units: str | None = None

    @property
    def object_id(self) -> str:
        """Return the canonical ``type,instance`` identifier."""
        return f"{self.object_type},{self.instance}"


@dataclass(slots=True)
class CovContext:
    """Bookkeeping for an active COV subscription task."""

    task: asyncio.Task
    cancel: asyncio.Event = field(default_factory=asyncio.Event)


class BACnetHubError(Exception):
    """Raised when a BACnet operation fails."""


class BACnetHub:
    """Manage a single bacpypes3 application instance.

    One hub corresponds to one config entry and owns exactly one local BACnet
    device/application bound to a network interface.
    """

    def __init__(
        self,
        *,
        local_ip: str,
        object_id: int,
        object_name: str,
        bbmd_address: str | None = None,
        bbmd_ttl: int = 30,
    ) -> None:
        """Initialise the hub configuration (no network I/O yet)."""
        self._local_ip = local_ip
        self._object_id = object_id
        self._object_name = object_name
        self._bbmd_address = bbmd_address
        self._bbmd_ttl = bbmd_ttl
        self._app: Any = None
        self._lock = asyncio.Lock()
        self._cov_contexts: dict[str, CovContext] = {}
        self._started = False

    @property
    def started(self) -> bool:
        """Return whether the underlying application is running."""
        return self._started

    async def async_start(self) -> None:
        """Create and start the bacpypes3 application."""
        if self._started:
            return

        # Imported lazily so the dependency is only required at runtime.
        from bacpypes3.app import Application
        from bacpypes3.local.device import DeviceObject
        from bacpypes3.local.networkport import NetworkPortObject

        try:
            device_object = DeviceObject(
                objectIdentifier=("device", self._object_id),
                objectName=self._object_name,
                vendorIdentifier=15,
            )
            network_port_object = NetworkPortObject(
                self._local_ip,
                objectName="NetworkPort-1",
                objectIdentifier=("network-port", 1),
            )
            if self._bbmd_address:
                # Register as a foreign device with the configured BBMD.
                network_port_object.bbmdAddress = self._bbmd_address
                network_port_object.bbmdAcceptFDRegistrations = True

            self._app = Application.from_object_list(
                [device_object, network_port_object]
            )
        except Exception as err:  # noqa: BLE001 - surface any stack failure
            raise BACnetHubError(
                f"Unable to start BACnet application: {err}"
            ) from err

        self._started = True
        _LOGGER.debug(
            "BACnet application started on %s as device %s",
            self._local_ip,
            self._object_id,
        )

    async def async_stop(self) -> None:
        """Cancel subscriptions and close the application."""
        for context in list(self._cov_contexts.values()):
            context.cancel.set()
            context.task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await context.task
        self._cov_contexts.clear()

        if self._app is not None:
            with suppress(Exception):
                self._app.close()
            self._app = None
        self._started = False

    def _require_app(self) -> Any:
        if self._app is None:
            raise BACnetHubError("BACnet application is not running")
        return self._app

    @staticmethod
    def _parse_object_id(object_id: str) -> tuple[str, int]:
        """Split a ``type,instance`` string into its components."""
        try:
            obj_type, instance = object_id.split(",", 1)
            return obj_type.strip(), int(instance)
        except (ValueError, AttributeError) as err:
            raise BACnetHubError(f"Invalid object id '{object_id}'") from err

    async def async_who_is(
        self,
        *,
        low_limit: int | None = None,
        high_limit: int | None = None,
        address: str | None = None,
        timeout: float = 5.0,
    ) -> list[DiscoveredDevice]:
        """Broadcast a Who-Is and collect the I-Am responses."""
        from bacpypes3.pdu import Address

        app = self._require_app()
        dest = Address(address) if address else None

        async with self._lock:
            try:
                i_ams = await asyncio.wait_for(
                    app.who_is(low_limit, high_limit, dest),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                i_ams = []
            except Exception as err:  # noqa: BLE001
                raise BACnetHubError(f"Who-Is failed: {err}") from err

        devices: list[DiscoveredDevice] = []
        for i_am in i_ams or []:
            device_id = int(i_am.iAmDeviceIdentifier[1])
            devices.append(
                DiscoveredDevice(
                    device_id=device_id,
                    address=str(i_am.pduSource),
                    vendor_id=int(getattr(i_am, "vendorID", 0) or 0),
                    max_apdu_length=int(
                        getattr(i_am, "maxAPDULengthAccepted", 0) or 0
                    ),
                    segmentation_supported=str(
                        getattr(i_am, "segmentationSupported", "") or ""
                    ),
                )
            )
        return devices

    async def async_read_property(
        self,
        address: str,
        object_id: str,
        prop: str,
        array_index: int | None = None,
    ) -> Any:
        """Read a single property from a remote object."""
        from bacpypes3.pdu import Address
        from bacpypes3.primitivedata import ObjectIdentifier

        app = self._require_app()
        obj_type, instance = self._parse_object_id(object_id)
        try:
            return await app.read_property(
                Address(address),
                ObjectIdentifier(f"{obj_type},{instance}"),
                prop,
                array_index,
            )
        except Exception as err:  # noqa: BLE001
            raise BACnetHubError(
                f"Read {prop} of {object_id}@{address} failed: {err}"
            ) from err

    async def async_read_present_value(
        self, address: str, object_id: str
    ) -> Any:
        """Convenience wrapper to read the present-value property."""
        return await self.async_read_property(address, object_id, "present-value")

    async def async_write_property(
        self,
        address: str,
        object_id: str,
        prop: str,
        value: Any,
        *,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        """Write a property to a remote object (priority array aware)."""
        from bacpypes3.pdu import Address
        from bacpypes3.primitivedata import ObjectIdentifier

        app = self._require_app()
        obj_type, instance = self._parse_object_id(object_id)
        try:
            await app.write_property(
                Address(address),
                ObjectIdentifier(f"{obj_type},{instance}"),
                prop,
                value,
                array_index,
                priority,
            )
        except Exception as err:  # noqa: BLE001
            raise BACnetHubError(
                f"Write {prop} of {object_id}@{address} failed: {err}"
            ) from err

    async def async_object_list(self, address: str, device_id: int) -> list[str]:
        """Return the raw object-list of a remote device."""
        ids = await self.async_read_property(
            address, f"device,{device_id}", "object-list"
        )
        result: list[str] = []
        for item in ids or []:
            try:
                result.append(f"{item[0]},{int(item[1])}")
            except (TypeError, IndexError):
                result.append(str(item))
        return result

    async def async_discover_objects(
        self, address: str, device_id: int
    ) -> list[DiscoveredObject]:
        """Discover objects on a device and read their friendly metadata."""
        object_ids = await self.async_object_list(address, device_id)
        objects: list[DiscoveredObject] = []
        for object_id in object_ids:
            obj_type, instance = self._parse_object_id(object_id)
            if obj_type == "device":
                continue
            name = None
            description = None
            units = None
            with suppress(BACnetHubError):
                name = str(
                    await self.async_read_property(
                        address, object_id, "object-name"
                    )
                )
            with suppress(BACnetHubError):
                description = str(
                    await self.async_read_property(
                        address, object_id, "description"
                    )
                )
            if obj_type.startswith("analog"):
                with suppress(BACnetHubError):
                    units = str(
                        await self.async_read_property(
                            address, object_id, "units"
                        )
                    )
            objects.append(
                DiscoveredObject(
                    object_type=obj_type,
                    instance=instance,
                    name=name,
                    description=description,
                    units=units,
                )
            )
        return objects

    @asynccontextmanager
    async def _change_of_value(
        self,
        address: str,
        object_id: str,
        *,
        confirmed: bool,
        lifetime: int,
    ) -> AsyncIterator[Any]:
        """Open a bacpypes3 change-of-value subscription context."""
        from bacpypes3.pdu import Address
        from bacpypes3.primitivedata import ObjectIdentifier

        app = self._require_app()
        obj_type, instance = self._parse_object_id(object_id)
        subscriber_process_id = (abs(hash(object_id)) % 0xFFFF) + 1
        async with app.change_of_value(
            Address(address),
            ObjectIdentifier(f"{obj_type},{instance}"),
            subscriber_process_id,
            confirmed,
            lifetime,
        ) as scm:
            yield scm

    async def async_subscribe_cov(
        self,
        address: str,
        object_id: str,
        callback: Callable[[dict[str, Any]], None],
        *,
        confirmed: bool = False,
        lifetime: int = 300,
    ) -> Callable[[], None]:
        """Subscribe to Change-Of-Value notifications for an object.

        Returns a callable that cancels the subscription.
        """
        key = f"{address}:{object_id}"
        if key in self._cov_contexts:
            self._cov_contexts[key].cancel.set()
            self._cov_contexts[key].task.cancel()

        context = CovContext(task=None)  # type: ignore[arg-type]

        async def _runner() -> None:
            while not context.cancel.is_set():
                try:
                    async with self._change_of_value(
                        address,
                        object_id,
                        confirmed=confirmed,
                        lifetime=lifetime,
                    ) as scm:
                        async for prop_id, prop_value in scm:
                            if context.cancel.is_set():
                                break
                            callback(
                                {
                                    "object_id": object_id,
                                    "address": address,
                                    "property": str(prop_id),
                                    "value": prop_value,
                                }
                            )
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug(
                        "COV subscription for %s lost (%s); retrying", key, err
                    )
                    await asyncio.sleep(min(lifetime, 30))

        context.task = asyncio.ensure_future(_runner())
        self._cov_contexts[key] = context

        def _unsubscribe() -> None:
            context.cancel.set()
            context.task.cancel()
            self._cov_contexts.pop(key, None)

        return _unsubscribe

    async def async_read_trend_log(
        self, address: str, object_id: str, count: int = 50
    ) -> list[dict[str, Any]]:
        """Read the most recent records from a Trend Log object."""
        record_count = await self.async_read_property(
            address, object_id, "record-count"
        )
        try:
            record_count = int(record_count)
        except (TypeError, ValueError):
            record_count = 0
        if record_count <= 0:
            return []

        start = max(1, record_count - count + 1)
        buffer = await self.async_read_property(
            address, object_id, "log-buffer", array_index=None
        )

        records: list[dict[str, Any]] = []
        for record in list(buffer or [])[-count:]:
            timestamp = getattr(record, "timestamp", None)
            log_datum = getattr(record, "logDatum", None)
            records.append(
                {
                    "timestamp": str(timestamp) if timestamp else None,
                    "value": _coerce_log_datum(log_datum),
                }
            )
        _LOGGER.debug(
            "Read %s trend records from %s (start=%s)",
            len(records),
            object_id,
            start,
        )
        return records

    async def async_read_schedule(
        self, address: str, object_id: str
    ) -> dict[str, Any]:
        """Read weekly and exception schedules from a Schedule object.

        The returned ``value_type`` is inferred from ``schedule-default`` and
        tells the caller (and the Lovelace card) which primitive datatype the
        schedule entries use, so a later write can be typed identically.
        """
        weekly = None
        exception = None
        present_value = None
        schedule_default = None
        with suppress(BACnetHubError):
            weekly = await self.async_read_property(
                address, object_id, "weekly-schedule"
            )
        with suppress(BACnetHubError):
            exception = await self.async_read_property(
                address, object_id, "exception-schedule"
            )
        with suppress(BACnetHubError):
            present_value = await self.async_read_property(
                address, object_id, "present-value"
            )
        with suppress(BACnetHubError):
            schedule_default = await self.async_read_property(
                address, object_id, "schedule-default"
            )

        value_type = _bacpypes_type_name(schedule_default)
        if value_type is None:
            value_type = _infer_value_type_from_weekly(weekly)

        return {
            "weekly_schedule": _serialize_weekly_schedule(weekly),
            "exception_schedule": _serialize_exception_schedule(exception),
            "present_value": _coerce_log_datum(present_value),
            "schedule_default": _coerce_log_datum(schedule_default),
            "value_type": value_type,
        }

    async def async_write_schedule(
        self,
        address: str,
        object_id: str,
        weekly_schedule: Any,
        *,
        value_type: str | None = None,
    ) -> None:
        """Write a full 7-day weekly schedule to a Schedule object.

        BACnet's ``weekly-schedule`` is a ``BACnetARRAY[7] of DailySchedule`` and
        most controllers only accept the *whole* array in a single write (this
        is exactly what is seen on the wire). We therefore always build all seven
        days as properly typed ``DailySchedule`` objects and write the complete
        array (no array index), instead of forwarding a loosely typed Python
        list. When ``value_type`` is not supplied it is auto-detected from the
        object's ``schedule-default`` property.
        """
        if value_type is None:
            with suppress(BACnetHubError):
                default = await self.async_read_property(
                    address, object_id, "schedule-default"
                )
                value_type = _bacpypes_type_name(default)
        if value_type is None:
            value_type = "real"

        weekly_object = _build_weekly_schedule(weekly_schedule, value_type)

        # array_index is intentionally None so the entire 7-day array is sent.
        await self.async_write_property(
            address,
            object_id,
            "weekly-schedule",
            weekly_object,
            array_index=None,
        )

    async def async_acknowledge_alarm(
        self,
        address: str,
        object_id: str,
        *,
        event_state: str,
        ack_source: str = "HomeAssistant",
    ) -> None:
        """Send an AcknowledgeAlarm request for an object's event state."""
        # Implemented through the generic confirmed service interface.
        from bacpypes3.pdu import Address
        from bacpypes3.primitivedata import ObjectIdentifier

        app = self._require_app()
        obj_type, instance = self._parse_object_id(object_id)
        try:
            await app.acknowledge_alarm(  # type: ignore[attr-defined]
                Address(address),
                ObjectIdentifier(f"{obj_type},{instance}"),
                event_state,
                ack_source,
            )
        except AttributeError as err:
            raise BACnetHubError(
                "AcknowledgeAlarm is not supported by this bacpypes3 build"
            ) from err
        except Exception as err:  # noqa: BLE001
            raise BACnetHubError(
                f"AcknowledgeAlarm for {object_id}@{address} failed: {err}"
            ) from err


def _coerce_log_datum(value: Any) -> Any:
    """Best-effort conversion of a bacpypes value into a JSON-friendly type."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
    for attr in ("value", "realValue", "enumeratedValue", "booleanValue"):
        if hasattr(value, attr):
            return getattr(value, attr)
    with suppress(Exception):
        return float(value)
    return str(value)


def _serialize_weekly_schedule(weekly: Any) -> list[list[dict[str, Any]]] | None:
    """Serialise a BACnet weekly schedule into plain dictionaries."""
    if weekly is None:
        return None
    days: list[list[dict[str, Any]]] = []
    for day in weekly:
        slots: list[dict[str, Any]] = []
        for time_value in getattr(day, "daySchedule", day) or []:
            slots.append(
                {
                    "time": str(getattr(time_value, "time", "")),
                    "value": _coerce_log_datum(getattr(time_value, "value", None)),
                }
            )
        days.append(slots)
    return days


def _serialize_exception_schedule(exception: Any) -> list[dict[str, Any]] | None:
    """Serialise a BACnet exception schedule into plain dictionaries."""
    if exception is None:
        return None
    result: list[dict[str, Any]] = []
    for special_event in exception:
        result.append({"raw": str(special_event)})
    return result


def _bacpypes_type_name(value: Any) -> str | None:
    """Map a bacpypes primitive instance to a canonical value-type name.

    Returns one of ``real``, ``unsigned``, ``integer``, ``boolean``,
    ``enumerated`` or ``None`` when the type cannot be determined.
    """
    if value is None:
        return None
    cls = type(value).__name__.lower()
    if "real" in cls or "double" in cls:
        return "real"
    if "unsigned" in cls:
        return "unsigned"
    if "boolean" in cls:
        return "boolean"
    if "enumerated" in cls:
        return "enumerated"
    if "integer" in cls:
        return "integer"
    return None


def _infer_value_type_from_weekly(weekly: Any) -> str:
    """Guess the entry datatype by inspecting the first value in the schedule."""
    if weekly is None:
        return "real"
    for day in weekly:
        for time_value in getattr(day, "daySchedule", day) or []:
            name = _bacpypes_type_name(getattr(time_value, "value", None))
            if name:
                return name
    return "real"


def _build_schedule_value(value: Any, value_type: str) -> Any:
    """Build a typed bacpypes primitive for a schedule entry value.

    A ``None`` value is encoded as ``Null`` which, in a BACnet schedule, means
    "no action" at that time (relinquish), matching the protocol semantics.
    """
    from bacpypes3.primitivedata import (
        Boolean,
        Enumerated,
        Integer,
        Null,
        Real,
        Unsigned,
    )

    if value is None:
        return Null(())

    vt = (value_type or "real").lower()
    try:
        if vt in ("real", "float", "analog", "double"):
            return Real(float(value))
        if vt in ("unsigned", "multistate", "multi-state", "multi_state"):
            return Unsigned(int(value))
        if vt in ("integer", "int"):
            return Integer(int(value))
        if vt in ("boolean", "bool"):
            if isinstance(value, str):
                value = value.lower() in ("1", "true", "on", "active")
            return Boolean(bool(value))
        if vt in ("enumerated", "binary", "binary-pv"):
            return Enumerated(int(value))
    except (TypeError, ValueError) as err:
        raise BACnetHubError(
            f"Cannot encode schedule value {value!r} as {vt}: {err}"
        ) from err

    # Fallback: best-effort real.
    with suppress(TypeError, ValueError):
        return Real(float(value))
    raise BACnetHubError(f"Unsupported schedule value type '{value_type}'")


def _build_daily_schedule(day_entries: Any, value_type: str) -> Any:
    """Build a bacpypes ``DailySchedule`` from a list of ``{time, value}``."""
    from bacpypes3.basetypes import DailySchedule, TimeValue
    from bacpypes3.primitivedata import Time

    time_values = []
    for entry in day_entries or []:
        raw_time = entry.get("time") if isinstance(entry, dict) else None
        raw_value = entry.get("value") if isinstance(entry, dict) else None
        if raw_time is None:
            continue
        time_values.append(
            TimeValue(
                time=Time(_normalize_time_string(raw_time)),
                value=_build_schedule_value(raw_value, value_type),
            )
        )
    return DailySchedule(daySchedule=time_values)


def _build_weekly_schedule(weekly_schedule: Any, value_type: str) -> Any:
    """Build a fully typed 7-day ``WeeklySchedule`` for writing.

    The result always contains exactly seven ``DailySchedule`` entries (empty
    days are kept as empty lists) so the complete array is written in one shot,
    which is what BACnet controllers expect on the wire.
    """
    from bacpypes3.basetypes import WeeklySchedule

    days = list(weekly_schedule or [])
    # Normalise to exactly 7 days.
    days = (days + [[] for _ in range(7)])[:7]

    daily = [_build_daily_schedule(day, value_type) for day in days]

    try:
        return WeeklySchedule(daySchedule=daily)
    except TypeError:
        # Some bacpypes3 versions accept the array positionally.
        return WeeklySchedule(daily)


def _normalize_time_string(value: Any) -> str:
    """Coerce a time into the ``HH:MM:SS`` form expected by bacpypes ``Time``."""
    text = str(value).strip()
    parts = text.split(":")
    while len(parts) < 3:
        parts.append("00")
    h, m, s = parts[0], parts[1], parts[2]
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

