# -*- coding: utf-8 -*-
"""WGFileManager / Nova player -- the plugin_util helpers the player uses,
copied from NovaPlay's plugin_util.py (only these; nothing site-related)."""
import os
import re
import hashlib

SAFE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"


_POSTER_CACHE_DIR = "/tmp/ap_cache"


def _strip_arabic_from_english_title(title):
    """Strip Arabic wrapper words -- site boilerplate meaning roughly
    "Movie ... translated online" around an English name -- keeping just
    the English title.

    [FIX] This used to bail out and return the title UNTOUCHED whenever
    Arabic characters made up >=30% of it -- meant to protect a genuinely
    Arabic-native title from being destroyed, but a site's own wrapper
    phrase alone (three Arabic words, a dozen-plus letters) is long
    enough that any short English name (e.g. "Rolling Loud") pushes the
    Arabic share past 30%, so the guard fired on exactly the case this
    function exists to fix and the raw Arabic+English title got shown
    as-is. Now it strips first and only falls back to the original when
    nothing meaningful survives (a title with no real English name at
    all), rather than refusing to even try based on a character count."""
    if not title:
        return title
    cleaned = re.sub(r"[\u0600-\u06ff]+", " ", title)
    cleaned = re.sub(r"[\s|\-–_]+$", "", cleaned)
    cleaned = re.sub(r"^[\s|\-–_]+", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -|_")
    # [2026-11-04] an Arabic title has no English name to keep: what is left
    # is only numbers ("طالع نازل الموسم 1 الحلقة 7" -> "1 7"), which named the
    # player "7 7" and found a wrong film on TMDb -> keep the Arabic title
    if not re.search(r"[A-Za-z]", cleaned):
        return title
    return cleaned if len(cleaned) >= 2 else title


def _wrap_ui_text(text, width=40, max_lines=2, fallback=""):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return fallback
    words = text.split(" ")
    lines = []
    current = ""

    for word in words:
        candidate = word if not current else "{} {}".format(current, word)
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            if len(lines) >= max_lines:
                break
        current = word

    if len(lines) < max_lines and current:
        lines.append(current)
    if not lines:
        lines = [text[:width]]

    consumed = " ".join(lines)
    if len(consumed) < len(text):
        if lines:
            lines[-1] = lines[-1].rstrip(" .،") + "..."
    return "\n".join(lines[:max_lines])


def _single_line_text(text, width=54, fallback=""):
    return _wrap_ui_text(text, width=width, max_lines=1, fallback=fallback)


def server_mark(s):
    """the text in front of a server's name: ★ / ✗ / nothing"""
    return {"good": u"\u2605 ", "broken": u"\u2717 "}.get((s or {}).get("_mark") or "", u"")


_AR_ORD = {u"الاول": 1, u"الأول": 1, u"الثاني": 2, u"الثانى": 2, u"الثالث": 3, u"الرابع": 4,
           u"الخامس": 5, u"السادس": 6, u"السابع": 7, u"الثامن": 8, u"التاسع": 9, u"العاشر": 10}


def _ar_num(tok):
    tok = (tok or "").strip()
    if tok in _AR_ORD:
        return _AR_ORD[tok]
    tok = tok.translate({ord(c): ord("0") + i for i, c in enumerate(u"٠١٢٣٤٥٦٧٨٩")})
    return int(tok) if tok.isdigit() else 0


def split_card_title(title):
    """[2026-10-28] Continue Watching cards: the season / episode words out of
    the title, as a short marker for the second line --
        "Phony الموسم الاول الحلقة 2"  ->  ("Phony", "S1 E2")
        "The Bear S02E05"             ->  ("The Bear", "S2 E5")
        "مسلسل X الحلقة 12"            ->  ("مسلسل X", "EP 12")
        "Verity 2026"                 ->  ("Verity 2026", "")"""
    t = (title or "").strip()
    season = ep = 0
    m = re.search(r"\bS(\d{1,3})\s*E(\d{1,4})\b", t, re.I)
    if m:
        season, ep = int(m.group(1)), int(m.group(2))
        t = (t[:m.start()] + " " + t[m.end():])
    m = re.search(u"(?:الموسم|موسم)\\s+(\\S+)", t)
    if m and _ar_num(m.group(1)):
        season = season or _ar_num(m.group(1))
        t = t[:m.start()] + " " + t[m.end():]
    m = re.search(u"(?:الحلقة|حلقة)\\s*([\\d٠-٩]+)", t)
    if m:
        ep = ep or _ar_num(m.group(1))
        t = t[:m.start()] + " " + t[m.end():]
    m = re.search(r"\bseason\s*(\d+)", t, re.I)
    if m:
        season = season or int(m.group(1))
        t = t[:m.start()] + " " + t[m.end():]
    m = re.search(r"\bepisode\s*(\d+)", t, re.I)
    if m:
        ep = ep or int(m.group(1))
        t = t[:m.start()] + " " + t[m.end():]
    if not (season or ep):
        return (title or "").strip(), ""
    t = re.sub(r"\s+", " ", t).strip(u" -:|\u2013\u00b7")
    if season and ep:
        mark = u"S%d E%d" % (season, ep)
    else:
        mark = (u"S%d" % season) if season else (u"EP %d" % ep)
    return (t or (title or "").strip()), mark


def _poster_cache_path(url):
    if not url: return None
    try:
        if not os.path.isdir(_POSTER_CACHE_DIR):
            os.makedirs(_POSTER_CACHE_DIR)
    except Exception: pass
    url_hash = hashlib.md5(url.encode("utf-8", "ignore")).hexdigest()
    return os.path.join(_POSTER_CACHE_DIR, "{}.jpg".format(url_hash))


def _get_cached_poster(url):
    path = _poster_cache_path(url)
    if path and os.path.exists(path):
        return path
    # Delegate to the shared async image cache (HDD-backed, survives
    # reboots) before falling back to None. Detail decodes with ePicLoad,
    # which handles any size, so exact-size keying doesn't matter here.
    try:
        from . import plugin_imagecache
        shared = plugin_imagecache.getCachedImage(url)
        if shared:
            return shared
    except Exception:
        pass
    return None


def quality_key(label):
    """[2026-10-28] one key per resolution, so the same quality listed twice
    (two 480p mirrors, "720p" / "1280x720" / "720P HD") shows once"""
    t = str(label or "").strip().lower()
    if "4k" in t or "2160" in t:
        return "2160p"
    m = re.search(r"(\d{3,4})\s*p\b", t) or re.search(r"\d{3,4}\s*x\s*(\d{3,4})", t)
    return (m.group(1) + "p") if m else t


def title_year(title, year=""):
    """[2026-10-30] "The Hunted 2026" -> ("The Hunted", "2026"): the year in
    the title picks the right film on TMDb (without it TMDb chose the 2003
    The Hunted for the 2026 one)"""
    title = str(title or "").strip()
    m = re.search(r"[\(\[]?\b(19[2-9]\d|20[0-4]\d)\b[\)\]]?\s*$", title)
    if m and int(m.group(1)) <= __import__("time").localtime().tm_year + 1 and len(title[:m.start()].strip()) >= 2:
        return title[:m.start()].strip(), str(year or m.group(1))[:4]
    return title, str(year or "")[:4]


def fit_title_line(name, bits, maxch):
    """[2026-10-31] "Name  ·  2026 · ★ 6.9 · Horror" within maxch characters:
    leave out the last items (genre, then rating, then year) instead of
    cutting the line with "…"; only a name too long on its own is cut"""
    bits = [b for b in (bits or []) if b]
    while True:
        line = name + ((u"  \u00b7  " + u" \u00b7 ".join(bits)) if bits else u"")
        if len(line) <= maxch or not bits:
            break
        bits = bits[:-1]
    if len(line) > maxch:
        line = _single_line_text(name, width=maxch, fallback=name)
    return line
