# -*- coding: utf-8 -*-
"""
novaplay_subtitles.py — Subtitle engine for NovaPlay Media Center
==================================================================
- SubSource + OpenSubtitles.com online search & download (Arabic-first)
- Local subtitle auto-match (strict scoring, episode markers)
- Folder browser with [BEST] tagging
- Last-subtitle memory: re-attaches remembered subtitle (+sync) on replay
- Subtitle sync shift (+/-250 ms) via cached SRT rewrite — image-independent
- Auto-attach on playback start (optional)
- Settings screen with cache clearing (NovaSubtitleSettings)

Fixes vs. the original revision:
  * maybe_resume_subtitle no longer runs a 3000-entry disk scan on the
    MAIN thread (multi-second UI freeze 3.5s after playback start).
  * Downloaded text subtitles are normalized to UTF-8 at write time
    (cp1256 Arabic subs used to render garbled unless you happened to
    sync-shift them, which re-encoded as a side effect).
  * NovaOnlineSubsScreen: results and displayed labels are kept
    index-aligned (an empty label used to shift every later selection
    onto the WRONG subtitle).
  * Arabic-only titles now try TMDB for an English title before failing.
  * adjust_sync/reset_sync failures actually retry (via _apply_with_retry).
  * Negative sync shifts drop cues that shift fully into the past
    instead of emitting zero-duration cues at 00:00:00,000.
  * SubSource fallback queries use an 8s timeout instead of 18s each.
  * callInMainThread comes from the shared novaplay_thread module
    (fallback copy kept in case that file is missing).
  * JSON searches go through extractors.base.fetch (gzip/charset/retry);
    BINARY downloads stay on raw urlopen — base.fetch decodes text and
    would corrupt zip payloads.
  * find_best_local_subtitle also scans the downloads dir, so sidecar
    subtitles saved by plugin_downloads auto-match on later plays.

  * v4.5: adjust_sync/reset_sync zero any live STUDIO in-memory offset
    before re-attaching the shifted file — the file now carries the
    FULL shift; a live studio offset would double-apply
    (STUDIO.attach() preserves a live offset across re-attach).

  * [PATCH 91] OpenSubtitles.com login support (username + password):
    /login → Bearer token (cached ~20h) → /download. Real HTTP errors
    reported (401/403 = bad login, 406 = quota). Also added the
    credentials to the API Keys picker.

NovaSubtitleBrowser._refresh and NovaSubtitleSettings are the plugin's
ORIGINAL classes (verbatim); only the browser's _ok/_cancel handlers are
new code (the original handlers were never shared).

plugin.py integration (Edits A–D):
  A) from novaplay_subtitles import (maybe_resume_subtitle,
     remember_subtitle, apply_subtitle, get_subtitle_state,
     SYNC_STEP_MS, NovaSubtitleSettings)
  B) call maybe_resume_subtitle(self.session, self.title, self._item_url)
     right after _start_pos_tracker(...) in __onConfirmed
  C) bind a free key (e.g. blue) to a subtitle menu — see the menu
     methods in the re-add instructions
  D) open NovaSubtitleSettings from the plugin's settings screen

Adapted from the XtreamNew vodplayer engine, reworked for NovaPlay.
"""

import os
import re
import json
import time
import hashlib
import zipfile
import threading

try:
    from urllib.parse import quote, unquote, urlencode
except ImportError:
    from urllib import quote, unquote, urlencode

try:
    import urllib.request as _urlreq
except ImportError:
    import urllib2 as _urlreq

try:
    from io import BytesIO
except ImportError:
    try:
        from StringIO import StringIO as BytesIO
    except ImportError:
        BytesIO = None

from Screens.Screen import Screen
from .novaplay_choice import NovaMessageBox as MessageBox
from .novaplay_choice import NovaChoiceBox as ChoiceBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from enigma import eTimer

try:
    from Screens.VirtualKeyBoard import VirtualKeyBoard
except Exception:
    VirtualKeyBoard = None

try:
    from Components.FileList import FileList
except Exception:
    FileList = None

try:
    from .plugin_state import _get_config, _set_config
except Exception:
    _get_config = None
    _set_config = None

# shared main-thread dispatcher (leaf module — no circular imports)
try:
    from .novaplay_thread import callInMainThread
except Exception:
    # fallback: self-contained copy, so the module still imports if
    # novaplay_thread.py is missing
    _MAIN_LOCK = threading.Lock()
    _MAIN_QUEUE = []
    _MAIN_TIMER = None

    def _drain_main_queue():
        global _MAIN_TIMER
        with _MAIN_LOCK:
            items = list(_MAIN_QUEUE)
            del _MAIN_QUEUE[:]
        for _f, _a, _kw in items:
            try:
                _f(*_a, **_kw)
            except Exception:
                pass
        with _MAIN_LOCK:
            pending = bool(_MAIN_QUEUE)
        if pending and _MAIN_TIMER is not None:
            try:
                _MAIN_TIMER.start(50, True)
            except Exception:
                pass

    def callInMainThread(func, *args, **kwargs):
        global _MAIN_TIMER
        with _MAIN_LOCK:
            _MAIN_QUEUE.append((func, args, kwargs))
            need_timer = (_MAIN_TIMER is None)
            if need_timer:
                try:
                    _MAIN_TIMER = eTimer()
                    _MAIN_TIMER.callback.append(_drain_main_queue)
                except Exception:
                    _MAIN_TIMER = None
        if _MAIN_TIMER is not None:
            try:
                _MAIN_TIMER.start(50, True)
            except Exception:
                pass
        else:
            try:
                from twisted.internet import reactor
                reactor.callFromThread(_drain_main_queue)
            except Exception:
                pass

# optional: route JSON API reads through the extractor transport
# (gzip/deflate/charset handling + retries). BINARY downloads never go
# through this — fetch() decodes bodies as text and would corrupt zips.
try:
    from .extractors.base import fetch as _BASE_FETCH
except Exception:
    _BASE_FETCH = None

PLUGIN_DIR = os.path.dirname(__file__)
SAFE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
_OS_UA = "NovaPlayE2/4.0"

SUBTITLE_EXT_RE = re.compile(r"\.(srt|sub|txt|ass|ssa|vtt)$", re.I)
AUTO_SUB_MIN_SCORE = 200      # strict-score threshold for auto-attach
MAX_BROWSER_ENTRIES = 800     # cap folder browser list
MAX_SCAN_ENTRIES = 3000       # cap auto-match directory scan
SYNC_STEP_MS = 250            # subtitle sync adjustment step

_state_cfg = {}


def _cfg(name, default=""):
    """Read config NovaPlay-style ("true"/"false"), with in-memory fallback."""
    if _get_config is not None:
        try:
            v = _get_config(name, "")
            if v not in (None, ""):
                return v
        except Exception:
            pass
    return _state_cfg.get(name, default)


def _cfg_bool(name, default=False):
    v = str(_cfg(name, "true" if default else "false")).strip().lower()
    return v in ("1", "true", "yes", "on")


def _cfg_set(name, value):
    _state_cfg[name] = value
    if _set_config is not None:
        try:
            _set_config(name, value)
        except Exception:
            pass


