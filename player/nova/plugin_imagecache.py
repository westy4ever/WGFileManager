# -*- coding: utf-8 -*-
"""Nova player (local files): posters are local files (or none)."""
import os


def getCachedImage(url, *a, **k):
    return url if url and os.path.isfile(url) else None


def requestImageAsyncPriority(url, callback=None, *a, **k):
    path = getCachedImage(url)
    if path and callback:
        try:
            callback(path)
        except Exception:
            pass
