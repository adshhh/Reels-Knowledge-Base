"""Fusion + fidelity gate (M5): caption + OCR + transcript -> model -> gate -> `fusion` table.

See `reelkb.fusion.stage` for the orchestration, `reelkb.fusion.fidelity` for the gate itself
(AC-3.1 / AC-FIDELITY), and `reelkb.fusion.model_client` for the model boundary that keeps
`groq` out of the unit-test import graph.
"""

from __future__ import annotations
