# -*- coding: utf-8 -*-
"""Nova player (local files): no TMDb lookups."""


def _tmdb_enabled():
    return False


def _tmdb_search_metadata(*a, **k):
    return None
