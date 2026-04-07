"""
Content-Based XML Comparison Engine
=====================================
Matches nodes between two XML files using a two-pass exact-first strategy.
No positional ordering, no unique key identifiers, no similarity thresholds.

Algorithm
---------
PASS 1 – Exact matching
  For every node in File A, search all unmatched File B nodes with the same
  tag for a node where EVERY field key-value pair matches (under configured
  rules).  When found, both nodes are locked and produce no diff output.
  Exact matches are resolved first so a perfect counterpart is never
  "stolen" by a partial match in Pass 2.

PASS 2 – Mismatch / missing detection
  For every A node not locked in Pass 1:
    - Find unmatched B candidates with the same tag.
    - If candidates exist  → pair with the one sharing the most field keys
                             (structural best-fit) and report field differences.
    - If no candidates     → report MISSING_IN_B.

PASS 3 – Orphan B nodes
  Any File B node still unmatched after both passes → MISSING_IN_A.

Field comparison (within a matched pair)
  - key in A only   → MISSING_IN_B
  - key in B only   → MISSING_IN_A
  - key in both, values differ → MISMATCH
  - key in both, values match  → silent (no entry)

Key properties
--------------
* Global: a node at any depth/position in A can match one at any depth in B.
* Exact-first: locks prevent perfect matches from being consumed by partials.
* Unordered fields: field order within a node is irrelevant.
* Deterministic: no floating-point thresholds; decisions are rule-based.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from lxml import etree

from models.schemas import ComparisonConfig, DiffEntry, DiffStatus
from rules.rules_engine import RulesEngine


# ---------------------------------------------------------------------------
# Internal data model
# ---------------------------------------------------------------------------

@dataclass
class _Node:
    """A comparable node extracted from an XML tree."""
    tag: str
    path: str
    fields: dict[str, str]          # Direct leaf children {tag: text}
    matched: bool = field(default=False, repr=False)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compare_xml_trees(
    root_a: etree._Element,
    root_b: etree._Element,
    config: ComparisonConfig,
) -> list[DiffEntry]:
    """
    Compare two parsed XML trees using content-based, exact-first matching.

    Parameters
    ----------
    root_a : Reference XML root (File A).
    root_b : Target XML root (File B).
    config : Comparison configuration.

    Returns
    -------
    List of DiffEntry objects for every detected difference.
    Empty list means the files are semantically equivalent.
    """
    rules = RulesEngine(config)

    nodes_a = _extract_nodes(root_a)
    nodes_b = _extract_nodes(root_b)

    # Index B nodes by tag for fast candidate retrieval
    b_index: dict[str, list[_Node]] = {}
    for node in nodes_b:
        b_index.setdefault(node.tag, []).append(node)

    differences: list[DiffEntry] = []

    # ── PASS 1: lock exact matches (all field key-value pairs identical) ─
    for node_a in nodes_a:
        if rules.should_ignore(node_a.tag):
            continue
        candidates = [n for n in b_index.get(node_a.tag, []) if not n.matched]
        exact = _find_exact(node_a, candidates, rules)
        if exact:
            node_a.matched = True
            exact.matched = True

    # ── PASS 2: handle remaining A nodes ────────────────────────────────
    for node_a in nodes_a:
        if node_a.matched or rules.should_ignore(node_a.tag):
            continue

        candidates = [n for n in b_index.get(node_a.tag, []) if not n.matched]

        if not candidates:
            differences.append(DiffEntry(path=node_a.path, status=DiffStatus.MISSING_IN_B))
            continue

        # Pair with the candidate that shares the most field keys (best structural fit)
        best = _structural_best(node_a, candidates, rules)
        best.matched = True
        _compare_fields(node_a.path, node_a.fields, best.fields, rules, differences)

    # ── PASS 3: unmatched B nodes have no counterpart in A ───────────────
    for node in nodes_b:
        if not node.matched and not rules.should_ignore(node.tag):
            differences.append(DiffEntry(path=node.path, status=DiffStatus.MISSING_IN_A))

    return differences


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_nodes(root: etree._Element) -> list[_Node]:
    """
    Walk the full XML tree and collect every element that owns at least one
    direct leaf child (i.e. carries key-value data of its own).
    Sibling elements sharing the same tag are indexed as [0], [1], …
    """
    result: list[_Node] = []
    _walk(root, root.tag, result)
    return result


def _walk(element: etree._Element, path: str, result: list[_Node]) -> None:
    child_elems = [c for c in element if isinstance(c.tag, str)]

    # Collect direct leaf children as key-value fields
    fields: dict[str, str] = {}
    for child in child_elems:
        if not _has_element_children(child):
            fields[child.tag] = _norm(child.text)

    if fields:
        result.append(_Node(tag=element.tag, path=path, fields=fields))

    # Recurse into non-leaf children with sibling-aware path indexing
    non_leaf_children = [c for c in child_elems if _has_element_children(c)]
    tag_counts = Counter(c.tag for c in non_leaf_children)
    tag_seen: dict[str, int] = {}

    for child in non_leaf_children:
        tag_seen[child.tag] = tag_seen.get(child.tag, 0) + 1
        idx = tag_seen[child.tag] - 1
        child_path = (
            f"{path}.{child.tag}[{idx}]"
            if tag_counts[child.tag] > 1
            else f"{path}.{child.tag}"
        )
        _walk(child, child_path, result)


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _find_exact(node_a: _Node, candidates: list[_Node], rules: RulesEngine) -> _Node | None:
    """
    Return the first candidate whose fields are an exact match for node_a
    under the configured rules (case, numeric tolerance).
    Both key sets must be identical and all values must match.
    """
    for candidate in candidates:
        if set(candidate.fields.keys()) != set(node_a.fields.keys()):
            continue
        if all(rules.values_match(node_a.fields[k], candidate.fields[k]) for k in node_a.fields):
            return candidate
    return None


def _structural_best(node_a: _Node, candidates: list[_Node], rules: RulesEngine) -> _Node:
    """
    Among candidates, return the best structural fit for node_a.

    Sort key (descending priority):
    1. Most shared field keys  — structural similarity
    2. Most matching values    — value closeness as tiebreaker (no threshold)

    Ties at both levels broken by document order (first occurrence in File B).
    """
    def _rank(candidate: _Node) -> tuple[int, int]:
        shared = set(node_a.fields.keys()) & set(candidate.fields.keys())
        matching_values = sum(
            1 for k in shared
            if rules.values_match(node_a.fields[k], candidate.fields[k])
        )
        return (len(shared), matching_values)

    return max(candidates, key=_rank)


# ---------------------------------------------------------------------------
# Field-level comparison
# ---------------------------------------------------------------------------

def _compare_fields(
    base_path: str,
    fields_a: dict[str, str],
    fields_b: dict[str, str],
    rules: RulesEngine,
    differences: list[DiffEntry],
) -> None:
    """Compare two field dicts (unordered, by key) and record differences."""
    for key in sorted(set(fields_a) | set(fields_b)):
        if rules.should_ignore(key):
            continue

        path = f"{base_path}.{key}"
        val_a = fields_a.get(key)
        val_b = fields_b.get(key)

        if val_a is None:
            differences.append(DiffEntry(path=path, value_b=val_b or None, status=DiffStatus.MISSING_IN_A))
        elif val_b is None:
            differences.append(DiffEntry(path=path, value_a=val_a or None, status=DiffStatus.MISSING_IN_B))
        elif not rules.values_match(val_a, val_b):
            differences.append(DiffEntry(path=path, value_a=val_a, value_b=val_b, status=DiffStatus.MISMATCH))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _has_element_children(element: etree._Element) -> bool:
    return any(isinstance(c.tag, str) for c in element)


def _norm(text: str | None) -> str:
    return (text or "").strip()
