"""The web app (M9/M10): category feed, detail view, search, and curation.

Owns nothing but reading and presenting. It opens the database read-only
(``connect_readonly``, AC-8.2) and writes owner actions only through
``reelkb.contract.curation`` (hide / unhide / edit / correct_category), which append to
``curation.jsonl`` / ``corrections.jsonl`` next to the database, never into it.
"""
