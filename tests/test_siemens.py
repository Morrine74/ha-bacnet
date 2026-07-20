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


class _Obj:
    """Stand-in for a DiscoveredObject (picker grouping tests)."""

    def __init__(self, object_id, tree_path=None, equipment_index=None,
                 description=None, name=None):
        self.object_id = object_id
        self.tree_path = tree_path
        self.equipment_index = equipment_index
        self.description = description
        self.name = name


_HEAT = ["Gymnase", "LT", "Production de chaleur", "Chaudière", "Température"]
_AHU = ["Gymnase", "Salle", "CTA", "Batterie chaude", "Vanne"]


def test_short_label_is_installation_relative():
    obj = _Obj("analog-input,1", tree_path=_HEAT, equipment_index=2)
    assert siemens.short_label(obj) == "Chaudière · Température [analog-input,1]"
    # No path: falls back to description, then name.
    assert siemens.short_label(
        _Obj("binary-value,2", description="Pompe")
    ) == "Pompe [binary-value,2]"
    assert siemens.short_label(_Obj("binary-value,3")) == (
        "binary-value,3 [binary-value,3]"
    )


def test_group_by_installation_splits_and_sorts():
    heat_a = _Obj("analog-input,1", tree_path=_HEAT, equipment_index=2)
    heat_b = _Obj(
        "analog-input,2",
        tree_path=["Gymnase", "LT", "Production de chaleur", "Alarme"],
        equipment_index=2,
    )
    ahu = _Obj("analog-input,3", tree_path=_AHU, equipment_index=2)
    loose = _Obj("binary-value,9", description="Point libre")

    groups, ungrouped = siemens.group_by_installation([heat_a, ahu, loose, heat_b])
    assert list(groups) == ["Production de chaleur", "CTA"]
    # Points inside a group are sorted by their short label.
    assert [o.object_id for o in groups["Production de chaleur"]] == [
        "analog-input,2",
        "analog-input,1",
    ]
    assert [o.object_id for o in groups["CTA"]] == ["analog-input,3"]
    assert [o.object_id for o in ungrouped] == ["binary-value,9"]


def test_group_by_installation_single_installation_still_groups():
    # Even one installation benefits from short labels and its own section.
    heat = _Obj("analog-input,1", tree_path=_HEAT, equipment_index=2)
    loose = _Obj("binary-value,9")
    groups, ungrouped = siemens.group_by_installation([heat, loose])
    assert list(groups) == ["Production de chaleur"]
    assert ungrouped == [loose]
    # Non-Siemens device (no installation at all) keeps the flat picker.
    groups, ungrouped = siemens.group_by_installation([loose])
    assert groups is None
    assert ungrouped == [loose]


def test_equipment_index_from_paths_prefix_match():
    system_paths = [
        ["Gymnase", "LT", "Production de chaleur"],
        ["Gymnase", "Salle", "CTA"],
    ]
    # Heat point: matches the first system path -> index 2.
    assert siemens.equipment_index_from_paths(_HEAT, system_paths) == 2
    assert siemens.equipment_index_from_paths(_AHU, system_paths) == 2
    # No system path is a prefix -> None.
    assert siemens.equipment_index_from_paths(
        ["Autre", "Chemin", "Point"], system_paths
    ) is None
    assert siemens.equipment_index_from_paths(None, system_paths) is None
    assert siemens.equipment_index_from_paths(_HEAT, []) is None


def test_equipment_index_from_paths_shallowest_wins_and_proper_prefix():
    # Nested system nodes: the shallowest wins (same rule as object-names).
    nested = [
        ["Gymnase", "LT", "Production de chaleur"],
        ["Gymnase", "LT", "Production de chaleur", "Chaudière"],
    ]
    assert siemens.equipment_index_from_paths(_HEAT, nested) == 2
    # A path equal to the point's own path is not an ancestor.
    assert siemens.equipment_index_from_paths(
        ["Gymnase", "LT", "Production de chaleur"],
        [["Gymnase", "LT", "Production de chaleur"]],
    ) is None


def test_group_by_installation_disambiguates_same_name_across_areas():
    a = _Obj(
        "analog-input,1",
        tree_path=["Bât. A", "CTA", "Vanne"],
        equipment_index=1,
    )
    b = _Obj(
        "analog-input,2",
        tree_path=["Bât. B", "CTA", "Vanne"],
        equipment_index=1,
    )
    groups, _ungrouped = siemens.group_by_installation([a, b])
    assert list(groups) == ["CTA — Bât. A", "CTA — Bât. B"]
