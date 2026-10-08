"""Tests for config-flow helpers (requires homeassistant, so CI-only)."""

from __future__ import annotations

import pytest

from bacnet import hub


def test_point_label_prefers_description():
    pytest.importorskip("homeassistant")
    from bacnet import config_flow

    described = hub.DiscoveredObject(
        object_type="analog-input",
        instance=3,
        name="AI_3",
        description="Température bureau",
    )
    assert (
        config_flow._point_label(described)
        == "Température bureau (AI_3) [analog-input,3]"
    )

    name_only = hub.DiscoveredObject(
        object_type="schedule", instance=1, name="SCH1"
    )
    assert config_flow._point_label(name_only) == "SCH1 [schedule,1]"

    bare = hub.DiscoveredObject(object_type="binary-value", instance=2)
    assert config_flow._point_label(bare) == "binary-value,2 [binary-value,2]"


class _FakeHub:
    """Minimal hub stub: answers a directed Who-Is from a fixed table."""

    started = True

    def __init__(self, answers: dict[str, int]) -> None:
        self._answers = answers
        self.calls: list[str] = []

    async def async_who_is(self, *, address=None, timeout=0):
        self.calls.append(address)
        device_id = self._answers.get(address)
        if device_id is None:
            return []
        return [hub.DiscoveredDevice(device_id=device_id, address=address)]


def _options_flow(hub_stub, devices):
    """Build an options flow around a fake entry holding ``devices``."""
    pytest.importorskip("homeassistant")
    from types import SimpleNamespace

    from bacnet import config_flow
    from bacnet.const import CONF_DEVICES, CONF_SCAN_INTERVAL

    entry = SimpleNamespace(
        options={
            CONF_DEVICES: [d.to_dict() for d in devices],
            CONF_SCAN_INTERVAL: 60,
        },
        runtime_data=SimpleNamespace(hub=hub_stub),
    )
    return config_flow.BACnetOptionsFlow(entry)


@pytest.mark.asyncio
async def test_change_address_checks_new_address_then_saves():
    pytest.importorskip("homeassistant")
    from bacnet.const import CONF_DEVICES, CONF_VERIFY_ADDRESS
    from bacnet.models import DeviceConfig

    device = DeviceConfig(device_id=42, address="192.168.0.10", name="Chaufferie")
    stub = _FakeHub({"192.168.0.20": 42})
    flow = _options_flow(stub, [device])

    await flow.async_step_change_address({"device": "42"})
    result = await flow.async_step_change_address_value(
        {"address": " 192.168.0.20 ", CONF_VERIFY_ADDRESS: True}
    )

    assert stub.calls == ["192.168.0.20"]
    assert result["type"] == "create_entry"
    saved = result["data"][CONF_DEVICES]
    assert saved[0]["device_address"] == "192.168.0.20"
    assert saved[0]["device_id"] == 42


@pytest.mark.asyncio
async def test_change_address_rejects_other_device_or_silence():
    pytest.importorskip("homeassistant")
    from bacnet.const import CONF_VERIFY_ADDRESS
    from bacnet.models import DeviceConfig

    device = DeviceConfig(device_id=42, address="192.168.0.10", name="Chaufferie")
    stub = _FakeHub({"192.168.0.30": 99})
    flow = _options_flow(stub, [device])
    await flow.async_step_change_address({"device": "42"})

    mismatch = await flow.async_step_change_address_value(
        {"address": "192.168.0.30", CONF_VERIFY_ADDRESS: True}
    )
    assert mismatch["type"] == "form"
    assert mismatch["errors"] == {"base": "device_id_mismatch"}

    silent = await flow.async_step_change_address_value(
        {"address": "192.168.0.31", CONF_VERIFY_ADDRESS: True}
    )
    assert silent["type"] == "form"
    assert silent["errors"] == {"base": "device_not_found"}
    assert device.address == "192.168.0.10"


@pytest.mark.asyncio
async def test_change_address_can_skip_verification():
    pytest.importorskip("homeassistant")
    from bacnet.const import CONF_DEVICES, CONF_VERIFY_ADDRESS
    from bacnet.models import DeviceConfig

    device = DeviceConfig(device_id=42, address="192.168.0.10", name="Chaufferie")
    stub = _FakeHub({})
    flow = _options_flow(stub, [device])
    await flow.async_step_change_address({"device": "42"})

    result = await flow.async_step_change_address_value(
        {"address": "10.0.0.5", CONF_VERIFY_ADDRESS: False}
    )
    assert stub.calls == []
    assert result["type"] == "create_entry"
    assert result["data"][CONF_DEVICES][0]["device_address"] == "10.0.0.5"
