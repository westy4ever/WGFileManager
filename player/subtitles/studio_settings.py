# -*- coding: utf-8 -*-
"""Studio settings overlay (guide §4) — card grid driving STUDIO.

< > select card    ^ v adjust    OK picker    EXIT save+close.
Changes apply on the next poll tick (overlay polls at 100 ms; this
screen invalidates STUDIO._last_rendered after each change).
Delay here is the LIVE renderer offset (STUDIO.set_offset); the
subtitle menu's Sync entries use the engine's shifted-file path.
"""
from enigma import eTimer, getDesktop, gRGB

from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Components.ActionMap import ActionMap
from Components.Label import Label

from .studio import STUDIO, _COLORS
from .engine import update_subtitle_state

_ALIGN = [("Top", 0), ("Bottom", 1), ("Middle", 2)]
_DELAY_OPTS = (-2000, -1000, -500, -250, 0, 250, 500, 1000, 2000)

_CARDS = [
    ("Delay", "delay", "delay"),
    ("Size", "int", "size"),
    ("Color", "color", "color_idx"),
    ("Outline", "bool", "outline"),
    ("Outline col", "color", "outline_color_idx"),
    ("Background", "bool", "bg"),
    ("BG alpha", "int", "bg_alpha"),
    ("Pos Y", "int", "offset_y"),
    ("Align", "align", "align"),
    ("Spacing", "int", "spacing"),
    ("Auto-wrap", "bool", "auto_wrap"),
    ("Cue pos", "bool", "use_cue_pos"),
    ("Save preset", "action", "__save"),
    ("Load preset", "action", "__load"),
    ("Reset style", "action", "__reset"),
]

_INT_RANGES = {
    "size": (22, 80, 2),
    "bg_alpha": (0, 255, 16),
    "offset_y": (-250, 120, 10),
    "spacing": (0, 120, 4),
}


