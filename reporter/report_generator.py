from collections import Counter

from models.schemas import ComparisonResponse, DiffEntry, DiffStatus


def generate_report(differences: list[DiffEntry]) -> ComparisonResponse:
    """
    Convert a flat list of DiffEntry objects into a structured report.

    The summary section breaks down counts by status so consumers can quickly
    gauge the scale and nature of discrepancies without iterating the full list.
    """
    counts = Counter(entry.status for entry in differences)

    summary: dict[str, int] = {
        "total": len(differences),
        DiffStatus.MISMATCH: counts.get(DiffStatus.MISMATCH, 0),
        DiffStatus.MISSING_IN_A: counts.get(DiffStatus.MISSING_IN_A, 0),
        DiffStatus.MISSING_IN_B: counts.get(DiffStatus.MISSING_IN_B, 0),
    }

    return ComparisonResponse(
        differences=differences,
        total_differences=len(differences),
        summary=summary,
    )
