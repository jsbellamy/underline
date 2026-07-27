"""DEPRECATED compatibility shim — ``pipeline.numeric_policy`` is canonical.

Re-exports the production numeric policy for legacy prototype imports. New code
should import from ``pipeline.numeric_policy`` directly.
"""

from __future__ import annotations

from pipeline.numeric_policy import NUMERIC_POLICY, canonical_metric, metric_passes

__all__ = ["NUMERIC_POLICY", "canonical_metric", "metric_passes"]
