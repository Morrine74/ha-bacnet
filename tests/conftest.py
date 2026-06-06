"""Pytest configuration.

The integration's ``__init__`` imports Home Assistant, which is not installed in
the lightweight test environment used for the pure-logic unit tests. To exercise
the dependency-free modules (``const``, ``models``, ``hub`` helpers) we register
a synthetic ``bacnet`` package pointing at the source directory *without*
executing ``custom_components/bacnet/__init__.py``. Relative imports inside those
modules then resolve correctly.
"""

from __future__ import annotations

import os
import sys
import types

_BACNET_DIR = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "bacnet"
)

if "bacnet" not in sys.modules:
    package = types.ModuleType("bacnet")
    package.__path__ = [os.path.abspath(_BACNET_DIR)]
    sys.modules["bacnet"] = package
