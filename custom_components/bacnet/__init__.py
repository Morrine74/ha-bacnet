"""The BACnet integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

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
    PLATFORMS,
)
from .coordinator import BACnetCoordinator
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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


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
