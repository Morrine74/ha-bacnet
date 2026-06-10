"""Service handlers for the BACnet integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    ATTR_ARRAY_INDEX,
    ATTR_COUNT,
    ATTR_DEVICE_ADDRESS,
    ATTR_OBJECT_ID,
    ATTR_PRIORITY,
    ATTR_PROPERTY,
    ATTR_SCHEDULE,
    ATTR_VALUE,
    DOMAIN,
    SERVICE_ACKNOWLEDGE_ALARM,
    SERVICE_READ_PROPERTY,
    SERVICE_READ_SCHEDULE,
    SERVICE_READ_TREND_LOG,
    SERVICE_WHO_IS,
    SERVICE_WRITE_PROPERTY,
    SERVICE_WRITE_SCHEDULE,
)
from .hub import BACnetHub, BACnetHubError, _coerce_log_datum

_LOGGER = logging.getLogger(__name__)

_READ_PROPERTY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ADDRESS): cv.string,
        vol.Required(ATTR_OBJECT_ID): cv.string,
        vol.Optional(ATTR_PROPERTY, default="present-value"): cv.string,
        vol.Optional(ATTR_ARRAY_INDEX): vol.Coerce(int),
    }
)

_WRITE_PROPERTY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ADDRESS): cv.string,
        vol.Required(ATTR_OBJECT_ID): cv.string,
        vol.Optional(ATTR_PROPERTY, default="present-value"): cv.string,
        vol.Required(ATTR_VALUE): vol.Any(cv.string, vol.Coerce(float), bool),
        vol.Optional(ATTR_PRIORITY): vol.All(int, vol.Range(min=1, max=16)),
        vol.Optional(ATTR_ARRAY_INDEX): vol.Coerce(int),
    }
)

_WHO_IS_SCHEMA = vol.Schema(
    {
        vol.Optional("low_limit"): vol.Coerce(int),
        vol.Optional("high_limit"): vol.Coerce(int),
        vol.Optional(ATTR_DEVICE_ADDRESS): cv.string,
    }
)

_SCHEDULE_READ_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ADDRESS): cv.string,
        vol.Required(ATTR_OBJECT_ID): cv.string,
    }
)

_SCHEDULE_WRITE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ADDRESS): cv.string,
        vol.Required(ATTR_OBJECT_ID): cv.string,
        vol.Required(ATTR_SCHEDULE): vol.Any(list, dict),
        vol.Optional("value_type"): vol.In(
            ["real", "unsigned", "integer", "boolean", "enumerated"]
        ),
    }
)

_TREND_LOG_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ADDRESS): cv.string,
        vol.Required(ATTR_OBJECT_ID): cv.string,
        vol.Optional(ATTR_COUNT, default=50): vol.All(int, vol.Range(min=1, max=1000)),
    }
)

_ACK_ALARM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ADDRESS): cv.string,
        vol.Required(ATTR_OBJECT_ID): cv.string,
        vol.Required("event_state"): cv.string,
    }
)


def _first_hub(hass: HomeAssistant) -> BACnetHub:
    """Return the first running BACnet hub, raising if none is available."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        data = getattr(entry, "runtime_data", None)
        if data and data.hub.started:
            return data.hub
    raise HomeAssistantError("No running BACnet hub is available")


