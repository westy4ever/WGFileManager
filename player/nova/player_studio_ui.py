# -*- coding: utf-8 -*-
"""NovaPlay -- Subtitle Studio as a side panel (2026-10-31).

The studio used to be a strip across the top of the picture with five text
cards ("Size: 32 px"). It is now a rounded panel on the right, in the style of
modern players: tabs (Style / Position / Sync / More) and one row per setting,
drawn as what it is -- size chips, colour dots, sliders, Off/On buttons,
action buttons. The subtitles keep running under it, so every change is seen.

Remote:  ▲ ▼ row   ◀ ▶ change   OK button / menu   1-4 or CH+/- tab   EXIT close

Only the look and the keys are new: the values, limits, saving (flush on
close), presets, font picker, "pick line to sync" and remove are the studio's
existing code in player_subs.py (PlayerSubs), reached through _studioIdx /
_studioAdjust / _studioOk.
"""

# ── layout (1920x1080 skin coordinates) ──────────────────────────────────
SX, SY, SW, SH = 1080, 64, 780, 812
ROWS = 6
ROW_Y0 = SY + 166
ROW_H = 96
CHIPS = 6
TAB_X = (SX + 40, SX + 190, SX + 320, SX + 510)
TAB_W = (120, 100, 160, 110)

GOLD = "#F2C230"
WHITE = "#F2F6FC"
MUTED = "#8B949E"
# [2026-11-04] slightly see-through, the same as the BLUE / MENU panels
CARD = "#1A121822"
ROWBG = "#1A1C2432"
CHIPBG = "#1A232C3B"
CHIPSEL = "#1A463A12"
TRACK = "#1A343C4A"

TABS = (u"Style", u"Box", u"Position", u"Sync")    # [2026-10-31] Box: background + corners

# the settings on each tab (keys of PlayerSubs._studioItemsList)
TAB_KEYS = (
    ("size", "color", "outline", "fixcaps", "font", "reset"),     # [2026-10-31] Bold removed; [2026-11-04] + fix capitals
    ("bg", "corners"),
    ("offset_y", "align"),          # [2026-10-31] line spacing / positions from the file removed
    ("delay", "finedelay", "pickline"),      # [2026-11-04] + fine sync (0.1 s)
)       # [2026-10-31] outline colour, split long lines, presets and Turn off removed
LABELS = {
    "size": u"TEXT SIZE", "color": u"COLOR", "bg": u"BACKGROUND",
    "outline": u"OUTLINE", "bold": u"BOLD", "corners": u"BOX CORNERS", "offset_y": u"VERTICAL POSITION", "align": u"PLACE ON SCREEN",
    "spacing": u"LINE SPACING", "cuepos": u"POSITIONS FROM THE FILE", "delay": u"SYNC TO AUDIO", "fixcaps": u"FIX CAPITALS", "finedelay": u"FINE SYNC",
    "pickline": u"SYNC TO A LINE", "font": u"FONT", "ocolor": u"OUTLINE COLOR",
    "autowrap": u"SPLIT LONG LINES", "presets": u"PRESETS A / B / C",
    "reset": u"DEFAULT STYLE", "remove": u"SUBTITLES",
}
SIZE_PCTS = (75, 100, 125, 150, 200)
SIZE_BASE = 38                      # the studio's default size (100 %)
BG_STEPS = (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100)   # % solid; 0 = no box
ALIGN_ORDER = (0, 2, 1)             # style "align": 0 top, 1 bottom, 2 centre -> shown Top / Center / Bottom
ACTIONS = {"pickline": u"Pick the line you hear  ›", "font": u"Choose a font  ›",
           "presets": u"Save / load  ›", "reset": u"Reset style", "remove": u"Turn off"}


def _row_names(r):
    return (["sRowBg%d" % r, "sRowEdge%d" % r, "sLbl%d" % r, "sVal%d" % r,
             "sTrack%d" % r, "sFill%d" % r, "sKnob%d" % r, "sRing%d" % r]
            + ["sChip%d_%d" % (r, k) for k in range(CHIPS)]
            + ["sDot%d_%d" % (r, k) for k in range(CHIPS)])


HEAD = ("studioCardBg", "studioHead", "studioClose", "studioTabLine", "studioRule", "studioHint") + \
       tuple("studioTabT%d" % i for i in range(4))
STUDIO_WIDGETS = HEAD + tuple(n for r in range(ROWS) for n in _row_names(r))