def _fmt_secs(value):
    try:
        value = int(value)
    except Exception:
        value = 0
    if value < 0:
        value = 0
    h, rest = divmod(value, 3600)
    m, s = divmod(rest, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%02d:%02d" % (m, s)


def _fmt_offset(ms):
    return ("%+d ms" % int(ms)) if ms else "0 ms"


# =============================================================================
#  Title / name cleaning
# =============================================================================

def clean_play_title(title):
    """Strips metadata-dict leaks and de-duplicates series titles:
    'Show - 1x1 Show Name...' -> 'Show - 1x1'."""
    txt = str(title or "").strip()
    if not txt:
        return ""
    txt = re.sub(r'\s*\{[\'"]?_unified_metadata.*$', "", txt).strip()
    txt = re.sub(r'\s*\|\s*\{[\'"]?_unified_metadata.*$', "", txt).strip()
    m = re.match(r"^(.*?)\s+-\s+((?:S\d+E\d+)|(?:\d+x\d+))\s+(.+)$", txt, re.I)
    if m:
        series = (m.group(1) or "").strip()
        marker = (m.group(2) or "").strip()
        tail = (m.group(3) or "").strip()
        norm_series = re.sub(r"[^a-z0-9]+", " ", series.lower()).strip()
        norm_tail = re.sub(r"[^a-z0-9]+", " ", tail.lower()).strip()
        if norm_series and norm_tail and (
            norm_series.startswith(norm_tail[:min(len(norm_tail), 18)]) or
            norm_tail.startswith(norm_series[:min(len(norm_series), 18)])
        ):
            txt = "%s - %s" % (series, marker)
    return txt


def clean_subtitle_query(title, url=""):
    """Build the best clean English-ish query from a (possibly Arabic) title."""
    txt = str(title or "").strip()
    if not txt:
        txt = str(url or "").strip()
    txt = re.sub(r"\s+-\s+Trailer\s*$", " ", txt, flags=re.I)
    txt = re.sub(r"\s+\|\s+.*$", " ", txt)
    txt = clean_play_title(txt)
    txt = re.sub(r"\\[cCpPbBuU][0-9A-Fa-f]{0,8}", " ", txt)
    low = _clean_name(txt)
    return low


def _clean_name(text):
    text = str(text or "").lower()
    text = os.path.basename(text)
    text = os.path.splitext(text)[0]
    text = re.sub(r"[._\-]+", " ", text)
    text = re.sub(r"\b(1080p|720p|480p|2160p|4k|x264|x265|h264|h265|hevc|bluray|blu-ray|web-?dl|web-?rip|web|hdrip|dvdrip|brrip|hdts|cam|nf|amzn|hbo|dsnp|proper|repack|extended|remastered|unrated|aac|ac3|eac3|ddp\d*|dd\+?|atmos|dts(hd)?|ma|yify|yts|tsx|hc|korsub|subs|ara|eng|arabic|english|مترجم|مدبلج|فيلم|مسلسل|حلقة|كامل)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _search_terms(title, url="", extra=""):
    candidates = []
    for item in (title, extra, url):
        txt = _clean_name(item)
        if txt and txt not in candidates:
            candidates.append(txt)
    expanded = []
    for txt in candidates:
        expanded.append(txt)
        for part in re.split(r"\s+", txt):
            if len(part) >= 3 and part not in expanded:
                expanded.append(part)
    return [x for x in expanded if x]


_STOPWORDS = set([
    'the', 'and', 'for', 'with', 'from', 'web', 'webrip', 'webdl', 'bluray',
    'hdrip', 'dvdrip', 'x264', 'x265', 'h264', 'h265', 'aac', 'ddp', 'atmos',
    'proper', 'repack', 'yts', 'brrip', 'movie', 'film', 'episode', 'season',
    'part', 'eng', 'english', 'arabic', 'ara', 'sub', 'subs', 'yify', 'final',
    'last', 'new', 'all', 'full',
])


def _significant_words(terms):
    words, seen = [], set()
    for term in (terms or []):
        clean = _clean_name(term)
        if not clean:
            continue
        for word in clean.split():
            if len(word) < 3 or word in _STOPWORDS or word in seen:
                continue
            seen.add(word)
            words.append(word)
    words.sort(key=lambda x: (-len(x), x))
    return words


def _episode_markers(terms):
    joined = " ".join([_clean_name(x) for x in (terms or [])])
    found = []
    for pat in (r"\bs\d{1,2}e\d{1,2}\b", r"\b\d{1,2}x\d{1,2}\b"):
        for m in re.findall(pat, joined, re.I):
            val = str(m).lower()
            if val not in found:
                found.append(val)
    return found


def _score_name(name, terms):
    low = _clean_name(name)
    if not low:
        return 0
    score = 0
    for term in (terms or []):
        term = _clean_name(term)
        if not term:
            continue
        if low == term:
            score += 500
        elif low.startswith(term) or term.startswith(low):
            score += 250
        elif term in low:
            score += 120
        else:
            pieces = [p for p in term.split(' ') if len(p) >= 3]
            hits = sum(1 for p in pieces if p in low)
            score += hits * 35
    if re.search(r"\b(ar|ara|arabic|english|eng|forced)\b", low):
        score += 10
    return score


def strict_score(name, terms, words, markers):
    """Strict mode: requires at least one strong word hit, rewards episode markers."""
    low = _clean_name(name)
    if not low:
        return 0
    hit_words = [w for w in (words or []) if w in low]
    if words and not hit_words:
        return 0
    score = 0
    for w in hit_words:
        score += 80 + min(len(w), 12)
    for term in (terms or []):
        term = _clean_name(term)
        if not term:
            continue
        if low == term:
            score += 500
        elif low.startswith(term):
            score += 260
        elif term in low:
            score += 120
    if markers:
        marker_hit = False
        for mk in markers:
            if mk in low:
                score += 160
                marker_hit = True
        if not marker_hit:
            score -= 120
    return score


# =============================================================================
#  Directory scanning (py2-safe)
# =============================================================================

def _iter_sub_entries(path):
    """Yield (name, full_path, is_dir) for subtitle files + dirs, bounded."""
    try:
        if hasattr(os, "scandir"):
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if entry.is_dir():
                            yield (entry.name, entry.path, True)
                        elif SUBTITLE_EXT_RE.search(entry.name):
                            yield (entry.name, entry.path, False)
                    except Exception:
                        continue
        else:
            for name in os.listdir(path):
                full = os.path.join(path, name)
                try:
                    if os.path.isdir(full):
                        yield (name, full, True)
                    elif SUBTITLE_EXT_RE.search(name):
                        yield (name, full, False)
                except Exception:
                    continue
    except Exception:
        return


def subtitle_dir():
    d = _cfg("subtitle_dir", "/media/hdd/subtitles")
    return d if d and os.path.isdir(d) else ""


# =============================================================================
#  Subtitle memory (per item_url — detail-page URL, so it survives
#  server switches and restarts, same key as resume position)
# =============================================================================

def _subs_memory_path():
    base = "/media/hdd/NovaPlay/cache"
    if not os.path.exists("/media/hdd"):
        base = os.path.join(PLUGIN_DIR, "cache")
    try:
        if not os.path.exists(base):
            os.makedirs(base)
    except Exception:
        pass
    return os.path.join(base, "subtitle_memory.json")


def _load_subs_memory():
    try:
        with open(_subs_memory_path(), "r") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_subs_memory(data):
    try:
        # keep memory bounded: newest 400 entries
        if len(data) > 400:
            items = sorted(data.items(), key=lambda kv: int((kv[1] or {}).get("time") or 0), reverse=True)
            data = dict(items[:400])
        with open(_subs_memory_path(), "w") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def remember_subtitle(item_url, path, offset_ms=0):
    item_url = str(item_url or "").strip()
    if not item_url or not path:
        return
    data = _load_subs_memory()
    data[item_url] = {"path": str(path), "offset_ms": int(offset_ms or 0),
                      "time": int(time.time()), "on": True}
    _save_subs_memory(data)
    global _CURRENT_SUB
    # [FIX] also reset _orig_path: a stale one from an earlier (synced) file made
    # the next sync step shift the OLD file. With an offset, the caller has
    # already put the shifted copy in "path" -- keep it.
    upd = {"item_url": item_url, "_orig_path": str(path), "offset_ms": int(offset_ms or 0)}
    if not offset_ms:
        upd["path"] = str(path)
    _CURRENT_SUB.update(upd)


def recall_subtitle(item_url, only_on=False):
    """the subtitle remembered for this title; only_on: not if it was turned
    off with YELLOW (what a resumed film uses)"""
    entry = _load_subs_memory().get(str(item_url or "").strip())
    if isinstance(entry, dict) and entry.get("path") and os.path.exists(entry["path"]):
        if only_on and entry.get("on") is False:
            return "", 0
        return entry.get("path"), int(entry.get("offset_ms") or 0)
    return "", 0


def set_subtitle_on(item_url, on):
    """[2026-10-31] YELLOW: remember whether subtitles were on for this title,
    so resuming it brings them back (or keeps them off). The file is kept."""
    item_url = str(item_url or "").strip()
    data = _load_subs_memory()
    entry = data.get(item_url)
    if isinstance(entry, dict):
        entry["on"] = bool(on)
        _save_subs_memory(data)


# current in-session subtitle state (for sync adjustments)
_CURRENT_SUB = {"item_url": "", "path": "", "offset_ms": 0}


# =============================================================================
#  SubSource online provider
# =============================================================================

def _ss_cache_dir():
    base = "/media/hdd/NovaPlay/cache/subsource"
    if not os.path.exists("/media/hdd"):
        base = os.path.join(PLUGIN_DIR, "cache", "subsource")
    try:
        if not os.path.exists(base):
            os.makedirs(base)
    except Exception:
        pass
    return base


def _ss_api_key():
    return str(_cfg("subsource_api_key", "")).strip()


def _ss_headers(api_key):
    return {
        "User-Agent": SAFE_UA,
        "Accept": "application/json, */*",
        "X-API-Key": str(api_key or "").strip(),
    }


def _ss_read_json(url, api_key, timeout=16):
    # JSON search endpoint: prefer the extractor transport (handles
    # forced gzip, charsets, retries). Fallback: plain urlopen.
    if _BASE_FETCH is not None:
        try:
            text, _final = _BASE_FETCH(url, extra_headers=_ss_headers(api_key))
            if text:
                return json.loads(text)
            return None
        except Exception:
            return None
    try:
        req = _urlreq.Request(url, headers=_ss_headers(api_key))
        raw = _urlreq.urlopen(req, timeout=timeout).read()
        try:
            txt = raw.decode('utf-8', 'ignore')
        except Exception:
            txt = str(raw or '')
        return json.loads(txt)
    except Exception:
        return None


def _ss_collect_dicts(obj, out=None, depth=0):
    if out is None:
        out = []
    if depth > 5:
        return out
    if isinstance(obj, dict):
        low_keys = set([str(k).lower() for k in obj.keys()])
        if any(k in low_keys for k in ('id', 'subtitle_id', 'subtitleid')) and \
           any(k in low_keys for k in ('title', 'release', 'name', 'file_name', 'filename', 'language')):
            out.append(obj)
        for v in obj.values():
            _ss_collect_dicts(v, out, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _ss_collect_dicts(item, out, depth + 1)
    return out


def _ss_value(row, keys):
    if not isinstance(row, dict):
        return ''
    for key in keys:
        for k, v in row.items():
            if str(k).lower() == key.lower():
                if isinstance(v, (str, int, float)):
                    return str(v)
                return v
    return ''


def _ss_looks_like_content(value):
    txt = str(value or '')
    if not txt:
        return False
    if re.search(r'\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}', txt):
        return True
    if txt.count('-->') >= 1:
        return True
    if len(txt) > 160 and ('-->' in txt or '\n' in txt or '\\N' in txt):
        return True
    return False


def _ss_clean_label(value):
    txt = str(value or '').strip()
    if not txt:
        return ''
    if _ss_looks_like_content(txt):
        return ''
    txt = txt.replace('\r', ' ').replace('\n', ' ')
    txt = re.sub(r'\s+', ' ', txt).strip()
    if _ss_looks_like_content(txt):
        return ''
    if '/' in txt or '\\' in txt:
        base = os.path.basename(txt.replace('\\', '/'))
        if base:
            txt = base
    txt = txt.strip(' ._-')
    low = txt.lower()
    if low in ('true', 'false', 'none', 'null', 'success', 'ok', 'data', 'results'):
        return ''
    if re.match(r'^\d{3,}$', txt):
        return ''
    if re.match(r'^[0-9a-f]{16,}$', low):
        return ''
    if low.startswith('subsource ') and re.search(r'\d{3,}', low):
        return ''
    if len(txt) > 150:
        txt = txt[:150].strip()
    return txt


def _ss_iter_release_info(value):
    out = []
    if isinstance(value, (list, tuple)):
        for item in value:
            out.extend(_ss_iter_release_info(item))
    elif isinstance(value, dict):
        for key in ('release', 'releaseName', 'release_name', 'fileName',
                    'file_name', 'filename', 'name', 'title'):
            val = _ss_value(value, (key,))
            label = _ss_clean_label(val)
            if label:
                out.append(label)
    else:
        label = _ss_clean_label(value)
        if label:
            out.append(label)
    clean, seen = [], set()
    for item in out:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            clean.append(item)
    return clean


def _ss_pick_release_title(row, sid=''):
    if not isinstance(row, dict):
        return ''
    release_info = _ss_value(row, ('releaseInfo', 'release_info', 'releases', 'releaseInfos'))
    releases = _ss_iter_release_info(release_info)
    if releases:
        return releases[0]
    keys = (
        'release_name', 'releaseName', 'release_title', 'releaseTitle',
        'movie_release_name', 'movieReleaseName', 'release',
        'file_name', 'fileName', 'filename', 'file',
        'subtitle_name', 'subtitleName', 'full_name', 'fullName',
        'display_name', 'displayName', 'name', 'title',
    )
    for key in keys:
        val = _ss_value(row, (key,))
        if isinstance(val, dict):
            for subkey in keys:
                subval = _ss_value(val, (subkey,))
                label = _ss_clean_label(subval)
                if label and label != str(sid or '').strip():
                    return label
        label = _ss_clean_label(val)
        if label and label != str(sid or '').strip():
            return label
    return ''


def _ss_build_release_titles(row, sid=''):
    if not isinstance(row, dict):
        return []
    release_info = _ss_value(row, ('releaseInfo', 'release_info', 'releases', 'releaseInfos'))
    releases = _ss_iter_release_info(release_info)
    if releases:
        return releases
    title = _ss_pick_release_title(row, sid)
    return [title] if title else []


# ── [2026-11-04] subtitle languages (Settings > Subtitle Languages) ─────
# code, name, flag file (images/flags), SubSource names, OpenSubtitles
# codes, SubDL codes. Arabic and English are on by default.
SUB_LANGS = (
    ("ar", u"Arabic", "eg", ("arabic",), "ar", "AR"),
    ("en", u"English", "gb", ("english",), "en", "EN"),
    ("tr", u"Turkish", "tr", ("turkish",), "tr", "TR"),
    ("fr", u"French", "fr", ("french",), "fr", "FR"),
    ("es", u"Spanish", "es", ("spanish",), "es", "ES"),
    ("de", u"German", "de", ("german",), "de", "DE"),
    ("it", u"Italian", "it", ("italian",), "it", "IT"),
    ("pt", u"Portuguese", "br", ("portuguese", "brazillian_portuguese"), "pt-pt,pt-br", "PT,BR_PT"),
)
SUB_LANG_DEFAULT = "ar,en"
_LANG_ALIAS = {
    "ar": ("arabic", "ar", "ara", u"العربية", u"عربي"),
    "en": ("english", "en", "eng"),
    "tr": ("turkish", "tr", "tur", u"türkçe", "turkce"),
    "fr": ("french", "fr", "fre", "fra", u"français", "francais"),
    "es": ("spanish", "es", "spa", "spanish latin america", "spanish (latin america)", "es-419",
           "es-mx", "es-es", "ea", u"español", "espanol"),
    "de": ("german", "de", "ger", "deu", "deutsch"),
    "it": ("italian", "it", "ita", "italiano"),
    "pt": ("portuguese", "pt", "por", "pt-pt", "pt-br", "pb", "pob", "brazilian portuguese",
           "brazillian portuguese", "portuguese (brazil)", "br_pt", "br pt", u"português", "portugues"),
}
_ALIAS_TO_CODE = dict((a, c) for c, names in _LANG_ALIAS.items() for a in names)


def lang_code(raw):
    """a provider's language (name or code, any spelling) -> "ar" / "en" /
    "tr" / ... ("other" when unknown)"""
    t = re.sub(r"\s+", " ", str(raw or "").strip().lower().replace("_", " "))
    if not t:
        return "other"
    if t in _ALIAS_TO_CODE:
        return _ALIAS_TO_CODE[t]
    t2 = t.replace(" ", "_")
    if t2 in _ALIAS_TO_CODE:
        return _ALIAS_TO_CODE[t2]
    return "other"


def lang_info(code):
    """-> (name, flag png path or "")"""
    for c, name, flag, _ss, _os, _sd in SUB_LANGS:
        if c == code:
            p = os.path.join(PLUGIN_DIR, "images", "flags", flag + ".png")
            return name, (p if os.path.exists(p) else "")
    return u"", ""


_LANG_ONLY = []          # [2026-11-04] set while searching one extra language


def sub_langs():
    """the languages ticked in Settings, in table order (at least one) --
    or the one language being searched from the results' language list"""
    if _LANG_ONLY:
        return list(_LANG_ONLY)
    raw = str(_cfg("subtitle_langs", SUB_LANG_DEFAULT) or SUB_LANG_DEFAULT)
    want = set(x.strip().lower() for x in raw.split(",") if x.strip())
    out = [c for c, *_r in SUB_LANGS if c in want]
    return out or ["ar", "en"]


def set_sub_langs(codes):
    codes = [c for c, *_r in SUB_LANGS if c in set(codes or [])] or ["ar", "en"]
    try:
        if _set_config is not None:
            _set_config("subtitle_langs", ",".join(codes))
    except Exception:
        pass
    return codes


def _lang_row(code):
    for r in SUB_LANGS:
        if r[0] == code:
            return r
    return None


# [2026-11-04] the film the player is showing: TMDb id + year, so every
# provider looks for THAT film (a new film with an old name -- Resident Evil
# 2026 -- got the 2002 film's subtitles). Set by the player before a search.
SEARCH_HINT = {"tmdb_id": None, "kind": "movie", "year": ""}


def set_search_hint(tmdb_id=None, kind="movie", year=""):
    SEARCH_HINT.update({"tmdb_id": tmdb_id or None, "kind": kind or "movie", "year": str(year or "")[:4]})


def _year_of(*vals):
    for v in vals:
        m = re.search(r"(19\d{2}|20\d{2})", str(v or ""))
        if m:
            return m.group(1)
    return ""


def _year_ok(found, want):
    """unknown on either side -> fine; else within one year"""
    if not found or not want:
        return True
    try:
        return abs(int(found) - int(want)) <= 1
    except ValueError:
        return True


def _ss_language_rank(item):
    """Arabic first, then English, then the other ticked languages in the
    table order, anything else last"""
    try:
        code = lang_code((item or {}).get('language'))
        if code == "other":
            m = re.match(r"\[([^\]]+)\]", str((item or {}).get('label') or ''))
            code = lang_code(m.group(1)) if m else "other"
    except Exception:
        code = "other"
    order = [r[0] for r in SUB_LANGS]
    return order.index(code) if code in order else len(order)


def _ss_normalize_results(data, query_terms=None):
    rows = _ss_collect_dicts(data)
    terms = _search_terms(' '.join(query_terms or []))
    results, seen = [], set()
    for row in rows:
        sid = _ss_value(row, ('subtitleId', 'subtitle_id', 'id', 'subtitleid'))
        if isinstance(sid, dict):
            sid = _ss_value(sid, ('subtitleId', 'subtitle_id', 'id', 'subtitleid'))
        sid = str(sid or '').strip()
        if not sid:
            continue
        lang = _ss_value(row, ('language', 'lang', 'language_name', 'languageName'))
        if isinstance(lang, dict):
            lang = _ss_value(lang, ('name', 'language', 'code'))
        lang = str(lang or '').strip()
        release_titles = _ss_build_release_titles(row, sid)
        if not release_titles:
            release_titles = ['Subtitle %s' % sid]
        for rel_title in release_titles:
            title = _ss_clean_label(rel_title)
            if not title:
                continue
            unique_key = sid + '|' + title.lower()
            if unique_key in seen:
                continue
            seen.add(unique_key)
            score = _score_name(title, terms) if terms else 0
            if lang.lower() in ('arabic', 'ar', 'ara', 'العربية'):
                score += 80
            elif lang:
                score += 5
            label = ('[%s] %s' % (lang, title)) if lang else title
            results.append({'id': sid, 'title': title, 'language': lang,
                            'score': score, 'label': label})
    results.sort(key=lambda x: (_ss_language_rank(x), -int(x.get('score') or 0),
                                x.get('label', '').lower()))
    return results[:80]


def _ss_add_unique(out, value):
    try:
        value = str(value or '').strip()
    except Exception:
        value = ''
    if not value:
        return
    value = re.sub(r'\s+', ' ', value).strip()
    key = value.lower()
    for old in out:
        if str(old or '').strip().lower() == key:
            return
    out.append(value)


def _ss_title_fallbacks(title):
    """Base-first candidate list: 'Greenland 2 Migration' -> ['Greenland 2', full]."""
    raw = str(title or '').strip()
    out = []
    if not raw:
        return out
    clean = re.sub(r'[_\.\-]+', ' ', raw)
    clean = re.sub(r'\s+', ' ', clean).strip()
    base_candidates = []
    for sep in (':', '|', ' - ', ' – ', ' — '):
        if sep in raw:
            _ss_add_unique(base_candidates, raw.split(sep, 1)[0].strip())
    m = re.match(r'^(.+?\b\d{1,2})\b\s+.+$', clean)
    if m:
        _ss_add_unique(base_candidates, m.group(1).strip())
    words = clean.split()
    if len(words) > 3:
        _ss_add_unique(base_candidates, ' '.join(words[:3]))
    if len(words) > 2:
        _ss_add_unique(base_candidates, ' '.join(words[:2]))
    for item in base_candidates:
        _ss_add_unique(out, item)
    _ss_add_unique(out, raw)
    return out


def subsource_search(title, video_url='', api_key=''):
    api_key = str(api_key or '').strip()
    if not api_key:
        return False, 'SubSource API key is empty.\nAdd it in NovaPlay settings.', []
    query = clean_subtitle_query(title, video_url)
    if not query:
        return False, 'No usable title for subtitle search.', []
    base = 'https://api.subsource.net/api/v1'

    year = ''
    m = re.search(r'\b(19\d{2}|20\d{2})\b', query)
    if m:
        year = m.group(1)
    q = re.sub(r'\b(19\d{2}|20\d{2})\b', ' ', query)
    q = re.sub(r'\s+', ' ', q).strip()

    queries = [q]
    for cand in _ss_title_fallbacks(q):
        cq = _clean_name(cand)
        if cq and cq not in queries:
            queries.append(cq)
    parts = q.split()
    if len(parts) > 5 and ' '.join(parts[:5]) not in queries:
        queries.append(' '.join(parts[:5]))
    if len(parts) > 3 and ' '.join(parts[:3]) not in queries:
        queries.append(' '.join(parts[:3]))
    queries = queries[:5]

    movie_ids = []
    last_data = None
    for q_idx, query_str in enumerate(queries):
        # fallback queries get a short timeout — 5 x 18s sequential
        # misses used to cost ~90s before the "no match" message.
        q_timeout = 18 if q_idx == 0 else 8
        params = {'searchType': 'text', 'q': query_str, 'type': 'all'}
        if year:
            params['year'] = year
        url = base + '/movies/search?' + urlencode(params)
        data = _ss_read_json(url, api_key, timeout=q_timeout)
        if data is None and year:
            params.pop('year', None)
            url = base + '/movies/search?' + urlencode(params)
            data = _ss_read_json(url, api_key, timeout=q_timeout)
        if data is None:
            continue
        last_data = data
        try:
            rows = data.get('data') or data.get('results') or []
        except Exception:
            rows = []
        if isinstance(rows, dict):
            rows = [rows]
        if year:
            # [2026-11-04] only the film of that year (when SubSource says the year)
            rows = [r for r in rows if not isinstance(r, dict) or _year_ok(
                _year_of(r.get('releaseYear'), r.get('year'), r.get('release_date'), r.get('releaseDate')), year)]
        for row in rows:
            if not isinstance(row, dict):
                continue
            mid = str(row.get('movieId') or row.get('movie_id') or row.get('id') or '').strip()
            if mid and mid not in movie_ids:
                movie_ids.append(mid)
        if movie_ids:
            break

    if not movie_ids:
        if last_data is not None:
            return False, 'No SubSource match found for:\n%s' % query, []
        return False, 'SubSource search failed.\nCheck API key / connection.', []

    results = []
    for movie_id in movie_ids[:3]:
        for lang in [n for c in sub_langs() for n in (_lang_row(c) or ((), (), (), ()))[3]]:
            params = {'movieId': movie_id, 'language': lang, 'limit': 100, 'sort': 'newest'}
            data = _ss_read_json(base + '/subtitles?' + urlencode(params), api_key, timeout=25)
            if data is None:
                continue
            results.extend(_ss_normalize_results(data, [query, video_url]))
        if results:
            break

    if not results:
        return False, 'No SubSource subtitles found for:\n%s' % query, []

    unique, seen = [], set()
    for item in sorted(results, key=lambda x: (_ss_language_rank(x), -int(x.get('score') or 0),
                                               x.get('label', '').lower())):
        sid = str(item.get('id') or '')
        tkey = str(item.get('title') or item.get('label') or '').strip().lower()
        key = sid + '|' + tkey
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return True, '', unique[:80]


def _ss_pick_srt_from_zip(raw, filename_base):
    if BytesIO is None:
        return None, ''
    try:
        zf = zipfile.ZipFile(BytesIO(raw))
    except Exception:
        return None, ''
    best_name, best_data = '', None
    try:
        names = zf.namelist()
    except Exception:
        names = []
    for name in names:
        low = str(name or '').lower()
        if low.endswith(('.srt', '.sub', '.txt', '.ass', '.ssa', '.vtt')) and not low.endswith('/'):
            try:
                data = zf.read(name)
                if data:
                    best_name = os.path.basename(name) or (filename_base + '.srt')
                    best_data = data
                    if low.endswith('.srt'):
                        break
            except Exception:
                pass
    return best_data, best_name


def _normalize_text_subtitle_bytes(data):
    """Best-effort convert a text subtitle to UTF-8.
    FIX: cp1256 Arabic subs used to stay cp1256 on disk unless the user
    sync-shifted them (which re-encoded as a side effect)."""
    if not data:
        return data
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):  # UTF-16 BOM
        try:
            return data.decode("utf-16").encode("utf-8")
        except Exception:
            return data
    for enc in ("utf-8-sig", "utf-8", "cp1256", "iso-8859-6"):
        try:
            return data.decode(enc).encode("utf-8")
        except (UnicodeDecodeError, LookupError):
            continue
    return data  # last resort: pass through untouched


def _write_subtitle_file(data, out_name):
    out_path = os.path.join(_ss_cache_dir(), out_name)
    tmp = out_path + ".tmp"
    try:
        if out_name.lower().endswith((".srt", ".txt", ".ass", ".ssa", ".vtt")):
            # NB: ".sub" intentionally excluded — VobSub .sub is binary
            # (idx/sub pair); text conversion would corrupt it.
            data = _normalize_text_subtitle_bytes(data)
        with open(tmp, 'wb') as f:
            f.write(data)
        os.rename(tmp, out_path)   # atomic on same dir, py2-safe
        return out_path
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return ""


def subsource_download(subtitle_id, title, api_key=''):
    # NOTE: binary payload (possibly a zip) — deliberately raw urlopen,
    # NOT extractors.base.fetch (which decodes bodies as text).
    api_key = str(api_key or '').strip()
    subtitle_id = str(subtitle_id or '').strip()
    if not api_key or not subtitle_id:
        return False, 'Missing SubSource data.', ''
    url = 'https://api.subsource.net/api/v1/subtitles/%s/download' % subtitle_id
    try:
        req = _urlreq.Request(url, headers=_ss_headers(api_key))
        raw = _urlreq.urlopen(req, timeout=25).read()
    except Exception:
        return False, 'SubSource download failed.', ''
    if not raw:
        return False, 'Empty SubSource subtitle file.', ''
    filename_base = re.sub(r'[^A-Za-z0-9_\-\.]+', '_', _clean_name(title) or
                           ('subsource_%s' % subtitle_id)).strip('._') or ('subsource_%s' % subtitle_id)
    data, out_name = raw, filename_base + '.srt'
    if raw[:2] == b'PK':
        picked, picked_name = _ss_pick_srt_from_zip(raw, filename_base)
        if not picked:
            return False, 'Downloaded zip has no supported subtitle file.', ''
        data = picked
        out_name = picked_name or out_name
    elif raw[:1] in (b'{', b'['):
        got = False
        try:
            js = json.loads(raw.decode('utf-8', 'ignore'))
            link = _ss_value(js, ('url', 'download_url', 'downloadUrl', 'link'))
            if link:
                fetched = _urlreq.urlopen(
                    _urlreq.Request(str(link), headers=_ss_headers(api_key)),
                    timeout=25).read()
                if fetched:
                    data = fetched
                    got = True
        except Exception:
            got = False
        if not got:
            # JSON body with no usable link — the old code fell through
            # and wrote the JSON itself out as an ".srt" file.
            return False, 'SubSource returned no downloadable file.', ''
    out_path = _write_subtitle_file(data, out_name)
    if out_path:
        return True, '', out_path
    return False, 'Write failed.', ''


# =============================================================================
#  OpenSubtitles.com provider
# =============================================================================

_OS_BASE = "https://api.opensubtitles.com/api/v1"


def _os_api_key():
    return str(_cfg("opensubtitles_api_key", "")).strip()


def _os_headers(api_key, json_body=False):
    h = {
        "Api-Key": str(api_key or "").strip(),
        "User-Agent": _OS_UA,
        "Accept": "application/json",
    }
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _os_read_json(url, api_key, timeout=20):
    if _BASE_FETCH is not None:
        try:
            text, _final = _BASE_FETCH(url, extra_headers=_os_headers(api_key))
            if text:
                return json.loads(text)
            return None
        except Exception:
            return None
    try:
        req = _urlreq.Request(url, headers=_os_headers(api_key))
        raw = _urlreq.urlopen(req, timeout=timeout).read()
        return json.loads(raw.decode('utf-8', 'ignore'))
    except Exception:
        return None


def opensubtitles_search(title, video_url='', api_key=''):
    api_key = str(api_key or '').strip()
    if not api_key:
        return False, 'OpenSubtitles API key is empty.\nAdd it in NovaPlay settings.', []
    query = clean_subtitle_query(title, video_url)
    if not query:
        return False, 'No usable title for subtitle search.', []

    year = ''
    m = re.search(r'\b(19\d{2}|20\d{2})\b', query)
    if m:
        year = m.group(1)
    q = re.sub(r'\b(19\d{2}|20\d{2})\b', ' ', query)
    q = re.sub(r'\s+', ' ', q).strip()
    if not q:
        q = query

    results = []
    last_ok = False
    for q_idx, query_str in enumerate([q] + _ss_title_fallbacks(q)[:2]):
        params = {'query': query_str, 'languages': ",".join(_lang_row(c)[4] for c in sub_langs())}
        if year:
            params['movieyear'] = year
        _h = SEARCH_HINT
        if _h.get("tmdb_id") and q_idx == 0 and _h.get("year") == (year or _h.get("year")):
            # [2026-11-04] the exact film by its TMDb id
            params = {'languages': params['languages'],
                      ('parent_tmdb_id' if _h.get("kind") == "tv" else 'tmdb_id'): _h["tmdb_id"]}
        url = _OS_BASE + '/subtitles?' + urlencode(params)
        data = _os_read_json(url, api_key, timeout=(20 if q_idx == 0 else 10))
        if data is None:
            continue
        last_ok = True
        rows = []
        try:
            rows = data.get('data') or []
        except Exception:
            rows = []
        if not isinstance(rows, list):
            continue
        for row in rows:
            try:
                attrs = row.get('attributes') or {}
                lang = str(attrs.get('language') or '').strip()
                files = attrs.get('files') or []
                feat = attrs.get('feature_details') or {}
                if year and not _year_ok(_year_of(feat.get('year')), year):
                    continue                       # [2026-11-04] another film of that name
                base_name = (_ss_clean_label(attrs.get('release')) or
                             _ss_clean_label(feat.get('movie_name')) or
                             _ss_clean_label(feat.get('title')) or 'Subtitle')
                for f in files:
                    fid = str(f.get('file_id') or '').strip()
                    if not fid:
                        continue
                    fname = _ss_clean_label(f.get('file_name')) or base_name
                    score = _score_name(fname, [query]) + _score_name(base_name, [query])
                    if lang.lower() in ('arabic', 'ar', 'ara', 'العربية'):
                        score += 80
                    results.append({'id': fid, 'title': fname, 'language': lang,
                                    'score': score,
                                    'label': ('[%s] %s' % (lang, fname)) if lang else fname})
            except Exception:
                continue
        if results:
            break

    if not results:
        if last_ok:
            return False, 'No OpenSubtitles match found for:\n%s' % query, []
        return False, 'OpenSubtitles search failed.\nCheck API key / connection.', []

    unique, seen = [], set()
    for item in sorted(results, key=lambda x: (_ss_language_rank(x), -int(x.get('score') or 0),
                                               x.get('label', '').lower())):
        key = str(item.get('id') or '') + '|' + str(item.get('title') or '').lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return True, '', unique[:80]


# find
# def opensubtitles_download(file_id, title, api_key=''):
# replace
_OS_TOKEN = {"token": "", "base": "", "user": "", "ts": 0}


def _os_post_json(url, body, headers, timeout=25):
    """[PATCH 91] POST a JSON string. Returns (json_or_None, http_status_or_0)."""
    try:
        req = _urlreq.Request(url, data=body.encode('utf-8'), headers=headers)
        raw = _urlreq.urlopen(req, timeout=timeout).read()
        return json.loads(raw.decode('utf-8', 'ignore')), 200
    except _urlreq.HTTPError as e:
        return None, int(getattr(e, 'code', 0) or 0)
    except Exception:
        return None, 0


def _os_login(api_key):
    """[PATCH 91] Returns (bearer_token, base_url) or ('', '') when no
    credentials are configured or the login fails. Token cached ~20h."""
    user = str(_cfg("opensubtitles_user", "")).strip()
    pw = str(_cfg("opensubtitles_pass", "")).strip()
    if not user or not pw:
        return "", ""
    if (_OS_TOKEN["token"] and _OS_TOKEN["user"] == user
            and time.time() - _OS_TOKEN["ts"] < 20 * 3600):
        return _OS_TOKEN["token"], _OS_TOKEN["base"]
    js, _code = _os_post_json(_OS_BASE + '/login',
                              json.dumps({'username': user, 'password': pw}),
                              _os_headers(api_key, json_body=True), timeout=20)
    if not isinstance(js, dict) or not js.get('token'):
        return "", ""
    host = (str(js.get('base_url') or '').replace('https://', '')
            .replace('http://', '').strip().strip('/'))
    base = ('https://%s/api/v1' % host) if host else ""
    _OS_TOKEN.update({"token": str(js['token']), "base": base,
                      "user": user, "ts": time.time()})
    return _OS_TOKEN["token"], base


def opensubtitles_download(file_id, title, api_key=''):
    api_key = str(api_key or '').strip()
    file_id = str(file_id or '').strip()
    if not api_key or not file_id:
        return False, 'Missing OpenSubtitles data.', ''
    try:
        body = json.dumps({'file_id': int(file_id)})
    except (TypeError, ValueError):
        return False, 'Invalid OpenSubtitles file id.', ''
    # [PATCH 91] login (when credentials are set) → Bearer; real HTTP errors reported
    creds = bool(str(_cfg("opensubtitles_user", "")).strip()
                 and str(_cfg("opensubtitles_pass", "")).strip())
    token, base = _os_login(api_key)
    hdrs = _os_headers(api_key, json_body=True)
    if token:
        hdrs["Authorization"] = "Bearer " + token
    js, code = _os_post_json((base or _OS_BASE) + '/download', body, hdrs)
    if js is None:
        if code in (401, 403):
            _OS_TOKEN["token"] = ""
            if creds:
                return False, 'OpenSubtitles rejected the login.\nCheck username / password.', ''
            return False, ('OpenSubtitles needs a login to download.\n'
                           'Add username + password in Subtitle Settings > API Keys.'), ''
        if code == 406:
            return False, 'OpenSubtitles download limit reached (HTTP 406).', ''
        return False, 'OpenSubtitles download failed (%s).' % (
            ('HTTP %d' % code) if code else 'network'), ''
    link = _ss_value(js, ('link', 'url', 'download_url'))
    if not link:
        return False, 'OpenSubtitles returned no download link.', ''
    try:
        # binary payload (possibly zip) — raw urlopen, NOT base.fetch
        req2 = _urlreq.Request(str(link), headers={"User-Agent": _OS_UA})
        data = _urlreq.urlopen(req2, timeout=30).read()
    except Exception:
        return False, 'OpenSubtitles file fetch failed.', ''
    if not data:
        return False, 'Empty OpenSubtitles subtitle file.', ''
    filename_base = re.sub(r'[^A-Za-z0-9_\-\.]+', '_', _clean_name(title) or
                           ('opensubs_%s' % file_id)).strip('._') or ('opensubs_%s' % file_id)
    out_name = filename_base + '.srt'
    if data[:2] == b'PK':
        picked, picked_name = _ss_pick_srt_from_zip(data, filename_base)
        if not picked:
            return False, 'Downloaded zip has no supported subtitle file.', ''
        data = picked
        out_name = picked_name or out_name
    out_path = _write_subtitle_file(data, out_name)
    if out_path:
        return True, '', out_path
    return False, 'Write failed.', ''


# =============================================================================
#  SubDL provider (api.subdl.com) -- [2026-10-28] good Arabic coverage.
#  Needs a free API key (subdl.com -> panel -> API). Written from SubDL's
#  public API; E2iPlayer's SubDL provider was only used as a reference.
# =============================================================================

_SD_API = "https://api.subdl.com/api/v1/subtitles"
_SD_DL = "https://dl.subdl.com"


def _sd_api_key():
    return str(_cfg("subdl_api_key", "")).strip()


def _sd_lang_name(code):
    c = str(code or "").strip().lower()
    known = lang_code(c)
    if known != "other":
        return lang_info(known)[0]
    return c.title() if c else ""


def subdl_search(title, video_url='', api_key=''):
    api_key = str(api_key or '').strip() or _sd_api_key()
    if not api_key:
        return False, ('SubDL needs a free API key.\n'
                       'Get it at subdl.com (panel -> API) and add it in\n'
                       'NovaPlay subtitle settings -> API Keys.'), []
    raw_title = str(title or '')
    # an episode: S01E05 in the title -> search the series, that season / episode
    season = episode = None
    m = re.search(r'\bS(\d{1,2})\s*E(\d{1,3})\b', raw_title, re.I)
    if m:
        season, episode = int(m.group(1)), int(m.group(2))
        raw_title = raw_title[:m.start()]
    query = clean_subtitle_query(raw_title, video_url) or _clean_name(raw_title)
    year = ''
    my = re.search(r'\b(19\d{2}|20\d{2})\b', query or '')
    if my:
        year = my.group(1)
        query = re.sub(r'\s+', ' ', query.replace(year, ' ')).strip()
    if not query:
        return False, 'No usable title for subtitle search.', []
    params = {"api_key": api_key, "film_name": query, "subs_per_page": "30",
              "languages": ",".join(_lang_row(c)[5] for c in sub_langs())}
    _h = SEARCH_HINT
    if _h.get("tmdb_id") and (not year or _h.get("year") == year):
        # [2026-11-04] the exact film by its TMDb id (the name alone found the
        # 2002 Resident Evil for the 2026 one)
        params.pop("film_name", None)
        params["tmdb_id"] = str(_h["tmdb_id"])
        if season is None and _h.get("kind") == "tv":
            params["type"] = "tv"
        elif season is None:
            params["type"] = "movie"
    if season is not None:
        params.update({"type": "tv", "season_number": str(season), "episode_number": str(episode)})
    elif year:
        params["year"] = year
    try:
        from urllib.parse import urlencode
    except ImportError:                                  # pragma: no cover
        from urllib import urlencode
    url = _SD_API + "?" + urlencode(params)
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        data = json.loads(_urlreq.urlopen(req, timeout=20).read().decode("utf-8", "replace"))
    except Exception as e:
        return False, 'SubDL search failed (%s).' % str(e)[:60], []
    if not isinstance(data, dict) or data.get("status") is False:
        msg = str((data or {}).get("error") or (data or {}).get("message") or "no answer") if isinstance(data, dict) else "no answer"
        return False, 'SubDL: %s' % msg[:80], []
    # [2026-11-04] SubDL says which film it found: another year -> nothing
    if year and season is None:
        films = [r for r in (data.get("results") or []) if isinstance(r, dict)]
        fy = [_year_of(r.get("year"), r.get("release_date"), r.get("first_air_date")) for r in films]
        if fy and all(y_ and not _year_ok(y_, year) for y_ in fy):
            return False, 'No SubDL subtitles for the %s film:\n%s' % (year, query), []
    results = []
    for sub in data.get("subtitles") or []:
        if not isinstance(sub, dict) or not sub.get("url"):
            continue
        lang = _sd_lang_name(sub.get("lang") or sub.get("language"))
        name = re.sub(r"\s+", " ", str(sub.get("release_name") or sub.get("name") or "")).strip() or "Subtitle"
        hi = " (HI)" if sub.get("hi") else ""
        results.append({"id": str(sub["url"]), "title": name, "language": lang,
                        "label": ("[%s] %s%s" % (lang, name, hi)) if lang else name + hi})
    if not results:
        return False, 'No SubDL subtitles found for:\n%s' % query, []
    results.sort(key=lambda x: (_ss_language_rank(x), x.get("title", "").lower()))
    return True, '', results


def subdl_download(subtitle_id, title, api_key=''):
    # binary (a zip): raw urlopen, not fetch() which decodes text
    path = str(subtitle_id or '').strip()
    if not path:
        return False, 'Missing SubDL data.', ''
    url = path if path.startswith("http") else _SD_DL + (path if path.startswith("/") else "/" + path)
    try:
        raw = _urlreq.urlopen(_urlreq.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read()
    except Exception:
        return False, 'SubDL download failed.', ''
    if not raw:
        return False, 'Empty SubDL file.', ''
    base = re.sub(r'[^A-Za-z0-9_\-\.]+', '_', _clean_name(title) or 'subdl').strip('._') or 'subdl'
    data, out_name = raw, base + '.srt'
    if raw[:2] == b'PK':
        data, picked = _ss_pick_srt_from_zip(raw, base)
        if not data:
            return False, 'SubDL zip has no supported subtitle file.', ''
        out_name = picked or out_name
    out_path = _write_subtitle_file(data, out_name)
    if out_path:
        return True, '', out_path
    return False, 'Write failed.', ''


_PROVIDERS = {
    "subsource": {"name": "SubSource", "key": _ss_api_key,
                  "search": subsource_search, "download": subsource_download},
    "opensubtitles": {"name": "OpenSubtitles", "key": _os_api_key,
                      "search": opensubtitles_search, "download": opensubtitles_download},
    "subdl": {"name": "SubDL", "key": _sd_api_key,
              "search": subdl_search, "download": subdl_download},
}


# =============================================================================
#  SRT sync shift — block-aware: cues that shift fully into the past are
#  DROPPED (the old regex version clamped them to 00:00:00,000 zero-length
#  cues that some players render as a flicker at playback start).
# =============================================================================

_TS_RE = re.compile(r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})')
_TIMING_RE = re.compile(
    r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*'
    r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})')


def _ts_ms(h, m, s, ms):
    return ((int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms))


def _fmt_ts(total_ms):
    if total_ms < 0:
        total_ms = 0
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def _shift_srt_text(text, delta_ms):
    if not text or not delta_ms:
        return text
    delta = int(delta_ms)
    blocks = re.split(r'\r?\n[ \t]*\r?\n', text)
    if len(blocks) == 1 and text.count('-->') > 1:
        # malformed SRT without blank-line separators — fall back to the
        # old pure regex substitution so we never make things worse
        def _repl(m):
            start = _ts_ms(m.group(1), m.group(2), m.group(3), m.group(4)) + delta
            end = _ts_ms(m.group(5), m.group(6), m.group(7), m.group(8)) + delta
            return _fmt_ts(start) + " --> " + _fmt_ts(end)
        return _TIMING_RE.sub(_repl, text)
    kept = []
    for block in blocks:
        if '-->' not in block:
            kept.append(block)
            continue

        def _repl(m):
            start = _ts_ms(m.group(1), m.group(2), m.group(3), m.group(4)) + delta
            end = _ts_ms(m.group(5), m.group(6), m.group(7), m.group(8)) + delta
            return _fmt_ts(start) + " --> " + _fmt_ts(end)

        new_block = _TIMING_RE.sub(_repl, block, count=1)
        tm = _TIMING_RE.search(new_block)
        if tm:
            end_ms = _ts_ms(tm.group(5), tm.group(6), tm.group(7), tm.group(8))
            if end_ms <= 0:
                continue  # cue shifted entirely before playback start
        kept.append(new_block)
    return "\n\n".join(kept)


def _make_shifted_copy(path, offset_ms):
    """Write a timestamp-shifted copy of an .srt into cache; returns new path
    or '' on failure (non-srt / unreadable)."""
    if not path or offset_ms == 0 or not str(path).lower().endswith('.srt'):
        return ""
    try:
        with open(path, 'rb') as fh:
            raw = fh.read()
        text = None
        _encs = ('utf-16',) if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else ()   # [WGFM] UTF-16
        for enc in _encs + ('utf-8-sig', 'utf-8', 'cp1256', 'latin-1'):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                text = None
        if text is None:
            return ""
        shifted = _shift_srt_text(text, offset_ms)
        base = os.path.splitext(os.path.basename(path))[0]
        base = re.sub(r'(_sync[+-]?\d+)?$', '', base) or 'sub'
        out_name = "%s_sync%+d.srt" % (re.sub(r'[^A-Za-z0-9_\-\.]+', '_', base), int(offset_ms))
        out_path = os.path.join(_ss_cache_dir(), out_name)
        with open(out_path, 'wb') as fh:
            fh.write(shifted.encode('utf-8'))
        return out_path
    except Exception:
        return ""


def get_subtitle_state():
    return dict(_CURRENT_SUB)          # a COPY — use update_subtitle_state() to write


def update_subtitle_state(**kw):
    """[PATCH 88] real writer for the in-session subtitle state."""
    _CURRENT_SUB.update(kw)


def has_subtitle_for(item_url):
    """[PATCH 88] True when a subtitle is attached for THIS item, or remembered for it."""
    item_url = str(item_url or "").strip()
    if _CURRENT_SUB.get("path") and _CURRENT_SUB.get("item_url") == item_url:
        return True
    return bool(recall_subtitle(item_url)[0])        # a COPY — use update_subtitle_state() to write


def adjust_sync(session, delta_ms):
    """Shift subtitle timing by delta_ms and re-attach. Returns status text."""
    state = _CURRENT_SUB
    path = state.get("path") or ""
    if not path or not os.path.exists(path):
        return "No subtitle active"
    if not path.lower().endswith('.srt'):
        return "Sync: SRT files only"
    orig = state.get("_orig_path") or path
    base_path = orig if os.path.exists(orig) else path
    new_offset = int(state.get("offset_ms") or 0) + int(delta_ms)
    if new_offset == 0:
        shifted = base_path
    else:
        shifted = _make_shifted_copy(base_path, new_offset)
        if not shifted:
            return "Sync shift failed"
    _CURRENT_SUB.update({"path": shifted, "_orig_path": base_path,
                         "offset_ms": new_offset})
    # v4.5: zero any live studio offset — the shifted file now carries
    # the FULL shift; a studio in-memory offset would double-apply
    # (STUDIO.attach() preserves a live offset across re-attach).
    try:
        from .novaplay_substudio import STUDIO
        if STUDIO.get_offset():
            STUDIO.set_offset(0)
    except Exception:
        pass
    disable_subtitle(session)
    ok = apply_subtitle(session, shifted)
    if not ok:
        # FIX: actually retry (service often isn't ready immediately)
        _apply_with_retry(session, shifted, tries=3)
    if state.get("item_url"):
        remember_subtitle(state["item_url"], base_path, new_offset)
    return "Sync: %s%s" % (_fmt_offset(new_offset), "" if ok else " (retrying)")


def reset_sync(session):
    state = _CURRENT_SUB
    base_path = state.get("_orig_path") or state.get("path") or ""
    if not base_path or not os.path.exists(base_path):
        return "No subtitle active"
    _CURRENT_SUB.update({"path": base_path, "_orig_path": base_path, "offset_ms": 0})
    # v4.5: zero the studio offset too — same double-apply guard as
    # adjust_sync (the base file must render unshifted).
    try:
        from .novaplay_substudio import STUDIO
        if STUDIO.get_offset():
            STUDIO.set_offset(0)
    except Exception:
        pass
    disable_subtitle(session)
    ok = apply_subtitle(session, base_path)
    if not ok:
        _apply_with_retry(session, base_path, tries=3)
    if state.get("item_url"):
        remember_subtitle(state["item_url"], base_path, 0)
    return "Sync: 0 ms%s" % ("" if ok else " (retrying)")


# =============================================================================
#  Subtitle attach / detach on the running service
# =============================================================================

# =============================================================================
#  [2026-10-31] Other text formats -> .srt, so every subtitle goes through the
#  Studio (style, sync, pick the line): .ass / .ssa, .vtt, MicroDVD .sub/.txt
#  ({start}{end}text, frames). A .txt that is really SRT is copied. VobSub
#  (.idx + binary .sub) is pictures -> left alone. The .srt is written next to
#  the cached downloads and reused while it is newer than its source.
# =============================================================================

def _log(msg):
    try:
        from .plugin_common import my_log
        my_log(msg)
    except Exception:
        pass


def _srt_ts(ms):
    ms = max(0, int(ms))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def _decode_text(raw):
    _encs = ("utf-16",) if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ()   # [WGFM] UTF-16
    for enc in _encs + ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("latin-1", "replace")


def _ass_ms(t):
    m = re.match(r"\s*(\d+):(\d{1,2}):(\d{1,2})[.,](\d{1,3})", t or "")
    if not m:
        return None
    frac = m.group(4)
    ms = int(frac) * (10 if len(frac) == 2 else (100 if len(frac) == 1 else 1))
    return ((int(m.group(1)) * 60 + int(m.group(2))) * 60 + int(m.group(3))) * 1000 + ms


def _cues_from_ass(text):
    cues, fmt, in_events = [], None, False
    for line in text.splitlines():
        st = line.strip()
        if st.startswith("["):
            in_events = st.lower() == "[events]"
            continue
        if not in_events:
            continue
        if st.lower().startswith("format:"):
            fmt = [f.strip().lower() for f in st[7:].split(",")]
            continue
        if not st.lower().startswith("dialogue:"):
            continue
        f = fmt or ["layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text"]
        parts = st[9:].split(",", len(f) - 1)
        if len(parts) < len(f):
            continue
        d = dict(zip(f, parts))
        a, b = _ass_ms(d.get("start")), _ass_ms(d.get("end"))
        body = d.get("text", "")
        if "\\p1" in body or "\\p2" in body:          # vector drawings, not text
            continue
        an = re.search(r"\\an[1-9]", body)
        body = re.sub(r"\{[^}]*\}", "", body).replace("\\h", " ")
        lines = [l.strip() for l in re.split(r"\\[Nn]", body) if l.strip()]
        if a is None or b is None or b <= a or not lines:
            continue
        if an:
            lines[0] = "{%s}" % an.group(0) + lines[0]      # keep "top of screen"
        cues.append((a, b, lines))
    return cues


def _cues_from_vtt(text):
    cues = []
    ts = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})")
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        lines = block.split("\n")
        for i, l in enumerate(lines):
            m = ts.search(l)
            if not m:
                continue
            g = [int(x or 0) for x in m.groups()]
            a = ((g[0] * 60 + g[1]) * 60 + g[2]) * 1000 + g[3]
            b = ((g[4] * 60 + g[5]) * 60 + g[6]) * 1000 + g[7]
            body = [re.sub(r"<[^>]+>", "", x).strip() for x in lines[i + 1:]]
            body = [x for x in body if x]
            if b > a and body:
                cues.append((a, b, body))
            break
    return cues


