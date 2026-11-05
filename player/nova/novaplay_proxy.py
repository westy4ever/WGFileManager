# -*- coding: utf-8 -*-
"""Nova player (local files): no streaming proxy. The names the player
reads exist so its code paths stay valid; the proxy never runs."""
SAFE_UA = "Mozilla/5.0"
_PROXY_PORT = 0
_PROXY_LAST_BYTES = 0
_PROXY_LAST_HIT = 0
_cached_playlist = {}


def start_proxy(*a, **k): return False
def attach_cookies(url, *a, **k): return url
def cached_extract(*a, **k): return None
def _host_of(url): return ""
def abort_open_streams(*a, **k): pass
def ahead_available(*a, **k): return False
def dead_host(*a, **k): return False
def get_stats(*a, **k): return {}
def playlist_fetch_in_progress(*a, **k): return False
def prefetch_hls(*a, **k): pass
def remux_available(*a, **k): return False