def studio_skin_xml():
    out = [
        '<widget name="studioCardBg" position="{x},{y}" size="{w},{h}" backgroundColor="{c}" cornerRadius="28" zPosition="85" />'
        .format(x=SX, y=SY, w=SW, h=SH, c=CARD),
        '<widget name="studioHead" position="{x},{y}" size="400,34" font="Bold;24" foregroundColor="{m}" backgroundColor="{c}" transparent="1" zPosition="89" />'
        .format(x=SX + 40, y=SY + 26, m=MUTED, c=CARD),
        '<widget name="studioClose" position="{x},{y}" size="200,34" font="Regular;22" halign="right" foregroundColor="{m}" backgroundColor="{c}" transparent="1" zPosition="89" />'
        .format(x=SX + SW - 240, y=SY + 28, m=MUTED, c=CARD),
        '<widget name="studioRule" position="{x},{y}" size="{w},2" backgroundColor="#1A2C3442" zPosition="86" />'
        .format(x=SX + 2, y=SY + 142, w=SW - 4),
        '<widget name="studioTabLine" position="{x},{y}" size="100,6" backgroundColor="{g}" cornerRadius="3" zPosition="88" />'
        .format(x=TAB_X[0], y=SY + 130, g=GOLD),
        '<widget name="studioHint" position="{x},{y}" size="{w},34" font="Regular;20" foregroundColor="{m}" backgroundColor="{c}" transparent="1" zPosition="89" />'
        .format(x=SX + 40, y=SY + SH - 52, w=SW - 80, m=MUTED, c=CARD),
    ]
    for i in range(4):
        out.append('<widget name="studioTabT{i}" position="{x},{y}" size="{w},48" font="Regular;30" foregroundColor="{m}" backgroundColor="{c}" transparent="1" zPosition="89" />'
                   .format(i=i, x=TAB_X[i], y=SY + 78, w=TAB_W[i], m=MUTED, c=CARD))
    for r in range(ROWS):
        y = ROW_Y0 + r * ROW_H
        out.append('<widget name="sRowBg{r}" position="{x},{y}" size="{w},{h}" backgroundColor="{c}" cornerRadius="16" zPosition="86" />'
                   .format(r=r, x=SX + 18, y=y, w=SW - 36, h=ROW_H - 8, c=ROWBG))
        out.append('<widget name="sRowEdge{r}" position="{x},{y}" size="6,{h}" backgroundColor="{g}" cornerRadius="3" zPosition="87" />'
                   .format(r=r, x=SX + 18, y=y + 8, h=ROW_H - 24, g=GOLD))
        out.append('<widget name="sLbl{r}" position="{x},{y}" size="440,30" font="Bold;20" foregroundColor="{m}" backgroundColor="{c}" transparent="1" zPosition="89" />'
                   .format(r=r, x=SX + 40, y=y + 6, m=MUTED, c=CARD))
        out.append('<widget name="sVal{r}" position="{x},{y}" size="300,30" font="Regular;22" halign="right" foregroundColor="{wh}" backgroundColor="{c}" transparent="1" zPosition="89" />'
                   .format(r=r, x=SX + SW - 340, y=y + 4, wh=WHITE, c=CARD))
        out.append('<widget name="sTrack{r}" position="{x},{y}" size="{w},8" backgroundColor="{t}" cornerRadius="4" zPosition="87" />'
                   .format(r=r, x=SX + 50, y=y + 56, w=SW - 100, t=TRACK))
        out.append('<widget name="sFill{r}" position="{x},{y}" size="10,8" backgroundColor="{g}" cornerRadius="4" zPosition="88" />'
                   .format(r=r, x=SX + 50, y=y + 56, g=GOLD))
        out.append('<widget name="sKnob{r}" position="{x},{y}" size="30,30" backgroundColor="{g}" cornerRadius="15" zPosition="90" />'
                   .format(r=r, x=SX + 50, y=y + 45, g=GOLD))
        out.append('<widget name="sRing{r}" position="{x},{y}" size="56,56" backgroundColor="{g}" cornerRadius="28" zPosition="88" />'
                   .format(r=r, x=SX + 40, y=y + 32, g=GOLD))
        for k in range(CHIPS):
            out.append('<widget name="sChip{r}_{k}" position="{x},{y}" size="120,44" font="Regular;22" halign="center" valign="center" foregroundColor="{wh}" backgroundColor="{cb}" cornerRadius="12" zPosition="89" />'
                       .format(r=r, k=k, x=SX + 40 + k * 124, y=y + 38, wh=WHITE, cb=CHIPBG))
            out.append('<widget name="sDot{r}_{k}" position="{x},{y}" size="44,44" backgroundColor="#FFFFFF" cornerRadius="22" zPosition="89" />'
                       .format(r=r, k=k, x=SX + 46 + k * 76, y=y + 38))
    return "\n        ".join(out)


