"""The BACnet integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_BBMD_ADDRESS,
    CONF_BBMD_TTL,
    CONF_LOCAL_IP,
    CONF_LOCAL_OBJECT_ID,
    CONF_LOCAL_OBJECT_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_BBMD_TTL,
    DEFAULT_LOCAL_OBJECT_ID,
    DEFAULT_LOCAL_OBJECT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
)
from .coordinator import BACnetCoordinator
from .frontend import async_register_card
from .hub import BACnetHub, BACnetHubError
from .models import devices_from_options
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

type BACnetConfigEntry = ConfigEntry[BACnetRuntimeData]


@dataclass(slots=True)
class BACnetRuntimeData:
    """Objects shared for the lifetime of a config entry."""

    hub: BACnetHub
    coordinator: BACnetCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: BACnetConfigEntry
) -> bool:
    """Set up BACnet from a config entry."""
    local_ip = entry.data.get(CONF_LOCAL_IP) or entry.data.get(CONF_IP_ADDRESS)
    hub = BACnetHub(
        local_ip=local_ip,
        object_id=entry.data.get(CONF_LOCAL_OBJECT_ID, DEFAULT_LOCAL_OBJECT_ID),
        object_name=entry.data.get(
            CONF_LOCAL_OBJECT_NAME, DEFAULT_LOCAL_OBJECT_NAME
        ),
        bbmd_address=entry.data.get(CONF_BBMD_ADDRESS),
        bbmd_ttl=entry.data.get(CONF_BBMD_TTL, DEFAULT_BBMD_TTL),
    )

    try:
        await hub.async_start()
    except BACnetHubError as err:
        raise ConfigEntryNotReady(f"Unable to start BACnet hub: {err}") from err

    devices = devices_from_options(dict(entry.options))
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = BACnetCoordinator(hass, entry, hub, devices, scan_interval)
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_setup()

    entry.runtime_data = BACnetRuntimeData(hub=hub, coordinator=coordinator)

    _async_register_hub_device(hass, entry)
    _async_register_devices(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)

    # Serve and register the bundled Lovelace card so it is available without
    # the user having to add a dashboard resource manually.
    await async_register_card(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_register_hub_device(
    hass: HomeAssistant, entry: BACnetConfigEntry
) -> None:
    """Register the parent hub device that remote devices reference.

    Entities use ``via_device=(DOMAIN, entry_id)`` to nest each remote BACnet
    device under this hub. The hub device must exist in the registry first,
    otherwise Home Assistant logs a ``non existing via_device`` warning.
    """
    device_registry = dr.async_get(hass)
    local_ip = entry.data.get(CONF_LOCAL_IP) or entry.data.get(CONF_IP_ADDRESS)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=MANUFACTURER,
        name=entry.title or "BACnet",
        model="BACnet/IP interface",
        configuration_url=None,
        sw_version=str(local_ip) if local_ip else None,
    )


def _async_register_devices(
    hass: HomeAssistant, entry: BACnetConfigEntry, coordinator: BACnetCoordinator
) -> None:
    """Register controller and equipment sub-devices in the device registry.

    Entities reference their parent via ``via_device``; Home Assistant warns when
    a referenced device does not yet exist. We therefore pre-create every
    controller (``entry_id_<device_id>``) and, for Siemens points carrying a tree
    path, every equipment sub-device (``entry_id_<equipment_slug>``) nested under
    its controller and placed in the suggested area.
    """
    from .entity import point_grouping

    device_registry = dr.async_get(hass)
    seen_equipment: set[str] = set()

    for device in coordinator.devices:
        controller_identifier = (DOMAIN, f"{entry.entry_id}_{device.device_id}")
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={controller_identifier},
            manufacturer=MANUFACTURER,
            name=device.name,
            model=f"Device {device.device_id}",
            via_device=(DOMAIN, entry.entry_id),
        )
        for point in device.points:
            split, slug = point_grouping(device.device_id, point)
            if not slug or slug in seen_equipment:
                continue
            seen_equipment.add(slug)
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"{entry.entry_id}_{slug}")},
                manufacturer=MANUFACTURER,
                name=split.equipment,
                model="Équipement",
                suggested_area=split.area,
                via_device=controller_identifier,
            )


async def async_unload_entry(
    hass: HomeAssistant, entry: BACnetConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.runtime_data is not None:
        await entry.runtime_data.coordinator.async_shutdown()
        await entry.runtime_data.hub.async_stop()

    if not any(
        e.state.recoverable
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ):
        async_unregister_services(hass)

    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: BACnetConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
