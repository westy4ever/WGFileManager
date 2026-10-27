# -*- coding: utf-8 -*-
"""SRT parse/write/shift + sidecar name scoring."""
import re

_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)(.*)")
_COORD = re.compile(r"(X1|X2|Y1|Y2):\s*(\d+)", re.I)
_EP = re.compile(r"S(\d{1,2})E(\d{1,3})|(\b\d{1,2})x(\d{1,3}\b)", re.I)


def _ms(h, m, s, f):
    return ((int(h) * 3600 + int(m) * 60 + int(s)) * 1000) + int(f)


def _cue(block):
    tsi = -1
    for i, l in enumerate(block[:3]):
        if "-->" in l:
            tsi = i
            break
    if tsi < 0:
        return None
    m = _TS.search(block[tsi])
    if not m:
        return None
    coords = {}
    for k, v in _COORD.findall(m.group(9) or ""):
        coords[k.upper()] = int(v)
    text = " ".join(l.strip() for l in block[tsi + 1:] if l.strip())
    italic = bool(re.match(r"^\s*<i>", text, re.I) and re.search(r"</i>\s*$", text, re.I))
    clean = re.sub(r"<[^>]+>", "", text).strip()
    if not clean:
        return None
    return {"start": _ms(m.group(1), m.group(2), m.group(3), m.group(4)),
            "end": _ms(m.group(5), m.group(6), m.group(7), m.group(8)),
            "text": clean, "italic": italic,
            "x1": coords.get("X1"), "y1": coords.get("Y1"),
            "x2": coords.get("X2"), "y2": coords.get("Y2")}


def parse_srt(text):
    cues, block = [], []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.strip() == "":
            if block:
                c = _cue(block)
                if c:
                    cues.append(c)
                block = []
        else:
            block.append(line)
    if block:
        c = _cue(block)
        if c:
            cues.append(c)
    cues.sort(key=lambda c: c["start"])
    return cues


def _fmt(ms):
    ms = max(0, int(ms))
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    s, f = divmod(r, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, f)


def write_srt(cues, path):
    out = []
    for i, c in enumerate(cues):
        out.append("%d\n%s --> %s\n%s\n" % (i + 1, _fmt(c["start"]),
                                            _fmt(c["end"]), c["text"]))
    with open(path, "w") as f:
        f.write(("\n".join(out)).encode("utf-8") if not isinstance(("\n".join(out)), str) else "\n".join(out))


def shifted_copy_text(text, offset_ms):
    cues = parse_srt(text)
    if not cues:
        return None
    for c in cues:
        c["start"] = max(0, c["start"] + offset_ms)
        c["end"] = max(0, c["end"] + offset_ms)
    out = []
    for i, c in enumerate(cues):
        out.append("%d\n%s --> %s\n%s\n" % (i + 1, _fmt(c["start"]),
                                            _fmt(c["end"]), c["text"]))
    return "\n".join(out)


def read_text(path):
    """UTF-8 first; cp1256 (Arabic) fallback; latin-1 last resort."""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "cp1256", "latin-1"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("latin-1", "replace"), "latin-1"


def _stem(name):
    n = re.sub(r"\.[a-z0-9]{1,4}$", "", name.strip().lower())
    return re.sub(r"[\._]", " ", n).strip()


def episode_key(name):
    m = _EP.search(name)
    if not m:
        return None
    if m.group(1) is not None:
        return (int(m.group(1)), int(m.group(2)))
    return (int(m.group(3)), int(m.group(4)))


def score(video_name, sub_name):
    """Heavier weight on episode markers: an E03 video must never
    match an E13 subtitle."""
    v, s = _stem(video_name), _stem(sub_name)
    base = 0
    if s == v:
        base += 1000
    elif s.startswith(v):
        base += 400
    elif v and v in s:
        base += 200
    else:
        base -= 800
    ev, es = episode_key(video_name), episode_key(sub_name)
    if ev and es:
        base += 800 if ev == es else -1500
    elif ev:
        base -= 100
    if ".ar." in sub_name.lower() or sub_name.lower().endswith(".ar.srt"):
        base += 50
    return base