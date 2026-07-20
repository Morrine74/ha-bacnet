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
    CONF_BBMD_ADDRESS,
    CONF_COV_LIFETIME,
    CONF_DEVICE_NAME,
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
    SELECTABLE_TYPES,
)
from .hub import BACnetHub, BACnetHubError, _ensure_cidr
from .models import DeviceConfig, PointConfig, devices_from_options
from .siemens import group_by_installation, short_label

_LOGGER = logging.getLogger(__name__)


def _point_label(obj: Any) -> str:
    """Build the picker label for a discovered object.

    When a Siemens tree path is available it is the clearest disambiguator (it
    spells out the full location/equipment/point chain), so it leads. Otherwise
    the description leads, with the object-name kept in parentheses.
    """
    if getattr(obj, "tree_path", None):
        return f"{' / '.join(obj.tree_path)} [{obj.object_id}]"
    if obj.description and obj.name and obj.description != obj.name:
        return f"{obj.description} ({obj.name}) [{obj.object_id}]"
    primary = obj.description or obj.name or obj.object_id
    return f"{primary} [{obj.object_id}]"


def _multi_select(options: dict[str, str]) -> Any:
    """Build a searchable multi-select dropdown (checkbox fallback)."""
    try:
        from homeassistant.helpers.selector import (
            SelectOptionDict,
            SelectSelector,
            SelectSelectorConfig,
            SelectSelectorMode,
        )
    except ImportError:
        return cv.multi_select(options)
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=oid, label=label)
                for oid, label in options.items()
            ],
            multiple=True,
            mode=SelectSelectorMode.DROPDOWN,
            custom_value=False,
        )
    )


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
            # Normalise to a CIDR so Who-Is broadcasts (Discover) work; a bare
            # host otherwise yields "no broadcast" and an empty discovery.
            local_ip = _ensure_cidr(user_input[CONF_LOCAL_IP])
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
        self._selected_vendor_id: int | None = None
        self._discovered_objects: list[Any] = []
        # Installation grouping of the point picker (None = flat picker).
        self._point_groups: dict[str, list[Any]] | None = None

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
                "manage_device",
                "rename_device",
                "settings",
                "remove_device",
            ],
        )

    async def async_step_rename_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a configured device to rename (no discovery round-trip)."""
        if not self._devices:
            return self.async_abort(reason="no_devices_configured")

        if user_input is not None:
            device = next(
                (
                    d
                    for d in self._devices
                    if d.device_id == int(user_input["device"])
                ),
                None,
            )
            if device is None:
                return self.async_abort(reason="no_devices_configured")
            self._selected_device = device
            return await self.async_step_rename_device_name()

        options = {
            str(d.device_id): f"{d.name} ({d.address})" for d in self._devices
        }
        return self.async_show_form(
            step_id="rename_device",
            data_schema=vol.Schema({vol.Required("device"): vol.In(options)}),
        )

    async def async_step_rename_device_name(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save the new name of the selected device immediately."""
        device = self._selected_device
        assert device is not None

        if user_input is not None:
            new_name = (user_input.get(CONF_DEVICE_NAME) or "").strip()
            if new_name:
                device.name = new_name
            return self._save(
                {CONF_DEVICES: [d.to_dict() for d in self._devices]}
            )

        return self.async_show_form(
            step_id="rename_device_name",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_NAME, default=device.name): str}
            ),
            description_placeholders={
                "device": f"{device.name} ({device.address})"
            },
        )

    async def async_step_manage_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick an already-configured device to edit its points / name.

        Re-runs object discovery for that device and re-enters the point picker
        with the current selection pre-ticked, so points can be added or removed
        without rebuilding the whole list.
        """
        if not self._devices:
            return self.async_abort(reason="no_devices_configured")

        if user_input is not None:
            device = next(
                (
                    d
                    for d in self._devices
                    if d.device_id == int(user_input["device"])
                ),
                None,
            )
            if device is None:
                return self.async_abort(reason="no_devices_configured")
            self._selected_device = device
            # Re-derive the vendor id so a Siemens device keeps its tree-path
            # grouping when re-discovered (DeviceConfig does not store it).
            self._selected_vendor_id = None
            hub = self._hub()
            if hub is not None and hub.started:
                try:
                    found = await hub.async_who_is(
                        address=device.address, timeout=DEFAULT_DISCOVERY_TIMEOUT
                    )
                except BACnetHubError:
                    found = []
                if found:
                    self._selected_vendor_id = found[0].vendor_id
            return await self.async_step_select_points()

        options = {
            str(d.device_id): f"{d.name} ({d.address})" for d in self._devices
        }
        return self.async_show_form(
            step_id="manage_device",
            data_schema=vol.Schema({vol.Required("device"): vol.In(options)}),
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
            match = next(
                (
                    d
                    for d in self._discovered
                    if str(d.device_id) == device_id and d.address == address
                ),
                None,
            )
            self._selected_vendor_id = match.vendor_id if match else None
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
                    self._selected_vendor_id = found[0].vendor_id
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

        # Settings of already-configured points must survive an edit: the form
        # shows one global COV/priority pair, so it only overrides per-point
        # values when the user actually changed it from the prefilled default.
        existing = next(
            (d for d in self._devices if d.device_id == device.device_id), None
        )
        existing_points = existing.points if existing else []
        existing_by_id = {p.object_id: p for p in existing_points}
        prefill_cov = any(p.use_cov for p in existing_points)
        prefill_priority = (
            existing_points[0].write_priority
            if existing_points
            else DEFAULT_WRITE_PRIORITY
        )

        if user_input is not None:
            # Selected points come from the flat "points" field (non-grouped
            # picker), the "other_points" field (grouped picker's points
            # without an installation) and/or one section per installation. A
            # section arrives nested ({key: {"points": [...]}}); the
            # sectionless fallback delivers the list directly under the
            # installation key.
            chosen = list(user_input.get("points") or [])
            chosen.extend(user_input.get("other_points") or [])
            for key in self._point_groups or {}:
                value = user_input.get(key)
                if isinstance(value, dict):
                    chosen.extend(value.get("points") or [])
                elif isinstance(value, list):
                    chosen.extend(value)
            use_cov = user_input.get(CONF_USE_COV, False)
            priority = user_input.get(CONF_WRITE_PRIORITY, DEFAULT_WRITE_PRIORITY)
            cov_changed = use_cov != prefill_cov
            priority_changed = priority != prefill_priority
            new_name = (user_input.get(CONF_DEVICE_NAME) or "").strip()
            if new_name:
                device.name = new_name
            lookup = {o.object_id: o for o in self._discovered_objects}
            points: list[PointConfig] = []
            for object_id in chosen:
                obj = lookup.get(object_id)
                if not obj:
                    continue
                prev = existing_by_id.get(object_id)
                points.append(
                    PointConfig(
                        object_type=obj.object_type,
                        instance=obj.instance,
                        # Keep the configured name; for new points prefer the
                        # human-readable description over the (often cryptic)
                        # BACnet object-name.
                        name=(prev.name if prev else None)
                        or obj.description
                        or obj.name
                        or object_id,
                        use_cov=(
                            use_cov
                            if prev is None or cov_changed
                            else prev.use_cov
                        ),
                        cov_lifetime=(
                            prev.cov_lifetime if prev else DEFAULT_COV_LIFETIME
                        ),
                        write_priority=(
                            priority
                            if prev is None or priority_changed
                            else prev.write_priority
                        ),
                        units=obj.units,
                        description=obj.description,
                        state_text=obj.state_text,
                        active_text=obj.active_text,
                        inactive_text=obj.inactive_text,
                        tree_path=obj.tree_path,
                        equipment_index=obj.equipment_index,
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
                device.address, device.device_id, self._selected_vendor_id
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
        # Other types (trend-log, file, loop, structured-view,
        # notification-class, proprietary types, ...) are accessed through
        # services instead. Schedules are included so they can be exposed and
        # edited with the schedule card.
        selectable = [
            o for o in self._discovered_objects if o.object_type in SELECTABLE_TYPES
        ]
        if not selectable:
            return self.async_abort(reason="no_objects_found")

        default_name = existing.name if existing else device.name
        selected = set(existing_by_id)

        # Siemens devices with several installations get one collapsible
        # section per installation, each holding a searchable multi-select of
        # its points with short (installation-relative) labels. Everything is
        # ticked across sections and saved in a single submit. Other devices
        # keep the flat searchable picker with full labels.
        self._point_groups, ungrouped = group_by_installation(selectable)

        schema: dict[Any, Any] = {
            vol.Optional(CONF_DEVICE_NAME, default=default_name): str
        }

        section: Any = None
        if self._point_groups is not None:
            try:
                from homeassistant.data_entry_flow import section
            except ImportError:
                section = None

        if self._point_groups is None:
            # Flat picker, sorted by tree path so related points stay adjacent.
            ungrouped = sorted(
                ungrouped,
                key=lambda o: o.tree_path or [o.object_type, f"{o.instance:08d}"],
            )
            options = {o.object_id: _point_label(o) for o in ungrouped}
            schema[
                vol.Required(
                    "points",
                    default=[oid for oid in options if oid in selected],
                )
            ] = _multi_select(options)
        else:
            if ungrouped:
                ungrouped = sorted(
                    ungrouped, key=lambda o: short_label(o).casefold()
                )
                options = {o.object_id: short_label(o) for o in ungrouped}
                schema[
                    vol.Optional(
                        "other_points",
                        default=[oid for oid in options if oid in selected],
                    )
                ] = _multi_select(options)
            for key, objs in self._point_groups.items():
                options = {o.object_id: short_label(o) for o in objs}
                defaults = [oid for oid in options if oid in selected]
                selector = _multi_select(options)
                if section is not None:
                    # Sections with already-configured points start expanded.
                    schema[vol.Optional(key)] = section(
                        vol.Schema(
                            {vol.Optional("points", default=defaults): selector}
                        ),
                        {"collapsed": not defaults},
                    )
                else:
                    schema[vol.Optional(key, default=defaults)] = selector

        schema[vol.Optional(CONF_USE_COV, default=prefill_cov)] = bool
        schema[vol.Optional(CONF_WRITE_PRIORITY, default=prefill_priority)] = (
            vol.All(
                int,
                vol.Range(min=MIN_WRITE_PRIORITY, max=MAX_WRITE_PRIORITY),
            )
        )

        return self.async_show_form(
            step_id="select_points",
            data_schema=vol.Schema(schema),
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
