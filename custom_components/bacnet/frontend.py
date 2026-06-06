"""Automatic registration of the bundled Lovelace card.

Installing the integration is enough to make the BACnet schedule card available
in the dashboard: the JavaScript module is served by Home Assistant itself and
registered as an extra frontend module, so the user does not have to add a
Lovelace resource manually.
"""

from __future__ import annotations

import json
import logging
import os

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Public URL the card is served from, and the file shipped inside the package.
CARD_FILENAME = "bacnet-schedule-card.js"
CARD_URL_PATH = f"/{DOMAIN}/{CARD_FILENAME}"
_LOVELACE_DIR = os.path.join(os.path.dirname(__file__), "lovelace")

_REGISTERED_KEY = f"{DOMAIN}_frontend_registered"


def _integration_version() -> str:
    """Read the integration version from manifest.json for cache busting."""
    try:
        manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
        with open(manifest_path, encoding="utf-8") as handle:
            return json.load(handle).get("version", "0")
    except (OSError, ValueError):
        return "0"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file and add it to the frontend's extra modules once."""
    if hass.data.get(_REGISTERED_KEY):
        return

    card_path = os.path.join(_LOVELACE_DIR, CARD_FILENAME)
    if not os.path.isfile(card_path):
        _LOGGER.warning("Lovelace card file missing at %s", card_path)
        return

    await _async_serve_card(hass, card_path)

    # Append a version query string so browsers reload the card after upgrades.
    versioned_url = f"{CARD_URL_PATH}?v={_integration_version()}"
    _add_extra_module(hass, versioned_url)

    hass.data[_REGISTERED_KEY] = True
    _LOGGER.info(
        "BACnet schedule card served at %s and registered with the frontend. "
        "If the card shows 'Custom element not found', hard-refresh your "
        "browser (Ctrl+Shift+R) to reload the frontend.",
        CARD_URL_PATH,
    )


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

