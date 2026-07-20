"""Siemens-specific helpers: turn a point's tree path into HA grouping.

Siemens controllers describe their plant tree with ``structured-view`` (type 29)
objects. Each carries the standard ``node-type`` property, and Siemens uses it
authoritatively:

- location nodes (``building`` / ``floor`` / ``area`` / ``zone`` ...) are the
  upper levels -> they become the Home Assistant **area**;
- a ``system`` node is an **installation** (Production de chaleur, Circuit de
  chauffage, CTA ...) -> it becomes the HA **sub-device** that groups points;
- ``functional`` nodes below it (Chaudière, Pompe, Batterie chaude ...) are kept
  as a breadcrumb inside the entity **name**.

Each point also exposes property 4397, an ``ArrayOf(CharacterString)`` with the
full friendly path, e.g.::

    ["Gymnase", "Locaux Techniques", "Production de chaleur",
     "Chaudière", "Température au retour"]

The point's ``object-name`` (``Gym'LT'HGen'Bo'TRt``) is the apostrophe-joined
prefix chain of the structured-views above it and aligns 1:1 with the 4397 path,
so the index of the ``system`` ancestor in ``object-name`` is also its index in
the 4397 path. ``find_equipment_index`` resolves that index from a structured-view
node-type map; ``build_split`` then turns (path, index) into (area, equipment,
name). Everything here is pure Python (no bacpypes3 / Home Assistant) and so is
unit-testable in isolation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Separator Siemens uses inside object-name to join path segments.
SV_NAME_SEP = "'"
# node-type values (lower-cased) that mark the installation / equipment level.
EQUIPMENT_NODE_TYPES: frozenset[str] = frozenset({"system"})

# Separator used to join intermediate (functional) segments into the entity name.
_BREADCRUMB_SEP = " · "
# Separator used to join location segments into the HA area name.
_AREA_SEP = " / "


@dataclass(slots=True)
class PathSplit:
    """Result of splitting a tree path into HA grouping components."""

    area: str | None
    equipment: str | None
    name: str
    segments: list[str]


def _normalize(text: str) -> str:
    """Lower-case and strip accents for tolerant / stable comparison."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return without_accents.casefold().strip()


def find_equipment_index(
    object_name: str | None, sv_node_types: dict[str, str]
) -> int | None:
    """Return the path index of the installation (``system``) ancestor.

    ``object_name`` is the point's BACnet object-name (``Gym'LT'HGen'Bo'TRt``);
    ``sv_node_types`` maps a structured-view object-name to its node-type token.
    Returns the index of the shallowest ancestor whose node-type is an equipment
    type, or ``None`` when there is none (the point then stays under its
    controller).
    """
    if not object_name:
        return None
    parts = object_name.split(SV_NAME_SEP)
    # Ancestors are the prefixes excluding the full name (the point itself).
    for i in range(len(parts) - 1):
        prefix = SV_NAME_SEP.join(parts[: i + 1])
        node_type = sv_node_types.get(prefix)
        if node_type and node_type.casefold() in EQUIPMENT_NODE_TYPES:
            return i
    return None


def equipment_index_from_paths(
    tree_path: list[str] | None, system_paths: list[list[str]]
) -> int | None:
    """Fallback: locate the installation level by tree-path prefix matching.

    ``system_paths`` are the 4397 tree paths of the structured-views whose
    node-type is ``system``. A point belongs to the installation whose path is
    a proper prefix of its own path; the installation level is that path's last
    segment. Like :func:`find_equipment_index`, the shallowest match wins.
    Unlike it, this needs no alignment between object-names and the tree —
    only the friendly paths themselves.
    """
    if not tree_path:
        return None
    best: int | None = None
    for system_path in system_paths:
        depth = len(system_path)
        if 0 < depth < len(tree_path) and tree_path[:depth] == system_path:
            index = depth - 1
            best = index if best is None else min(best, index)
    return best


def build_split(
    tree_path: list[str] | None, equipment_index: int | None
) -> PathSplit:
    """Split a friendly tree path into (area, equipment, name).

    ``equipment_index`` is the index of the installation level (from
    :func:`find_equipment_index`). Segments before it form the area, the segment
    at it is the equipment sub-device, and everything after it (functional
    breadcrumb + leaf) forms the entity name. When there is no equipment level
    the point keeps just its leaf name and stays attached to the controller.
    """
    segments = [s.strip() for s in (tree_path or []) if s and s.strip()]
    if not segments:
        return PathSplit(area=None, equipment=None, name="", segments=[])

    leaf_index = len(segments) - 1
    if equipment_index is None or not (0 <= equipment_index < leaf_index):
        # No installation level: leaf only, attached to the controller.
        return PathSplit(
            area=None, equipment=None, name=segments[leaf_index], segments=segments
        )

    area = _AREA_SEP.join(segments[:equipment_index]) or None
    equipment = segments[equipment_index]
    name = _BREADCRUMB_SEP.join(segments[equipment_index + 1 :])
    return PathSplit(area=area, equipment=equipment, name=name, segments=segments)


def short_label(obj) -> str:
    """Build a compact picker label for a point listed under its installation.

    The installation (and everything above it) is already the group title, so
    only the functional breadcrumb and leaf remain, e.g.
    ``Chaudière · Température au retour [analog-input,1006]``.
    """
    split = build_split(
        getattr(obj, "tree_path", None), getattr(obj, "equipment_index", None)
    )
    primary = (
        split.name
        or getattr(obj, "description", None)
        or getattr(obj, "name", None)
        or obj.object_id
    )
    return f"{primary} [{obj.object_id}]"


def group_by_installation(objects: list) -> tuple[dict[str, list] | None, list]:
    """Group discovered points by their installation (``system`` node).

    Returns ``(groups, ungrouped)`` where ``groups`` maps a unique display name
    (the installation, disambiguated by its area when two areas contain a
    same-named installation) to its points, sorted by label, and ``ungrouped``
    collects points without an installation level. When no installation exists
    at all (typically a non-Siemens device), ``(None, objects)`` is returned
    and the caller keeps its flat picker.
    """
    by_install: dict[tuple[str, str], list] = {}
    ungrouped: list = []
    for obj in objects:
        split = build_split(
            getattr(obj, "tree_path", None), getattr(obj, "equipment_index", None)
        )
        if split.equipment:
            by_install.setdefault((split.area or "", split.equipment), []).append(obj)
        else:
            ungrouped.append(obj)
    if not by_install:
        return None, objects

    names = [equipment for (_area, equipment) in by_install]
    groups: dict[str, list] = {}
    for (area, equipment), objs in sorted(by_install.items()):
        key = equipment
        if names.count(equipment) > 1 and area:
            key = f"{equipment} — {area}"
        objs.sort(key=lambda o: short_label(o).casefold())
        groups[key] = objs
    return groups, ungrouped


def _slug(text: str) -> str:
    """Reduce a string to a stable, identifier-safe token."""
    norm = _normalize(text)
    return re.sub(r"[^a-z0-9]+", "-", norm).strip("-")


def slugify_equipment(device_id: int, split: PathSplit) -> str | None:
    """Build a stable HA sub-device key for an installation node.

    Returns ``None`` when the path has no equipment level (the point then stays
    attached to its controller device). The key is deterministic across restarts
    so the same physical installation always maps to the same HA device.
    """
    if not split.equipment:
        return None
    parts = [str(device_id), _slug(split.area or ""), _slug(split.equipment)]
    return ":".join(p for p in parts if p)
