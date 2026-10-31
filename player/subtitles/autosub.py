# -*- coding: utf-8 -*-
"""WGFileManager — background auto-subtitle worker (vendored from NovaPlay).

Background SubSource worker: searches the playing title, picks the best
Arabic (then English) subtitle, downloads it and applies it through the
main thread. Completely silent on any failure — convenience, never
disruption.

Body is novaplay_autosub.py with these changes:
  * _dbg writes to /tmp/wgfilemanager.log
  * _cfg reads through the local JSON bridge
  * _worker / _apply import from .engine and .thread (no novaplay_* names)
  * _http_get's extractors.base.fetch fallback removed
"""

import os
import re
import io
import json
import time
import gzip
import zipfile
import threading
import urllib.request
import urllib.parse

_API = "https://api.subsource.net/api/v1"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_SUB_DIR = "/tmp/wgfm_autosub"
_TIMEOUT = 15

_TAG_RE = re.compile(r"\s*\[\d{3,4}p\]\s*$")
_AR_NOISE = ("فيلم", "مسلسل", "الحلقة", "مترجم", "مترجمة", "مدبلج", "مدبلجة",
             "مشاهدة", "تحميل", "اون لاين", "أون لاين", "كامل", "والموسم", "الحلقات")

# ── CHANGED imports ────────────────────────────────────────────────────
from .config import get as _cfg_get
from .thread import callInMainThread


def _dbg(msg):
    try:
        with open("/tmp/wgfilemanager.log", "a") as f:
            f.write("[subtitles.autosub] %s\n" % msg)
    except Exception:
        pass


def _cfg(key, default):
    return str(_cfg_get(key, default))


def _http_get(url):
    headers = {"User-Agent": _UA}
    if url.startswith(_API):
        _key = _cfg("subsource_api_key", "")
        if _key:
            headers["X-API-Key"] = _key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read()
            if (resp.headers.get("Content-Encoding", "").lower().find("gzip") >= 0
                    or raw[:2] == b"\x1f\x8b"):
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return raw
    except Exception as e:
        _dbg("autosub http error: %s (%s)" % (e, url[:90]))
    return None


def _clean_title(raw):
    t = (raw or "").strip()
    t = _TAG_RE.sub("", t)
    t = t.replace(u"\u2026", " ")
    for w in _AR_NOISE:
        t = t.replace(w, " ")
    t = re.sub(r"\s+", " ", t).strip(" -|:.")
    return t.strip()


def _year_of(t):
    m = re.search(r"\b(19\d{2}|20\d{2})\b", t)
    return m.group(1) if m else ""


def _search_movie(title, year):
    url = "{}/movies/search?searchType=text&q={}&type=all".format(
        _API, urllib.parse.quote_plus(title))
    if year:
        url += "&year=" + year
    raw = _http_get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None
    movies = data.get("movies") or data.get("data") or []
    if isinstance(movies, dict):
        movies = list(movies.values())
    for m in movies:
        mid = m.get("movieId") or m.get("id") or m.get("movieID")
        if mid:
            try:
                return int(mid)
            except Exception:
                pass
    return None


def _list_subs(movie_id, lang):
    url = "{}/subtitles?movieId={}&language={}&limit=100&sort=newest".format(
        _API, movie_id, lang)
    raw = _http_get(url)
    if not raw:
        return []
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return []
    subs = data.get("subtitles") or data.get("data") or []
    if isinstance(subs, dict):
        subs = list(subs.values())
    out = []
    for s in subs:
        sid = s.get("id") or s.get("subtitleId")
        if not sid:
            continue
        name = str(s.get("releaseName") or s.get("linkName") or s.get("name") or "")
        out.append((str(sid), name))
    return out


def _pick_best(subs, title):
    if not subs:
        return None
    tokens = [w for w in re.split(r"[^0-9a-zA-Z]+", title.lower()) if len(w) > 2]

    def score(item):
        name = item[1].lower()
        sc = sum(1 for w in tokens if w in name)
        if "bluray" in name or "brrip" in name or "web" in name:
            sc += 1
        return sc

    return max(subs, key=score)


def _looks_like_sub(raw):
    if not raw or len(raw) < 50:
        return False
    try:
        head = raw[:8192].decode("utf-8", "replace")
    except Exception:
        return False
    if "-->" in head:
        return True
    if head.lstrip().upper().startswith("WEBVTT"):
        return True
    if "[Script Info]" in head:
        return True
    return False