def _cues_from_microdvd(text):
    cues, fps = [], 23.976
    for line in text.splitlines():
        m = re.match(r"\s*\{(\d+)\}\{(\d*)\}(.*)", line)
        if not m:
            continue
        a, b, body = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if a in (0, 1) and b in (0, 1):                     # {1}{1}23.976 = frame rate
            try:
                fps = float(body.strip()) or fps
            except Exception:
                pass
            continue
        body = re.sub(r"\{[a-zA-Z]:[^}]*\}", "", body)
        lines = [l.strip() for l in body.split("|") if l.strip()]
        if not b:
            b = a + int(fps * 3)
        if b > a and lines:
            cues.append((int(a * 1000 / fps), int(b * 1000 / fps), lines))
    return cues


def to_srt(path):
    """a subtitle path the Studio can use: the .srt itself, or an .srt made from
    .ass/.ssa/.vtt/MicroDVD; the original path when it can't be converted"""
    path = str(path or "")
    low = path.lower()
    if not path or low.endswith(".srt") or not os.path.isfile(path):
        return path
    if not low.endswith((".ass", ".ssa", ".vtt", ".sub", ".txt")):
        return path
    try:
        base = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", os.path.splitext(os.path.basename(path))[0])[:80] or "sub"
        out = os.path.join(_ss_cache_dir(), "%s_%s.srt" % (
            base, hashlib.md5(path.encode("utf-8")).hexdigest()[:6]))
        if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(path):
            return out
        with open(path, "rb") as fh:
            raw = fh.read()
        if low.endswith(".sub") and raw[:4] == b"\x00\x00\x01\xba":
            return path                                     # VobSub pictures
        text = _decode_text(raw)
        if low.endswith((".ass", ".ssa")) or "[events]" in text[:20000].lower():
            cues = _cues_from_ass(text)
        elif low.endswith(".vtt") or text.lstrip().startswith("WEBVTT"):
            cues = _cues_from_vtt(text)
        elif re.search(r"\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->", text):
            cues = None                                     # already SRT inside
        else:
            cues = _cues_from_microdvd(text)
        if cues is None:
            data = text
        else:
            if not cues:
                _log("to_srt: nothing readable in %s" % os.path.basename(path))
                return path
            cues.sort(key=lambda c: c[0])
            data = "\n".join("%d\n%s --> %s\n%s\n" % (i + 1, _srt_ts(a), _srt_ts(b), "\n".join(body))
                             for i, (a, b, body) in enumerate(cues))
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.rename(tmp, out)
        _log("to_srt: %s -> %s (%s cues)" % (os.path.basename(path), os.path.basename(out),
                                            "copied" if cues is None else len(cues)))
        return out
    except Exception as e:
        _log("to_srt failed for %s: %s" % (os.path.basename(path), e))
        return path


