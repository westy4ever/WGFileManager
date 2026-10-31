# -*- coding: utf-8 -*-
"""Online subtitle providers: SubSource (primary) + OpenSubtitles.com."""
import io
import json
import re
import sys
import time
import zipfile

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


def _request(url, headers=None, data=None, timeout=20):
    """Py2/Py3 HTTP. Returns (status, body_bytes)."""
    if sys.version_info[0] >= 3:
        import urllib.request as ureq
        import urllib.parse as upar
        if isinstance(data, dict):
            data = upar.urlencode(data).encode("utf-8")
        req = ureq.Request(url, data=data, headers=headers or {})
        resp = ureq.urlopen(req, timeout=timeout)
        return resp.getcode(), resp.read()
    else:
        import urllib2 as ureq
        import urllib as upar
        if isinstance(data, dict):
            data = upar.urlencode(data)
        req = ureq.Request(url, data=data, headers=headers or {})
        resp = ureq.urlopen(req, timeout=timeout)
        return resp.getcode(), resp.read()


def _quote(s):
    if sys.version_info[0] >= 3:
        import urllib.parse as upar
        return upar.quote(s)
    import urllib
    return urllib.quote(s)


def _decode_sub(body):
    """bytes -> (text, was_cp1256). cp1256 Arabic re-encoded to UTF-8
    semantics by decoding to unicode here."""
    for enc in ("utf-8", "cp1256", "latin-1"):
        try:
            return body.decode(enc), enc
        except Exception:
            continue
    return body.decode("latin-1", "replace"), "latin-1"


def _extract_srt(body):
    """Handle zip archives and JSON-instead-of-file responses."""
    if body[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(body))
            for n in zf.namelist():
                if n.lower().endswith(".srt"):
                    return zf.read(n)
        except Exception as e:
            logger.warning("[Sub][prov] zip extract failed: %s", e)
            return None
    t = body[:200].strip()
    if t[:1] in (b"{", b"["):
        try:
            j = json.loads(body.decode("utf-8", "replace"))
            # Some endpoints answer with a link/redirect to the file.
            for k in ("link", "url", "file", "download"):
                if isinstance(j, dict) and j.get(k):
                    st, b2 = _request(j[k], headers={"User-Agent": "WGFileManager"})
                    if st == 200:
                        return _extract_srt(b2)
            logger.warning("[Sub][prov] JSON response: %s", str(j)[:200])
        except Exception:
            pass
        return None
    return body


class SubSourceProvider(object):
    ID = "subsource"
    BASE = "https://api.subsource.net/api"

    def __init__(self, state):
        self.state = state
        self.key = state.get("subsource_key", "")

    def _get(self, path):
        st, body = _request(self.BASE + path,
                            headers={"User-Agent": "WGFileManager",
                                     "Accept-Encoding": "identity"})
        if st != 200:
            raise RuntimeError("HTTP %d" % st)
        return body

    @staticmethod
    def _title_variants(query):
        """Multi-title fallback: 'Greenland 2 Migration' -> full title,
        then progressively shorter prefixes."""
        out = [query]
        parts = query.split()
        for cut in range(len(parts) - 1, 1, -1):
            out.append(" ".join(parts[:cut]))
        return out

    def search(self, query, year=None):
        if not self.key:
            return []
        results = []
        for title in self._title_variants(query):
            try:
                data = json.loads(self._get("/search/" + _quote(title)).decode("utf-8", "replace"))
                entries = []
                for sect in ("movies", "tvShows"):
                    entries.extend(data.get(sect) or [])
                if not entries:
                    continue
                best = entries[0]
                if year:
                    for e in entries:
                        if str(year) in (e.get("releaseDate") or ""):
                            best = e
                            break
                link = best.get("linkName")
                if not link:
                    continue
                subs = json.loads(self._get("/subtitles/" + _quote(link)).decode("utf-8", "replace"))
                for s in (subs.get("subtitles") or []):
                    lang = (s.get("langauge") or s.get("language") or "").lower()
                    if lang not in ("arabic", "ar", "english", "en"):
                        continue
                    results.append({
                        "provider": self.ID,
                        "label": "%s  [%s]" % (s.get("releaseName", "?"), lang[:3]),
                        "lang": "ar" if "ar" in lang else "en",
                        "handle": (s.get("releaseName"), s.get("linkName")),
                    })
                if results:
                    # Arabic first, then English.
                    results.sort(key=lambda r: 0 if r["lang"] == "ar" else 1)
                    return results
            except Exception as e:
                logger.warning("[Sub][subsource] search '%s' failed: %s", title, e)
        return results

    def download(self, result):
        release, link = result["handle"]
        body = self._get("/download/%s/%s" % (_quote(release), _quote(link)))
        srt = _extract_srt(body)
        if not srt:
            raise RuntimeError("no srt in response")
        return _decode_sub(srt)[0]


