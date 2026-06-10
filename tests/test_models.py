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
        units="degrees-celsius",
        description="Room setpoint",
    )
    restored = models.PointConfig.from_dict(point.to_dict())
    assert restored == point
    assert restored.object_id == "analog-value,7"
    assert restored.writable is True
    assert restored.units == "degrees-celsius"
    assert restored.description == "Room setpoint"


def test_point_config_state_text_round_trip():
    point = models.PointConfig(
        object_type="multi-state-value",
        instance=2,
        name="Mode",
        state_text=["Off", "Comfort", "Eco"],
    )
    restored = models.PointConfig.from_dict(point.to_dict())
    assert restored.state_text == ["Off", "Comfort", "Eco"]


def test_point_config_binary_text_round_trip():
    point = models.PointConfig(
        object_type="binary-value",
        instance=3,
        name="Pump",
        active_text="Running",
        inactive_text="Stopped",
    )
    restored = models.PointConfig.from_dict(point.to_dict())
    assert restored.active_text == "Running"
    assert restored.inactive_text == "Stopped"


def test_point_config_tree_path_round_trip():
    point = models.PointConfig(
        object_type="analog-input",
        instance=6,
        name="Température au retour",
        tree_path=[
            "Gymnase",
            "Locaux Techniques",
            "Production de chaleur",
            "Chaudière",
            "Température au retour",
        ],
        equipment_index=2,
    )
    restored = models.PointConfig.from_dict(point.to_dict())
    assert restored.tree_path == point.tree_path
    assert restored.equipment_index == 2


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
