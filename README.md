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
| Write points (WriteProperty + priority array) | ✅ | `number`, `switch`, `select` entities |
| Change-Of-Value subscriptions (COV) | ✅ | Push updates (`local_push`) |
| BACnet/IP | ✅ | Native |
| Foreign Device / BBMD registration | ✅ | Optional in setup |
| Trend Logs | 🧪 | `bacnet.read_trend_log` service |
| Schedules (weekly/exception) | 🧪 | `bacnet.read_schedule` / `bacnet.write_schedule` |
| Graphical schedule editor | 🛠️ | Lovelace card (planned, see `www/`) |
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

## Development

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements_test.txt
pytest
```

## License

[MIT](LICENSE)