# [2026-10-31] the Subtitle Studio is always on (no switch any more); it takes
# .srt files and anything else falls back to the box's own subtitles. Set to
# False to go back to the box's own subtitles for everything.
STUDIO_ON = True


def apply_subtitle(session, path):
    """Attach an external subtitle file to the currently playing service.
    Subtitle Studio mode renders via the custom engine instead of the
    service layer; non-SRT or engine failure falls back to the service."""
    path = to_srt(str(path or ''))           # [2026-10-31] other formats -> .srt
    if not path or not os.path.exists(path):
        return False
    if STUDIO_ON:
        try:
            from .novaplay_substudio import STUDIO
            if STUDIO.attach(path):
                try:
                    # avoid double rendering: kill the service subtitle
                    svc = session.nav.getCurrentService()
                    if svc:
                        sub = svc.subtitle()
                        if sub:
                            sub.disableSubtitle()
                except Exception:
                    pass
                return True
        except Exception:
            pass
    try:
        service = session.nav.getCurrentService()
        if not service:
            return False
        sub = service.subtitle()
        if not sub:
            return False
        for sub_tuple in ((1, 0, 0, path), (1, 0, 1, path)):
            try:
                sub.enableSubtitle(sub_tuple)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def turn_off_subtitle(session, item_url=""):
    """[FIX] user switched subtitles OFF: stop rendering AND clear the state
    (the CC mark, the sync rows and the Blue panel used to keep showing the
    old file) and forget it for this title so it doesn't come back on resume."""
    disable_subtitle(session)
    url = item_url or _CURRENT_SUB.get("item_url") or ""
    _CURRENT_SUB.update({"path": "", "_orig_path": "", "offset_ms": 0})
    if url:
        try:
            data = _load_subs_memory()
            if data.pop(str(url).strip(), None) is not None:
                _save_subs_memory(data)
        except Exception:
            pass


