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


def test_infer_value_type_none_when_nothing_is_typed():
    assert hub._infer_value_type_from_weekly(None) is None
    assert hub._infer_value_type_from_weekly([[], [], []]) is None


def test_bacpypes_type_name_unwraps_any_atomic():
    """Schedule values arrive wrapped in AnyAtomic: the type is inside."""
    import pytest

    pytest.importorskip("bacpypes3")
    from bacpypes3.basetypes import BinaryPV
    from bacpypes3.constructeddata import AnyAtomic
    from bacpypes3.primitivedata import Null, Real as BReal, Unsigned as BUnsigned

    assert hub._bacpypes_type_name(AnyAtomic(BUnsigned(2))) == "unsigned"
    assert hub._bacpypes_type_name(AnyAtomic(BReal(21.5))) == "real"
    # An enumeration subclass is still an Enumerated on the wire.
    assert hub._bacpypes_type_name(AnyAtomic(BinaryPV("active"))) == "enumerated"
    assert hub._bacpypes_type_name(BinaryPV("active")) == "enumerated"
    # Null ("no action") says nothing about the datatype.
    assert hub._bacpypes_type_name(AnyAtomic(Null(()))) is None


def test_schedule_value_type_resolution_order():
    no_texts = {"state_texts": None, "active_text": None, "inactive_text": None}
    week = [_DayWithValue(Unsigned())]
    assert hub._schedule_value_type(Real(), week, None, no_texts) == "real"
    assert hub._schedule_value_type(None, week, Real(), no_texts) == "unsigned"
    assert hub._schedule_value_type(None, None, Enumerated(), no_texts) == "enumerated"
    # Nothing typed on the schedule itself: the commanded object decides.
    assert (
        hub._schedule_value_type(None, [], None, {**no_texts, "state_texts": ["A"]})
        == "unsigned"
    )
    assert (
        hub._schedule_value_type(None, [], None, {**no_texts, "active_text": "On"})
        == "enumerated"
    )
    assert hub._schedule_value_type(None, [], None, no_texts) == "real"


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


def test_ensure_cidr_adds_default_prefix():
    # A bare host gets /24 (otherwise bacpypes3 cannot broadcast Who-Is).
    assert hub._ensure_cidr("192.168.0.216") == "192.168.0.216/24"
    # An explicit prefix is preserved.
    assert hub._ensure_cidr("192.168.0.216/16") == "192.168.0.216/16"
    # Surrounding whitespace is trimmed.
    assert hub._ensure_cidr("  10.0.0.5  ") == "10.0.0.5/24"
    # A port without a prefix keeps the port after the inserted mask.
    assert hub._ensure_cidr("192.168.0.216:47808") == "192.168.0.216/24:47808"
    # Empty stays empty (validated/handled elsewhere).
    assert hub._ensure_cidr("") == ""


def test_decode_tree_path_from_list():
    # The usual case: an ArrayOf(CharacterString) arrives as a list-like.
    assert hub._decode_tree_path(["Gymnase", "Locaux Techniques", "Chaudière"]) == [
        "Gymnase",
        "Locaux Techniques",
        "Chaudière",
    ]
    # Blank / whitespace-only segments are dropped.
    assert hub._decode_tree_path(["A", "  ", "", "B"]) == ["A", "B"]


def test_decode_tree_path_empty_and_none():
    assert hub._decode_tree_path(None) is None
    assert hub._decode_tree_path([]) is None
    assert hub._decode_tree_path(["", "  "]) is None


def test_decode_tree_path_string_fallback():
    # Defensive: a single apostrophe-delimited string still splits.
    assert hub._decode_tree_path("Gym'LT'HGen") == ["Gym", "LT", "HGen"]


def test_node_type_token_extracts_enum_name():
    assert hub._node_type_token("<NodeType: system>") == "system"
    assert hub._node_type_token("system") == "system"
    assert hub._node_type_token("<NodeType: functional>") == "functional"
    assert hub._node_type_token("") == ""


