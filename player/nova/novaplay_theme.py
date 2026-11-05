# -*- coding: utf-8 -*-
"""NovaPlay -- Theme colour (Green / Blue / Red / Gold) and the armoured frames.

Settings > Theme Colour picks the accent. It is read once when NovaPlay loads
(every screen builds its skin then), so a change takes effect after Enigma2
restarts -- the same as Text Size.

1. Colour: every skin passes through plugin_gridlist.scale_skin_xml(), which
   calls recolor(): the old gold accent (#F2C230) and its pale / dark / tinted
   variants become the chosen colour's. Code that sets colours uses the TH_*
   names below instead of the gold literals.

2. Frames: a skin element marked theme="panel" / theme="card" (a big panel,
   a small card) is drawn as a picture: an armoured metal plate with cut
   corners and a neon edge in the theme colour (images/theme/<colour>/
   <kind>_<w>x<h>.png, made by tools/make_theme_frames.py). An <eLabel>
   becomes an <ePixmap>; a named <widget> becomes a picture widget, so the
   screen's code makes it with Frame() instead of Label(). theme="hide" makes
   an old outline element invisible (the frame has its own edge).
   A picture that is missing leaves the element as it was (recoloured):
   nothing breaks, it just looks flat.
"""
import os
import re

THEMES = (
    ("green", u"Green", (0x39, 0xFF, 0x6A)),
    ("blue", u"Blue", (0x1E, 0x9B, 0xFF)),
    ("red", u"Red", (0xFF, 0x2A, 0x3A)),
    ("gold", u"Gold", (0xF2, 0xC2, 0x30)),
)
DEFAULT = "gold"
_HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_DIR = os.path.join(_HERE, "images", "theme")
KEY_YELLOW = "#F2C231"       # the YELLOW remote-key dots: never recoloured (one off from the old gold)
REQUESTED = set()            # (kind, w, h) every skin asked for -- the frame maker reads this
GENERIC = {"panel": (1200, 720), "card": (520, 300)}   # <kind>_any.png: sizes known only at run time


def theme_name():
    try:
        try:
            from .plugin_state import _get_config
        except ImportError:
            from .plugin_state import _get_config
        v = str(_get_config("theme_colour", DEFAULT) or DEFAULT).lower()
    except Exception:
        v = DEFAULT
    return v if v in [t[0] for t in THEMES] else DEFAULT


def theme_label(name=None):
    name = name or theme_name()
    return dict((t[0], t[1]) for t in THEMES).get(name, u"Gold")


def rgb(name=None):
    name = name or theme_name()
    return dict((t[0], t[2]) for t in THEMES).get(name, THEMES[-1][2])


def _hex(c):
    return "%02X%02X%02X" % tuple(max(0, min(255, int(round(v)))) for v in c)


def _mix(c, other, t):
    return tuple(a + (b - a) * t for a, b in zip(c, other))


_NAME = theme_name()
_C = rgb(_NAME)
TH_GOLD = "#" + _hex(_C)                                   # the accent (was #F2C230)
TH_GOLD_INT = int(_hex(_C), 16)
TH_PALE = "#" + _hex(_mix(_C, (255, 255, 255), 0.62))      # was #E5D1A6 (pale text)
TH_DARK = "#" + _hex(_mix(_C, (0, 0, 0), 0.43))            # was #8A6D1E
TH_DARK_INT = int(_hex(_mix(_C, (0, 0, 0), 0.62)), 16)     # was 0x5C4A12
TH_CHIPSEL = "#1A" + _hex(_mix(_C, (0, 0, 0), 0.71))       # was #1A463A12 (selected chip)
TH_TINT = "#" + _hex(_mix(_C, (12, 16, 23), 0.86))         # was #2A2717 (accent-tinted dark)
if _NAME == "gold":                                        # Gold: exactly today's shades
    TH_PALE, TH_DARK, TH_DARK_INT, TH_CHIPSEL, TH_TINT = "#E5D1A6", "#8A6D1E", 0x5C4A12, "#1A463A12", "#2A2717"

# "#RRGGBB" or "#AARRGGBB" (AA = transparency, kept)
_RECOLOR = tuple((re.compile(r"#((?:[0-9A-Fa-f]{2})?)" + old + r"\b", re.I), new) for old, new in (
    ("F2C230", _hex(_C)),
    ("E5D1A6", TH_PALE[1:]),
    ("8A6D1E", TH_DARK[1:]),
    ("463A12", TH_CHIPSEL[3:]),
    ("2A2717", TH_TINT[1:]),
))


def recolor(text):
    """the gold accent family in a skin / colour string -> the theme's"""
    for rx, new in _RECOLOR:
        text = rx.sub(lambda m: "#" + m.group(1) + new, text)
    return text


def frame_path(kind, w, h, name=None):
    return os.path.join(FRAME_DIR, name or _NAME, "%s_%dx%d.png" % (kind, int(w), int(h)))


_ATTR = re.compile(r'(\w+)="([^"]*)"')
_EL = re.compile(r'<(eLabel|widget)\b([^<>]*?)\btheme="(panel|card|hide)"([^<>]*?)/>', re.S)
_KEEP = ("name", "position", "size", "zPosition")


def _frame_el(m):
    tag, kind = m.group(1), m.group(3)
    attrs = dict(_ATTR.findall(m.group(2) + " " + m.group(4)))
    if kind == "hide":
        if tag == "eLabel":
            return ""
        return '<widget name="%s" position="%s" size="%s" backgroundColor="#FF000000" transparent="1" zPosition="0" />' % (
            attrs.get("name", ""), attrs.get("position", "0,0"), attrs.get("size", "1,1"))
    try:
        w, h = [int(v) for v in attrs.get("size", "").split(",")]
    except Exception:
        return m.group(0).replace(' theme="%s"' % kind, "")
    if w < 60 or h < 40:                             # a placeholder size the code resizes: the general frame
        path = os.path.join(FRAME_DIR, _NAME, "%s_any.png" % kind)
    else:
        REQUESTED.add((kind, w, h))
        path = frame_path(kind, w, h)
    if not os.path.isfile(path):                     # a size made at run time: the general frame, stretched
        path = os.path.join(FRAME_DIR, _NAME, "%s_any.png" % kind)
    if not os.path.isfile(path):                     # no picture at all: the old flat panel
        return m.group(0).replace(' theme="%s"' % kind, "")
    keep = " ".join('%s="%s"' % (k, attrs[k]) for k in _KEEP if k in attrs)
    el = "widget" if tag == "widget" else "ePixmap"
    return '<%s %s pixmap="%s" alphatest="blend" scale="1" />' % (el, keep, path)


def apply(xml):
    """recolour + frames; called by scale_skin_xml() for every skin"""
    if 'theme="' in xml:
        xml = _EL.sub(_frame_el, xml)
    return recolor(xml)


try:
    from Components.Pixmap import Pixmap as _Pixmap
except Exception:                                   # tests without Enigma2
    _Pixmap = object


class Frame(_Pixmap):
    """a theme="panel|card" widget: a picture; takes the Label calls code may
    still make on it (setText) and ignores them"""

    def setText(self, *a, **k):
        pass

    def getText(self):
        return u""
