"""Shared four-place ceiling quantization (#38).

Uses Decimal so values that are exactly four-place decimals (e.g. 0.2795) are
not pushed upward by the IEEE float trap in ``math.ceil(value * 10000)``.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

NUMERIC_POLICY = {
    "schema": "gate-numeric-policy/0",
    "precision_decimal_places": 4,
    "rounding": "ceiling",
    "comparison": "metric <= budget",
    "comparison_epsilon": 0,
    "decided_in": "https://github.com/jsbellamy/underline/issues/38",
}


def canonical_metric(value: float) -> float:
    """Ceil ``value`` to four decimal places toward the worse defect."""
    quantized = (Decimal(format(value, ".16f")) * 10_000).to_integral_value(
        rounding=ROUND_CEILING
    ) / Decimal(10_000)
    return float(quantized)