def test_object_ids_to_str_handles_tuples_and_strings():
    assert hub._object_ids_to_str(
        [("analog-input", 1), ("binary-value", 4)]
    ) == ["analog-input,1", "binary-value,4"]
    # Non-tuple items fall back to their string form.
    assert hub._object_ids_to_str(["device,99"]) == ["device,99"]
    assert hub._object_ids_to_str(None) == []



class _MemberRef:
    """Stand-in for a bacpypes DeviceObjectPropertyReference."""

    def __init__(self, object_identifier, device_identifier=None):
        self.objectIdentifier = object_identifier
        self.deviceIdentifier = device_identifier


def test_schedule_member_target_local_reference():
    ref = _MemberRef(("multi-state-value", 12))
    assert hub._schedule_member_target(ref) == "multi-state-value,12"


def test_schedule_member_target_accepts_own_device_reference():
    # Siemens fills deviceIdentifier with the controller's own instance.
    own = _MemberRef(("multi-state-value", 12), device_identifier=("device", 2000))
    assert hub._schedule_member_target(own, 2000) == "multi-state-value,12"
    # Unknown device id: still tried locally (a bad read is just skipped).
    assert hub._schedule_member_target(own) == "multi-state-value,12"


def test_schedule_member_target_skips_remote_and_malformed():
    remote = _MemberRef(("binary-value", 3), device_identifier=("device", 99))
    assert hub._schedule_member_target(remote, 2000) is None
    broken = _MemberRef(("binary-value", 3), device_identifier=("device",))
    assert hub._schedule_member_target(broken, 2000) is None
    assert hub._schedule_member_target(_MemberRef(None)) is None
    assert hub._schedule_member_target(_MemberRef(("analog-value",))) is None
    assert hub._schedule_member_target(object()) is None


def _hub_with_reads(reads):
    """Build a non-started hub whose optional reads answer from a dict."""
    instance = hub.BACnetHub(
        local_ip="192.168.0.10/24", object_id=1, object_name="test"
    )

    async def _fake_read(address, object_id, prop):
        return reads.get((object_id, prop))

    instance._async_read_optional = _fake_read
    return instance


def test_schedule_member_texts_from_multistate_member():
    import asyncio

    instance = _hub_with_reads(
        {
            ("schedule,1", "list-of-object-property-references"): [
                _MemberRef(("multi-state-value", 5))
            ],
            ("multi-state-value,5", "state-text"): ["Confort", "Réduit", "Hors gel"],
        }
    )
    texts = asyncio.run(
        instance._async_schedule_member_texts("192.168.0.20", "schedule,1")
    )
    assert texts["state_texts"] == ["Confort", "Réduit", "Hors gel"]
    assert texts["active_text"] is None


def test_schedule_member_texts_from_binary_member():
    import asyncio

    instance = _hub_with_reads(
        {
            ("schedule,2", "list-of-object-property-references"): [
                # A remote member is skipped; the local binary supplies texts.
                _MemberRef(("binary-value", 1), device_identifier=("device", 9)),
                _MemberRef(("binary-value", 2)),
            ],
            ("binary-value,2", "active-text"): "Marche",
            ("binary-value,2", "inactive-text"): "Arrêt",
        }
    )
    texts = asyncio.run(
        instance._async_schedule_member_texts(
            "192.168.0.20", "schedule,2", device_id=2000
        )
    )
    assert texts["state_texts"] is None
    assert texts["active_text"] == "Marche"
    assert texts["inactive_text"] == "Arrêt"


def test_schedule_member_texts_siemens_self_referencing_member():
    """Siemens references carry the controller's own device id: still local."""
    import asyncio

    instance = _hub_with_reads(
        {
            ("schedule,4", "list-of-object-property-references"): [
                _MemberRef(
                    ("multi-state-value", 8), device_identifier=("device", 2000)
                )
            ],
            ("multi-state-value,8", "state-text"): ["Confort", "Réduit"],
        }
    )
    texts = asyncio.run(
        instance._async_schedule_member_texts(
            "192.168.0.20", "schedule,4", device_id=2000
        )
    )
    assert texts["state_texts"] == ["Confort", "Réduit"]


