"""The search engine: hybrid dense + sparse retrieval implementing ``Searcher`` (§5, M8).

See ``docs/PLAN.md`` §5 and ``src/reelkb/contract/search_api.py`` for the interface this
package implements. ``python -m reelkb.search.embed`` is the pipeline stage that produces the
vector files this package searches over.
"""
