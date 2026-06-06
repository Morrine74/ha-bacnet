"""Tests for the BACnet data models (pure, no Home Assistant required)."""

from __future__ import annotations

from bacnet import models


def test_point_config_round_trip():
    point = models.PointConfig(
        object_type="analog-value",
        instance=7,
        name="Setpoint",
        use_cov=True,
        cov_lifetime=120,
        write_priority=8,
    )
    restored = models.PointConfig.from_dict(point.to_dict())
    assert restored == point
    assert restored.object_id == "analog-value,7"
    assert restored.writable is True


def test_point_config_read_only_type_not_writable():
    point = models.PointConfig(object_type="analog-input", instance=1, name="Temp")
    assert point.writable is False


def test_device_config_round_trip():
    device = models.DeviceConfig(
        device_id=1001,
        address="192.168.1.50",
        name="AHU-1",
        points=[
            models.PointConfig(object_type="binary-output", instance=2, name="Fan"),
        ],
    )
    restored = models.DeviceConfig.from_dict(device.to_dict())
    assert restored.device_id == 1001
    assert restored.unique_id == "1001"
    assert len(restored.points) == 1
    assert restored.points[0].object_id == "binary-output,2"


def test_devices_from_options_empty():
    assert models.devices_from_options({}) == []
