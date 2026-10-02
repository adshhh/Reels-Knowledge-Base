"""INGEST (M2): turns message_1.json into the items table (docs/CONTRACT.md). The only stage
that reads the raw export -- everything downstream reads only the `items` table this stage
writes, never the file itself, which is what makes the export parser "the scope contract"
(docs/PLAN.md §2): whatever this stage counts as an item is all the pipeline will ever see.
"""

from __future__ import annotations
