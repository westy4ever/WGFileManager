# -*- coding: utf-8 -*-
"""Nova player: the two NovaPlay network helpers the subtitle search uses
(plain HTTP GET), plus no-op quality helpers."""
try:
    from urllib.request import Request, urlopen
except ImportError:                                    # py2
    from urllib2 import Request, urlopen

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def fetch(url, referer=None, extra_headers=None, post_data=None, timeout=20, **k):
    """-> (text, final_url), or (None, url) on error"""
    try:
        hdr = {"User-Agent": _UA}
        if referer:
            hdr["Referer"] = referer
        hdr.update(extra_headers or {})
        data = None
        if post_data is not None:
            if isinstance(post_data, dict):
                try:
                    from urllib.parse import urlencode
                except ImportError:
                    from urllib import urlencode
                data = urlencode(post_data).encode("utf-8")
            else:
                data = post_data if isinstance(post_data, bytes) else str(post_data).encode("utf-8")
        r = urlopen(Request(url, data=data, headers=hdr), timeout=timeout)
        raw = r.read()
        try:
            return raw.decode("utf-8"), r.geturl()
        except Exception:
            return raw.decode("latin-1"), r.geturl()
    except Exception:
        return None, url


def _label_quality_variant(url): return ""
def get_last_quality_variants(*a, **k): return []