def test_schedule_member_texts_none_when_analog_member():
    import asyncio

    instance = _hub_with_reads(
        {
            ("schedule,3", "list-of-object-property-references"): [
                _MemberRef(("analog-value", 7))
            ],
        }
    )
    texts = asyncio.run(
        instance._async_schedule_member_texts("192.168.0.20", "schedule,3")
    )
    assert texts == {
        "state_texts": None,
        "active_text": None,
        "inactive_text": None,
    }


def test_schedule_member_texts_siemens_sibling_without_members():
    """No member reference: texts come from the PrOpMod next to the schedule."""
    import asyncio

    instance = _hub_with_reads(
        {
            ("schedule,6", "list-of-object-property-references"): [],
            ("schedule,6", "object-name"): "EREP'R+1'LT_CTA'Ahu'Sched",
            ("multi-state-value,16", "state-text"): ["Arrêt", "Marche"],
        }
    )
    asked = []

    async def _fake_find(address, object_name):
        asked.append(object_name)
        return "multi-state-value,16"

    instance._async_find_object_by_name = _fake_find
    texts = asyncio.run(
        instance._async_schedule_member_texts("192.168.0.182", "schedule,6")
    )
    assert asked == ["EREP'R+1'LT_CTA'Ahu'PrOpMod"]
    assert texts["state_texts"] == ["Arrêt", "Marche"]


def test_write_schedule_uses_the_device_type_over_a_wrong_hint():
    """A multi-state schedule is written Unsigned whatever the caller asked."""
    import asyncio

    import pytest

    pytest.importorskip("bacpypes3")
    from bacpypes3.constructeddata import AnyAtomic
    from bacpypes3.primitivedata import Unsigned as BUnsigned

    instance = _hub_with_reads(
        {("schedule,6", "schedule-default"): AnyAtomic(BUnsigned(1))}
    )
    written = {}

    async def _fake_write(address, object_id, prop, value, **kwargs):
        written["value"] = value

    instance.async_write_property = _fake_write
    week = [[{"time": "06:00", "value": 2}, {"time": "19:00", "value": None}]]
    asyncio.run(
        instance.async_write_schedule(
            "192.168.0.182", "schedule,6", week, value_type="enumerated"
        )
    )
    entries = written["value"][0].daySchedule
    # TimeValue wraps its value in AnyAtomic: the wire type is inside.
    assert type(entries[0].value.get_value()).__name__ == "Unsigned"
    assert type(entries[1].value.get_value()).__name__ == "Null"
    assert len(written["value"]) == 7


def test_structured_view_types_collects_node_types_and_system_paths():
    import asyncio

    instance = _hub_with_reads(
        {
            ("structured-view,1", "object-name"): "Gym'LT'HGen",
            ("structured-view,1", "node-type"): "<NodeType: system>",
            ("structured-view,2", "object-name"): "Gym'LT'HGen'Bo",
            ("structured-view,2", "node-type"): "functional",
            # node-type unreadable: skipped entirely.
            ("structured-view,3", "object-name"): "Gym'X",
        }
    )
    paths = {
        "structured-view,1": ["Gymnase", "LT", "Production de chaleur"],
    }

    async def _fake_tree_path(address, object_id):
        return paths.get(object_id)

    instance.async_read_tree_path = _fake_tree_path

    node_types, system_paths = asyncio.run(
        instance._async_structured_view_types(
            "192.168.0.20",
            ["structured-view,1", "structured-view,2", "structured-view,3",
             "analog-input,7"],
        )
    )
    assert node_types == {"Gym'LT'HGen": "system", "Gym'LT'HGen'Bo": "functional"}
    # Only system nodes contribute a path (for the prefix-match fallback).
    assert system_paths == [["Gymnase", "LT", "Production de chaleur"]]
