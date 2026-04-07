from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DiffStatus(str, Enum):
    MISMATCH = "MISMATCH"
    MISSING_IN_A = "MISSING_IN_A"
    MISSING_IN_B = "MISSING_IN_B"


class DiffEntry(BaseModel):
    path: str
    value_a: Optional[str] = None
    value_b: Optional[str] = None
    status: DiffStatus


class ComparisonConfig(BaseModel):
    case_insensitive: bool = False
    numeric_tolerance: float = 0.0
    ignore_fields: list[str] = Field(default_factory=list)


class ComparisonResponse(BaseModel):
    differences: list[DiffEntry]
    total_differences: int
    summary: dict[str, int]