def disable_subtitle(session):
    try:
        from .novaplay_substudio import STUDIO
        STUDIO.detach()
    except Exception:
        pass
    try:
        service = session.nav.getCurrentService()
        if service:
            sub = service.subtitle()
            if sub:
                sub.disableSubtitle()
                return True
    except Exception:
        pass
    return False


# =============================================================================
#  Local auto-match + memory-first attach on playback start
# =============================================================================

def find_best_local_subtitle(title, url="", extra_roots=None):
    """Score subtitle files in the configured dir (+ one subdir level,
    plus extra roots, plus the downloads dir so sidecar subs match).
    Returns (path, score) or ('', 0)."""
    roots = []
    root = subtitle_dir()
    if root:
        roots.append(root)
    for extra in (extra_roots or []):
        if extra and extra not in roots and os.path.isdir(extra):
            roots.append(extra)
    try:
        from .plugin_downloads import download_dir as _dl_dir
        _dl = _dl_dir()
        if _dl and _dl not in roots and os.path.isdir(_dl):
            roots.append(_dl)
    except Exception:
        pass
    if not roots:
        return '', 0
    title = clean_play_title(title)
    terms = _search_terms(title, url)
    if not terms:
        return '', 0
    words = _significant_words(terms)
    markers = _episode_markers(terms)

    scored = []
    scanned = [0]

    def _scan(dirpath, depth):
        if scanned[0] >= MAX_SCAN_ENTRIES:
            return
        for name, full, is_dir in _iter_sub_entries(dirpath):
            scanned[0] += 1
            if scanned[0] >= MAX_SCAN_ENTRIES:
                return
            if is_dir:
                if depth == 0:
                    _scan(full, depth + 1)
                continue
            sc = strict_score(name, terms, words, markers)
            if sc > 0:
                scored.append((sc, full))

    try:
        for r in roots:
            _scan(r, 0)
    except Exception:
        return '', 0
    if not scored:
        return '', 0
    best = max(scored, key=lambda x: x[0])
    return best[1], best[0]


