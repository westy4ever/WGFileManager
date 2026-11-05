# -*- coding: utf-8 -*-
"""Nova player (local files): one playback method per file, nothing to remember."""


def order(cands): return cands
def describe(url): return "local"
def record(*a, **k): pass
