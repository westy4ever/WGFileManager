# -*- coding: utf-8 -*-
"""
Movy-style column panels for the player.

  NovaPlayerPanel (Yellow): Quality | Server | Speed
  NovaSubsPanel   (Blue):   Audio | Subtitles | More

One dark panel under the top of the screen. LEFT/RIGHT moves between
columns, UP/DOWN through a column, OK picks, EXIT (or the colour key that
opened it) closes. Closes with (column_key, index) or None.

Items are (text, is_current) or (text, is_current, stay): a "stay" item
calls the panel's live callback and keeps the panel open (used for the
subtitle sync steps), showing the callback's answer on the help line.
"""
from Screens.Screen import Screen
from .novaplay_theme import TH_CHIPSEL, TH_GOLD, Frame  # [theme]
from Components.ActionMap import ActionMap
from Components.Label import Label
from enigma import ePoint

try:
    from skin import parseColor
except Exception:
    parseColor = None

from .plugin_gridlist import scale_skin_xml

ROWS = 9
_Y0 = 200        # first row
_RH = 50         # row height
# enigma2 doesn't blend widgets with each other: a widget's pixels REPLACE the
# panel under it, so a see-through colour punches a hole to the video/TV
# picture. Every colour here uses the panel's own alpha (1A).
_FOCUS = "#1A5C4A12"     # focused column highlight (dark gold)
_IDLE = "#1A2D333B"      # remembered row in the other columns (dark grey)
_HELP = u"◀ ▶ column    ▲ ▼ choose    OK apply    EXIT close"

_PLAYER_COLS = (
    # key, x, width, title
    ("quality", 300, 330, u"QUALITY"),
    ("server", 650, 640, u"SERVER"),
    ("speed", 1310, 310, u"SPEED"),
)
_SUBS_COLS = (
    ("audio", 300, 330, u"AUDIO"),
    ("subs", 650, 640, u"SUBTITLES"),
    ("more", 1310, 310, u"MORE"),
)


