"""Automatic registration of the bundled Lovelace card.

Installing the integration is enough to make the BACnet schedule card available
in the dashboard: the JavaScript module is served by Home Assistant itself and
registered as a *persistent* Lovelace resource (the same mechanism HACS uses).

Persistence matters: the previous approach (``add_extra_js_url``) only lives in
memory and is injected into ``index.html``, which the frontend service worker
caches aggressively. Any boot where the integration was not yet set up when the
browser loaded the page - or any client with a cached index.html - showed
"Configuration error: custom element doesn't exist" until a hard refresh. A
storage-mode Lovelace resource is loaded by every dashboard on every page load,
independent of the integration's own setup state, so the card keeps working
even when the BACnet entry is still retrying.

``add_extra_js_url`` is kept as a fallback for YAML-mode dashboards, where the
resource collection is read-only (those users manage resources in YAML anyway).
"""

from __future__ import annotations

import logging
import os

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Public URL the card is served from, and the file shipped inside the package.
CARD_FILENAME = "bacnet-schedule-card.js"
CARD_URL_PATH = f"/{DOMAIN}/{CARD_FILENAME}"
_LOVELACE_DIR = os.path.join(os.path.dirname(__file__), "lovelace")

_REGISTERED_KEY = f"{DOMAIN}_frontend_registered"


async def _async_integration_version(hass: HomeAssistant) -> str:
    """Return the integration version without blocking the event loop.

    The version is read from the already-loaded integration metadata instead of
    opening manifest.json directly (which would be blocking file I/O).
    """
    try:
        integration = await async_get_integration(hass, DOMAIN)
        return str(integration.version or "0")
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not resolve integration version: %s", err)
        return "0"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file and register it with the frontend once.

    Must be called *before* anything in the entry setup that can raise
    ``ConfigEntryNotReady``: the card has to stay available on dashboards even
    while the BACnet stack itself is still retrying.
    """
    if hass.data.get(_REGISTERED_KEY):
        return

    card_path = os.path.join(_LOVELACE_DIR, CARD_FILENAME)
    if not await hass.async_add_executor_job(os.path.isfile, card_path):
        _LOGGER.warning("Lovelace card file missing at %s", card_path)
        return

    await _async_serve_card(hass, card_path)

    # Append a version query string so browsers reload the card after upgrades.
    version = await _async_integration_version(hass)
    versioned_url = f"{CARD_URL_PATH}?v={version}"

    if await _async_register_lovelace_resource(hass, versioned_url):
        _LOGGER.debug("BACnet card registered as a Lovelace resource")
    else:
        # Lovelace is not ready yet (startup ordering) or runs in YAML mode.
        # Fall back to an extra module now, and retry the persistent resource
        # once Home Assistant has fully started. The card guards against being
        # defined twice, so a double load is harmless.
        _add_extra_module(hass, versioned_url)
        if not hass.is_running:

            async def _retry(_event) -> None:
                await _async_register_lovelace_resource(hass, versioned_url)

            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _retry)

    hass.data[_REGISTERED_KEY] = True
    _LOGGER.info("BACnet schedule card served at %s", CARD_URL_PATH)


async def _async_register_lovelace_resource(
    hass: HomeAssistant, url: str
) -> bool:
    """Add/refresh the card in the Lovelace resource storage collection.

    Returns True when the resource is present (created, updated or already
    current); False when the collection is unavailable (YAML mode, lovelace
    not loaded yet, or an unexpected API shape).
    """
    resources = _resource_collection(hass)
    if resources is None:
        return False
    # YAML-mode resource collections are read-only.
    if not hasattr(resources, "async_create_item"):
        return False

    try:
        if hasattr(resources, "loaded") and not resources.loaded:
            await resources.async_load()
            resources.loaded = True

        base_url = url.split("?")[0]
        for item in resources.async_items():
            item_url = str(item.get("url", ""))
            if item_url.split("?")[0] != base_url:
                continue
            if item_url != url:
                # Same card, older version string: refresh to bust caches.
                await resources.async_update_item(item["id"], {"url": url})
            return True

        await resources.async_create_item({"res_type": "module", "url": url})
        return True
    except Exception as err:  # noqa: BLE001 - never break entry setup
        _LOGGER.warning("Could not register the Lovelace resource: %s", err)
        return False


def _resource_collection(hass: HomeAssistant):
    """Return the Lovelace resource collection across HA versions, or None."""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return None
    # 2024.2+: LovelaceData dataclass; before: plain dict.
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    return resources


async def _async_serve_card(hass: HomeAssistant, card_path: str) -> None:
    """Register the static path, supporting both new and old HA APIs."""
    # Newer HA (2024.7+): async bulk registration.
    register_async = getattr(hass.http, "async_register_static_paths", None)
    if register_async is not None:
        try:
            from homeassistant.components.http import StaticPathConfig

            await register_async(
                [StaticPathConfig(CARD_URL_PATH, card_path, False)]
            )
            return
        except RuntimeError:
            # Path already registered (e.g. after a reload) - safe to ignore.
            return
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("async_register_static_paths failed: %s", err)

    # Older HA: synchronous registration.
    register_sync = getattr(hass.http, "register_static_path", None)
    if register_sync is not None:
        try:
            register_sync(CARD_URL_PATH, card_path, False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not serve the BACnet card file: %s", err)
    else:
        _LOGGER.warning(
            "This Home Assistant version cannot serve the BACnet card file."
        )


def _add_extra_module(hass: HomeAssistant, url: str) -> None:
    """Register the card as an ES module with the frontend (best effort)."""
    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, url)
    except Exception as err:  # noqa: BLE001 - frontend optional/edge cases
        _LOGGER.warning(
            "Could not auto-register the BACnet card module (%s). Add it "
            "manually as a Lovelace resource: %s (type: module).",
            err,
            url,
        )
