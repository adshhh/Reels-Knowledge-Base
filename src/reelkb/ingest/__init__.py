"""INGEST (M2): turns message_1.json into the items table (see docs/CONTRACT.md).

This is the only stage that reads the raw export. Everything downstream — fetch, OCR,
speech, fusion — only ever reads the ``items`` table this stage writes, never the export
file itself. That is what makes the export parser "the scope contract" (docs/PLAN.md §2,
Build milestone M2): whatever this stage decides counts as an item is the entire universe
the rest of the pipeline will ever see.
"""

from __future__ import annotations
