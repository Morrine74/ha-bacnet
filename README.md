# BACnet for Home Assistant

A modern, **HACS-installable** Home Assistant integration for the
[BACnet](http://www.bacnet.org/) building-automation protocol, built on the
asyncio-native [`bacpypes3`](https://github.com/JoelBender/BACpypes3) stack.

This integration aims to go further than existing community BACnet bridges by
exposing not just simple read/write of points, but also **Change-Of-Value (COV)
push updates**, **Trend Logs**, **Schedules**, and **alarms/events** — directly
inside Home Assistant.

> ⚠️ **Status: early (v0.1.0).** The core (discovery, read/write, COV, services)
> is implemented. Trend/Schedule/Alarm support is exposed through services and
> is being progressively surfaced as native entities and a graphical schedule
> card. Contributions and testing on real hardware are very welcome.

## Features

| Capability | Status | How it surfaces |
|------------|:------:|-----------------|
| Device discovery (Who-Is / I-Am) | ✅ | Config flow + `bacnet.who_is` service |
| Object discovery (object-list) | ✅ | Config flow point picker |
| Read points (ReadProperty) | ✅ | Sensors / polling coordinator |
| Batched polling (ReadPropertyMultiple) | ✅ | Automatic, with per-point fallback |
| Write points (WriteProperty + priority array) | ✅ | `number`, `switch`, `select` entities |
| Change-Of-Value subscriptions (COV) | ✅ | Push updates (`local_push`) |
| BACnet/IP | ✅ | Native |
| Foreign Device / BBMD registration | ✅ | Optional in setup |
| Trend Logs | 🧪 | `bacnet.read_trend_log` service |
| Schedules (weekly/exception) | 🧪 | `bacnet.read_schedule` / `bacnet.write_schedule` |
| Graphical schedule editor | ✅ | Bundled Lovelace card (auto-registered) |
| Alarms & events | 🧪 | `bacnet.acknowledge_alarm` service |
| BACnet MS/TP (serial) | ⛔ | Planned |

Legend: ✅ done · 🧪 via services · 🛠️ in progress · ⛔ planned

## Installation (HACS)

1. In HACS, add this repository as a **custom repository** (category:
   *Integration*).
2. Install **BACnet**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration → BACnet**.

### Manual installation

Copy `custom_components/bacnet` into your Home Assistant `config/custom_components`
directory and restart.

## Configuration

The integration is configured entirely through the UI (Config Flow):

1. **Setup** — provide the local interface in CIDR notation
   (e.g. `192.168.1.10/24`), a local device instance number, and optionally a
   BBMD address for foreign-device registration across subnets.
2. **Options → Discover and add a device** — runs a Who-Is, lists answering
   devices, then reads their object-list so you can pick which points to expose.
3. For each point you can enable **COV** (push updates) and set a default
   **write priority** (1–16).

Points map to Home Assistant entities as follows:

| BACnet object | Entity |
|---------------|--------|
| analog-input, multi-state-input | `sensor` |
| binary-input | `binary_sensor` |
| analog-output, analog-value | `number` |
| binary-output, binary-value | `switch` |
| multi-state-output, multi-state-value | `select` |

### Polling & availability

Each poll cycle batches all the points of a device into a few
**ReadPropertyMultiple** requests (instead of one ReadProperty round-trip per
point). Devices that reject the RPM service automatically fall back to
per-point reads. COV points are polled too: pushes stay authoritative between
polls, while the poll recovers from missed notifications.

A point that fails to read keeps its last known value for a couple of cycles
(riding out one-off timeouts), then its entity is marked **unavailable** until
the device answers again — stale values are never shown indefinitely.

## Services

- `bacnet.read_property` — read any property of any object (returns a response).
- `bacnet.write_property` — write any property, optionally at a priority.
- `bacnet.who_is` — discover devices (returns a response).
- `bacnet.read_schedule` / `bacnet.write_schedule` — work with Schedule objects.
- `bacnet.read_trend_log` — fetch recent Trend Log records (returns a response).
- `bacnet.acknowledge_alarm` — acknowledge an object's event state.

Example:

```yaml
action: bacnet.write_property
data:
  device_address: "192.168.1.50"
  object_id: "analog-value,2"
  property: present-value
  value: 21.5
  priority: 8
```

## Graphical schedule editor (Lovelace card)

A custom Lovelace card renders a BACnet `schedule` object as an interactive
**days × hours** grid with a soft pastel palette.

- **Columns** = the 7 days of the week
- **Rows** = the hours of the day (15 / 30 / 60 min resolution)
- **Left click / drag** (or **tap / drag** on touch screens) = paint the
  selected state
- **Right click / long-press** = context menu (set a state, clear slot,
  **delete segment**, fill the day, copy/paste a day)
- **Save** writes the grid back through `bacnet.write_schedule`, then reads it
  back so "In sync" reflects what the device actually stored
- **Hatched cells** = BACnet *no action*: the device falls back to its
  `schedule-default` value; they are written back as `Null` entries so a
  read-modify-write round trip never changes the device's relinquish behavior
- **Labels come from the device**: a `schedule` object has no state texts of
  its own, so the integration follows its
  `list-of-object-property-references` to the first member object and uses its
  `state-text` (multi-state) or `active`/`inactive-text` (binary) — in the
  card's palette *and* as the schedule sensor's displayed state. An explicit
  `states:` card config overrides this.

> **About writing:** a BACnet `weekly-schedule` is a `BACnetARRAY[7] of
> DailySchedule`, and controllers expect the **whole week** to be written at
> once (as you can confirm on a Wireshark capture). The integration therefore
> always builds and sends all seven days as properly typed `DailySchedule`
> objects. Entry values are typed (`Real`, `Unsigned`, `Enumerated`, …); the
> type is auto-detected from the object's `schedule-default`, or can be forced
> via the `value_type` option / card config.

### Install the card

The card ships **inside** the integration and is registered automatically: once
the BACnet integration is set up, Home Assistant serves the card and loads it as
a frontend module — **no Lovelace resource to add manually**. Just add the card
to a dashboard:

```yaml
type: custom:bacnet-schedule-card
device_address: "192.168.1.50"
object_id: "schedule,1"
title: "AHU-1 Occupancy"
resolution: 30            # minutes per slot: 15 / 30 / 60
states:                   # optional - omit to use the device's own state texts
  - { label: "Occupied",   value: 1, color: "#BFE3C0" }
  - { label: "Standby",    value: 2, color: "#FCE1B6" }
  - { label: "Unoccupied", value: 0, color: "#E3EAF2" }
```

## Development

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements_test.txt
pytest
```

## License

[MIT](LICENSE)