_RETRY_TIMERS = []


def _apply_with_retry(session, path, tries=3, delay_ms=2500):
    """Service may not be ready right at playback start — retry a few times."""
    if tries <= 0:
        return
    if apply_subtitle(session, path):
        return
    t = eTimer()

    def _retry():
        _apply_with_retry(session, path, tries - 1, delay_ms)
    try:
        t.callback.append(_retry)
        t.start(delay_ms, True)
    except Exception:
        pass
    global _RETRY_TIMERS
    _RETRY_TIMERS.append(t)
    if len(_RETRY_TIMERS) > 6:
        _RETRY_TIMERS = _RETRY_TIMERS[-6:]


_AUTO_SUB_TIMER = None


def _apply_path_with_offset(session, item_url, path, offset_ms):
    """Attach subtitle, applying a remembered sync offset if any."""
    path = to_srt(path)                      # [2026-10-31] other formats -> .srt
    if not path or not os.path.exists(path):
        return False
    target = path
    if offset_ms:
        shifted = _make_shifted_copy(path, offset_ms)
        if shifted:
            target = shifted
    _CURRENT_SUB.update({"item_url": item_url or "", "path": target,
                         "_orig_path": path, "offset_ms": int(offset_ms or 0)})
    ok = apply_subtitle(session, target)
    if not ok:
        _apply_with_retry(session, target, tries=3)
    return True


def maybe_resume_subtitle(session, title, item_url="", apply=True):
    """Call right after playback starts. Priority:
    1) remembered subtitle for this item (+ remembered sync)
    2) auto-matched local subtitle (if 'auto_subtitle' enabled)

    FIX: the disk scan now runs on a WORKER thread — it used to run in
    the eTimer callback (= main thread) and could freeze the UI for
    seconds right when the user reaches for the remote."""
    item_url = str(item_url or "").strip()
    # [PATCH 88] drop the previous title's subtitle state NOW, not 3.5s later
    if _CURRENT_SUB.get("item_url") != item_url:
        _CURRENT_SUB.update({"item_url": item_url, "path": "",
                             "_orig_path": "", "offset_ms": 0})

    def _do():
        try:
            _CURRENT_SUB.update({"item_url": item_url, "path": "",
                                 "_orig_path": "", "offset_ms": 0})
            if not apply:
                return
            # [2026-10-31] a resumed title: its subtitle comes back only if it
            # was on when you stopped (YELLOW off is remembered)
            path, offset = recall_subtitle(item_url, only_on=True)
            if path:
                _apply_path_with_offset(session, item_url, path, offset)
                return
            # [2026-11-04] Auto-Attach removed: subtitles start off, YELLOW turns
            # them on (a file in the folder no longer loads by itself)
            if False:
                def _scan():
                    try:
                        lpath, score = find_best_local_subtitle(title, item_url)
                        if lpath and score >= AUTO_SUB_MIN_SCORE:
                            callInMainThread(_apply_path_with_offset,
                                             session, item_url, lpath, 0)
                    except Exception:
                        pass
                threading.Thread(target=_scan, daemon=True).start()
        except Exception:
            pass

    global _AUTO_SUB_TIMER
    try:
        if _AUTO_SUB_TIMER is not None:
            try:
                _AUTO_SUB_TIMER.stop()
            except Exception:
                pass
        _AUTO_SUB_TIMER = eTimer()
        _AUTO_SUB_TIMER.callback.append(_do)
        _AUTO_SUB_TIMER.start(3500, True)
    except Exception:
        threading.Thread(target=_do, daemon=True).start()


def maybe_auto_subtitle(session, title, url="", delay_ms=3500):
    """Backward-compatible wrapper (memory-first is maybe_resume_subtitle)."""
    maybe_resume_subtitle(session, title, url)


# =============================================================================
#  Screens
# =============================================================================

def _menu_index(menu_list, entries_count):
    """Robust current-index lookup across Enigma2 generations."""
    try:
        idx = menu_list.getSelectedIndex()
        if idx is not None and 0 <= int(idx) < entries_count:
            return int(idx)
    except Exception:
        pass
    try:
        cur = menu_list.getCurrent()
    except Exception:
        return -1
    if isinstance(cur, tuple) and len(cur) >= 2:
        try:
            idx = int(cur[1])
            if 0 <= idx < entries_count:
                return idx
        except Exception:
            pass
    elif isinstance(cur, int):
        if 0 <= cur < entries_count:
            return cur
    return -1


