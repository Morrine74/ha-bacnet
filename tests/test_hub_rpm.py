"""Tests for batched present-value reads (ReadPropertyMultiple)."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("bacpypes3")

from bacnet import hub


class _FakeApp:
    """Minimal stand-in for a bacpypes3 Application.

    ``responses`` is consumed one element per read_property_multiple call;
    an element that is an exception instance is raised instead of returned.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[list] = []

    async def read_property_multiple(self, address, parameters):
        self.calls.append(list(parameters))
        result = self._responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _hub_with_app(app):
    instance = hub.BACnetHub(
        local_ip="192.168.0.10/24", object_id=1, object_name="test"
    )
    instance._app = app
    instance._started = True
    return instance


def _read(instance, object_ids, **kwargs):
    return asyncio.run(
        instance.async_read_present_values("192.168.0.20", object_ids, **kwargs)
    )


def test_rpm_maps_values_back_by_requested_id():
    # The device answers with camelCase type names; values must still be keyed
    # by the exact object ids that were requested.
    app = _FakeApp(
        [
            [
                (("analogInput", 1), "present-value", None, 21.5),
                (("binaryValue", 4), "present-value", None, 1),
            ]
        ]
    )
    values = _read(_hub_with_app(app), ["analog-input,1", "binary-value,4"])
    assert values == {"analog-input,1": 21.5, "binary-value,4": 1}
    # The request uses the flat [objid, [props], ...] form bacpypes3 expects.
    assert app.calls == [
        ["analog-input,1", ["present-value"], "binary-value,4", ["present-value"]]
    ]


def test_rpm_skips_per_object_errors():
    from bacpypes3.basetypes import ErrorType

    error = ErrorType(errorClass="object", errorCode="unknown-object")
    app = _FakeApp(
        [
            [
                (("analog-input", 1), "present-value", None, 21.5),
                (("analog-input", 2), "present-value", None, error),
                (("analog-input", 3), "present-value", None, None),
            ]
        ]
    )
    values = _read(
        _hub_with_app(app), ["analog-input,1", "analog-input,2", "analog-input,3"]
    )
    # Failed objects are absent, not None: the caller counts them as misses.
    assert values == {"analog-input,1": 21.5}


def test_rpm_device_reject_raises_service_unsupported():
    from bacpypes3.apdu import RejectPDU, RejectReason

    # bacpypes3 *returns* the reject rather than raising it.
    app = _FakeApp([RejectPDU(reason=RejectReason.unrecognizedService)])
    with pytest.raises(hub.BACnetServiceUnsupported):
        _read(_hub_with_app(app), ["analog-input,1", "analog-input,2"])


def test_rpm_chunks_requests():
    app = _FakeApp(
        [
            [
                (("analog-input", 1), "present-value", None, 1.0),
                (("analog-input", 2), "present-value", None, 2.0),
            ],
            [(("analog-input", 3), "present-value", None, 3.0)],
        ]
    )
    values = _read(
        _hub_with_app(app),
        ["analog-input,1", "analog-input,2", "analog-input,3"],
        chunk_size=2,
    )
    assert len(app.calls) == 2
    assert values == {
        "analog-input,1": 1.0,
        "analog-input,2": 2.0,
        "analog-input,3": 3.0,
    }


def test_rpm_timeout_aborts_remaining_chunks_and_returns_partial():
    app = _FakeApp(
        [
            [(("analog-input", 1), "present-value", None, 1.0)],
            asyncio.TimeoutError(),
        ]
    )
    values = _read(
        _hub_with_app(app),
        ["analog-input,1", "analog-input,2", "analog-input,3"],
        chunk_size=1,
    )
    # Chunk 3 is never attempted once chunk 2 timed out.
    assert len(app.calls) == 2
    assert values == {"analog-input,1": 1.0}


def test_rpm_undecodable_response_raises():
    app = _FakeApp([None])
    with pytest.raises(hub.BACnetHubError):
        _read(_hub_with_app(app), ["analog-input,1"])


def test_canonical_type_collapses_variants():
    assert hub._canonical_type("analog-input") == "analoginput"
    assert hub._canonical_type("analogInput") == "analoginput"
    assert hub._canonical_type("analog_input") == "analoginput"