class OpenSubtitlesProvider(object):
    ID = "opensubtitles"
    BASE = "https://api.opensubtitles.com/api/v1"
    LANGS = {"ar": "ara", "en": "eng"}

    def __init__(self, state):
        self.state = state
        self._token = None
        self._token_ts = 0.0

    def _headers(self, auth=False):
        h = {"Api-Key": self.state.get("opensub_key", ""),
             "User-Agent": "WGFileManager",
             "Accept-Encoding": "identity",
             "Content-Type": "application/json"}
        if auth:
            h["Authorization"] = "Bearer " + (self._token or "")
        return h

    def _login(self):
        if self._token and (time.time() - self._token_ts) < 20 * 3600:
            return True
        u, p = self.state.get("opensub_user", ""), self.state.get("opensub_pass", "")
        if not (u and p):
            raise RuntimeError("OpenSubtitles needs username + password")
        st, body = _request(self.BASE + "/login", headers=self._headers(),
                            data=json.dumps({"username": u, "password": p}))
        if st in (401, 403):
            raise RuntimeError("bad login (401/403)")
        j = json.loads(body.decode("utf-8", "replace"))
        self._token = (j.get("token") or "")
        self._token_ts = time.time()
        return bool(self._token)

    def search(self, query, year=None):
        if not self.state.get("opensub_key"):
            return []
        try:
            self._login()
        except Exception as e:
            logger.warning("[Sub][os] login failed: %s", e)
            raise
        url = self.BASE + "/subtitles?query=%s&languages=ara,eng" % _quote(query)
        if year:
            url += "&year=%d" % year
        st, body = _request(url, headers=self._headers(auth=True))
        if st != 200:
            raise RuntimeError("HTTP %d" % st)
        j = json.loads(body.decode("utf-8", "replace"))
        results = []
        for item in (j.get("data") or []):
            a = item.get("attributes") or {}
            fid = None
            for f in (a.get("files") or []):
                fid = f.get("file_id")
                break
            if not fid:
                continue
            lang = (a.get("language") or "")[:3].lower()
            results.append({
                "provider": self.ID,
                "label": "%s  [%s]" % (a.get("release") or a.get("details") or "?", lang),
                "lang": "ar" if "ara" in lang else "en",
                "handle": fid,
            })
        results.sort(key=lambda r: 0 if r["lang"] == "ar" else 1)
        return results

    def download(self, result):
        self._login()
        st, body = _request(self.BASE + "/download", headers=self._headers(auth=True),
                            data=json.dumps({"file_id": result["handle"]}))
        if st == 406:
            raise RuntimeError("daily download quota reached (406)")
        if st != 200:
            raise RuntimeError("download HTTP %d" % st)
        link = (json.loads(body.decode("utf-8", "replace")) or {}).get("link")
        if not link:
            raise RuntimeError("no link in download response")
        st2, body2 = _request(link, headers={"User-Agent": "WGFileManager",
                                             "Accept-Encoding": "identity"})
        if st2 != 200:
            raise RuntimeError("fetch HTTP %d" % st2)
        srt = _extract_srt(body2)
        if not srt:
            raise RuntimeError("no srt in response")
        return _decode_sub(srt)[0]
