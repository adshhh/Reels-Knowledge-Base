"""The local labelling page for the evaluation fixtures (docs/PLAN.md §7, DESIGN_RATIONALE
§6). Builds two files by hand, never a model: `eval/holdout_v1.jsonl` (150 stratified reels,
hand-labelled with a category) and `eval/queries_v1.jsonl` (hand-written queries, each judged
against a pooled candidate set). Run with ``python -m reelkb.label``; see `app.py`.
"""
