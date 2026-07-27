"""Production canonical metric quantization and comparison (#38)."""

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


def metric_passes(metric: float, budget: float) -> bool:
    """Inclusive pass at ``metric <= budget`` with zero comparison epsilon."""
    return canonical_metric(metric) <= budget