class NovaOnlineSubsScreen(Screen):
    """Background online search + download (SubSource or OpenSubtitles);
    closes with the .srt path."""

    skin = """
    <screen name="NovaOnlineSubsScreen" position="center,center" size="1700,940" backgroundColor="transparent" title="Online subtitles" flags="wfNoBorder">
        <eLabel position="0,0" size="1700,940" backgroundColor="#1A121822" cornerRadius="18" zPosition="0" />
        <eLabel position="40,78" size="140,4" backgroundColor="#F2C230" cornerRadius="2" zPosition="2" />
        <widget name="header" position="50,20" size="1600,50" font="Bold;38" foregroundColor="#F2C230" transparent="1" zPosition="2" />
        <widget name="list" position="40,110" size="1620,688" scrollbarMode="showOnDemand" backgroundColor="#1A121822" backgroundColorSelected="#1A2B3648" zPosition="2" />
        <widget name="hint" position="50,860" size="1600,40" font="Regular;24" foregroundColor="#A3ADBB" transparent="1" zPosition="2" />
    </screen>"""

    def __init__(self, session, title="", video_url="", provider="subsource", api_key=""):
        Screen.__init__(self, session)
        self.skinName = ["NovaOnlineSubsScreen"]
        self.search_title = str(title or "")
        self.video_url = str(video_url or "")
        self.provider = provider if provider in _PROVIDERS else "subsource"
        self.api_key = str(api_key or "").strip()
        self.results = []
        self.chosen = None
        self.mode = "search"
        prov_name = _PROVIDERS[self.provider]["name"]

        self["header"] = Label("Searching %s ..." % prov_name)
        self["hint"] = Label(u"OK download  \u00b7  \u25b2\u25bc move  \u00b7  \u25c0\u25b6 page  \u00b7  "
                             u"RED all  GREEN Arabic  YELLOW English  BLUE languages  \u00b7  EXIT back")
        from .novaplay_cardlist import CardList
        self["list"] = CardList(width=1620, row_h=86)      # [subs-ui] two-line cards
        # [2026-11-04] language filter, remembered: "all" / "ar" / "en"
        self._all = []
        try:
            from .plugin_state import _get_config
            self._lang = str(_get_config("subs_lang_filter", "all") or "all")
        except Exception:
            self._lang = "all"
        if self._lang != "all" and self._lang not in [r[0] for r in SUB_LANGS]:
            self._lang = "all"
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
            "ok": self._ok,
            "cancel": self._cancel,
            "left": self._pageUp,
            "right": self._pageDown,
            "red": lambda: self._setLang("all"),
            "green": lambda: self._setLang("ar"),
            "yellow": lambda: self._setLang("en"),
            "blue": self._pickLang,
        }, -1)
        # [2026-11-04] closed screens must not be touched by a search that
        # finishes later: that crashed Enigma2 (signal) after EXIT
        self._closed = False
        self.onClose.append(self._markClosed)
        threading.Thread(target=self._searchThread, daemon=True).start()

    def _markClosed(self):
        self._closed = True

    def _pageUp(self):
        try:
            self["list"].instance.moveSelection(self["list"].instance.pageUp)
        except Exception:
            pass

    def _pageDown(self):
        try:
            self["list"].instance.moveSelection(self["list"].instance.pageDown)
        except Exception:
            pass

    # ── [subs-ui] how well a release fits the playing file ───────────
    _NOISE = set("mkv mp4 avi ts m3u8 stream play link index www com net org".split())

    def _fileTokens(self):
        """words of the playing file's release name that are not the title
        itself (1080p, web, dl, flux, ...); [] when the URL has no name"""
        try:
            from urllib.parse import urlparse, unquote
            base = unquote(urlparse(self.video_url).path.rsplit("/", 1)[-1])
        except Exception:
            base = ""
        base = re.sub(r"\.[a-z0-9]{2,4}$", "", base.lower())
        title_words = set(re.findall(r"[a-z0-9]+", self.search_title.lower()))
        toks = [t for t in re.findall(r"[a-z0-9]+", base)
                if t not in title_words and t not in self._NOISE and not re.match(r"^(19|20)\d\d$", t)
                and len(t) >= 2 and not re.match(r"^[0-9a-f]{16,}$", t)]
        return list(dict.fromkeys(toks)) if len(set(toks)) >= 2 else []

    @staticmethod
    def _kfmt(n):
        n = int(n or 0)
        if n >= 1000000:
            return "%.1fM" % (n / 1000000.0)
        if n >= 1000:
            return "%dk" % (n // 1000)
        return str(n)

    def _cardRows(self, items):
        from .novaplay_cardlist import card, CHIP_BG, GOLD, DARK, GREEN
        ft = self._fileTokens()
        pcts = []
        for it in items:
            if ft:
                rel = set(re.findall(r"[a-z0-9]+", str(it.get("title") or "").lower()))
                pcts.append(int(round(100.0 * sum(1 for t in ft if t in rel) / len(ft))))
            else:
                pcts.append(-1)
        # BEST: the top language group (the list is sorted Arabic first), best fit there
        best = -1
        if len(items) >= 2:
            lang0 = str(items[0].get("language") or "").lower()
            group = [i for i, it in enumerate(items) if str(it.get("language") or "").lower() == lang0]
            best = max(group, key=lambda i: (pcts[i], -i)) if group else 0
        prov = _PROVIDERS[self.provider]["name"]
        rows = []
        for i, it in enumerate(items):
            code = self._langOf(it)
            lname, flag = lang_info(code)
            lang = lname or str(it.get("language") or "").strip().title()
            is_ar = code == "ar"
            chips = []
            if lang:
                chips.append((lang, DARK if is_ar else 0xF0F6FC, GOLD if is_ar else 0x2E3A4D))
            chips.append(prov)
            if pcts[i] > 0:
                chips.append(("%d%% match" % pcts[i], 0xF0F6FC if pcts[i] >= 70 else 0xC9D0DA,
                              0x1E7A4A if pcts[i] >= 70 else CHIP_BG))
            if it.get("downloads"):
                chips.append(u"\u2b07 " + self._kfmt(it["downloads"]))
            if "(HI)" in str(it.get("label") or ""):
                chips.append("HI")
            title = str(it.get("title") or it.get("label") or "Subtitle")
            rows.append(card(i, 1620, 86, title, chips,
                             badge=("BEST", DARK, GOLD) if i == best else None, flag=flag))
        return rows

    def _searchThread(self):
        title = self.search_title
        # (1) collapse Latin series markers
        try:
            from .novaplay_subtitles import clean_play_title as _cpt
            title = _cpt(title) or title
        except Exception:
            pass
        # (2) NEW: strip Arabic season/episode words → bare series name
        try:
            _ep_markers = re.search(
                r"(?:الموسم|موسم|الحلقة|حلقة|والأخيرة|والاخيرة|الأخيرة|الاخيرة|مترجم(?:ة)?|مدبلج(?:ة)?|كامل|مسلسل)\s*[\d\u0660-\u0669]*",
                title)
            if _ep_markers:
                _bare_series = title[:_ep_markers.start()].strip(" -_|")
                if len(_bare_series) >= 3:
                    title = _bare_series
        except Exception:
            pass
        # (3) TMDB English-title fallback (now also fires on Arabic-heavy queries)
        try:
            q = clean_subtitle_query(title, self.video_url)
            _ar_ratio = sum(1 for c in (q or "") if "\u0600" <= c <= "\u06ff") / max(1, len(q or " "))
            if not q or len(q.strip()) < 3 or _ar_ratio > 0.5:
                from .plugin_tmdb import _tmdb_search_metadata
                meta = _tmdb_search_metadata(title, "", "movie")
                if isinstance(meta, dict):
                    for k in ("title", "original_title", "name", "original_name"):
                        if meta.get(k):
                            title = str(meta[k])
                            break
        except Exception:
            pass
        prov = _PROVIDERS[self.provider]
        self._used_title = title            # [2026-11-04] for a one-language search later
        try:
            ok, error, results = prov["search"](title, self.video_url, self.api_key)
        except Exception as e:      # [PATCH 90]
            ok, error, results = False, "Search error: %s" % str(e)[:80], []
        callInMainThread(self._onSearchDone, results or [], ("" if ok else (error or "")))

    def _downloadThread(self):
        prov = _PROVIDERS[self.provider]
        try:
            ok, error, path = prov["download"](
                self.chosen.get("id", ""), self.chosen.get("title", ""), self.api_key)
        except Exception as e:      # [PATCH 90]
            ok, error, path = False, "Download error: %s" % str(e)[:80], ""
        callInMainThread(self._onDownloadDone, bool(ok), error or "Download failed.", path or "")

    def _onSearchDone(self, results, error=""):
        # FIX: user may EXIT while the search thread is in flight —
        # touching widgets on a closed screen raises.
        if getattr(self, "_closed", False):
            return
        try:
            if self.session is None:   # closed screens null this in Enigma2
                return
        except Exception:
            return
        # FIX: results and labels are filtered TOGETHER —
        # filtered empty labels out of the display list only, so any
        # empty label shifted every selection after it onto the wrong
        # subtitle (wrong file downloaded).
        pairs = []
        for i in (results or []):
            label = str(i.get("label") or i.get("title") or "")
            if label:
                pairs.append((label, i))
        if not pairs:
            self._fail(error or 'No subtitles found.')
            return
        self._all = self._yearFirst([i for _, i in pairs])
        self._showLang()

    def _yearFirst(self, items):
        """[2026-11-04] a release naming another year (a remake / the older
        film: "Resident.Evil[2002]" for the 2026 one) goes to the end"""
        m = re.search(r"\b(19\d{2}|20\d{2})\b", self.search_title or "")
        if not m:
            return items
        want = m.group(1)

        def _other(it):
            ys = re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", str(it.get("title") or it.get("label") or ""))
            return 1 if ys and want not in ys else 0
        return sorted(items, key=_other)          # stable: the order otherwise stays

    # ── [2026-11-04] Arabic / English / all, with counts ─────────────
    @staticmethod
    def _langOf(it):
        return lang_code(it.get("language", ""))

    def _pickLang(self):
        """BLUE: every language in the results, with its flag and count"""
        if self.mode != "search" or not self._all:
            return
        counts = {}
        for i in self._all:
            c = self._langOf(i)
            counts[c] = counts.get(c, 0) + 1
        searched = set(sub_langs()) | set(getattr(self, "_extra_langs", set()))
        opts = [("all", u"All languages", "", len(self._all))]
        # [2026-11-04] all 8 languages: found ones with their count, the others
        # "search" (picking one searches just that language, Settings unchanged)
        for c, name, *_r in SUB_LANGS:
            if counts.get(c):
                opts.append((c, name, lang_info(c)[1], counts[c]))
            else:
                opts.append((c, name, lang_info(c)[1], u"none found" if c in searched else u"search \u203a"))
        if counts.get("other"):
            opts.append(("other", u"Other", "", counts["other"]))

        def _picked(c):
            if not c:
                return
            if c in counts or c in ("all", "other"):
                self._setLang(c)
            elif c in searched:
                self._setLang(c)              # shows all, with "(no French ones)"
            else:
                self._searchLang(c)
        self.session.openWithCallback(_picked, NovaLangPick, opts, current=self._lang)

    def _searchLang(self, code):
        """[2026-11-04] one more language, searched on its own and added to
        the list"""
        if self.mode != "search":
            return
        name = lang_info(code)[0] or code
        self.mode = "busy"
        self["header"].setText(u"Searching %s subtitles\u2026" % name)

        def _work():
            global _LANG_ONLY
            prov = _PROVIDERS[self.provider]
            _LANG_ONLY = [code]
            try:
                ok, _err, res = prov["search"](getattr(self, "_used_title", "") or self.search_title,
                                               self.video_url, self.api_key)
            except Exception as e:
                ok, res = False, []
                _log("one-language search %s: %s" % (code, e))
            finally:
                _LANG_ONLY = []
            callInMainThread(self._onLangSearched, code, res if ok else [])
        threading.Thread(target=_work, daemon=True).start()

    def _onLangSearched(self, code, results):
        if getattr(self, "_closed", False):
            return
        try:
            if self.session is None:
                return
        except Exception:
            return
        self.mode = "search"
        self.__dict__.setdefault("_extra_langs", set()).add(code)
        have = set((str(i.get("id")), str(i.get("title"))) for i in self._all)
        for i in results or []:
            if (i.get("label") or i.get("title")) and (str(i.get("id")), str(i.get("title"))) not in have:
                self._all.append(i)
        self._lang = code
        self._showLang()

    def _setLang(self, lang):
        if self.mode != "search" or lang == self._lang:
            return
        self._lang = lang
        try:
            from .plugin_state import _set_config
            _set_config("subs_lang_filter", lang)
        except Exception:
            pass
        if self._all:
            self._showLang()

    def _showLang(self):
        counts = {}
        for i in self._all:
            c = self._langOf(i)
            counts[c] = counts.get(c, 0) + 1
        lang = self._lang
        if lang != "all" and not counts.get(lang):
            lang = "all"                 # none in that language: show them all
        self.results = list(self._all) if lang == "all" else [i for i in self._all if self._langOf(i) == lang]
        self["list"].setRows(self._cardRows(self.results))
        try:
            self["list"].instance.moveSelectionTo(0)
        except Exception:
            pass

        def _t(key, name, n):
            return (u"[ %s %d ]" if key == lang else u"%s %d") % (name, n)
        parts = [_t("all", u"All", len(self._all))]
        shown = ["ar", "en"] + ([lang] if lang not in ("all", "ar", "en") else [])
        for c in shown:
            parts.append(_t(c, lang_info(c)[0] or u"Other", counts.get(c, 0)))
        more = len([c for c in counts if c not in shown])
        if more:
            parts.append(u"+%d more (BLUE)" % more)
        note = u"" if lang == self._lang else u"   (no %s ones)" % (
            lang_info(self._lang)[0] or u"other")
        self["header"].setText(u"%s   %s%s" % (_PROVIDERS[self.provider]["name"], u"   ".join(parts), note))

    def _onDownloadDone(self, ok, error, path):
        if getattr(self, "_closed", False):
            return
        try:
            if self.session is None:
                return
        except Exception:
            return
        if ok and path:
            self.close(path)
        else:
            self._fail(error)

    def _fail(self, message):
        try:
            self.session.openWithCallback(
                lambda a: self.close(""), MessageBox,
                message, MessageBox.TYPE_ERROR, timeout=10)
        except Exception:
            self.close("")

    def _ok(self):
        if self.mode != "search" or not self.results:
            return
        idx = _menu_index(self["list"], len(self.results))
        if idx < 0:
            return
        self.chosen = self.results[idx]
        self.mode = "download"
        self["header"].setText("Downloading: %s" % (self.chosen.get("title") or ""))
        threading.Thread(target=self._downloadThread, daemon=True).start()

    def _cancel(self):
        self.close("")


# Backwards-compatible alias (older patches referenced this name)
NovaSubSourceScreen = NovaOnlineSubsScreen


class NovaLangPick(Screen):
    """[2026-11-04] a language list with flags.
    pick mode:   opts [(code, name, flag, count)] -> closes with the code.
    tick mode:   multi=True, opts [(code, name, flag, on)] -> OK ticks /
                 unticks, EXIT closes with the ticked codes."""

    skin = """
    <screen name="NovaLangPick" position="center,center" size="760,760" backgroundColor="transparent" title="Languages" flags="wfNoBorder">
        <eLabel position="0,0" size="760,760" backgroundColor="#1A121822" cornerRadius="18" zPosition="0" />
        <eLabel position="36,78" size="120,4" backgroundColor="#F2C230" cornerRadius="2" zPosition="2" />
        <widget name="header" position="40,20" size="680,50" font="Bold;34" foregroundColor="#F2C230" transparent="1" zPosition="2" />
        <widget name="list" position="30,100" size="700,590" scrollbarMode="showOnDemand" backgroundColor="#1A121822" backgroundColorSelected="#1A2B3648" zPosition="2" />
        <widget name="hint" position="40,704" size="680,36" font="Regular;22" foregroundColor="#A3ADBB" transparent="1" zPosition="2" />
    </screen>"""

    def __init__(self, session, opts, current="", multi=False, title=u"Subtitle languages"):
        Screen.__init__(self, session)
        self.skinName = ["NovaLangPick"]
        self._opts = list(opts or [])
        self._multi = bool(multi)
        self._on = set(o[0] for o in self._opts if multi and o[3])
        self._current = current
        self["header"] = Label(title if multi else u"Show subtitles in")
        self["hint"] = Label(u"OK tick / untick    EXIT save" if multi else u"OK show    EXIT back")
        from .novaplay_cardlist import CardList
        self["list"] = CardList(width=700, row_h=66)
        self["actions"] = ActionMap(["OkCancelActions"], {"ok": self._ok, "cancel": self._cancel}, -1)
        self._paint()
        self.onLayoutFinish.append(self._focus)

    def _paint(self):
        from .novaplay_cardlist import GOLD, GREEN, MUTED
        rows = []
        for i, (code, name, flag, n) in enumerate(self._opts):
            if self._multi:
                on = code in self._on
                rows.append(self._row(i, name, flag, u"\u2713  On" if on else u"Off",
                                      GREEN if on else MUTED))
            else:
                rows.append(self._row(i, name, flag, str(n), GOLD if code == self._current else MUTED))
        self["list"].setRows(rows)

    @staticmethod
    def _row(i, name, flag, right, right_color):
        from Components.MultiContent import MultiContentEntryText
        from enigma import RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER
        from .novaplay_cardlist import _pixmap, FLAG_W, FLAG_H, F_TITLE, F_SMALL, TEXT, GOLD
        row = [i]
        x = 20
        pm = _pixmap(flag) if flag else None
        if pm is not None:
            try:
                from Components.MultiContent import MultiContentEntryPixmapAlphaBlend
                row.append(MultiContentEntryPixmapAlphaBlend(pos=(x, (66 - FLAG_H) // 2),
                                                             size=(FLAG_W, FLAG_H), png=pm))
            except Exception:
                pass
        x += FLAG_W + 18
        row.append(MultiContentEntryText(pos=(x, 0), size=(440, 66), font=F_TITLE,
                                         flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
                                         text=name, color=TEXT, color_sel=GOLD))
        row.append(MultiContentEntryText(pos=(520, 0), size=(160, 66), font=F_SMALL,
                                         flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER,
                                         text=right, color=right_color, color_sel=right_color))
        return row

    def _focus(self):
        for i, o in enumerate(self._opts):
            if o[0] == self._current:
                self["list"].moveToIndex(i)
                break

    def _ok(self):
        i = self["list"].getSelectedIndex()
        if not (0 <= i < len(self._opts)):
            return
        code = self._opts[i][0]
        if not self._multi:
            self.close(code)
            return
        if code in self._on:
            if len(self._on) > 1:            # at least one language stays on
                self._on.discard(code)
        else:
            self._on.add(code)
        self._paint()
        self["list"].moveToIndex(i)

    def _cancel(self):
        self.close([o[0] for o in self._opts if o[0] in self._on] if self._multi else "")


def open_language_settings(session, done=None):
    """Settings > Subtitle Languages: tick the languages to search"""
    on = set(sub_langs())
    opts = [(c, name, lang_info(c)[1], c in on) for c, name, *_r in SUB_LANGS]

    def _closed(codes):
        if codes:
            set_sub_langs(codes)
        if done:
            done()
    session.openWithCallback(_closed, NovaLangPick, opts, multi=True)


class NovaSubtitleBrowser(Screen):
    """Folder browser for local subtitle files; best match tagged [BEST]."""

    skin = """
    <screen name="NovaSubtitleBrowser" position="center,center" size="1500,860" backgroundColor="transparent" title="Select subtitle" flags="wfNoBorder">
        <eLabel position="0,0" size="1500,860" backgroundColor="#1A121822" cornerRadius="18" zPosition="0" />
        <eLabel position="40,78" size="140,4" backgroundColor="#F2C230" cornerRadius="2" zPosition="2" />
        <widget name="path" position="40,18" size="1420,44" font="Bold;30" foregroundColor="#F2C230" transparent="1" zPosition="2" />
        <widget name="list" position="30,100" size="1440,672" scrollbarMode="showOnDemand" backgroundColor="#1A121822" backgroundColorSelected="#1A2B3648" zPosition="2" />
        <widget name="hint" position="40,800" size="1420,36" font="Regular;24" foregroundColor="#A3ADBB" transparent="1" zPosition="2" />
    </screen>"""

    def __init__(self, session, start_dir="", video_title=""):
        Screen.__init__(self, session)
        self.skinName = ["NovaSubtitleBrowser"]
        video_title = clean_play_title(video_title)
        self.terms = _search_terms(video_title)
        self.words = _significant_words(self.terms)
        self.markers = _episode_markers(self.terms)
        self.entries = []
        self.current_dir = start_dir or subtitle_dir() or "/media/hdd"

        self["path"] = Label(self.current_dir)
        self["hint"] = Label(u"OK open / select   \u00b7   EXIT up a folder / back")
        from .novaplay_cardlist import CardList
        self["list"] = CardList(width=1440, row_h=56, title_size=26)   # [subs-ui]
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self._ok,
            "cancel": self._cancel,
        }, -1)
        self.onLayoutFinish.append(self._refresh)

    def _refresh(self):
        entries = []
        try:
            for name, full, is_dir in _iter_sub_entries(self.current_dir):
                entries.append((name, full, is_dir))
                if len(entries) >= MAX_BROWSER_ENTRIES:
                    break
            entries.sort(key=lambda item: (0 if item[2] else 1, item[0].lower()))
        except Exception:
            entries = []

        best_path, best_score = "", 0
        for name, full, is_dir in entries:
            if not is_dir:
                sc = strict_score(name, self.terms, self.words, self.markers)
                if sc > best_score:
                    best_score, best_path = sc, full

        # [subs-ui] folder / file icons, size + date in grey, BEST in gold
        from .novaplay_cardlist import line, GOLD, MUTED
        rows = []
        self.entries = []
        for n_, (name, full, is_dir) in enumerate(entries):
            if is_dir:
                rows.append(line(n_, 1440, 56, name, icon=u"\U0001F4C1", icon_color=GOLD))
            else:
                info = ""
                try:
                    st = os.stat(full)
                    kb = st.st_size / 1024.0
                    info = ("%.1f MB" % (kb / 1024.0) if kb >= 1024 else "%d KB" % max(1, kb)) + \
                        "   " + time.strftime("%d %b %Y", time.localtime(st.st_mtime))
                except Exception:
                    pass
                best = full == best_path and best_score > 0
                rows.append(line(n_, 1440, 56, name, icon=u"\U0001F4C4", icon_color=MUTED,
                                 right=(u"\u2605 BEST   " + info) if best else info,
                                 right_color=GOLD if best else MUTED,
                                 text_color=0xF2C230 if best else 0xF0F6FC))
            self.entries.append((name, full, is_dir))
        self["list"].setRows(rows)
        self["path"].setText(self.current_dir or "/")

    # ── _ok / _cancel are the only new code in this class (the original
    # handlers were never shared). They close(path) on a file pick,
    # matching plugin.py's _onSubtitlePicked callback contract. ──
    def _ok(self):
        idx = _menu_index(self["list"], len(self.entries))
        if idx < 0 or idx >= len(self.entries):
            return
        name, full, is_dir = self.entries[idx]
        if is_dir:
            self.current_dir = full
            self._refresh()
        elif os.path.exists(full):
            self.close(full)

    def _cancel(self):
        parent = os.path.dirname(self.current_dir.rstrip("/")) or "/"
        if parent and parent != self.current_dir:
            self.current_dir = parent
            self._refresh()
        elif self.current_dir not in ("/", "/media"):
            # top of the subtree — jump to "/" so mounted USB/HDD
            # devices are reachable instead of closing the browser
            self.current_dir = "/"
            self._refresh()
        else:
            self.close("")