def async_register_services(hass: HomeAssistant) -> None:
    """Register all BACnet services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_READ_PROPERTY):
        return

    async def _read_property(call: ServiceCall) -> ServiceResponse:
        hub = _first_hub(hass)
        try:
            value = await hub.async_read_property(
                call.data[ATTR_DEVICE_ADDRESS],
                call.data[ATTR_OBJECT_ID],
                call.data[ATTR_PROPERTY],
                call.data.get(ATTR_ARRAY_INDEX),
            )
        except BACnetHubError as err:
            raise HomeAssistantError(str(err)) from err
        return {"value": _jsonify(value)}

    async def _write_property(call: ServiceCall) -> None:
        hub = _first_hub(hass)
        try:
            await hub.async_write_property(
                call.data[ATTR_DEVICE_ADDRESS],
                call.data[ATTR_OBJECT_ID],
                call.data[ATTR_PROPERTY],
                call.data[ATTR_VALUE],
                priority=call.data.get(ATTR_PRIORITY),
                array_index=call.data.get(ATTR_ARRAY_INDEX),
            )
        except BACnetHubError as err:
            raise HomeAssistantError(str(err)) from err

    async def _who_is(call: ServiceCall) -> ServiceResponse:
        hub = _first_hub(hass)
        devices = await hub.async_who_is(
            low_limit=call.data.get("low_limit"),
            high_limit=call.data.get("high_limit"),
            address=call.data.get(ATTR_DEVICE_ADDRESS),
        )
        return {
            "devices": [
                {
                    "device_id": d.device_id,
                    "address": d.address,
                    "vendor_id": d.vendor_id,
                }
                for d in devices
            ]
        }

    async def _read_schedule(call: ServiceCall) -> ServiceResponse:
        hub = _first_hub(hass)
        try:
            return await hub.async_read_schedule(
                call.data[ATTR_DEVICE_ADDRESS], call.data[ATTR_OBJECT_ID]
            )
        except BACnetHubError as err:
            raise HomeAssistantError(str(err)) from err

    async def _write_schedule(call: ServiceCall) -> None:
        hub = _first_hub(hass)
        try:
            await hub.async_write_schedule(
                call.data[ATTR_DEVICE_ADDRESS],
                call.data[ATTR_OBJECT_ID],
                call.data[ATTR_SCHEDULE],
                value_type=call.data.get("value_type"),
            )
        except BACnetHubError as err:
            raise HomeAssistantError(str(err)) from err

    async def _read_trend_log(call: ServiceCall) -> ServiceResponse:
        hub = _first_hub(hass)
        try:
            records = await hub.async_read_trend_log(
                call.data[ATTR_DEVICE_ADDRESS],
                call.data[ATTR_OBJECT_ID],
                call.data[ATTR_COUNT],
            )
        except BACnetHubError as err:
            raise HomeAssistantError(str(err)) from err
        return {"records": records}

    async def _acknowledge_alarm(call: ServiceCall) -> None:
        hub = _first_hub(hass)
        try:
            await hub.async_acknowledge_alarm(
                call.data[ATTR_DEVICE_ADDRESS],
                call.data[ATTR_OBJECT_ID],
                event_state=call.data["event_state"],
            )
        except BACnetHubError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_PROPERTY,
        _read_property,
        schema=_READ_PROPERTY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_WRITE_PROPERTY, _write_property, schema=_WRITE_PROPERTY_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_WHO_IS,
        _who_is,
        schema=_WHO_IS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_SCHEDULE,
        _read_schedule,
        schema=_SCHEDULE_READ_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_WRITE_SCHEDULE, _write_schedule, schema=_SCHEDULE_WRITE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_TREND_LOG,
        _read_trend_log,
        schema=_TREND_LOG_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ACKNOWLEDGE_ALARM, _acknowledge_alarm, schema=_ACK_ALARM_SCHEMA
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove all BACnet services."""
    for service in (
        SERVICE_READ_PROPERTY,
        SERVICE_WRITE_PROPERTY,
        SERVICE_WHO_IS,
        SERVICE_READ_SCHEDULE,
        SERVICE_WRITE_SCHEDULE,
        SERVICE_READ_TREND_LOG,
        SERVICE_ACKNOWLEDGE_ALARM,
    ):
        hass.services.async_remove(DOMAIN, service)


def _jsonify(value: Any) -> Any:
    """Convert a bacpypes value into something JSON serialisable."""
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    # Shares the hub's coercion logic (AnyAtomic/Null unwrapping included).
    return _coerce_log_datum(value)
