from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict

from lxml import etree


@dataclass
class NodeStructure:
    """
    Structural metadata for a single XML tag as observed in File A.

    node_type: "SINGLE"   – tag appears at most once under its parent.
                "MULTIPLE" – tag appears more than once under its parent;
                             elements are compared in strict index order.
    is_leaf:   True when the element carries only text content (no child elements).
    children:  Structural metadata for each distinct child tag.
    """

    node_type: str
    is_leaf: bool = True
    children: Dict[str, NodeStructure] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_structure(element: etree._Element) -> NodeStructure:
    """
    Recursively walk *element* (from File A) and return a NodeStructure that
    captures, for every descendant tag, whether it is SINGLE or MULTIPLE under
    its parent.

    Algorithm
    ---------
    1. Count occurrences of each direct-child tag.
    2. Tags with count > 1 → MULTIPLE (ordered comparison required).
    3. Tags with count == 1 → SINGLE (direct comparison, no indexing).
    4. Recurse into all child instances and merge structures so that the
       richest structural description survives (handles variation across
       repeated nodes).
    """
    child_elements = _element_children(element)

    if not child_elements:
        return NodeStructure(node_type="SINGLE", is_leaf=True)

    tag_counts = Counter(c.tag for c in child_elements)

    grouped: dict[str, list[etree._Element]] = {}
    for child in child_elements:
        grouped.setdefault(child.tag, []).append(child)

    children_structures: Dict[str, NodeStructure] = {}
    for tag, instances in grouped.items():
        node_type = "MULTIPLE" if tag_counts[tag] > 1 else "SINGLE"
        instance_structs = [analyze_structure(inst) for inst in instances]
        children_structures[tag] = _merge_structures(instance_structs, node_type)

    return NodeStructure(node_type="SINGLE", is_leaf=False, children=children_structures)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _element_children(element: etree._Element) -> list[etree._Element]:
    """Return only true element children (no comments, PIs, etc.)."""
    return [c for c in element if isinstance(c.tag, str)]


def _merge_structures(structures: list[NodeStructure], node_type: str) -> NodeStructure:
    """
    Merge several NodeStructure instances that all correspond to the same tag
    (typically from repeated MULTIPLE nodes) into one canonical structure.

    Merging rules:
    - If all instances are leaves → merged result is a leaf.
    - Otherwise, recursively merge children; if any instance promotes a child
      to MULTIPLE, that promotion is preserved.
    """
    if not structures:
        return NodeStructure(node_type=node_type, is_leaf=True)

    if all(s.is_leaf for s in structures):
        return NodeStructure(node_type=node_type, is_leaf=True)

    merged_children: Dict[str, NodeStructure] = {}
    for struct in structures:
        for tag, child_struct in struct.children.items():
            if tag not in merged_children:
                merged_children[tag] = child_struct
            else:
                existing = merged_children[tag]
                # Promote to MULTIPLE if either instance says so.
                merged_type = (
                    "MULTIPLE"
                    if existing.node_type == "MULTIPLE" or child_struct.node_type == "MULTIPLE"
                    else "SINGLE"
                )
                merged_children[tag] = _merge_structures([existing, child_struct], merged_type)

    return NodeStructure(node_type=node_type, is_leaf=False, children=merged_children)
