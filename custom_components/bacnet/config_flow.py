"""Config and options flow for the BACnet integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    ANALOG_TYPES,
    BINARY_TYPES,
    CONF_BBMD_ADDRESS,
    CONF_COV_LIFETIME,
    CONF_DEVICES,
    CONF_LOCAL_IP,
    CONF_LOCAL_OBJECT_ID,
    CONF_LOCAL_OBJECT_NAME,
    CONF_SCAN_INTERVAL,
    CONF_USE_COV,
    CONF_WRITE_PRIORITY,
    DEFAULT_COV_LIFETIME,
    DEFAULT_DISCOVERY_TIMEOUT,
    DEFAULT_LOCAL_OBJECT_ID,
    DEFAULT_LOCAL_OBJECT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WRITE_PRIORITY,
    DOMAIN,
    MAX_WRITE_PRIORITY,
    MIN_SCAN_INTERVAL,
    MIN_WRITE_PRIORITY,
    MULTI_STATE_TYPES,
)
from .hub import BACnetHub, BACnetHubError
from .models import DeviceConfig, PointConfig, devices_from_options

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_LOCAL_IP, default=defaults.get(CONF_LOCAL_IP, "")
            ): str,
            vol.Optional(
                CONF_LOCAL_OBJECT_ID,
                default=defaults.get(CONF_LOCAL_OBJECT_ID, DEFAULT_LOCAL_OBJECT_ID),
            ): vol.All(int, vol.Range(min=0, max=4194302)),
            vol.Optional(
                CONF_LOCAL_OBJECT_NAME,
                default=defaults.get(
                    CONF_LOCAL_OBJECT_NAME, DEFAULT_LOCAL_OBJECT_NAME
                ),
            ): str,
            vol.Optional(
                CONF_BBMD_ADDRESS, default=defaults.get(CONF_BBMD_ADDRESS, "")
            ): str,
        }
    )


class BACnetConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial BACnet configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect local interface settings and validate the stack starts."""
        errors: dict[str, str] = {}
        if user_input is not None:
            local_ip = user_input[CONF_LOCAL_IP].strip()
            await self.async_set_unique_id(f"{local_ip}_{user_input[CONF_LOCAL_OBJECT_ID]}")
            self._abort_if_unique_id_configured()

            bbmd = user_input.get(CONF_BBMD_ADDRESS, "").strip() or None
            hub = BACnetHub(
                local_ip=local_ip,
                object_id=user_input[CONF_LOCAL_OBJECT_ID],
                object_name=user_input[CONF_LOCAL_OBJECT_NAME],
                bbmd_address=bbmd,
            )
            try:
                await hub.async_start()
            except BACnetHubError:
                errors["base"] = "cannot_connect"
            finally:
                await hub.async_stop()

            if not errors:
                data = {
                    CONF_LOCAL_IP: local_ip,
                    CONF_LOCAL_OBJECT_ID: user_input[CONF_LOCAL_OBJECT_ID],
                    CONF_LOCAL_OBJECT_NAME: user_input[CONF_LOCAL_OBJECT_NAME],
                }
                if bbmd:
                    data[CONF_BBMD_ADDRESS] = bbmd
                return self.async_create_entry(
                    title=f"BACnet ({local_ip})",
                    data=data,
                    options={CONF_DEVICES: [], CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )

        return self.async_show_form(
            step_id="user", data_schema=_user_schema(user_input), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "BACnetOptionsFlow":
        """Return the options flow handler."""
        return BACnetOptionsFlow(config_entry)


class BACnetOptionsFlow(OptionsFlow):
    """Manage devices, points and polling options after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Store the entry and load current device configuration."""
        self._entry = config_entry
        self._devices: list[DeviceConfig] = devices_from_options(
            dict(config_entry.options)
        )
        self._discovered: list[Any] = []
        self._selected_device: DeviceConfig | None = None
        self._discovered_objects: list[Any] = []

    def _hub(self) -> BACnetHub | None:
        data = getattr(self._entry, "runtime_data", None)
        return data.hub if data else None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the top-level options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "discover",
                "add_by_ip",
                "settings",
                "remove_device",
            ],
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the polling interval."""
        if user_input is not None:
            return self._save(
                {CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]}
            )
        current = self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        int, vol.Range(min=MIN_SCAN_INTERVAL)
                    )
                }
            ),
        )

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run a Who-Is and let the user pick a device to add."""
        hub = self._hub()
        if hub is None or not hub.started:
            return self.async_abort(reason="not_loaded")

        errors: dict[str, str] = {}
        if user_input is not None:
            selection = user_input["device"]
            device_id, address = selection.split("@", 1)
            self._selected_device = DeviceConfig(
                device_id=int(device_id),
                address=address,
                name=f"BACnet Device {device_id}",
            )
            return await self.async_step_select_points()

        try:
            self._discovered = await hub.async_who_is(
                timeout=DEFAULT_DISCOVERY_TIMEOUT
            )
        except BACnetHubError:
            errors["base"] = "discovery_failed"
            self._discovered = []

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        options = {
            f"{d.device_id}@{d.address}": f"Device {d.device_id} ({d.address})"
            for d in self._discovered
        }
        return self.async_show_form(
            step_id="discover",
            data_schema=vol.Schema({vol.Required("device"): vol.In(options)}),
            errors=errors,
        )

    async def async_step_add_by_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a device by its IP address using a directed (unicast) Who-Is.

        This bypasses broadcast issues (Docker/VM networking, multiple
        interfaces, routed segments): the device is contacted directly, exactly
        like a directed discovery in YABE.
        """
        hub = self._hub()
        if hub is None or not hub.started:
            return self.async_abort(reason="not_loaded")

        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input["address"].strip()
            manual_id = user_input.get("device_id")

            device_id: int | None = (
                int(manual_id) if manual_id not in (None, "") else None
            )
            try:
                # Directed Who-Is first; fall back to reading the device id.
                found = await hub.async_who_is(
                    address=address, timeout=DEFAULT_DISCOVERY_TIMEOUT
                )
                if found:
                    device_id = found[0].device_id
                    address = found[0].address
                elif device_id is None:
                    device_id = await hub.async_read_device_instance(address)
            except BACnetHubError:
                errors["base"] = "discovery_failed"

            if not errors and device_id is None:
                errors["base"] = "device_not_found"

            if not errors:
                self._selected_device = DeviceConfig(
                    device_id=int(device_id),
                    address=address,
                    name=f"BACnet Device {device_id}",
                )
                return await self.async_step_select_points()

        return self.async_show_form(
            step_id="add_by_ip",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "address",
                        default=(user_input or {}).get("address", ""),
                    ): str,
                    vol.Optional("device_id"): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=4194302)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select_points(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover objects on the selected device and add chosen points."""
        hub = self._hub()
        assert hub is not None and self._selected_device is not None
        device = self._selected_device

        if user_input is not None:
            chosen = user_input.get("points", [])
            use_cov = user_input.get(CONF_USE_COV, False)
            priority = user_input.get(CONF_WRITE_PRIORITY, DEFAULT_WRITE_PRIORITY)
            lookup = {o.object_id: o for o in self._discovered_objects}
            points: list[PointConfig] = []
            for object_id in chosen:
                obj = lookup.get(object_id)
                if not obj:
                    continue
                points.append(
                    PointConfig(
                        object_type=obj.object_type,
                        instance=obj.instance,
                        name=obj.name or object_id,
                        use_cov=use_cov,
                        cov_lifetime=DEFAULT_COV_LIFETIME,
                        write_priority=priority,
                        units=obj.units,
                        description=obj.description,
                    )
                )
            device.points = points
            # Replace any previous configuration for this device.
            self._devices = [
                d for d in self._devices if d.device_id != device.device_id
            ]
            self._devices.append(device)
            return self._save(
                {CONF_DEVICES: [d.to_dict() for d in self._devices]}
            )

        try:
            self._discovered_objects = await hub.async_discover_objects(
                device.address, device.device_id
            )
        except BACnetHubError as err:
            _LOGGER.warning(
                "Object discovery failed for %s (%s): %s",
                device.name,
                device.address,
                err,
            )
            return self.async_abort(reason="discovery_failed")
        except Exception as err:  # noqa: BLE001 - surface as clean abort
            _LOGGER.exception(
                "Unexpected error discovering objects on %s (%s): %s",
                device.name,
                device.address,
                err,
            )
            return self.async_abort(reason="discovery_failed")

        if not self._discovered_objects:
            return self.async_abort(reason="no_objects_found")

        # Only objects that map to a Home Assistant entity are offered here.
        # Other types (schedule, trend-log, file, loop, structured-view,
        # notification-class, proprietary types, ...) are accessed through
        # services and the Lovelace card instead.
        mappable = ANALOG_TYPES | BINARY_TYPES | MULTI_STATE_TYPES
        options = {
            o.object_id: f"{o.name or o.object_id} [{o.object_type}]"
            for o in self._discovered_objects
            if o.object_type in mappable
        }
        if not options:
            return self.async_abort(reason="no_objects_found")
        return self.async_show_form(
            step_id="select_points",
            data_schema=vol.Schema(
                {
                    vol.Required("points", default=[]): cv.multi_select(options),
                    vol.Optional(CONF_USE_COV, default=False): bool,
                    vol.Optional(
                        CONF_WRITE_PRIORITY, default=DEFAULT_WRITE_PRIORITY
                    ): vol.All(
                        int,
                        vol.Range(min=MIN_WRITE_PRIORITY, max=MAX_WRITE_PRIORITY),
                    ),
                }
            ),
            description_placeholders={
                "device": f"{device.name} ({device.address})"
            },
        )

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a configured device and its points."""
        if not self._devices:
            return self.async_abort(reason="no_devices_configured")

        if user_input is not None:
            remove_id = int(user_input["device"])
            self._devices = [
                d for d in self._devices if d.device_id != remove_id
            ]
            return self._save(
                {CONF_DEVICES: [d.to_dict() for d in self._devices]}
            )

        options = {
            str(d.device_id): f"{d.name} ({d.address})" for d in self._devices
        }
        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema({vol.Required("device"): vol.In(options)}),
        )

    def _save(self, partial: dict[str, Any]) -> ConfigFlowResult:
        """Persist updated options, merging with the existing values."""
        options = dict(self._entry.options)
        options.setdefault(CONF_DEVICES, [d.to_dict() for d in self._devices])
        options.setdefault(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        options.update(partial)
        return self.async_create_entry(title="", data=options)