class StudioSettingsScreen(Screen):
    skinName = ["WGStudioSettings"]

    def __init__(self, session):
        self.session = session
        try:
            s = getDesktop(0).size()
            dw, dh = s.width(), s.height()
        except Exception:
            dw, dh = 1280, 720
        w, h = min(dw, 1280), min(dh, 720)
        cw, ch = (w - 70) // 5, (h - 230) // 3
        cards = []
        for i in range(len(_CARDS)):
            r, c = divmod(i, 5)
            cards.append('  <widget name="card_%d" position="%d,%d" size="%d,%d" '
                         'font="Regular;20" halign="center" valign="center" '
                         'backgroundColor="#001B2A44" transparent="0" />'
                         % (i, 10 + c * (cw + 12), 10 + r * (ch + 12), cw, ch))
        self.skin = ('<screen name="WGStudioSettings" position="center,center" '
                     'size="%d,%d" title="Studio Settings" '
                     'backgroundColor="#00101010" flags="wfNoBorder">\n%s\n'
                     '  <widget name="hint" position="10,%d" size="%d,36" '
                     'font="Regular;20" foregroundColor="#00FFD24D" '
                     'backgroundColor="#00101010" transparent="0" />\n'
                     '  <widget name="preview" position="10,%d" size="%d,80" '
                     'font="Regular;26" halign="center" valign="center" '
                     'foregroundColor="#00FFFFFF" '
                     'backgroundColor="#00101010" transparent="0" />\n</screen>'
                     % (w, h, "\n".join(cards), h - 170, w - 20, h - 120, w - 20))
        Screen.__init__(self, session)
        for i in range(len(_CARDS)):
            self["card_%d" % i] = Label("")
        self["hint"] = Label("< > select   ^ v adjust   OK picker   EXIT save")
        self["preview"] = Label("")
        self.idx = 0
        self["actions"] = ActionMap(
            ["WizardActions", "OkCancelActions"],
            {"left": self._left, "right": self._right, "up": self._up,
             "down": self._down, "ok": self._ok, "cancel": self._save_close},
            -2)
        self._ptimer = eTimer()
        try:
            self._ptimer.timeout.connect(self._refresh_preview)
        except Exception:
            self._ptimer.callback.append(self._refresh_preview)
        self._ptimer.start(500, False)
        self.onShow.append(self._repaint)

    # ---------------------------------------------------------- helpers
    def _style(self):
        return STUDIO.style

    def _card_value(self, i):
        _t, kind, key = _CARDS[i]
        st = self._style()
        if kind == "bool":
            return "ON" if st.get(key) else "OFF"
        if kind == "int":
            return str(st.get(key, 0))
        if kind == "color":
            return _COLORS[int(st.get(key, 0)) % len(_COLORS)][1]
        if kind == "align":
            for lbl, v in _ALIGN:
                if v == st.get(key, 1):
                    return lbl
            return "Bottom"
        if kind == "delay":
            return "%+d ms" % STUDIO.get_offset()
        return ""

    def _repaint(self):
        for i in range(len(_CARDS)):
            self["card_%d" % i].setText(
                "%s\n%s" % (_CARDS[i][0], self._card_value(i)))
            try:
                inst = self["card_%d" % i].instance
                if inst is not None:
                    inst.setBackgroundColor(
                        gRGB(0x002E86C1 if i == self.idx else 0x001B2A44))
            except Exception:
                pass
        self._refresh_preview()

    def _refresh_preview(self):
        try:
            body = STUDIO.get_preview()
            txt = " ".join(body) if body else "(no active cue)"
        except Exception:
            txt = ""
        self["preview"].setText(txt)

    def _apply(self):
        try:
            STUDIO._layout_static()
            STUDIO._last_rendered = None   # re-render on next poll tick
        except Exception:
            pass
        self._repaint()

    # -------------------------------------------------------- movement
    def _left(self):
        self.idx = (self.idx - 1) % len(_CARDS)
        self._repaint()

    def _right(self):
        self.idx = (self.idx + 1) % len(_CARDS)
        self._repaint()

    def _adjust(self, d):
        _t, kind, key = _CARDS[self.idx]
        st = self._style()
        if kind == "bool":
            st[key] = not st.get(key)
        elif kind == "int":
            lo, hi, step = _INT_RANGES[key]
            st[key] = max(lo, min(hi, int(st.get(key, 0)) + d * step))
        elif kind == "color":
            st[key] = (int(st.get(key, 0)) + d) % len(_COLORS)
        elif kind == "align":
            st[key] = (int(st.get(key, 1)) + d) % 3
        elif kind == "delay":
            v = max(-10000, min(10000, STUDIO.get_offset() + d * 250))
            STUDIO.set_offset(v)
            update_subtitle_state(offset_ms=v)
        self._apply()

    def _up(self):
        self._adjust(1)

    def _down(self):
        self._adjust(-1)

    # --------------------------------------------------------- actions
    def _ok(self):
        _t, kind, key = _CARDS[self.idx]
        st = self._style()
        if kind == "delay":
            self.session.openWithCallback(self._set_delay, ChoiceBox,
                                          title="Delay",
                                          list=[("%+d ms" % v, v)
                                                for v in _DELAY_OPTS])
        elif kind == "color":
            self.session.openWithCallback(self._pick_color, ChoiceBox,
                                          title=_t,
                                          list=[(n, i) for i, (_h, n)
                                                in enumerate(_COLORS)])
        elif kind == "align":
            self.session.openWithCallback(self._pick_align, ChoiceBox,
                                          title=_t,
                                          list=[(l, v) for l, v in _ALIGN])
        elif key == "__save":
            self.session.openWithCallback(self._save_preset, ChoiceBox,
                                          title="Save preset",
                                          list=[("A", "A"), ("B", "B"), ("C", "C")])
        elif key == "__load":
            self.session.openWithCallback(self._load_preset, ChoiceBox,
                                          title="Load preset",
                                          list=[(k, k) for k in ("A", "B", "C")])
        elif key == "__reset":
            STUDIO.reset_style()
            self._repaint()

    def _set_delay(self, choice):
        if not choice:
            return
        STUDIO.set_offset(int(choice[1]))
        update_subtitle_state(offset_ms=int(choice[1]))
        self._apply()

    def _pick_color(self, choice):
        if not choice:
            return
        self._style()[_CARDS[self.idx][2]] = choice[1]
        self._apply()

    def _pick_align(self, choice):
        if not choice:
            return
        self._style()[_CARDS[self.idx][2]] = choice[1]
        self._apply()

    def _save_preset(self, choice):
        if choice:
            STUDIO.save_preset(choice[1])
            self._repaint()

    def _load_preset(self, choice):
        if choice and STUDIO.load_preset(choice[1]):
            self._apply()

    def _save_close(self):
        STUDIO.flush_style()
        self.close()