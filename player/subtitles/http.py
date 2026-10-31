# -*- coding: utf-8 -*-
"""
WGFileManager — minimal HTTP fetcher for the vendored subtitle engine.
Replaces extractors.base.fetch. JSON API reads only; binary subtitle
downloads use raw urlopen inside the engine.
Returns (text, final_url) or (None, url).
"""

import gzip
import io
import re
import zlib

try:
    import urllib.request as _urlreq
    from urllib.parse import urlencode
except ImportError:
    import urllib2 as _urlreq
    from urllib import urlencode

try:
    import brotli
except ImportError:
    try:
        import brotlicffi as brotli
    except ImportError:
        brotli = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")


def _decode(raw, headers):
    ce = (headers.get("Content-Encoding") or "").lower()
    if "gzip" in ce:
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        except Exception:
            pass
    elif "deflate" in ce:
        try:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        except Exception:
            try:
                raw = zlib.decompress(raw)
            except Exception:
                pass
    elif "br" in ce and brotli is not None:
        try:
            raw = brotli.decompress(raw)
        except Exception:
            pass

    ctype = (headers.get("Content-Type") or "").lower()
    enc = "utf-8"
    m = re.search(r"charset=([^\s;]+)", ctype)
    if m:
        enc = m.group(1).strip("\"'")
    for cand in (enc, "utf-8", "windows-1256", "latin-1"):
        try:
            return raw.decode(cand)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def fetch(url, extra_headers=None, post_data=None, timeout=20):
    headers = {
        "User-Agent": UA,
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br" if brotli else "gzip, deflate",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = None
    if post_data is not None:
        if isinstance(post_data, dict):
            data = urlencode(post_data).encode("utf-8")
            headers.setdefault("Content-Type",
                               "application/x-www-form-urlencoded")
        elif isinstance(post_data, str):
            data = post_data.encode("utf-8")
        elif isinstance(post_data, bytes):
            data = post_data
    req = _urlreq.Request(url, data=data, headers=headers)
    try:
        resp = _urlreq.urlopen(req, timeout=timeout)
        try:
            raw = resp.read()
            final = resp.geturl()
            hdrs = {}
            try:
                for k, v in resp.headers.items():
                    hdrs[k] = v
            except Exception:
                try:
                    hdrs = dict(resp.info().items())
                except Exception:
                    pass
            return _decode(raw, hdrs), final
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except Exception:
        return None, url
