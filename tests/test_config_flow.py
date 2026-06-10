"""Tests for config-flow helpers (requires homeassistant, so CI-only)."""

from __future__ import annotations

import pytest

from bacnet import hub


def test_point_label_prefers_description():
    pytest.importorskip("homeassistant")
    from bacnet import config_flow

    described = hub.DiscoveredObject(
        object_type="analog-input",
        instance=3,
        name="AI_3",
        description="Température bureau",
    )
    assert (
        config_flow._point_label(described)
        == "Température bureau (AI_3) [analog-input,3]"
    )

    name_only = hub.DiscoveredObject(
        object_type="schedule", instance=1, name="SCH1"
    )
    assert config_flow._point_label(name_only) == "SCH1 [schedule,1]"

    bare = hub.DiscoveredObject(object_type="binary-value", instance=2)
    assert config_flow._point_label(bare) == "binary-value,2 [binary-value,2]"