def _extract_sub_data(raw):
    if _looks_like_sub(raw):
        return raw
    if raw[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
            names = [n for n in zf.namelist()
                     if n.lower().endswith((".srt", ".ass", ".vtt", ".txt"))]
            for n in (names or zf.namelist()):
                data = zf.read(n)
                if _looks_like_sub(data):
                    return data
        except Exception:
            pass
        return None
    try:
        d = json.loads(raw.decode("utf-8", "replace"))
        link = d.get("link") or d.get("url") or d.get("download") or d.get("file")
        if isinstance(link, str) and link.startswith("http"):
            raw2 = _http_get(link)
            if raw2:
                return _extract_sub_data(raw2)
    except Exception:
        pass
    return None


def _download_sub(sub_id):
    for url in ("{}/download?subtitleId={}".format(_API, sub_id),
                "{}/subtitle?subtitleId={}".format(_API, sub_id)):
        raw = _http_get(url)
        if raw:
            data = _extract_sub_data(raw)
            if data:
                return data
    return None


def _save(raw):
    try:
        os.makedirs(_SUB_DIR, exist_ok=True)
    except Exception:
        return None
    ext = ".srt"
    try:
        head = raw[:8192].decode("utf-8", "replace")
        if "[Script Info]" in head:
            ext = ".ass"
        elif head.lstrip().upper().startswith("WEBVTT"):
            ext = ".vtt"
    except Exception:
        pass
    path = os.path.join(_SUB_DIR, "auto_%d%s" % (int(time.time()), ext))
    try:
        with open(path, "wb") as fh:
            fh.write(raw)
        return path
    except Exception as e:
        _dbg("autosub save error: %s" % e)
    return None


def auto_subtitle_async(screen, gen):
    t = threading.Thread(target=_worker, args=(screen, gen), daemon=True)
    t.start()


def _try_vidy(screen, gen, title, item_url):
    """[NovaPlay port] Arabic, else English, from Movy's subtitle index
    (subtitles.vidy.st). True when one was applied. No API key, no daily
    limit — tried before SubSource so the user gets subtitles even
    without configuring a SubSource key."""
    try:
        from .engine import vidy_search, vidy_download
        ok, err, results = vidy_search(title, item_url)
        if not ok or not results:
            _dbg("autosub: movy subs - %s" % ((err or "none")[:60]))
            return False
        for r in [x for x in results if x.get("rank", 2) < 2][:4]:
            ok2, _e, path = vidy_download(r.get("id"), title)
            if ok2 and path:
                _apply(screen, gen, path, item_url, str(r.get("language") or ""))
                return True
    except Exception as e:
        _dbg("autosub: movy subs error: %s" % e)
    return False


def _worker(screen, gen):
    try:
        title = _clean_title(getattr(screen, "title", ""))
        item_url = getattr(screen, "_item_url", "")
        if not title:
            return
        # [NovaPlay port] Movy's subtitle index first: no key, no daily
        # limit, matched by TMDB id. Falls through to SubSource if Movy
        # has nothing (or the title has no TMDB id pattern in its URL).
        if _try_vidy(screen, gen, title, item_url):
            return
        api_key = _cfg("subsource_api_key", "").strip()
        if not api_key:
            return
        _dbg("autosub: searching '%s'" % title)
        try:
            from .engine import subsource_search, subsource_download
        except Exception as e:
            _dbg("autosub import error: %s" % e)
            return
        ok, err, results = subsource_search(title, item_url, api_key)
        if not ok or not results:
            _dbg("autosub: no match (%s)" % ((err or "no results")[:60]))
            return
        for r in results[:6]:
            sid = str(r.get("id") or "").strip()
            if not sid:
                continue
            name = str(r.get("label") or r.get("title") or "")
            _dbg("autosub: trying %s (id=%s)" % (name[:60], sid))
            ok2, _err2, path = subsource_download(sid, title, api_key)
            if ok2 and path:
                _apply(screen, gen, path, item_url,
                       str(r.get("language") or ""))
                return
        _dbg("autosub: nothing downloadable")
    except Exception as e:
        _dbg("autosub worker error: %s" % e)


def _apply(screen, gen, path, item_url, lang):
    def _do():
        try:
            if getattr(screen, "_autosub_gen", 0) != gen:
                return
            from .engine import (get_subtitle_state,
                                 apply_subtitle,
                                 remember_subtitle)
            if get_subtitle_state().get("path"):
                return
            apply_subtitle(screen.session, path)
            if item_url:
                remember_subtitle(item_url, path, 0)
            _dbg("autosub: applied [%s] %s" % (lang, path))
            try:
                screen._autoSubNotify("CC OK subtitle auto")
            except Exception:
                pass
        except Exception as e:
            _dbg("autosub apply error: %s" % e)
    try:
        callInMainThread(_do)
    except Exception:
        _do()