class NovaFolderBrowser(Screen):
    """Directory picker for the subtitle folder — remote-friendly
    replacement for typing a path on the VirtualKeyBoard."""

    skin = """
    <screen name="NovaFolderBrowser" position="center,center" size="1500,860" backgroundColor="transparent" title="Select Folder" flags="wfNoBorder">
        <eLabel position="0,0" size="1500,860" backgroundColor="#1A121822" cornerRadius="18" zPosition="0" />
        <eLabel position="40,78" size="140,4" backgroundColor="#F2C230" cornerRadius="2" zPosition="2" />
        <widget name="path" position="40,18" size="1420,44" font="Bold;30" foregroundColor="#F2C230" transparent="1" zPosition="2" />
        <widget name="list" position="30,100" size="1440,680" scrollbarMode="showOnDemand" foregroundColor="#D6DCE5" foregroundColorSelected="#F2C230" backgroundColor="#1A121822" backgroundColorSelected="#1A2B3648" zPosition="2" />
        <widget name="hint" position="40,800" size="1420,36" font="Regular;24" foregroundColor="#A3ADBB" transparent="1" zPosition="2" />
    </screen>"""

    def __init__(self, session, start_dir="/"):
        Screen.__init__(self, session)
        start = start_dir if start_dir and os.path.isdir(start_dir) else "/media/hdd"
        if not os.path.isdir(start):
            start = "/"
        self["path"] = Label(start)
        self["list"] = self._makeFileList(start)
        self["hint"] = Label("OK open  |  GREEN choose  |  RED root  |  YELLOW /media  |  EXIT back")
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
            "ok": self._ok, "cancel": self.close,
            "green": self._select, "red": lambda: self._go("/"),
            "yellow": lambda: self._go("/media"),
            "up": self._up, "down": self._down,
            "left": self._pageUp, "right": self._pageDown,
        }, -1)

    def _makeFileList(self, d):
        for kwargs in [
            {"showDirectories": True, "showFiles": False, "inhibitMounts": False, "inhibitDirs": False, "isTop": False},
            {"showDirectories": True, "showFiles": False, "inhibitMounts": False, "isTop": False},
            {"showDirectories": True, "showFiles": False},
        ]:
            try:
                return FileList(d, **kwargs)
            except Exception:
                continue
        return FileList(d, showDirectories=True, showFiles=False)

    def _go(self, d):
        if os.path.isdir(d):
            try:
                self["list"] = self._makeFileList(d)
                self["path"].setText(d)
            except Exception:
                pass

    def _ok(self):
        try:
            if self["list"].canDescent():
                self["list"].descent()
                self["path"].setText(self._current())
                return
        except Exception:
            pass
        try:
            sel = self["list"].getFilename()
            if sel and os.path.isdir(sel):
                self._go(sel)
        except Exception:
            pass

    def _current(self):
        try:
            c = self["list"].getCurrentDirectory()
            if c:
                return str(c)
        except Exception:
            pass
        return "/"

    def _select(self):
        d = self._current()
        if d and os.path.isdir(d):
            self.close(d)

    def _up(self):
        try: self["list"].up()
        except Exception: pass
    def _down(self):
        try: self["list"].down()
        except Exception: pass
    def _pageUp(self):
        try: self["list"].pageUp()
        except Exception: pass
    def _pageDown(self):
        try: self["list"].pageDown()
        except Exception: pass


class NovaSubtitleSettings(Screen):
    """Subtitle settings: provider API keys, subtitle dir, auto-attach,
    cache clearing."""

    skin = """
    <screen name="NovaSubtitleSettings" position="center,center" size="1500,860" title="Subtitle Settings" flags="wfNoBorder" backgroundColor="transparent">
        <eLabel position="0,0" size="1500,860" backgroundColor="#1A121822" cornerRadius="18" zPosition="0" />
        <eLabel position="40,78" size="140,4" backgroundColor="#F2C230" cornerRadius="2" zPosition="2" />
        <widget name="header" position="40,18" size="1420,52" font="Bold;32" foregroundColor="#F2C230" transparent="1" zPosition="2" />
        <widget name="body" position="40,104" size="1420,660" font="Regular;26" foregroundColor="#D6DCE5" transparent="1" zPosition="2" />
        <eLabel position="20,780" size="1460,62" backgroundColor="#1A212D" cornerRadius="14" zPosition="1" />
        <eLabel position="44,801" size="20,20" backgroundColor="#E5484D" cornerRadius="10" zPosition="2" />
        <widget name="key_red"    position="74,793"  size="290,36" font="Regular;24" valign="center" foregroundColor="#FFFFFF" transparent="1" zPosition="2" />
        <eLabel position="404,801" size="20,20" backgroundColor="#30A46C" cornerRadius="10" zPosition="2" />
        <widget name="key_green"  position="434,793" size="290,36" font="Regular;24" valign="center" foregroundColor="#FFFFFF" transparent="1" zPosition="2" />
        <eLabel position="764,801" size="20,20" backgroundColor="#F2C230" cornerRadius="10" zPosition="2" />
        <widget name="key_yellow" position="794,793" size="290,36" font="Regular;24" valign="center" foregroundColor="#FFFFFF" transparent="1" zPosition="2" />
        <eLabel position="1124,801" size="20,20" backgroundColor="#3E7BFA" cornerRadius="10" zPosition="2" />
        <widget name="key_blue"   position="1154,793" size="310,36" font="Regular;24" valign="center" foregroundColor="#FFFFFF" transparent="1" zPosition="2" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.skinName = ["NovaSubtitleSettings"]
        self["header"] = Label("Subtitle Settings")
        self["body"] = ScrollLabel("")
        self["key_red"] = Label("API Keys")
        self["key_green"] = Label("Subtitle Folder")
        self["key_yellow"] = Label("Test keys")
        self["key_blue"] = Label("Clear Cache")
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "red": self._chooseKey,
            "green": self._editDir,
            "yellow": self._testKeys,
            "blue": self._clearCache,
            "ok": self._chooseKey,
            "cancel": self.close,
        }, -1)
        self._refresh()

    @staticmethod
    def _mask(key):
        return (key[:6] + "..." + key[-4:]) if len(key) > 12 else (key or "(not set)")

    def _refresh(self):
        ss = _ss_api_key()
        osk = _os_api_key()
        # [2026-11-04] up to date: no Auto-Attach, the keys as the player has them
        try:
            langs = u", ".join(lang_info(c)[0] for c in sub_langs())
        except Exception:
            langs = u"Arabic, English"
        txt = (
            u"API keys:\n  SubSource:  %s\n  SubDL:  %s\n  OpenSubtitles:  %s\n\n"
            u"Subtitle Folder:\n  %s\n\n"
            u"Search languages:  %s  (Settings \u203a Subtitles \u203a Subtitle Languages)\n\n"
            u"Subtitles start off. In the player: YELLOW on / off, BLUE \u203a Subtitles to find one;\n"
            u"a subtitle you used is brought back with its sync when you continue a film.\n\n"
            u"Free keys: subsource.net / opensubtitles.com / subdl.com\n\n"
            u"RED / OK keys   GREEN folder   YELLOW test keys   BLUE clear cache   EXIT close"
        ) % (self._mask(ss), self._mask(_sd_api_key()), self._mask(osk),
             _cfg("subtitle_dir", "/media/hdd/subtitles"), langs)
        self["body"].setText(txt)

    _KEY_MAP = {
        "subsource": "subsource_api_key",
        "opensubtitles": "opensubtitles_api_key",
        "subdl": "subdl_api_key",
        "os_user": "opensubtitles_user",
        "os_pass": "opensubtitles_pass",
    }

    def _chooseKey(self):
        entries = [
            ("SubSource API Key", "subsource"),
            ("OpenSubtitles API Key", "opensubtitles"),
            ("SubDL API Key", "subdl"),
            ("OpenSubtitles username (for downloads)", "os_user"),
            ("OpenSubtitles password (for downloads)", "os_pass"),
        ]
        self.session.openWithCallback(self._keyProviderChosen, ChoiceBox,
                                      title="API Keys", list=entries)

    def _keyProviderChosen(self, choice):
        if not choice or VirtualKeyBoard is None:
            return
        which = choice[1]
        current = str(_cfg(self._KEY_MAP[which], "")).strip()
        self.session.openWithCallback(
            lambda v: self._keyCb(which, v), VirtualKeyBoard,
            title=choice[0], text=current)

    def _keyCb(self, which, value):
        if value is not None and str(value).strip():
            _cfg_set(self._KEY_MAP[which], str(value).strip())
        self._refresh()

    def _editDir(self):
        # Browse instead of typing — VKB path entry was typo-prone on a remote.
        if FileList is not None:
            try:
                self.session.openWithCallback(self._dirCb, NovaFolderBrowser,
                                              _cfg("subtitle_dir", "/media/hdd/subtitles"))
                return
            except Exception:
                pass
        if VirtualKeyBoard is None:
            return
        self.session.openWithCallback(self._dirCb, VirtualKeyBoard,
            title="Subtitle folder path",
            text=_cfg("subtitle_dir", "/media/hdd/subtitles"))

    def _dirCb(self, value=None):
        # Called from BOTH the VirtualKeyBoard (value = typed string,
        # possibly None on cancel) and NovaFolderBrowser (value = selected
        # directory string). Some images also re-fire the callback with
        # no arguments during processDelay — tolerate all shapes.
        try:
            if value is not None:
                d = str(value).strip()
                if d:
                    if os.path.isdir(d):
                        _cfg_set("subtitle_dir", d)
                    else:
                        try:
                            os.makedirs(d)
                            _cfg_set("subtitle_dir", d)
                        except Exception:
                            pass
        except Exception:
            pass
        self._refresh()

    def _testKeys(self):
        """[2026-11-04] YELLOW: ask the three subtitle services about their keys"""
        def _work():
            try:
                from . import novaplay_keytest as _kt
                rows = [(l, st, m) for (n, l, _c) in _kt.KEYS if n in ("subsource", "subdl", "opensubtitles")
                        for st, m in [_kt.test_key(n)]]
                txt = _kt.report(rows)
            except Exception as e:
                txt = u"Test failed: %s" % str(e)[:60]
            callInMainThread(lambda: self.session.open(MessageBox, txt, MessageBox.TYPE_INFO))
        self["key_yellow"].setText("Testing\u2026")
        threading.Thread(target=_work, daemon=True).start()
        try:
            self._ktT = eTimer()
            self._ktT.callback.append(lambda: self["key_yellow"].setText("Test keys"))
            self._ktT.start(8000, True)
        except Exception:
            pass

    def _clearCache(self):
        """Delete all cached downloaded subtitles + the subtitle memory file,
        reset in-session subtitle state, then close."""
        freed, n = 0, 0
        try:
            cache_dir = _ss_cache_dir()
            for name in os.listdir(cache_dir):
                full = os.path.join(cache_dir, name)
                try:
                    if os.path.isfile(full):
                        freed += os.path.getsize(full)
                        os.remove(full)
                        n += 1
                except Exception:
                    pass
        except Exception:
            pass
        try:
            mem = _subs_memory_path()
            if os.path.exists(mem):
                freed += os.path.getsize(mem)
                os.remove(mem)
                n += 1
        except Exception:
            pass
        # reset in-session subtitle state
        global _CURRENT_SUB
        _CURRENT_SUB = {"item_url": "", "path": "", "offset_ms": 0}
        msg = "Cleared %d file(s)\n%.1f MB freed" % (n, freed / 1024.0 / 1024.0)
        try:
            self.session.openWithCallback(lambda a: self.close(), MessageBox,
                                          msg, MessageBox.TYPE_INFO, timeout=6)
        except Exception:
            self.close()