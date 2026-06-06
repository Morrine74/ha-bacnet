"""Constants for the BACnet integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "bacnet"

# Config entry / options keys
CONF_LOCAL_IP: Final = "local_ip"
CONF_LOCAL_OBJECT_ID: Final = "local_object_id"
CONF_LOCAL_OBJECT_NAME: Final = "local_object_name"
CONF_BBMD_ADDRESS: Final = "bbmd_address"
CONF_BBMD_TTL: Final = "bbmd_ttl"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_DEVICES: Final = "devices"
CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_ADDRESS: Final = "device_address"
CONF_DEVICE_NAME: Final = "device_name"
CONF_OBJECTS: Final = "objects"
CONF_OBJECT_TYPE: Final = "object_type"
CONF_OBJECT_INSTANCE: Final = "object_instance"
CONF_OBJECT_NAME: Final = "object_name"
CONF_USE_COV: Final = "use_cov"
CONF_COV_LIFETIME: Final = "cov_lifetime"
CONF_WRITE_PRIORITY: Final = "write_priority"
CONF_UNITS: Final = "units"
CONF_DESCRIPTION: Final = "description"

# Defaults
DEFAULT_LOCAL_OBJECT_ID: Final = 599
DEFAULT_LOCAL_OBJECT_NAME: Final = "HomeAssistant"
DEFAULT_SCAN_INTERVAL: Final = 60
DEFAULT_COV_LIFETIME: Final = 300
DEFAULT_WRITE_PRIORITY: Final = 16
DEFAULT_BBMD_TTL: Final = 30
DEFAULT_DISCOVERY_TIMEOUT: Final = 5

MIN_SCAN_INTERVAL: Final = 5
MIN_WRITE_PRIORITY: Final = 1
MAX_WRITE_PRIORITY: Final = 16

UPDATE_INTERVAL: Final = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

# BACnet present-value property identifier
PROP_PRESENT_VALUE: Final = "present-value"
PROP_OBJECT_NAME: Final = "object-name"
PROP_DESCRIPTION: Final = "description"
PROP_UNITS: Final = "units"
PROP_STATUS_FLAGS: Final = "status-flags"
PROP_OUT_OF_SERVICE: Final = "out-of-service"
PROP_RELIABILITY: Final = "reliability"
PROP_PRIORITY_ARRAY: Final = "priority-array"
PROP_LOG_BUFFER: Final = "log-buffer"
PROP_WEEKLY_SCHEDULE: Final = "weekly-schedule"
PROP_EXCEPTION_SCHEDULE: Final = "exception-schedule"
PROP_PRESENT_VALUE_SCHEDULE: Final = "present-value"

# Platforms
PLATFORMS: Final = [
    "sensor",
    "binary_sensor",
    "number",
    "switch",
    "select",
]

# Object type groups -> HA platform mapping
# Analog -> number (writable) / sensor (read-only)
ANALOG_INPUT: Final = "analog-input"
ANALOG_OUTPUT: Final = "analog-output"
ANALOG_VALUE: Final = "analog-value"
BINARY_INPUT: Final = "binary-input"
BINARY_OUTPUT: Final = "binary-output"
BINARY_VALUE: Final = "binary-value"
MULTI_STATE_INPUT: Final = "multi-state-input"
MULTI_STATE_OUTPUT: Final = "multi-state-output"
MULTI_STATE_VALUE: Final = "multi-state-value"
TREND_LOG: Final = "trend-log"
SCHEDULE: Final = "schedule"

READ_ONLY_TYPES: Final = frozenset(
    {ANALOG_INPUT, BINARY_INPUT, MULTI_STATE_INPUT}
)

ANALOG_TYPES: Final = frozenset({ANALOG_INPUT, ANALOG_OUTPUT, ANALOG_VALUE})
BINARY_TYPES: Final = frozenset({BINARY_INPUT, BINARY_OUTPUT, BINARY_VALUE})
MULTI_STATE_TYPES: Final = frozenset(
    {MULTI_STATE_INPUT, MULTI_STATE_OUTPUT, MULTI_STATE_VALUE}
)
WRITABLE_TYPES: Final = frozenset(
    {
        ANALOG_OUTPUT,
        ANALOG_VALUE,
        BINARY_OUTPUT,
        BINARY_VALUE,
        MULTI_STATE_OUTPUT,
        MULTI_STATE_VALUE,
    }
)

# Services
SERVICE_READ_PROPERTY: Final = "read_property"
SERVICE_WRITE_PROPERTY: Final = "write_property"
SERVICE_WHO_IS: Final = "who_is"
SERVICE_READ_SCHEDULE: Final = "read_schedule"
SERVICE_WRITE_SCHEDULE: Final = "write_schedule"
SERVICE_READ_TREND_LOG: Final = "read_trend_log"
SERVICE_ACKNOWLEDGE_ALARM: Final = "acknowledge_alarm"

ATTR_DEVICE_ADDRESS: Final = "device_address"
ATTR_OBJECT_ID: Final = "object_id"
ATTR_PROPERTY: Final = "property"
ATTR_VALUE: Final = "value"
ATTR_PRIORITY: Final = "priority"
ATTR_ARRAY_INDEX: Final = "array_index"
ATTR_SCHEDULE: Final = "schedule"
ATTR_COUNT: Final = "count"

# Dispatcher signals
SIGNAL_COV_UPDATE: Final = "bacnet_cov_update_{entry_id}"
SIGNAL_ALARM_EVENT: Final = "bacnet_alarm_event_{entry_id}"

MANUFACTURER: Final = "BACnet"
