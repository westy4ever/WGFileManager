# -*- coding: utf-8 -*-
"""
WGFileManager — subtitle engine state store.
Backs the vendored engine's _get_config/_set_config calls. Isolated
from WGFileManager's ConfigSubsection so subtitle settings can never
collide with the file manager's own preferences.
"""

import json
import os
import threading

_LOCK = threading.RLock()
_CACHE = None

_STATE_DIRS = [
    "/media/hdd/WGFileManager/subtitles",
    "/tmp/WGFileManager/subtitles",
]


def _state_path():
    for d in _STATE_DIRS:
        try:
            if not os.path.isdir(d):
                os.makedirs(d)
            if os.access(d, os.W_OK):
                return os.path.join(d, "state.json")
        except Exception:
            continue
    return "/tmp/wgfm_subtitle_state.json"


def _load():
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        path = _state_path()
        data = {}
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception:
            data = {}
        _CACHE = data
        return _CACHE


def _save():
    with _LOCK:
        path = _state_path()
        tmp = path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(_CACHE or {}, f)
            os.rename(tmp, path)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass


def get(key, default=""):
    return _load().get(key, default)


def set_(key, value):
    with _LOCK:
        _load()[key] = value
        _save()