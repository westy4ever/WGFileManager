# -*- coding: utf-8 -*-
"""NovaPlay -- per-series choices remembered across episodes (2026-10-28).

When you change the audio track or the subtitles in one episode, the next
episodes of the same series start the same way (like Netflix):

    audio     language of the chosen audio track       ("eng", "ara", ...)
    sub_lang  language of the chosen subtitles         ("arabic" / "english")
    subs      "off" when you turned subtitles off       (no auto subtitles)

The series is recognised from the title: "The Bear S02E05" and
"The Bear S02E06" are the same series; "مسلسل X الحلقة 5" and "... الحلقة 6"
too. Stored in the settings under "series_prefs" (newest 300 series).
"""
import re
import time

_KEY = "series_prefs"
_MAX = 300


def series_key(title):
    """series name from an episode title; "" when it isn't an episode"""
    t = str(title or "")
    m = re.search(r"\bS\d{1,2}\s*E\d{1,3}\b", t, re.I)
    if not m:
        m = re.search(u"(?:الحلقة|حلقة)\\s*[\\d٠-٩]+", t)
    if not m:
        return ""
    name = t[:m.start()]
    name = re.sub(u"(?:الموسم|موسم)\\s*[\\d٠-٩]*", " ", name)
    name = re.sub(r"\bseason\s*\d+\b", " ", name, flags=re.I)
    name = re.sub(r"[^0-9a-z؀-ۿ]+", " ", name.lower()).strip()
    return name


def get(title):
    key = series_key(title)
    if not key:
        return {}
    try:
        from .plugin_state import _get_config
        return dict((_get_config(_KEY, {}) or {}).get(key, {}) or {})
    except Exception:
        return {}


def set_pref(title, **values):
    key = series_key(title)
    if not key:
        return
    try:
        from .plugin_state import _get_config, _set_config
        allp = dict(_get_config(_KEY, {}) or {})
        cur = dict(allp.get(key, {}) or {})
        for k, v in values.items():
            if v is None:
                cur.pop(k, None)
            else:
                cur[k] = v
        cur["_ts"] = int(time.time())
        allp[key] = cur
        if len(allp) > _MAX:
            for k, _v in sorted(allp.items(), key=lambda kv: kv[1].get("_ts", 0))[:len(allp) - _MAX]:
                allp.pop(k, None)
        _set_config(_KEY, allp)
    except Exception:
        pass


def subtitle_language(path):
    """"arabic" / "english" guessed from a subtitle file's text"""
    try:
        with open(path, "rb") as f:
            raw = f.read(6000).decode("utf-8", "replace")
    except Exception:
        return ""
    letters = [c for c in raw if c.isalpha()]
    if not letters:
        return ""
    ar = sum(1 for c in letters if u"؀" <= c <= u"ۿ")
    return "arabic" if ar > len(letters) * 0.3 else "english"