def _seps(cols):
    """x of the divider between each pair of neighbouring columns"""
    return [(cols[i][1] + cols[i][2] + cols[i + 1][1]) // 2 for i in range(len(cols) - 1)]


def _skin(name, cols):
    x0 = cols[0][1] - 30
    x1 = cols[-1][1] + cols[-1][2] + 30
    w = []
    w.append('<widget name="panelBg" theme="panel" position="{x},100" size="{w},{h}" backgroundColor="#1A0C1017" '
             'cornerRadius="22" zPosition="1" />'.format(x=x0, w=x1 - x0, h=150 + ROWS * _RH))
    w.append('<widget name="panelTop" theme="hide" position="{x},100" size="{w},6" backgroundColor="#F2C230" '
             'zPosition="2" />'.format(x=x0, w=x1 - x0))
    for key, x, wd, _t in cols:
        w.append('<widget name="h_{k}" position="{x},126" size="{w},40" font="Regular;24" '
                 'foregroundColor="#8B949E" transparent="1" zPosition="3" />'.format(k=key, x=x + 14, w=wd - 14))
        w.append('<widget name="bar_{k}" position="{x},{y}" size="{w},{h}" backgroundColor="{c}" '
                 'cornerRadius="10" zPosition="2" />'.format(k=key, x=x, y=_Y0, w=wd, h=_RH - 4, c=_FOCUS))
        # [2026-10-30] gold bar at the left of the chosen row (focused column), like the other screens
        w.append('<widget name="gbar_{k}" position="{x},{y}" size="6,{h}" backgroundColor="#F2C230" '
                 'cornerRadius="3" zPosition="3" />'.format(k=key, x=x, y=_Y0 + 8, h=_RH - 20))
        for i in range(ROWS):
            w.append('<widget name="r_{k}{i}" position="{x},{y}" size="{w},{h}" font="Regular;30" '
                     'valign="center" foregroundColor="#F0F6FC" transparent="1" zPosition="3" />'.format(
                         k=key, i=i, x=x + 18, y=_Y0 + i * _RH, w=wd - 30, h=_RH - 4))
    for i, x in enumerate(_seps(cols)):
        w.append('<widget name="sep{i}" position="{x},130" size="2,{h}" backgroundColor="#1A30363D" '
                 'zPosition="2" />'.format(i=i, x=x, h=60 + ROWS * _RH))
    w.append('<widget name="help" position="{x},{y}" size="{w},36" font="Regular;24" halign="center" '
             'foregroundColor="#8B949E" transparent="1" zPosition="3" />'.format(
                 x=x0 + 30, w=x1 - x0 - 60, y=_Y0 + ROWS * _RH + 12))
    return ('<screen name="{n}" position="0,0" size="1920,1080" flags="wfNoBorder" '
            'backgroundColor="transparent">'.format(n=name) + "".join(w) + "</screen>")


class _ColumnPanel(Screen):
    COLS = ()
    CLOSE_KEY = "yellow"

    def __init__(self, session, data, start_col=None, live_cb=None):
        Screen.__init__(self, session)
        self._data = dict((k, list(data.get(k) or [])) for k, _x, _w, _t in self.COLS)
        self._live_cb = live_cb
        self._sel = {}
        self._top = {}
        for key, _x, _w, title in self.COLS:
            self._resetPos(key)
            self["h_" + key] = Label(title)
            self["bar_" + key] = Label("")
            self["gbar_" + key] = Label("")
            for i in range(ROWS):
                self["r_%s%d" % (key, i)] = Label("")
        self["panelBg"] = Frame()
        self["panelTop"] = Label("")
        for i in range(len(self.COLS) - 1):
            self["sep%d" % i] = Label("")
        self["help"] = Label(_HELP)
        keys = [k for k, _x, _w, _t in self.COLS]
        self._col = start_col if start_col in keys else next(
            (k for k in keys if self._data[k]), keys[0])
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions", "MenuActions"], {
            "ok": self._ok,
            "cancel": lambda: self.close(None),
            self.CLOSE_KEY: lambda: self.close(None),
            "left": lambda: self._moveCol(-1),
            "right": lambda: self._moveCol(1),
            "up": lambda: self._move(-1),
            "down": lambda: self._move(1),
        }, -1)
        self.onLayoutFinish.append(self._paint)

    def _resetPos(self, key):
        items = self._data[key]
        cur = next((i for i, it in enumerate(items) if it[1]), 0)
        self._sel[key] = cur
        self._top[key] = max(0, min(cur - ROWS // 2, max(0, len(items) - ROWS)))

    def setColumn(self, key, items):
        """Replace a column's items while the panel is open (async results)."""
        if key not in self._data:
            return
        self._data[key] = list(items or [])
        self._resetPos(key)
        try:
            self._paint()
        except Exception:
            pass

    def setHelp(self, text):
        try:
            self["help"].setText(text or _HELP)
        except Exception:
            pass

    def _cols(self):
        return [k for k, _x, _w, _t in self.COLS if self._data[k]] or [self._col]

    def _moveCol(self, d):
        cols = self._cols()
        i = cols.index(self._col) if self._col in cols else 0
        self._col = cols[(i + d) % len(cols)]
        self._paint()

    def _move(self, d):
        items = self._data[self._col]
        if not items:
            return
        s = (self._sel[self._col] + d) % len(items)
        self._sel[self._col] = s
        top = self._top[self._col]
        if s < top:
            top = s
        elif s >= top + ROWS:
            top = s - ROWS + 1
        self._top[self._col] = top
        self._paint()

    def _ok(self):
        items = self._data[self._col]
        if not items:
            return
        idx = self._sel[self._col]
        it = items[idx]
        if len(it) > 2 and it[2] and self._live_cb:
            try:
                msg = self._live_cb(self._col, idx)
            except Exception as e:
                msg = str(e)
            self.setHelp(msg)
            return
        self.close((self._col, idx))

    def _paint(self):
        for key, _x, _w, _t in self.COLS:
            items = self._data[key]
            top = self._top[key]
            for i in range(ROWS):
                j = top + i
                txt = ""
                if j < len(items):
                    t, cur = items[j][0], items[j][1]
                    txt = (u"● " if cur else u"   ") + t
                if i == 0 and top > 0 and txt:
                    txt = u"▲ " + txt.lstrip(u"● ").strip()
                if i == ROWS - 1 and j < len(items) - 1:
                    txt = u"▼ " + txt.lstrip(u"● ").strip()
                self["r_%s%d" % (key, i)].setText(txt)
            bar = self["bar_" + key]
            gbar = self["gbar_" + key]
            if not items:
                bar.hide()
                gbar.hide()
                continue
            row = self._sel[key] - top
            try:
                rl = self["r_%s%d" % (key, max(0, min(ROWS - 1, row)))].instance
                bi = bar.instance
                if rl and bi:
                    bi.move(ePoint(bi.position().x(), rl.position().y()))
                    gi = gbar.instance
                    if gi:
                        gi.move(ePoint(bi.position().x(), rl.position().y() + 8))
                    if parseColor is not None:
                        bi.setBackgroundColor(parseColor(_FOCUS if key == self._col else _IDLE))
                        bi.invalidate()
            except Exception:
                pass
            bar.show()
            gbar.show() if key == self._col else gbar.hide()
            try:
                if parseColor is not None:
                    self["h_" + key].instance.setForegroundColor(
                        parseColor(TH_GOLD if key == self._col else "#8B949E"))
            except Exception:
                pass


class NovaPlayerPanel(_ColumnPanel):
    """Yellow: Quality | Server | Speed."""
    COLS = _PLAYER_COLS
    CLOSE_KEY = "yellow"
    skin = scale_skin_xml(_skin("NovaPlayerPanel", _PLAYER_COLS))

    def __init__(self, session, quality, server, speed, start_col="quality"):
        _ColumnPanel.__init__(self, session,
                              {"quality": quality, "server": server, "speed": speed},
                              start_col=start_col)


class NovaSubsPanel(_ColumnPanel):
    """Blue: Audio | Subtitles | More."""
    COLS = _SUBS_COLS
    CLOSE_KEY = "blue"
    skin = scale_skin_xml(_skin("NovaSubsPanel", _SUBS_COLS))

    def __init__(self, session, audio, subs, more, live_cb=None, start_col="subs"):
        _ColumnPanel.__init__(self, session,
                              {"audio": audio, "subs": subs, "more": more},
                              start_col=start_col, live_cb=live_cb)


_QUALITY_COLS = (
    ("quality", 360, 420, u"QUALITY"),
    ("server", 820, 740, u"SERVER"),
)


class NovaQualityPanel(_ColumnPanel):
    """Detail screen, after a server resolves: Quality | Server."""
    COLS = _QUALITY_COLS
    CLOSE_KEY = "yellow"
    skin = scale_skin_xml(_skin("NovaQualityPanel", _QUALITY_COLS))

    def __init__(self, session, quality, server, start_col="quality"):
        _ColumnPanel.__init__(self, session, {"quality": quality, "server": server},
                              start_col=start_col)


_MENU_COLS = (
    ("picture", 300, 300, u"PICTURE"),
    ("timer", 630, 480, u"TIMER · REC"),
    ("settings", 1140, 480, u"SETTINGS"),
)


# ─── [2026-10-31] one Settings panel with tabs (Yellow and Blue) ─────────────
# The side-panel look of the new Subtitle Studio: a rounded card on the right,
# tabs along the top (Server · Quality · Speed · Audio · Subtitles · More),
# one list per tab with the current choice ticked. ◀ ▶ switch tabs, ▲ ▼ choose,
# OK applies, Yellow / Blue / EXIT close. Same data and answers as the two
# column panels it replaces: closes with (tab_key, index) or None; "stay"
# items call live_cb and keep it open; setColumn() refreshes a tab (Movy's
# subtitle list arrives in the background).
_SP_X, _SP_Y, _SP_W, _SP_H = 1080, 64, 780, 812
_SP_ROW_X = _SP_X + 30          # [theme] the chosen-row bar stays inside the frame's side lights
_SP_ROWS = 11
_SP_RH = 52
_SP_Y0 = _SP_Y + 164
_SP_TABS = (
    # key, title, width
    ("server", u"Server", 90),
    ("quality", u"Quality", 100),
    ("speed", u"Playback settings", 240),     # [2026-11-04] was "Speed" (190 wrapped onto 2 lines)
    ("audio", u"Audio", 80),
    ("subs", u"Subtitles", 120),
)
_SP_HELP = u"◀▶ tabs    ▲▼ choose    OK apply    EXIT close"
# [2026-10-31] a row with a value (meta {"adj": True}): ◀▶ change it, OK resets
_SP_ADJ_HELP = u"◀▶ change    OK reset    ▲▼ choose    EXIT close"
# [2026-10-31] the panel opens on its tab bar: ◀▶ tabs, ▼ into the list,
# ▲ from the first row back up to the tabs
_SP_TABS_HELP = u"◀▶ tabs    ▼ list    EXIT close"
_SP_GRID_HELP = u"◀▶▲▼ choose    OK apply    ▲ from the top row: tabs"


def _sp_tab_x(tabs=_SP_TABS):
    xs, x = [], _SP_X + 36
    for _k, _t, w in tabs:
        xs.append(x)
        x += w + 16
    return xs


def _sp_skin(name="NovaSettingsPanel", tabs=_SP_TABS):
    xs = _sp_tab_x(tabs)
    w = ['<widget name="spBg" theme="panel" position="{x},{y}" size="{w},{h}" backgroundColor="#1A121822" cornerRadius="28" zPosition="1" />'
         .format(x=_SP_X, y=_SP_Y, w=_SP_W, h=_SP_H),
         '<widget name="spHead" position="{x},{y}" size="400,34" font="Bold;24" foregroundColor="#8B949E" transparent="1" zPosition="3" />'
         .format(x=_SP_X + 40, y=_SP_Y + 26),
         '<widget name="spClose" position="{x},{y}" size="200,34" font="Regular;22" halign="right" foregroundColor="#8B949E" transparent="1" zPosition="3" />'
         .format(x=_SP_X + _SP_W - 240, y=_SP_Y + 28),
         '<widget name="spRule" position="{x},{y}" size="{w},2" backgroundColor="#1A2C3442" zPosition="2" />'
         .format(x=_SP_X + 2, y=_SP_Y + 142, w=_SP_W - 4),
         '<widget name="spTabLine" position="{x},{y}" size="80,6" backgroundColor="#F2C230" cornerRadius="3" zPosition="3" />'
         .format(x=xs[0], y=_SP_Y + 130),
         '<widget name="spRowBg" position="{x},{y}" size="{w},{h}" backgroundColor="#1A1C2432" cornerRadius="14" zPosition="2" />'
         .format(x=_SP_ROW_X, y=_SP_Y0, w=_SP_W - 60, h=_SP_RH - 4),
         '<widget name="spRowEdge" position="{x},{y}" size="6,{h}" backgroundColor="#F2C230" cornerRadius="3" zPosition="3" />'
         .format(x=_SP_ROW_X, y=_SP_Y0 + 8, h=_SP_RH - 20),
         '<widget name="help" position="{x},{y}" size="{w},34" font="Regular;20" foregroundColor="#8B949E" transparent="1" zPosition="3" />'
         .format(x=_SP_X + 40, y=_SP_Y + _SP_H - 52, w=_SP_W - 80)]
    for i, (k, _t, tw) in enumerate(tabs):
        w.append('<widget name="spTab_{k}" position="{x},{y}" size="{w},44" font="Regular;26" foregroundColor="#8B949E" transparent="1" noWrap="1" zPosition="3" />'
                 .format(k=k, x=xs[i], y=_SP_Y + 82, w=tw + 10))
    for k in range(6):
        w.append('<widget name="spChip{k}" position="{x},{y}" size="200,56" font="Regular;28" halign="center" valign="center" foregroundColor="#F0F6FC" backgroundColor="#1A232C3B" cornerRadius="14" zPosition="3" />'
                 .format(k=k, x=_SP_X + 40 + (k % 3) * 236, y=_SP_Y0 + (k // 3) * 72))
    for i in range(_SP_ROWS):
        y = _SP_Y0 + i * _SP_RH
        w.append('<widget name="spDot{i}" position="{x},{y}" size="16,16" backgroundColor="#22C55E" cornerRadius="8" zPosition="3" />'
                 .format(i=i, x=_SP_X + 44, y=y + (_SP_RH - 4) // 2 - 8))
        w.append('<widget name="spTagA{i}" position="{x},{y}" size="120,34" font="Regular;20" halign="center" valign="center" foregroundColor="#22C55E" backgroundColor="#1A123224" cornerRadius="10" zPosition="3" />'
                 .format(i=i, x=_SP_X + _SP_W - 330, y=y + 7))
        w.append('<widget name="spTagB{i}" position="{x},{y}" size="96,34" font="Regular;20" halign="center" valign="center" foregroundColor="#7FB8FF" backgroundColor="#1A1A2A44" cornerRadius="10" zPosition="3" />'
                 .format(i=i, x=_SP_X + _SP_W - 200, y=y + 7))
        w.append('<widget name="spRow{i}" position="{x},{y}" size="{w},{h}" font="Regular;28" valign="center" foregroundColor="#F0F6FC" transparent="1" zPosition="3" />'
                 .format(i=i, x=_SP_X + 44, y=y, w=_SP_W - 150, h=_SP_RH - 4))
        w.append('<widget name="spTick{i}" position="{x},{y}" size="60,{h}" font="Regular;28" halign="right" valign="center" foregroundColor="#F2C230" transparent="1" zPosition="3" />'
                 .format(i=i, x=_SP_X + _SP_W - 100, y=y, h=_SP_RH - 4))
    return ('<screen name="{n}" position="0,0" size="1920,1080" flags="wfNoBorder" '
            'backgroundColor="transparent">'.format(n=name) + "".join(w) + "</screen>")


class NovaSettingsPanel(Screen):
    TABS = _SP_TABS
    HEAD = u"SETTINGS"
    CLOSE_KEYS = ("blue",)
    skin = scale_skin_xml(_sp_skin("NovaSettingsPanel", _SP_TABS))

    def __init__(self, session, data, start_col="server", live_cb=None):
        Screen.__init__(self, session)
        self._data = dict((k, list(data.get(k) or [])) for k, _t, _w in self.TABS)
        self._live_cb = live_cb
        self._sel, self._top = {}, {}
        for k, t, _w in self.TABS:
            self._resetPos(k)
            self["spTab_" + k] = Label(t)
        for n in ("spBg", "spRule", "spTabLine", "spRowBg", "spRowEdge"):
            self[n] = Frame() if n == "spBg" else Label("")
        self["spHead"] = Label(self.HEAD)
        self["spClose"] = Label(u"EXIT  ✕")
        self["help"] = Label(_SP_HELP)
        for i in range(_SP_ROWS):
            for n in ("spRow", "spTick", "spDot", "spTagA", "spTagB"):
                self["%s%d" % (n, i)] = Label("")
        for k in range(6):
            self["spChip%d" % k] = Label("")
        keys = [k for k, _t, _w in self.TABS]
        self._onTabs = True
        self._col = start_col if start_col in keys and self._data.get(start_col) else next(
            (k for k in keys if self._data[k]), keys[0])
        acts = {
            "ok": self._ok,
            "cancel": lambda: self.close(None),
            "left": lambda: self._leftRight(-1),
            "right": lambda: self._leftRight(1),
            "up": lambda: self._move(-1),
            "down": lambda: self._move(1),
        }
        for ck in self.CLOSE_KEYS:
            acts[ck] = lambda: self.close(None)
        for n in range(1, len(self.TABS) + 1):
            acts[str(n)] = (lambda i=n - 1: self._jumpTab(i))
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions", "NumberActions",
                                     "MenuActions"], acts, -1)
        self.onLayoutFinish.append(self._paint)

    # shared behaviour of the column panels (same data model)
    _resetPos = _ColumnPanel._resetPos
    setColumn = _ColumnPanel.setColumn

    def setHelp(self, text):
        try:
            self["help"].setText(text or (_SP_TABS_HELP if getattr(self, "_onTabs", False)
                                          else _SP_GRID_HELP if self._inGrid()
                                          else _SP_ADJ_HELP if self._curAdj() else _SP_HELP))
        except Exception:
            pass

    def _gridN(self, col=None):
        """[2026-11-04] Playback settings: the speed buttons (a grid) come
        first, then ordinary rows (skip intro length, next-episode prompt)"""
        col = col or self._col
        if col != "speed":
            return 0
        n = 0
        for it in self._data.get("speed") or []:
            if len(it) > 3 and isinstance(it[3], dict):
                break
            n += 1
        return n

    def _inGrid(self):
        return self._col == "speed" and self._sel.get("speed", 0) < self._gridN()

    def _curAdj(self):
        """is the chosen row a value row (◀▶ change it)?"""
        if getattr(self, "_onTabs", False):
            return False
        try:
            it = self._data[self._col][self._sel[self._col]]
            return len(it) > 3 and isinstance(it[3], dict) and bool(it[3].get("adj"))
        except Exception:
            return False

    def _leftRight(self, d):
        if not self._onTabs and self._inGrid():
            # [2026-10-31] Speed grid: ◀▶ along the row of buttons (3 a row)
            n = self._gridN()
            k = self._sel.get("speed", 0)
            row0 = (k // 3) * 3
            self._sel["speed"] = max(row0, min(min(row0 + 2, n - 1), k + d))
            self._paint()
            return
        if self._curAdj() and self._live_cb:
            try:
                msg = self._live_cb(self._col, self._sel[self._col], d)
            except Exception as e:
                msg = str(e)
            self.setHelp(msg)
            return
        self._moveCol(d)

    def updateColumn(self, key, items):
        """a tab's rows changed (a value was changed): keep the chosen row"""
        if key not in self._data:
            return
        sel, top = self._sel.get(key, 0), self._top.get(key, 0)
        self._data[key] = list(items or [])
        n = len(self._data[key])
        self._sel[key] = max(0, min(sel, n - 1)) if n else 0
        self._top[key] = max(0, min(top, max(0, n - _SP_ROWS)))
        try:
            self._paint()
        except Exception:
            pass

    def _ok(self):
        """OK on a value row resets it (live_cb with d=0); else as before"""
        if self._onTabs:
            self._enterList()
            return
        if self._curAdj() and self._live_cb:
            try:
                msg = self._live_cb(self._col, self._sel[self._col], 0)
            except Exception as e:
                msg = str(e)
            self.setHelp(msg)
            return
        _ColumnPanel._ok(self)

    def _cols(self):
        return [k for k, _t, _w in self.TABS if self._data[k]] or [self._col]

    def _moveCol(self, d):
        cols = self._cols()
        i = cols.index(self._col) if self._col in cols else 0
        self._col = cols[(i + d) % len(cols)]
        self.setHelp(None)
        self._paint()

    def _jumpTab(self, i):
        k = self.TABS[i][0]
        if self._data.get(k):
            self._col = k
            self.setHelp(None)
            self._paint()

    def _enterList(self):
        if self._data[self._col]:
            self._onTabs = False
            self.setHelp(None)
            self._paint()

    def _move(self, d):
        items = self._data[self._col]
        if self._onTabs:
            if d > 0:
                self._enterList()
            return
        if not items:
            return
        if self._col == "speed":
            # [2026-10-31] Speed grid: ▲▼ between the two rows of buttons,
            # ▲ from the top row back to the tab bar; [2026-11-04] ▼ from the
            # last row of buttons into the rows under them
            g = self._gridN()
            k = self._sel["speed"]
            if k < g:
                if d < 0 and k < 3:
                    self._onTabs = True
                elif d > 0 and k + 3 < g:
                    self._sel["speed"] = k + 3
                elif d > 0 and len(items) > g:
                    self._sel["speed"] = g
                elif d < 0:
                    self._sel["speed"] = k - 3
            else:
                if d < 0 and k == g:
                    self._sel["speed"] = ((g - 1) // 3) * 3 if g else 0
                    if not g:
                        self._onTabs = True
                else:
                    self._sel["speed"] = max(g, min(len(items) - 1, k + d))
            self.setHelp(None)
            self._paint()
            return
        if d < 0 and self._sel[self._col] == 0:
            # [2026-10-31] up from the first row: back to the tab bar
            self._onTabs = True
            self.setHelp(None)
            self._paint()
            return
        s = max(0, min(len(items) - 1, self._sel[self._col] + d))
        self._sel[self._col] = s
        top = self._top[self._col]
        if s < top:
            top = s
        elif s >= top + _SP_ROWS:
            top = s - _SP_ROWS + 1
        self._top[self._col] = top
        self.setHelp(None)
        self._paint()

    def _paint(self):
        self._paintBody()
        if not getattr(self, "_onTabs", False):
            return
        # on the tab bar: the tab is gold, no row is highlighted
        for k, _t, _w in self.TABS:
            if k == self._col:
                try:
                    lab = self["spTab_" + k]
                    if parseColor is not None and lab.instance:
                        lab.instance.setForegroundColor(parseColor(TH_GOLD))
                        lab.instance.invalidate()
                except Exception:
                    pass
        self["spRowBg"].hide()
        self["spRowEdge"].hide()
        for i in range(_SP_ROWS):
            try:
                inst = self["spRow%d" % i].instance
                if parseColor is not None and inst:
                    inst.setForegroundColor(parseColor("#F0F6FC"))
                    inst.invalidate()
            except Exception:
                pass
        if self._col == "speed":
            items = self._data["speed"]
            for k in range(min(6, self._gridN())):
                if not items[k][1]:
                    self._box("spChip%d" % k, _SP_X + 40 + (k % 3) * 236, _SP_Y0 + (k // 3) * 72, 216, 56,
                              bg="#1A232C3B", fg="#F0F6FC")

    def _box(self, name, x, y, w=None, h=None, bg=None, fg=None):
        try:
            from enigma import eSize
            from .plugin_gridlist import sc
            inst = self[name].instance
            if inst is None:
                return
            inst.move(ePoint(sc(x), sc(y)))
            if w is not None:
                inst.resize(eSize(max(1, sc(w)), max(1, sc(h))))
            if parseColor is not None and (bg or fg):
                if bg:
                    inst.setBackgroundColor(parseColor(bg))
                if fg:
                    inst.setForegroundColor(parseColor(fg))
                inst.invalidate()
        except Exception:
            pass

    def _fit(self, body_h):
        """[2026-10-31] the panel is as tall as what the tab shows"""
        h = (_SP_Y0 - _SP_Y) + body_h + 70
        self._box("spBg", _SP_X, _SP_Y, _SP_W, h)
        self._box("help", _SP_X + 40, _SP_Y + h - 52)

    def _paintBody(self):
        xs = _sp_tab_x(self.TABS)
        for i, (k, _t, tw) in enumerate(self.TABS):
            on = k == self._col
            lab = self["spTab_" + k]
            try:
                if parseColor is not None and lab.instance:
                    lab.instance.setForegroundColor(parseColor(
                        "#F2F6FC" if on else ("#8B949E" if self._data[k] else "#4A525E")))
                    lab.instance.invalidate()
            except Exception:
                pass
            if on:
                self._box("spTabLine", xs[i], _SP_Y + 130, tw - 6, 6)
        items = self._data[self._col]
        grid = self._col == "speed"
        g = self._gridN()
        # [2026-10-31] Speed: a grid of buttons (3 a row), the current one gold
        for k in range(6):
            lab = self["spChip%d" % k]
            if grid and k < g:
                cur = bool(items[k][1])
                foc = k == self._sel.get("speed", 0)
                lab.setText(items[k][0])
                self._box("spChip%d" % k, _SP_X + 40 + (k % 3) * 236, _SP_Y0 + (k // 3) * 72, 216, 56,
                          bg=TH_CHIPSEL if cur else ("#1A2E3A4E" if foc else "#1A232C3B"),
                          fg=TH_GOLD if (cur or foc) else "#F0F6FC")
                lab.show()
            else:
                lab.hide()
        if grid:
            k = self._sel.get("speed", 0)
            gh = ((g + 2) // 3) * 72
            rows = items[g:]
            # [2026-11-04] the rows under the buttons (value rows / switches)
            for i in range(_SP_ROWS):
                w5 = [self["%s%d" % (n, i)] for n in ("spRow", "spTick", "spDot", "spTagA", "spTagB")]
                if i >= len(rows):
                    for w in w5:
                        w.hide()
                    continue
                it = rows[i]
                meta = it[3] if len(it) > 3 and isinstance(it[3], dict) else {}
                y = _SP_Y0 + gh + 12 + i * _SP_RH
                self._box("spRow%d" % i, _SP_X + 44, y)
                w5[0].setText(it[0])
                w5[0].show()
                w5[1].setText(u"\u2713" if it[1] else u"")
                w5[1].show()
                w5[2].hide()
                w5[4].hide()
                tag = ([t for t in (meta.get("tags") or []) if t] or [u""])[0]
                if tag:
                    tw = 26 + 12 * len(tag)
                    self._box("spTagA%d" % i, _SP_X + _SP_W - 106 - tw - 10, y + 7, tw, 34,
                              bg="#1A1A2A44", fg="#7FB8FF")
                    w5[3].setText(tag)
                    w5[3].show()
                else:
                    w5[3].hide()
                try:
                    if parseColor is not None:
                        w5[0].instance.setForegroundColor(parseColor(TH_GOLD if g + i == k else "#F0F6FC"))
                        w5[0].instance.invalidate()
                except Exception:
                    pass
            if k < g:
                self["spRowBg"].hide()
                self._box("spRowEdge", _SP_X + 30, _SP_Y0 + (k // 3) * 72 + 12, 6, 32)
            else:
                y = _SP_Y0 + gh + 12 + (k - g) * _SP_RH
                self._box("spRowBg", _SP_ROW_X, y)
                self._box("spRowEdge", _SP_ROW_X, y + 8, 6, _SP_RH - 20)
                self["spRowBg"].show()
            self["spRowEdge"].show() if items else self["spRowEdge"].hide()
            self._fit(gh + (12 + len(rows) * _SP_RH if rows else 0))
            return
        top = self._top.get(self._col, 0)
        shown = 0
        for i in range(_SP_ROWS):
            j = top + i
            row, tick, dot, tag_a, tag_b = self["spRow%d" % i], self["spTick%d" % i], \
                self["spDot%d" % i], self["spTagA%d" % i], self["spTagB%d" % i]
            if j >= len(items):
                for w in (row, tick, dot, tag_a, tag_b):
                    w.hide()
                continue
            shown += 1
            it = items[j]
            meta = it[3] if len(it) > 3 and isinstance(it[3], dict) else {}
            txt = it[0]
            if i == 0 and top > 0:
                txt = u"\u25b2  " + txt
            elif i == _SP_ROWS - 1 and j < len(items) - 1:
                txt = u"\u25bc  " + txt
            y = _SP_Y0 + i * _SP_RH
            has_dot = "dot" in meta
            self._box("spRow%d" % i, _SP_X + (70 if has_dot else 44), y)
            row.setText(txt)
            row.show()
            tick.setText(u"\u2713" if it[1] else u"")
            tick.show()
            if has_dot:
                col = {"ok": "#22C55E", "bad": "#E5484D"}.get(meta.get("dot"), "#5A6270")
                self._box("spDot%d" % i, _SP_X + 44, y + (_SP_RH - 4) // 2 - 8, bg=col)
                dot.show()
            else:
                dot.hide()
            tags = [t for t in (meta.get("tags") or []) if t][:2]
            # right to left: the tick, then the tags
            x = _SP_X + _SP_W - 106
            for w, name, t in ((tag_b, "spTagB%d" % i, tags[1] if len(tags) > 1 else ""),
                               (tag_a, "spTagA%d" % i, tags[0] if tags else "")):
                if not t:
                    w.hide()
                    continue
                tw = 26 + 12 * len(t)
                x -= tw + 10
                play = t in (u"Playing",)
                self._box(name, x, y + 7, tw, 34,
                          bg="#1A123224" if play else "#1A1A2A44",
                          fg="#22C55E" if play else "#7FB8FF")
                w.setText(t)
                w.show()
        self._fit(max(1, shown) * _SP_RH)
        if not items:
            self["spRow0"].setText(u"\u2014")
            self["spRow0"].show()
            self["spRowBg"].hide()
            self["spRowEdge"].hide()
            return
        row = max(0, min(_SP_ROWS - 1, self._sel[self._col] - top))
        y = _SP_Y0 + row * _SP_RH
        self._box("spRowBg", _SP_ROW_X, y)
        self._box("spRowEdge", _SP_ROW_X, y + 8, 6, _SP_RH - 20)
        self["spRowBg"].show()
        self["spRowEdge"].show()
        for i in range(_SP_ROWS):
            try:
                if parseColor is not None:
                    inst = self["spRow%d" % i].instance
                    inst.setForegroundColor(parseColor(TH_GOLD if i == row else "#F0F6FC"))
                    inst.invalidate()
            except Exception:
                pass


class NovaMenuPanel(NovaSettingsPanel):
    """[2026-10-31] Menu: Picture · Timer & record · Settings -- the same
    side-panel look as Yellow / Blue (was three columns across the top)"""
    TABS = (("picture", u"Picture", 108), ("timer", u"Timer \u00b7 Rec", 160), ("settings", u"Player", 100))   # [2026-11-04] was "Settings" (clashed with the BLUE panel)
    HEAD = u"MENU"
    CLOSE_KEYS = ("menu",)
    skin = scale_skin_xml(_sp_skin("NovaMenuPanel", TABS))

    def __init__(self, session, picture, timer, settings, live_cb=None, start_col="picture"):
        NovaSettingsPanel.__init__(self, session, {"picture": picture, "timer": timer, "settings": settings},
                                   start_col=start_col, live_cb=live_cb)