class PlayerStudioUI(object):
    """Overrides the studio's look and keys (listed before PlayerSubs and
    PlayerControls in the player's bases, so these methods win)."""

    # old slide code (player_osd._applyStudioSlide) has nothing to move
    _STUDIO_DESIGN_Y = {}
    _STUDIO_KEYS = STUDIO_WIDGETS

    # ── state ──────────────────────────────────────────────────────────
    def _studioTabNow(self):
        return int(getattr(self, "_studioTab", 0)) % len(TABS)

    def _studioKeysNow(self):
        have = set(it[2] for it in (getattr(self, "_studioItems", None) or []))
        return [k for k in TAB_KEYS[self._studioTabNow()] if k in have]

    def _studioSelectKey(self, key):
        for i, it in enumerate(self._studioItems or []):
            if it[2] == key:
                self._studioIdx = i
                return

    def _studioCurKey(self):
        keys = self._studioKeysNow()
        if not keys:
            return ""
        r = max(0, min(int(getattr(self, "_studioRow", 0)), len(keys) - 1))
        self._studioRow = r
        return keys[r]

    # ── show / hide (no slide: the panel simply appears) ─────────────────
    def _showStudioOverlay(self):
        self._studioOverlayActive = True
        self._studioOnTabs = True        # [2026-10-31] opens on the tab bar
        try:
            from .novaplay_substudio import STUDIO
            STUDIO.set_sample(True)      # [2026-11-04] a sample line to see the style
        except Exception:
            pass
        self._studioItems = self._studioItemsList()
        self._studioTab = self._studioTabNow()
        try:
            self._studioTimer.start(100, False)     # subtitles keep running under it
        except Exception:
            pass
        for k in HEAD:
            try:
                self[k].show()
            except Exception:
                pass
        self._studioRefresh()

    def _hideStudioOverlay(self):
        self._studioOverlayActive = False
        try:
            from .novaplay_substudio import STUDIO
            STUDIO.set_sample(False)
            STUDIO.set_sync_view(False)
        except Exception:
            pass
        try:
            self._studioTimer.start(100, False)
        except Exception:
            pass
        for k in STUDIO_WIDGETS + ("safeTop", "safeBottom", "safeLeft", "safeRight"):
            try:
                self[k].hide()
            except Exception:
                pass
        try:
            from .novaplay_substudio import STUDIO
            STUDIO.flush_style()
        except Exception:
            pass

    # ── tabs / rows / values (the keys) ──────────────────────────────────
    def _studioGroupIdx(self, idx=None):
        return self._studioTabNow()

    def _studioGroup(self, g):
        self._studioTab = g % len(TABS)
        self._studioRow = 0
        self._studioRefresh()

    def _pl_studioAdjustVKey(self, direction):
        """▲ (+1) / ▼ (-1): the row above / below. [2026-10-31] ▼ from the tab
        bar goes to the first row, ▲ from the first row back to the tab bar."""
        if not getattr(self, "_studioOverlayActive", False):
            return
        keys = self._studioKeysNow()
        r = int(getattr(self, "_studioRow", 0))
        if getattr(self, "_studioOnTabs", False):
            if direction < 0 and keys:
                self._studioOnTabs = False
                self._studioRow = 0
        elif direction > 0 and r == 0:
            self._studioOnTabs = True
        elif keys:
            self._studioRow = max(0, min(len(keys) - 1, r - direction))
        self._studioRefresh()

    _VALUE_KEYS = ("size", "bg", "outline", "bold", "corners", "autowrap", "cuepos", "fixcaps", "align", "spacing",
                   "delay", "finedelay", "color", "ocolor", "offset_y")

    def _studioMove(self, step):
        """◀ (-1) / ▶ (+1): on the tab bar or a button row, the next tab;
        on a value row, change the value"""
        key = self._studioCurKey()
        if getattr(self, "_studioOnTabs", False) or key not in self._VALUE_KEYS:
            self._studioTab = (self._studioTabNow() + step) % len(TABS)
            self._studioRow = 0
            self._studioRefresh()
            return
        from .novaplay_substudio import STUDIO
        s = STUDIO.style
        if key == "size":
            pcts = [int(round(SIZE_BASE * p / 100.0)) for p in SIZE_PCTS]
            i = min(range(len(pcts)), key=lambda j: abs(pcts[j] - int(s["size"])))
            s["size"] = max(22, min(80, pcts[max(0, min(len(pcts) - 1, i + step))]))
            STUDIO._layout_static()
        elif key == "bg":
            cur = self._studioBgPct()
            i = min(range(len(BG_STEPS)), key=lambda j: abs(BG_STEPS[j] - cur))
            new = BG_STEPS[max(0, min(len(BG_STEPS) - 1, i + step))]
            s["bg"] = new > 0
            if new > 0:
                s["bg_alpha"] = max(0, min(255, int(round(255 - 255 * new / 100.0))))
            STUDIO._layout_static()
        elif key == "outline":
            # [2026-10-31] Off / Thin / Thick
            steps = (0, 2, 4)
            cur = int(s.get("outline_w", 2 if s["outline"] else 0))
            i = steps.index(cur) if cur in steps else 1
            s["outline_w"] = steps[max(0, min(2, i + step))]
            s["outline"] = s["outline_w"] > 0
            STUDIO._layout_static()
        elif key == "bold":
            s["bold"] = step > 0
            STUDIO._layout_static()
        elif key == "corners":
            s["bg_round"] = step < 0                 # Rounded | Square
            STUDIO._layout_static()
        elif key in ("autowrap", "cuepos", "fixcaps"):
            field = {"autowrap": "auto_wrap", "cuepos": "use_cue_pos", "fixcaps": "fix_caps"}[key]
            s[field] = step > 0
            if key in ("cuepos", "fixcaps"):
                STUDIO._last_rendered = None
        elif key == "align":
            i = ALIGN_ORDER.index(s["align"] % 3)
            s["align"] = ALIGN_ORDER[max(0, min(2, i + step))]
            from .novaplay_substudio import clamp_offset
            clamp_offset(s)                          # keep the text on screen
        elif key == "spacing":
            s["spacing"] = max(0, min(120, s["spacing"] + 4 * step))
        elif key == "delay":
            # [2026-10-31] half a second a press, like other players
            # (◀ heard the audio first -> subtitles earlier, ▶ saw the caption first -> later)
            self._studioSetDelay(self._studioDelayTotal() + 500 * step)
        elif key == "finedelay":
            # [2026-11-04] a tenth of a second, once it is close
            self._studioSetDelay(self._studioDelayTotal() + 100 * step)
        elif key in ("color", "ocolor", "offset_y"):
            self._studioSelectKey(key)
            self._studioAdjust(step)                 # the studio's own step and limits
            return
        else:
            return                                   # buttons: OK
        try:
            STUDIO.refresh()
        except Exception:
            pass
        self._studioItems = self._studioItemsList()
        self._studioRefresh()

    def _studioOk(self):
        if getattr(self, "_studioOnTabs", False):
            if self._studioKeysNow():
                self._studioOnTabs = False
                self._studioRow = 0
                self._studioRefresh()
            return
        key = self._studioCurKey()
        if key in ("delay", "finedelay"):
            self._studioSetDelay(0)
            self._studioItems = self._studioItemsList()
            self._studioRefresh()
            return
        if key in ("pickline", "font", "presets", "reset", "remove"):
            self._studioSelectKey(key)
            if key in ("reset", "remove"):
                self._studioAdjust(1)                # (the studio's reset / remove)
                if key == "remove":
                    self._hideStudioOverlay()
                return
            return super(PlayerStudioUI, self)._studioOk()

    # ── drawing ──────────────────────────────────────────────────────────
    def _studioBgPct(self):
        from .novaplay_substudio import STUDIO
        s = STUDIO.style
        if not s.get("bg"):
            return 0
        return int(round((255 - int(s.get("bg_alpha", 128))) * 100 / 255.0))

    def _studioRow_model(self, key):
        """-> (kind, value text, options, selected, fraction)"""
        from .novaplay_substudio import STUDIO, _COLORS
        s = STUDIO.style
        if key == "size":
            pcts = [int(round(SIZE_BASE * p / 100.0)) for p in SIZE_PCTS]
            sel = min(range(len(pcts)), key=lambda j: abs(pcts[j] - int(s["size"])))
            return ("chips", u"%d px" % s["size"], [u"%d%%" % p for p in SIZE_PCTS], sel, 0)
        if key in ("color", "ocolor"):
            ci = s["color_idx" if key == "color" else "outline_color_idx"] % len(_COLORS)
            return ("dots", _COLORS[ci][1], [c[0] for c in _COLORS], ci, 0)
        if key == "bg":
            p = self._studioBgPct()
            return ("slider", u"Off" if p == 0 else u"%d%%" % p, None, -1, p / 100.0)
        if key == "outline":
            cur = int(s.get("outline_w", 2 if s["outline"] else 0))
            return ("chips", u"", [u"Off", u"Thin", u"Thick"], {0: 0, 2: 1, 3: 2, 4: 2}.get(cur, 1), 0)
        if key == "bold":
            return ("chips", u"", [u"Off", u"On"], 1 if s.get("bold") else 0, 0)
        if key == "corners":
            return ("chips", u"", [u"Rounded", u"Square"], 0 if s.get("bg_round", True) else 1, 0)
        if key in ("autowrap", "cuepos"):
            on = bool(s.get({"autowrap": "auto_wrap", "cuepos": "use_cue_pos"}[key], True))
            return ("chips", u"", [u"Off", u"On"], 1 if on else 0, 0)
        if key == "fixcaps":
            return ("chips", u"", [u"Off", u"On"], 1 if s.get("fix_caps") else 0, 0)
        if key == "offset_y":
            from .novaplay_substudio import offset_limits
            v = int(s["offset_y"])
            lo, hi = offset_limits(s["align"])
            return ("slider", u"%+d px" % v, None, -1, (v - lo) / float(hi - lo))
        if key == "spacing":
            v = int(s["spacing"])
            return ("slider", u"%d" % v, None, -1, v / 120.0)
        if key == "align":
            return ("chips", u"", [u"Top", u"Center", u"Bottom"], ALIGN_ORDER.index(s["align"] % 3), 0)
        if key == "delay":
            ms = self._studioDelayTotal()
            # [2026-11-04] named by what you notice, like other players
            return ("buttons", u"%+.1f s" % (ms / 1000.0), [u"◀  Heard audio", u"OK  0", u"Saw caption  ▶"], -1, 0)
        if key == "finedelay":
            ms = self._studioDelayTotal()
            return ("buttons", u"%+.1f s" % (ms / 1000.0), [u"◀  −0.1 s", u"OK  0", u"+0.1 s  ▶"], -1, 0)
        if key == "font":
            import os
            name = os.path.basename(s.get("font_path") or "") or s.get("font_name") or u"Default"
            return ("buttons", name, [ACTIONS[key]], -1, 0)
        return ("buttons", u"", [ACTIONS.get(key, u"OK")], -1, 0)

    def _sw(self, name, show=True):
        try:
            self[name].show() if show else self[name].hide()
        except Exception:
            pass

    def _sbox(self, name, x, y, w, h, bg=None, fg=None, text=None):
        try:
            from .plugin_gridlist import sc
        except Exception:
            sc = lambda v: int(v)
        try:
            inst = self[name].instance
            if inst is not None:
                inst.move(ePoint(sc(x), sc(y)))
                inst.resize(eSize(max(1, sc(w)), max(1, sc(h))))
                if parseColor is not None:
                    if bg:
                        inst.setBackgroundColor(parseColor(bg))
                    if fg:
                        inst.setForegroundColor(parseColor(fg))
            if text is not None:
                self[name].setText(text)
            if inst is not None:
                inst.invalidate()
        except Exception:
            pass
        self._sw(name, True)

    def _scolor(self, name, fg=None, bg=None):
        try:
            inst = self[name].instance
            if inst is not None and parseColor is not None:
                if fg:
                    inst.setForegroundColor(parseColor(fg))
                if bg:
                    inst.setBackgroundColor(parseColor(bg))
                inst.invalidate()
        except Exception:
            pass

    def _studioRefresh(self):
        if not getattr(self, "_studioItems", None):
            return
        tab = self._studioTabNow()
        keys = self._studioKeysNow()
        cur = self._studioCurKey()
        try:
            from .novaplay_substudio import STUDIO
            STUDIO.set_sync_view(TABS[tab] == u"Sync")      # [2026-11-05] no sample while syncing
        except Exception:
            pass
        if cur:
            self._studioSelectKey(cur)
        # header and tabs
        try:
            self["studioHead"].setText(u"SUBTITLES")
            self["studioClose"].setText(u"EXIT  ✕")
            onT = getattr(self, "_studioOnTabs", False)
            _smsg = getattr(self, "_studioSyncMsg", None)   # [WGFM] why sync did nothing
            self["studioHint"].setText(
                u"◀▶ tabs    ▼ list    EXIT close" if onT else
                _smsg if (_smsg and cur in ("delay", "finedelay")) else
                u"◀ heard the voice first  ·  saw the subtitle first ▶   (0.5 s)"
                if cur == "delay" else
                u"◀▶ 0.1 s, once it is nearly right    OK back to 0"
                if cur == "finedelay" else
                u"▲▼ choose    ◀▶ change    EXIT close" if cur in self._VALUE_KEYS else
                u"▲▼ choose    ◀▶ tabs    OK apply    EXIT close")
        except Exception:
            pass
        for i in range(4):
            try:
                self["studioTabT%d" % i].setText(TABS[i] if i < len(TABS) else u"")
            except Exception:
                pass
            self._scolor("studioTabT%d" % i, fg=(GOLD if getattr(self, "_studioOnTabs", False) else WHITE)
                         if i == tab else MUTED)
        self._sbox("studioTabLine", TAB_X[tab], SY + 130, TAB_W[tab] - 20, 6)
        for k in HEAD:
            self._sw(k, True)
        # rows
        for r in range(ROWS):
            names = _row_names(r)
            if r >= len(keys):
                for n in names:
                    self._sw(n, False)
                continue
            key = keys[r]
            kind, val, opts, sel, frac = self._studioRow_model(key)
            y = ROW_Y0 + r * ROW_H
            focus = key == cur and not getattr(self, "_studioOnTabs", False)
            self._sw("sRowBg%d" % r, focus)
            self._sw("sRowEdge%d" % r, focus)
            self["sLbl%d" % r].setText(LABELS.get(key, key.upper()))
            self._scolor("sLbl%d" % r, fg=GOLD if focus else MUTED)
            self["sVal%d" % r].setText(val)
            self._sw("sLbl%d" % r, True)
            self._sw("sVal%d" % r, bool(val))
            is_slider = kind == "slider"
            for n in ("sTrack%d", "sFill%d", "sKnob%d"):
                self._sw(n % r, is_slider)
            self._sw("sRing%d" % r, False)
            for k in range(CHIPS):
                self._sw("sChip%d_%d" % (r, k), False)
                self._sw("sDot%d_%d" % (r, k), False)
            if is_slider:
                x0, w = SX + 50, SW - 100
                f = max(0.0, min(1.0, frac))
                self._sbox("sFill%d" % r, x0, y + 56, max(8, int(w * f)), 8)
                self._sbox("sKnob%d" % r, x0 + int(w * f) - 15, y + 45, 30, 30)
            elif kind == "dots":
                for k, col in enumerate(opts[:CHIPS]):
                    x = SX + 46 + k * 76
                    self._sbox("sDot%d_%d" % (r, k), x, y + 38, 44, 44, bg="#" + col[-6:])
                    if k == sel:
                        self._sbox("sRing%d" % r, x - 6, y + 32, 56, 56)
            else:
                n = len(opts)
                avail = SW - 80
                if kind == "chips" and n == 2:
                    w = 150
                elif n == 1:
                    w = min(avail, 360)
                else:
                    w = (avail - 12 * (n - 1)) // n
                for k, txt in enumerate(opts[:CHIPS]):
                    on = (k == sel)
                    self._sbox("sChip%d_%d" % (r, k), SX + 40 + k * (w + 12), y + 38, w, 44,
                               bg=CHIPSEL if on else CHIPBG, fg=GOLD if on else WHITE, text=txt)
        # [2026-10-31] no guide lines any more (the user found them confusing)
        for k in ("safeTop", "safeBottom", "safeLeft", "safeRight"):
            self._sw(k, False)


try:                                         # (Enigma2 names, as player_base has them)
    from enigma import ePoint, eSize
except Exception:                            # (tests outside the box)
    ePoint = eSize = None
try:
    from skin import parseColor
except Exception:
    parseColor = None
