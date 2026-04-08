"""
XML → CSV Normalizer
====================
Walks the entire XML tree and emits one CSV row for every leaf node
(an element with no child elements — only text content).

No value is skipped. Every leaf at every depth and every repeated block
(Correspondence[0], Correspondence[1], PartyInfo[0], …) is captured.

CSV columns
-----------
  policy_number  – value of the first field whose tag matches
                   /policy.*(number|id|no)/i  (used as sort key).
                   Falls back to "UNKNOWN".
  full_path      – complete dot-path to the leaf, e.g.
                   Document.Correspondence[0].PartyInfo[1].GivenName
  field_name     – leaf tag name only, e.g.  GivenName
  field_value    – normalised text content

Sort order:  policy_number → full_path  (both ascending)
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from lxml import etree


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert(content: bytes, original_filename: str, output_dir: Path) -> Path:
    """
    Parse *content* as XML, flatten every leaf to a row, sort, and write CSV.

    Returns the Path of the written .csv file.
    """
    root = _parse(content)
    rows = _extract_all_leaves(root)
    _sort(rows)

    stem = Path(original_filename).stem
    out_path = output_dir / f"{stem}.csv"
    _write(rows, out_path)
    return out_path


# ---------------------------------------------------------------------------
# Core: walk every node, emit every leaf
# ---------------------------------------------------------------------------

def _extract_all_leaves(root: etree._Element) -> list[dict]:
    """
    Recursively walk the full tree.
    Every element that has NO element children is a leaf → one CSV row.
    """
    rows: list[dict] = []
    _walk(root, root.tag, rows)

    # Back-fill policy_number once we have seen every leaf
    policy_number = _find_policy_number(rows)
    for row in rows:
        row["policy_number"] = policy_number

    return rows


def _walk(element: etree._Element, path: str, rows: list[dict]) -> None:
    child_elems = [c for c in element if isinstance(c.tag, str)]

    if not child_elems:
        # ── This IS a leaf node ──────────────────────────────────────────
        rows.append({
            "policy_number": "",                    # filled after full scan
            "full_path":     path,
            "field_name":    element.tag,
            "field_value":   (element.text or "").strip(),
        })
        return

    # ── Non-leaf: recurse into every child with sibling-aware indexing ───
    counts = Counter(c.tag for c in child_elems)
    seen:   dict[str, int] = {}

    for child in child_elems:
        seen[child.tag] = seen.get(child.tag, 0) + 1
        idx = seen[child.tag] - 1

        child_path = (
            f"{path}.{child.tag}[{idx}]"
            if counts[child.tag] > 1
            else f"{path}.{child.tag}"
        )
        _walk(child, child_path, rows)


# ---------------------------------------------------------------------------
# Policy number detection
# ---------------------------------------------------------------------------

_POLICY_RE = re.compile(r"policy.*(number|id|no)", re.IGNORECASE)


def _find_policy_number(rows: list[dict]) -> str:
    for row in rows:
        if _POLICY_RE.search(row["field_name"]) and row["field_value"]:
            return row["field_value"]
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Sort & write
# ---------------------------------------------------------------------------

COLUMNS = ["policy_number", "field_name", "field_value", "full_path"]


def _sort(rows: list[dict]) -> None:
    rows.sort(key=lambda r: (r["policy_number"].lower(), r["full_path"].lower()))


def _write(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# XML parser
# ---------------------------------------------------------------------------

def _parse(content: bytes) -> etree._Element:
    parser = etree.XMLParser(remove_comments=True, remove_pis=True, huge_tree=True)
    try:
        return etree.fromstring(content, parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Invalid XML: {exc}") from exc
