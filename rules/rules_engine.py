from __future__ import annotations

from models.schemas import ComparisonConfig


class RulesEngine:
    """
    Encapsulates all configurable comparison rules.

    Rules applied in priority order:
    1. Exact string equality (always checked first).
    2. Numeric tolerance (when numeric_tolerance > 0 and both values parse as float).
    3. Case-insensitive string equality (when case_insensitive is True).
    """

    def __init__(self, config: ComparisonConfig) -> None:
        self._config = config
        self._ignore_set: frozenset[str] = frozenset(config.ignore_fields)

    # ------------------------------------------------------------------
    # Value comparison
    # ------------------------------------------------------------------

    def values_match(self, val_a: str | None, val_b: str | None) -> bool:
        """Return True if the two leaf values should be considered equal."""
        a = val_a or ""
        b = val_b or ""

        # Fast path: identical strings
        if a == b:
            return True

        # Numeric tolerance
        if self._config.numeric_tolerance > 0:
            try:
                if abs(float(a) - float(b)) <= self._config.numeric_tolerance:
                    return True
            except ValueError:
                pass

        # Case-insensitive fallback
        if self._config.case_insensitive and a.lower() == b.lower():
            return True

        return False

    # ------------------------------------------------------------------
    # Field filtering
    # ------------------------------------------------------------------

    def should_ignore(self, tag: str) -> bool:
        """Return True if *tag* should be excluded from the comparison."""
        return tag in self._ignore_set
