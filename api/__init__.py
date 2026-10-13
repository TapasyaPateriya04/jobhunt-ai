"""Local HTTP layer for the React front end.

The modules here only read settings and call the existing backend functions
(``parser``, ``scraper``, ``matching``, ``generator``, ``db``). They add no job
sources, no scoring rules and no prompts of their own.
"""
