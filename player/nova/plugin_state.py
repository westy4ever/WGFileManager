# -*- coding: utf-8 -*-
"""WGFileManager / Nova player -- settings and resume positions.

Stands in for NovaPlay's plugin_state: the same function names the player
calls, kept in WGFileManager's own file (/etc/enigma2/wgfilemanager_nova.json),
keyed by the file's path."""
import json
import os
import threading
import time

_STATE_FILE = "/etc/enigma2/wgfilemanager_nova.json"
_STATE_LOCK = threading.RLock()
_cache = {"state": None}
_MAX_POSITIONS = 500


def _load_state():
    with _STATE_LOCK:
        if _cache["state"] is None:
            st = {}
            try:
                with open(_STATE_FILE, "r") as f:
                    st = json.load(f) or {}
            except Exception:
                st = {}
            st.setdefault("config", {})
            st.setdefault("positions", {})
            _cache["state"] = st
        return _cache["state"]


def _save_state(state=None):
    with _STATE_LOCK:
        st = state if state is not None else _load_state()
        pos = st.get("positions") or {}
        if len(pos) > _MAX_POSITIONS:            # keep the newest ones
            keep = sorted(pos.items(), key=lambda kv: -int((kv[1] or {}).get("ts") or 0))[:_MAX_POSITIONS]
            st["positions"] = dict(keep)
        tmp = _STATE_FILE + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(st, f)
            os.rename(tmp, _STATE_FILE)
        except Exception:
            pass


# API keys (subtitle sites, TMDb) are never in the repo: they are read from
# WGFileManager's own keys file, else from an installed NovaPlay's
# api_keys.conf (the same KEY=value lines), so nothing is entered twice.
_KEY_NAMES = ("tmdb_api_key", "subsource_api_key", "subdl_api_key", "opensubtitles_api_key",
              "opensubtitles_user", "opensubtitles_pass", "fanart_api_key")
_OWN_KEYS_FILE = "/etc/enigma2/wgfilemanager_api_keys.conf"
_PLUGINS_DIR = "/usr/lib/enigma2/python/Plugins/Extensions"
_keys_cache = {"at": 0, "keys": None}


def _keys_files():
    files = [_OWN_KEYS_FILE]
    try:
        for d in sorted(os.listdir(_PLUGINS_DIR)):
            if "nova" in d.lower():
                files.append(os.path.join(_PLUGINS_DIR, d, "api_keys.conf"))
    except Exception:
        pass
    return files


def _read_keys():
    """KEY=value lines; the first file that has a key wins (re-read each minute)"""
    now = time.time()
    if _keys_cache["keys"] is not None and now - _keys_cache["at"] < 60:
        return _keys_cache["keys"]
    keys = {}
    for path in _keys_files():
        try:
            with open(path, "r") as f:
                for line in f.read().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k in _KEY_NAMES and v and k not in keys:
                        keys[k] = v
        except Exception:
            continue
    _keys_cache.update(at=now, keys=keys)
    return keys


def _get_config(key, default=""):
    if key == "theme_colour":                  # [2026-11-05] WGFileManager > Setup > Player Theme Colour
        try:
            from Components.config import config
            return config.plugins.wgfilemanager.player_theme_colour.value
        except Exception:
            pass
    value = (_load_state().get("config") or {}).get(key, None)
    if key in _KEY_NAMES and not value:
        value = _read_keys().get(key, None)
    return default if value is None else value


def _set_config(key, value):
    with _STATE_LOCK:
        st = _load_state()
        st.setdefault("config", {})[key] = value
        _save_state(st)


def _get_saved_position(url):
    p = (_load_state().get("positions") or {}).get(url or "") or {}
    pos = int(p.get("pos") or 0)
    return pos if pos > 30 else 0


def _save_position(url, seconds, force=False):
    seconds = int(seconds or 0)
    if not url or 0 < seconds < 30:
        return
    with _STATE_LOCK:
        st = _load_state()
        p = st.setdefault("positions", {}).setdefault(url, {})
        if p.get("pos") == seconds and not force:
            return
        p["pos"] = seconds
        p["ts"] = int(time.time())
        _save_state(st)


def _save_total_duration(url, total):
    try:
        total = int(total or 0)
    except Exception:
        return
    if not url or total <= 60:
        return
    with _STATE_LOCK:
        st = _load_state()
        p = st.setdefault("positions", {}).setdefault(url, {})
        if int(p.get("total") or 0) != total:
            p["total"] = total
            _save_state(st)


def position_info(url):
    """(saved position, total length) for the file list's progress marks"""
    p = (_load_state().get("positions") or {}).get(url or "") or {}
    return int(p.get("pos") or 0), int(p.get("total") or 0)
