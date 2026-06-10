"""Tests for the Siemens path-grouping logic (pure, no bacpypes3 / HA)."""

from __future__ import annotations

from bacnet import siemens
from bacnet.siemens import build_split, find_equipment_index, slugify_equipment

# A small structured-view node-type map, mirroring real Siemens data: the
# installation level ("system") sits above functional sub-parts.
SV_TYPES = {
    "Gym'LT'HGen": "system",
    "Gym'LT'HGen'Bo": "functional",
    "Gym'LT'HGen'HwStk": "functional",
    "Gym'LT'Hcr": "system",
    "Gym'LT'Hcr'HydCrt": "functional",
    "Gym'Salle de sport'Ahu": "system",
    "Gym'Salle de sport'Ahu'Hcl": "functional",
}


def test_find_equipment_index_points_to_system_ancestor():
    # Boiler return temperature: system ancestor is "Gym'LT'HGen" at index 2.
    assert find_equipment_index("Gym'LT'HGen'Bo'TRt", SV_TYPES) == 2
    # AHU heating coil point: system ancestor "Gym'Salle de sport'Ahu" at index 2.
    assert find_equipment_index("Gym'Salle de sport'Ahu'Hcl'T", SV_TYPES) == 2
    # Point directly under the system node (outside air temp).
    assert find_equipment_index("Gym'LT'HGen'TOa", SV_TYPES) == 2


def test_find_equipment_index_uses_shallowest_system():
    # If two ancestors are systems, the shallowest (topmost) wins.
    types = {"A": "system", "A'B": "system"}
    assert find_equipment_index("A'B'pt", types) == 0


def test_find_equipment_index_none_when_no_system():
    assert find_equipment_index("Gym'LT'Foo'pt", {"Gym'LT'Foo": "functional"}) is None
    assert find_equipment_index("", SV_TYPES) is None
    assert find_equipment_index(None, SV_TYPES) is None


def test_build_split_installation_level():
    path = [
        "Gymnase",
        "Locaux Techniques",
        "Production de chaleur",
        "Chaudière",
        "Température au retour",
    ]
    split = build_split(path, 2)
    assert split.area == "Gymnase / Locaux Techniques"
    assert split.equipment == "Production de chaleur"
    # Functional sub-part is kept as a breadcrumb in the entity name.
    assert split.name == "Chaudière · Température au retour"


def test_build_split_no_breadcrumb_when_leaf_under_system():
    path = ["Gymnase", "Locaux Techniques", "Production de chaleur", "Température ext."]
    split = build_split(path, 2)
    assert split.area == "Gymnase / Locaux Techniques"
    assert split.equipment == "Production de chaleur"
    assert split.name == "Température ext."


def test_build_split_without_equipment_keeps_leaf_only():
    path = ["Gymnase", "Locaux Techniques", "Quelque chose"]
    split = build_split(path, None)
    assert split.equipment is None
    assert split.area is None
    assert split.name == "Quelque chose"


def test_build_split_empty_path():
    split = build_split(None, None)
    assert split == siemens.PathSplit(area=None, equipment=None, name="", segments=[])


def test_build_split_clamps_out_of_range_index():
    # An index pointing at/after the leaf must not produce an empty name.
    path = ["A", "B", "C"]
    split = build_split(path, 2)  # 2 == leaf index -> treated as "no equipment"
    assert split.equipment is None
    assert split.name == "C"


def test_slugify_equipment_is_stable_and_deterministic():
    split = build_split(
        ["Gymnase", "Locaux Techniques", "Production de chaleur", "T"], 2
    )
    slug = slugify_equipment(4007, split)
    assert slug == slugify_equipment(4007, split)  # deterministic
    assert slug is not None
    # Accents/spaces normalised; device id kept as the leading token.
    assert slug.startswith("4007:")
    assert "production-de-chaleur" in slug


def test_slugify_equipment_none_without_equipment():
    split = build_split(["Gymnase", "T"], None)
    assert slugify_equipment(4007, split) is None
