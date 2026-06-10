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


class _AnyAtomic:
    """Stand-in for bacpypes AnyAtomic exposing get_value()."""

    def __init__(self, value):
        self._value = value

    def get_value(self):
        return self._value


def test_coerce_log_datum_unwraps_get_value():
    assert hub._coerce_log_datum(_AnyAtomic(21.5)) == 21.5
    # Nested: get_value returns another wrapper.
    assert hub._coerce_log_datum(_AnyAtomic(_Wrapper(3))) == 3


def test_coerce_log_datum_null_to_none():
    # A BACnet Null (schedule "no action" entry) becomes None, not a string.
    null = type("Null", (), {})()
    assert hub._coerce_log_datum(null) is None
    assert hub._coerce_log_datum(_AnyAtomic(null)) is None


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


class _NamedPrimitive:
    """Stand-in whose class name mimics a bacpypes primitive type."""


class Real(_NamedPrimitive):
    pass


class Unsigned(_NamedPrimitive):
    pass


class Enumerated(_NamedPrimitive):
    pass


def test_bacpypes_type_name_maps_by_class():
    assert hub._bacpypes_type_name(Real()) == "real"
    assert hub._bacpypes_type_name(Unsigned()) == "unsigned"
    assert hub._bacpypes_type_name(Enumerated()) == "enumerated"
    assert hub._bacpypes_type_name(None) is None


def test_normalize_time_string_pads_components():
    assert hub._normalize_time_string("8:0") == "08:00:00"
    assert hub._normalize_time_string("08:30") == "08:30:00"
    assert hub._normalize_time_string("23:15:45") == "23:15:45"


def test_normalize_time_string_fractional_seconds():
    # str() of a bacpypes Time includes hundredths; round-tripping a read
    # schedule back into a write must not crash on them.
    assert hub._normalize_time_string("08:00:00.00") == "08:00:00"
    assert hub._normalize_time_string("06:30:15.50") == "06:30:15"


def test_normalize_time_string_invalid_raises():
    import pytest

    with pytest.raises(hub.BACnetHubError):
        hub._normalize_time_string("garbage")


def test_infer_value_type_defaults_to_real_when_empty():
    assert hub._infer_value_type_from_weekly(None) == "real"
    assert hub._infer_value_type_from_weekly([[], [], []]) == "real"


class _DayWithValue:
    def __init__(self, value):
        self.daySchedule = [type("TV", (), {"value": value})()]


def test_infer_value_type_from_first_typed_value():
    assert hub._infer_value_type_from_weekly([_DayWithValue(Unsigned())]) == (
        "unsigned"
    )


def test_build_weekly_schedule_round_trip_with_real_bacpypes():
    import pytest

    pytest.importorskip("bacpypes3")
    weekly = hub._build_weekly_schedule(
        [[{"time": "06:00", "value": 1}, {"time": "18:00", "value": None}]],
        "unsigned",
    )
    serialized = hub._serialize_weekly_schedule(weekly)
    assert len(serialized) == 7
    assert serialized[0][0]["value"] == 1
    # Null ("no action") entries come back as None.
    assert serialized[0][1]["value"] is None
    # The serialized form (times include hundredths) can be written back as-is.
    rebuilt = hub._build_weekly_schedule(serialized, "unsigned")
    assert hub._serialize_weekly_schedule(rebuilt) == serialized


def test_object_ids_to_str_handles_tuples_and_strings():
    assert hub._object_ids_to_str(
        [("analog-input", 1), ("binary-value", 4)]
    ) == ["analog-input,1", "binary-value,4"]
    # Non-tuple items fall back to their string form.
    assert hub._object_ids_to_str(["device,99"]) == ["device,99"]
    assert hub._object_ids_to_str(None) == []

