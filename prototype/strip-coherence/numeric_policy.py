"""Compatibility forwarder — production ``pipeline.numeric_policy`` is canonical."""

from __future__ import annotations

from pipeline.numeric_policy import NUMERIC_POLICY, canonical_metric, metric_passes

__all__ = ["NUMERIC_POLICY", "canonical_metric", "metric_passes"]
