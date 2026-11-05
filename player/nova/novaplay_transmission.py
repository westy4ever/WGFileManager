# -*- coding: utf-8 -*-
"""Nova player (local files): no torrent client to pause while playing."""


def __getattr__(name):                     # any helper -> harmless no-op
    return lambda *a, **k: None


def pause_for_playback(*a, **k): pass
def resume_after_playback(*a, **k): pass
