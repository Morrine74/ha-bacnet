"""Tests for the hub's pure helper functions (no bacpypes3 required)."""

from __future__ import annotations

from bacnet import hub


class _Wrapper:
    """Stand-in for a bacpypes primitive exposing a ``value`` attribute."""

    def __init__(self, value):
        self.value = value


def test_coerce_log_datum_passthrough():
    assert hub._coerce_log_datum(3.14) == 3.14
    assert hub._coerce_log_datum(True) is True
    assert hub._coerce_log_datum("on") == "on"
    assert hub._coerce_log_datum(None) is None


def test_coerce_log_datum_unwraps_value_attr():
    assert hub._coerce_log_datum(_Wrapper(42)) == 42


def test_parse_object_id_valid():
    assert hub.BACnetHub._parse_object_id("analog-input,5") == ("analog-input", 5)


def test_parse_object_id_invalid():
    import pytest

    with pytest.raises(hub.BACnetHubError):
        hub.BACnetHub._parse_object_id("not-an-id")


def test_serialize_weekly_schedule_none():
    assert hub._serialize_weekly_schedule(None) is None


def test_discovered_object_object_id():
    obj = hub.DiscoveredObject(object_type="analog-value", instance=9)
    assert obj.object_id == "analog-value,9"
