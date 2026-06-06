"""Mapping of BACnet engineering units to Home Assistant unit strings.

bacpypes3 returns the ``units`` property as an enumeration whose string form is
the BACnet name (e.g. ``degrees-celsius``). Home Assistant expects its own unit
constants (e.g. ``°C``). This module translates the most common ones and, where
relevant, suggests a sensor device class.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)

# BACnet unit name -> (HA unit, optional device class)
_UNIT_MAP: dict[str, tuple[str | None, SensorDeviceClass | None]] = {
    "degrees-celsius": (UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "degrees-fahrenheit": (
        UnitOfTemperature.FAHRENHEIT,
        SensorDeviceClass.TEMPERATURE,
    ),
    "degrees-kelvin": (UnitOfTemperature.KELVIN, SensorDeviceClass.TEMPERATURE),
    "percent": (PERCENTAGE, None),
    "percent-relative-humidity": (PERCENTAGE, SensorDeviceClass.HUMIDITY),
    "parts-per-million": (
        CONCENTRATION_PARTS_PER_MILLION,
        SensorDeviceClass.CO2,
    ),
    "pascals": (UnitOfPressure.PA, SensorDeviceClass.PRESSURE),
    "kilopascals": (UnitOfPressure.KPA, SensorDeviceClass.PRESSURE),
    "bars": (UnitOfPressure.BAR, SensorDeviceClass.PRESSURE),
    "hectopascals": (UnitOfPressure.HPA, SensorDeviceClass.PRESSURE),
    "watts": (UnitOfPower.WATT, SensorDeviceClass.POWER),
    "kilowatts": (UnitOfPower.KILO_WATT, SensorDeviceClass.POWER),
    "watt-hours": (UnitOfEnergy.WATT_HOUR, SensorDeviceClass.ENERGY),
    "kilowatt-hours": (UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY),
    "volts": (UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
    "millivolts": (
        UnitOfElectricPotential.MILLIVOLT,
        SensorDeviceClass.VOLTAGE,
    ),
    "amperes": (UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
    "milliamperes": (
        UnitOfElectricCurrent.MILLIAMPERE,
        SensorDeviceClass.CURRENT,
    ),
    "cubic-meters-per-hour": (
        UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        None,
    ),
    "liters-per-second": (UnitOfVolumeFlowRate.LITERS_PER_MINUTE, None),
    "revolutions-per-minute": (REVOLUTIONS_PER_MINUTE, None),
    "seconds": (UnitOfTime.SECONDS, None),
    "minutes": (UnitOfTime.MINUTES, None),
    "hours": (UnitOfTime.HOURS, None),
    "no-units": (None, None),
}


def map_unit(bacnet_unit: str | None) -> tuple[str | None, SensorDeviceClass | None]:
    """Translate a BACnet unit name to (HA unit, device class).

    Unknown units are returned verbatim (so the user still sees something) with
    no device class.
    """
    if not bacnet_unit:
        return (None, None)
    key = str(bacnet_unit).strip().lower()
    if key in _UNIT_MAP:
        return _UNIT_MAP[key]
    # Unknown but non-empty: show the raw BACnet name as the unit label.
    if key in ("none", ""):
        return (None, None)
    return (str(bacnet_unit), None)
