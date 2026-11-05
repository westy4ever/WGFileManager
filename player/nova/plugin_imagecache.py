# -*- coding: utf-8 -*-
"""Nova player (local files) -- the poster in the panel.

A local picture is used as-is. A "tmdb:" address (made by player/nova from
the file name, see poster_query) is looked up on TMDb in the background with
the TMDb key from the keys files (plugin_state._get_config), the poster is
saved under /tmp/wgfm_posters, and the panel paints it on its next refresh
(it repaints every second while it is shown). Nothing found -> the
placeholder stays; the miss is remembered so the lookup isn't repeated.
"""
import hashlib
import json
import os
import re
import threading

try:
    from urllib.parse import quote, unquote
    from urllib.request import Request, urlopen
except ImportError:                                    # py2
    from urllib import quote, unquote
    from urllib2 import Request, urlopen

from .plugin_common import my_log

CACHE_DIR = "/tmp/wgfm_posters"
_TMDB = "https://api.themoviedb.org/3"
_IMG = "https://image.tmdb.org/t/p/w342"
_lock = threading.Lock()
_busy = set()

# words that end a title in a release name ("Movie.Name.2021.1080p.WEB-DL.x264")
_JUNK = re.compile(
    r"\b(?:480p|576p|720p|1080p|2160p|4k|uhd|hdr\d*|dv|web[- ]?dl|web[- ]?rip|webrip|bluray|blu[- ]?ray|"
    r"brrip|bdrip|dvdrip|hdtv|hdrip|x26[45]|h\.?26[45]|hevc|avc|aac\d?(?:\.\d)?|ac3|dts|ddp?\d?(?:\.\d)?|"
    r"atmos|10bit|8bit|remux|proper|repack|extended|unrated|imax|multi|dubbed|subbed|"
    r"arabic|english|nf|amzn|dsnp|hmax|atvp)\b.*$", re.I)


def poster_query(filename):
    """file name -> (title, year, kind) for TMDb; kind "tv" when SxxEyy / 1x02"""
    name = os.path.splitext(os.path.basename(filename or ""))[0]
    name = re.sub(r"[._]+", " ", name)
    name = re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", name)
    kind = "movie"
    m = re.search(r"\bS(\d{1,2})\s*E(\d{1,3})\b|\b(\d{1,2})x(\d{2,3})\b", name, re.I)
    if m:
        kind = "tv"
        name = name[:m.start()]
    year = ""
    ys = list(re.finditer(r"\(?\b(19[3-9]\d|20[0-4]\d)\b\)?", name))
    if ys and ys[-1].start() > 0:                       # a year AFTER the title
        year = ys[-1].group(1)
        name = name[:ys[-1].start()]
    name = _JUNK.sub("", name)
    name = re.sub(r"[-(]+\s*$", "", name)
    name = re.sub(r"\s+", " ", name).strip(" -")
    return name, year, kind


def tmdb_address(filename):
    t, y, k = poster_query(filename)
    return "tmdb:" + quote(json.dumps([t, y, k])) if t else ""


def _cache_file(url):
    return os.path.join(CACHE_DIR, hashlib.md5(url.encode("utf-8")).hexdigest() + ".jpg")


def getCachedImage(url, *a, **k):
    if not url:
        return None
    if url.startswith("tmdb:"):
        p = _cache_file(url)
        return p if os.path.isfile(p) and os.path.getsize(p) > 0 else None
    return url if os.path.isfile(url) else None


def _get_json(url):
    r = urlopen(Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}), timeout=15)
    return json.loads(r.read().decode("utf-8"))


def _lookup(url):
    try:
        title, year, kind = json.loads(unquote(url[len("tmdb:"):]))
        from .plugin_state import _get_config
        key = str(_get_config("tmdb_api_key", "") or "").strip()
        if not key:
            my_log("poster: no TMDb key (api_keys.conf) -- placeholder stays")
            return
        miss = _cache_file(url) + ".none"
        if os.path.isfile(miss):
            return
        q = "{}/search/{}?api_key={}&query={}".format(_TMDB, kind, key, quote(title.encode("utf-8")))
        if year:
            q += ("&year=" if kind == "movie" else "&first_air_date_year=") + year
        res = (_get_json(q).get("results") or [])
        if not res and year:                            # year off by one / missing on TMDb
            res = (_get_json(q.rsplit("&", 1)[0]).get("results") or [])
        poster = next((r.get("poster_path") for r in res if r.get("poster_path")), "")
        if not os.path.isdir(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        if not poster:
            open(miss, "w").close()
            my_log("poster: TMDb has nothing for {!r} {} ({})".format(title, year, kind))
            return
        data = urlopen(Request(_IMG + poster, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
        tmp = _cache_file(url) + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.rename(tmp, _cache_file(url))
        my_log("poster: {!r} {} -> {}".format(title, year, poster))
    except Exception as e:
        my_log("poster lookup failed: {}".format(e))
    finally:
        with _lock:
            _busy.discard(url)


def requestImageAsyncPriority(url, callback=None, *a, **k):
    """local picture: hand it back; tmdb: look it up in a thread (the panel
    repaints and picks the file up from getCachedImage)"""
    if not url:
        return
    if not url.startswith("tmdb:"):
        path = getCachedImage(url)
        if path and callback:
            try:
                callback(path)
            except Exception:
                pass
        return
    if getCachedImage(url):
        return
    with _lock:
        if url in _busy:
            return
        _busy.add(url)
    t = threading.Thread(target=_lookup, args=(url,))
    t.daemon = True
    t.start()
