"""End-to-end loopback test for schedule read/write.

Spins up a simulated BACnet "controller" (a bacpypes3 application hosting a
Schedule object) on 127.0.0.1:47809, then drives it through the integration's
own BACnetHub bound to 127.0.0.1:47808. The write travels as a real
WriteProperty APDU over UDP, so this exercises encoding, the typed
ArrayOfDailySchedule build, and the device-side decode - everything except
vendor-specific controller quirks.

Run from the repository root:

    .venv\\Scripts\\python.exe scripts\\loopback_schedule_test.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import types

# Make `custom_components/bacnet` importable as the `bacnet` package without
# executing its __init__.py (which needs homeassistant). Same trick as tests.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_package = types.ModuleType("bacnet")
_package.__path__ = [os.path.join(_REPO_ROOT, "custom_components", "bacnet")]
sys.modules["bacnet"] = _package

from bacnet.hub import BACnetHub  # noqa: E402

SERVER_ADDRESS = "127.0.0.1:47809"
SCHEDULE_ID = "schedule,1"

TARGET_WEEK = [
    [{"time": "06:00", "value": 21.0}, {"time": "22:00", "value": 16.0}],
    [],
    [],
    [],
    [],
    [],
    [{"time": "08:00", "value": 19.5}],
]


def _build_server():
    """Create the simulated controller application with one Schedule object."""
    from bacpypes3.app import Application
    from bacpypes3.basetypes import DailySchedule, DateRange
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.local.networkport import NetworkPortObject
    from bacpypes3.local.schedule import ScheduleObject
    from bacpypes3.primitivedata import Date, Real

    device = DeviceObject(
        objectIdentifier=("device", 900),
        objectName="SimController",
        vendorIdentifier=15,
    )
    port = NetworkPortObject(
        "127.0.0.1/32:47809",
        objectName="NetworkPort-1",
        objectIdentifier=("network-port", 1),
    )
    app = Application.from_object_list([device, port])
    schedule = ScheduleObject(
        objectIdentifier=("schedule", 1),
        objectName="Sim Schedule",
        presentValue=Real(0.0),
        scheduleDefault=Real(0.0),
        effectivePeriod=DateRange(
            startDate=Date((0, 1, 1, 1)), endDate=Date((254, 12, 31, 7))
        ),
        weeklySchedule=[DailySchedule(daySchedule=[]) for _ in range(7)],
    )
    app.add_object(schedule)
    return app


def _simplify(day):
    """Reduce serialized entries to (HH:MM, value) pairs for comparison."""
    return [(entry["time"][:5], entry["value"]) for entry in day]


async def main() -> int:
    server = _build_server()

    hub = BACnetHub(
        local_ip="127.0.0.1/32:47808", object_id=599, object_name="HA-loopback"
    )
    await hub.async_start()
    failures: list[str] = []
    try:
        # Directed Who-Is (same path as the "add by IP" config flow). The
        # wildcard-instance ReadProperty is not supported by the bacpypes3
        # server side, so it is not exercised here.
        found = await hub.async_who_is(address=SERVER_ADDRESS, timeout=3)
        print(f"directed Who-Is found: {[(d.device_id, d.address) for d in found]}")
        if not found or found[0].device_id != 900:
            failures.append(f"directed Who-Is did not find device 900: {found}")

        before = await hub.async_read_schedule(SERVER_ADDRESS, SCHEDULE_ID)
        print(f"value_type detected from schedule-default: {before['value_type']}")
        if before["value_type"] != "real":
            failures.append(f"expected value_type 'real', got {before['value_type']}")

        await hub.async_write_schedule(SERVER_ADDRESS, SCHEDULE_ID, TARGET_WEEK)
        print("weekly-schedule written (full 7-day array, auto-typed)")

        after = await hub.async_read_schedule(SERVER_ADDRESS, SCHEDULE_ID)
        week = after["weekly_schedule"]
        if _simplify(week[0]) != [("06:00", 21.0), ("22:00", 16.0)]:
            failures.append(f"day 0 mismatch: {week[0]}")
        if _simplify(week[6]) != [("08:00", 19.5)]:
            failures.append(f"day 6 mismatch: {week[6]}")
        for day_index in range(1, 6):
            if week[day_index]:
                failures.append(f"day {day_index} should be empty: {week[day_index]}")
        print(f"read back day 0: {week[0]}")
        print(f"read back day 6: {week[6]}")
    finally:
        await hub.async_stop()
        server.close()

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("ROUNDTRIP OK: write accepted and read back identically over UDP")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
