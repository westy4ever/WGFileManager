# -*- coding: utf-8 -*-
"""WGFileManager — subtitle screens (vendored from NovaPlay).

The four Screen classes from novaplay_subtitles.py, verbatim except for
imports (which now point at the local engine / thread modules) and one
in-place fix in NovaSubtitleSettings._clearCache (see comment there).
"""

import os
import re
import json
import threading

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel

try:
    from Screens.VirtualKeyBoard import VirtualKeyBoard
except Exception:
    VirtualKeyBoard = None

try:
    from Components.FileList import FileList
except Exception:
    FileList = None

# ── CHANGED imports ────────────────────────────────────────────────────
from .engine import (
    _ss_api_key, _os_api_key, _ss_cache_dir, _subs_memory_path,
    _cfg, _cfg_bool, _cfg_set, _CURRENT_SUB,
    _PROVIDERS,
    clean_play_title, clean_subtitle_query,
    _search_terms, _significant_words, _episode_markers,
    _iter_sub_entries, strict_score, subtitle_dir,
)
from .thread import callInMainThread


# ── local scale_skin_xml (matches NovaPlay's plugin_gridlist helper) ──
import re as _re
try:
    from enigma import getDesktop as _gd
    _s = _gd(0).size()
    _SCALE = max(0.5, min(2.0, int(_s.width()) / 1920.0))
except Exception:
    _SCALE = 1.0


def scale_skin_xml(xml):
    if _SCALE == 1.0:
        return xml

    def _sub(m):
        name, q, val = m.group(1), m.group(2), m.group(3)
        if name in ("position", "size", "cornerRadius", "itemHeight"):
            val = _re.sub(r"-?\d+",
                          lambda n: str(int(round(int(n.group()) * _SCALE))),
                          val)
        elif name == "font":
            parts = val.split(";")
            if len(parts) == 2 and parts[1].strip().isdigit():
                parts[1] = str(max(12, int(round(int(parts[1]) * _SCALE))))
                val = ";".join(parts)
        return "%s=%s%s%s" % (name, q, val, q)
    return _re.sub(r'(\w+)=("|\')([^"\']*)\2', _sub, xml)


def _menu_index(menu_list, entries_count):
    """Robust current-index lookup across Enigma2 generations."""
    try:
        idx = menu_list.getSelectedIndex()
        if idx is not None and 0 <= int(idx) < entries_count:
            return int(idx)
    except Exception:
        pass
    try:
        cur = menu_list.getCurrent()
    except Exception:
        return -1
    if isinstance(cur, tuple) and len(cur) >= 2:
        try:
            idx = int(cur[1])
            if 0 <= idx < entries_count:
                return idx
        except Exception:
            pass
    elif isinstance(cur, int):
        if 0 <= cur < entries_count:
            return cur
    return -1


# =============================================================================
#  Online subtitle search / download screen
# =============================================================================

class NovaOnlineSubsScreen(Screen):
    """Background online search + download (SubSource or OpenSubtitles);
    closes with the .srt path."""

    skin = """
    <screen name="NovaOnlineSubsScreen" position="center,center" size="1700,940" title="Online subtitles" flags="wfNoBorder">
        <eLabel position="0,0" size="1700,940" backgroundColor="#0D1117" zPosition="0" />
        <eLabel position="0,0" size="1700,90" backgroundColor="#161B22" zPosition="1" />
        <widget name="header" position="50,20" size="1600,50" font="Regular;38" foregroundColor="#00E5FF" transparent="1" zPosition="2" />
        <widget name="list" position="40,110" size="1620,720" scrollbarMode="showOnDemand" foregroundColor="#F0F6FC" foregroundColorSelected="#00E5FF" backgroundColor="#161B22" backgroundColorSelected="#21262D" font="Regular;40" itemHeight="60" zPosition="2" />
        <widget name="hint" position="50,860" size="1600,40" font="Regular;28" foregroundColor="#8B949E" transparent="1" zPosition="2" />
    </screen>"""

    def __init__(self, session, title="", video_url="", provider="subsource", api_key=""):
        Screen.__init__(self, session)
        self.skinName = ["NovaOnlineSubsScreen"]
        self.search_title = str(title or "")
        self.video_url = str(video_url or "")
        self.provider = provider if provider in _PROVIDERS else "subsource"
        self.api_key = str(api_key or "").strip()
        self.results = []
        self.chosen = None
        self.mode = "search"
        prov_name = _PROVIDERS[self.provider]["name"]

        self["header"] = Label("Searching %s ..." % prov_name)
        self["hint"] = Label("OK = download      EXIT = back")
        self["list"] = MenuList([])
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self._ok,
            "cancel": self._cancel,
        }, -1)
        threading.Thread(target=self._searchThread, daemon=True).start()

    def _searchThread(self):
        title = self.search_title
        # (1) collapse Latin series markers
        try:
            title = clean_play_title(title) or title
        except Exception:
            pass
        # (2) strip Arabic season / episode words -> bare series name
        try:
            _ep_markers = re.search(
                r"(?:الموسم|موسم|الحلقة|حلقة|والأخيرة|والاخيرة|الأخيرة|الاخيرة|مترجم(?:ة)?|مدبلج(?:ة)?|كامل|مسلسل)\s*[\d\u0660-\u0669]*",
                title)
            if _ep_markers:
                _bare_series = title[:_ep_markers.start()].strip(" -_|")
                if len(_bare_series) >= 3:
                    title = _bare_series
        except Exception:
            pass
        # (3) TMDB English-title fallback (soft dependency — absent on WGFileManager by default)
        try:
            q = clean_subtitle_query(title, self.video_url)
            _ar_ratio = sum(1 for c in (q or "") if "\u0600" <= c <= "\u06ff") / max(1, len(q or " "))
            if not q or len(q.strip()) < 3 or _ar_ratio > 0.5:
                try:
                    from ..plugin_tmdb import _tmdb_search_metadata
                except Exception:
                    _tmdb_search_metadata = None
                if _tmdb_search_metadata is not None:
                    meta = _tmdb_search_metadata(title, "", "movie")
                    if isinstance(meta, dict):
                        for k in ("title", "original_title", "name", "original_name"):
                            if meta.get(k):
                                title = str(meta[k])
                                break
        except Exception:
            pass
        prov = _PROVIDERS[self.provider]
        try:
            ok, error, results = prov["search"](title, self.video_url, self.api_key)
        except Exception as e:
            ok, error, results = False, "Search error: %s" % str(e)[:80], []
        callInMainThread(self._onSearchDone, results or [], ("" if ok else (error or "")))

    def _downloadThread(self):
        prov = _PROVIDERS[self.provider]
        try:
            ok, error, path = prov["download"](
                self.chosen.get("id", ""), self.chosen.get("title", ""), self.api_key)
        except Exception as e:
            ok, error, path = False, "Download error: %s" % str(e)[:80], ""
        callInMainThread(self._onDownloadDone, bool(ok), error or "Download failed.", path or "")

    def _onSearchDone(self, results, error=""):
        # User may EXIT while the search thread is in flight.
        try:
            if self.session is None:
                return
        except Exception:
            return
        # Filter labels and results together so indices stay aligned.
        pairs = []
        for i in (results or []):
            label = str(i.get("label") or i.get("title") or "")
            if label:
                pairs.append((label, i))
        if not pairs:
            self._fail(error or 'No subtitles found.')
            return
        self.results = [i for _, i in pairs]
        self["list"].setList([l for l, _ in pairs])
        ar = sum(1 for i in self.results if str(i.get("language", "")).lower() in ("arabic", "ar", "ara", "العربية"))
        en = sum(1 for i in self.results if str(i.get("language", "")).lower() in ("english", "en", "eng"))
        self["header"].setText("%s: %d subs - AR %d / EN %d (scroll down)" % (
            _PROVIDERS[self.provider]["name"], len(pairs), ar, en))

    def _onDownloadDone(self, ok, error, path):
        try:
            if self.session is None:
                return
        except Exception:
            return
        if ok and path:
            self.close(path)
        else:
            self._fail(error)

    def _fail(self, message):
        try:
            self.session.openWithCallback(
                lambda a: self.close(""), MessageBox,
                message, MessageBox.TYPE_ERROR, timeout=10)
        except Exception:
            self.close("")

    def _ok(self):
        if self.mode != "search" or not self.results:
            return
        idx = _menu_index(self["list"], len(self.results))
        if idx < 0:
            return
        self.chosen = self.results[idx]
        self.mode = "download"
        self["header"].setText("Downloading: %s" % (self.chosen.get("title") or ""))
        threading.Thread(target=self._downloadThread, daemon=True).start()

    def _cancel(self):
        self.close("")


# Backwards-compatible alias (older patches referenced this name)
NovaSubSourceScreen = NovaOnlineSubsScreen


# =============================================================================
#  Local subtitle folder browser
# =============================================================================

class NovaSubtitleBrowser(Screen):
    """Folder browser for local subtitle files; best match tagged [BEST]."""

    skin = """
    <screen name="NovaSubtitleBrowser" position="center,center" size="1500,860" title="Select subtitle" flags="wfNoBorder">
        <eLabel position="0,0" size="1500,860" backgroundColor="#0D1117" zPosition="0" />
        <eLabel position="0,0" size="1500,80" backgroundColor="#161B22" zPosition="1" />
        <widget name="path" position="40,18" size="1420,44" font="Regular;30" foregroundColor="#00E5FF" transparent="1" zPosition="2" />
        <widget name="list" position="30,100" size="1440,680" scrollbarMode="showOnDemand" zPosition="2" />
        <widget name="hint" position="40,800" size="1420,36" font="Regular;24" foregroundColor="#8B949E" transparent="1" zPosition="2" />
    </screen>"""

    def __init__(self, session, start_dir="", video_title=""):
        Screen.__init__(self, session)
        self.skinName = ["NovaSubtitleBrowser"]
        video_title = clean_play_title(video_title)
        self.terms = _search_terms(video_title)
        self.words = _significant_words(self.terms)
        self.markers = _episode_markers(self.terms)
        self.entries = []
        self.current_dir = start_dir or subtitle_dir() or "/media/hdd"

        self["path"] = Label(self.current_dir)
        self["hint"] = Label("OK = select      EXIT = up / back")
        self["list"] = MenuList([])
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self._ok,
            "cancel": self._cancel,
        }, -1)
        self.onLayoutFinish.append(self._refresh)

    def _refresh(self):
        entries = []
        try:
            for name, full, is_dir in _iter_sub_entries(self.current_dir):
                entries.append((name, full, is_dir))
                if len(entries) >= 800:
                    break
            entries.sort(key=lambda item: (0 if item[2] else 1, item[0].lower()))
        except Exception:
            entries = []

        best_path, best_score = "", 0
        for name, full, is_dir in entries:
            if not is_dir:
                sc = strict_score(name, self.terms, self.words, self.markers)
                if sc > best_score:
                    best_score, best_path = sc, full

        labels = []
        self.entries = []
        for name, full, is_dir in entries:
            if is_dir:
                labels.append("[ %s ]" % name)
            else:
                labels.append(name + ("  [BEST]" if full == best_path and best_score > 0 else ""))
            self.entries.append((name, full, is_dir))
        self["list"].setList(labels)
        self["path"].setText(self.current_dir or "/")

    def _ok(self):
        idx = _menu_index(self["list"], len(self.entries))
        if idx < 0 or idx >= len(self.entries):
            return
        name, full, is_dir = self.entries[idx]
        if is_dir:
            self.current_dir = full
            self._refresh()
        elif os.path.exists(full):
            self.close(full)

    def _cancel(self):
        parent = os.path.dirname(self.current_dir.rstrip("/")) or "/"
        if parent and parent != self.current_dir:
            self.current_dir = parent
            self._refresh()
        elif self.current_dir not in ("/", "/media"):
            self.current_dir = "/"
            self._refresh()
        else:
            self.close("")


# =============================================================================
#  Subtitle folder picker (settings)
# =============================================================================

class NovaFolderBrowser(Screen):
    """Directory picker for the subtitle folder — remote-friendly
    replacement for typing a path on the VirtualKeyBoard."""

    skin = """
    <screen name="NovaFolderBrowser" position="center,center" size="1500,860" title="Select Folder" flags="wfNoBorder">
        <eLabel position="0,0" size="1500,860" backgroundColor="#0D1117" zPosition="0" />
        <eLabel position="0,0" size="1500,80" backgroundColor="#161B22" zPosition="1" />
        <widget name="path" position="40,18" size="1420,44" font="Regular;30" foregroundColor="#00E5FF" transparent="1" zPosition="2" />
        <widget name="list" position="30,100" size="1440,680" scrollbarMode="showOnDemand" zPosition="2" />
        <widget name="hint" position="40,800" size="1420,36" font="Regular;24" foregroundColor="#8B949E" transparent="1" zPosition="2" />
    </screen>"""

    def __init__(self, session, start_dir="/"):
        Screen.__init__(self, session)
        start = start_dir if start_dir and os.path.isdir(start_dir) else "/media/hdd"
        if not os.path.isdir(start):
            start = "/"
        self["path"] = Label(start)
        self["list"] = self._makeFileList(start)
        self["hint"] = Label("OK open  |  GREEN select  |  RED root  |  YELLOW /media  |  EXIT back")
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
            "ok": self._ok, "cancel": self.close,
            "green": self._select, "red": lambda: self._go("/"),
            "yellow": lambda: self._go("/media"),
            "up": self._up, "down": self._down,
            "left": self._pageUp, "right": self._pageDown,
        }, -1)

    def _makeFileList(self, d):
        for kwargs in [
            {"showDirectories": True, "showFiles": False, "inhibitMounts": False, "inhibitDirs": False, "isTop": False},
            {"showDirectories": True, "showFiles": False, "inhibitMounts": False, "isTop": False},
            {"showDirectories": True, "showFiles": False},
        ]:
            try:
                return FileList(d, **kwargs)
            except Exception:
                continue
        return FileList(d, showDirectories=True, showFiles=False)

    def _go(self, d):
        if os.path.isdir(d):
            try:
                self["list"] = self._makeFileList(d)
                self["path"].setText(d)
            except Exception:
                pass

    def _ok(self):
        try:
            if self["list"].canDescent():
                self["list"].descent()
                self["path"].setText(self._current())
                return
        except Exception:
            pass
        try:
            sel = self["list"].getFilename()
            if sel and os.path.isdir(sel):
                self._go(sel)
        except Exception:
            pass

    def _current(self):
        try:
            c = self["list"].getCurrentDirectory()
            if c:
                return str(c)
        except Exception:
            pass
        return "/"

    def _select(self):
        d = self._current()
        if d and os.path.isdir(d):
            self.close(d)

    def _up(self):
        try: self["list"].up()
        except Exception: pass
    def _down(self):
        try: self["list"].down()
        except Exception: pass
    def _pageUp(self):
        try: self["list"].pageUp()
        except Exception: pass
    def _pageDown(self):
        try: self["list"].pageDown()
        except Exception: pass


# =============================================================================
#  Subtitle settings screen
# =============================================================================

class NovaSubtitleSettings(Screen):
    """Subtitle settings: provider API keys, subtitle dir, auto-attach,
    cache clearing."""

    skin = """
    <screen name="NovaSubtitleSettings" position="center,center" size="1500,860" title="Subtitle Settings" flags="wfNoBorder">
        <eLabel position="0,0" size="1500,860" backgroundColor="#0D1117" zPosition="0" />
        <eLabel position="0,0" size="1500,80" backgroundColor="#161B22" zPosition="1" />
        <widget name="header" position="40,18" size="1420,44" font="Regular;32" foregroundColor="#00E5FF" transparent="1" zPosition="2" />
        <widget name="body" position="40,100" size="1420,660" font="Regular;26" foregroundColor="#F0F6FC" transparent="1" zPosition="2" />
        <eLabel position="0,790" size="1500,70" backgroundColor="#161B22" zPosition="1" />
        <widget name="key_red"    position="30,806"  size="350,32" font="Regular;24" foregroundColor="#FF6B6B" transparent="1" halign="center" zPosition="2" />
        <widget name="key_green"  position="390,806" size="350,32" font="Regular;24" foregroundColor="#39D98A" transparent="1" halign="center" zPosition="2" />
        <widget name="key_yellow" position="750,806" size="350,32" font="Regular;24" foregroundColor="#FFD740" transparent="1" halign="center" zPosition="2" />
        <widget name="key_blue"   position="1110,806" size="360,32" font="Regular;24" foregroundColor="#58A6FF" transparent="1" halign="center" zPosition="2" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.skinName = ["NovaSubtitleSettings"]
        self["header"] = Label("Subtitle Settings")
        self["body"] = ScrollLabel("")
        self["key_red"] = Label("API Keys")
        self["key_green"] = Label("Subtitle Folder")
        self["key_yellow"] = Label("Auto-Attach: OFF")
        self["key_blue"] = Label("Clear Cache")
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "red": self._chooseKey,
            "green": self._editDir,
            "yellow": self._toggleAuto,
            "blue": self._clearCache,
            "ok": self._chooseKey,
            "cancel": self.close,
        }, -1)
        self._refresh()

    @staticmethod
    def _mask(key):
        return (key[:6] + "..." + key[-4:]) if len(key) > 12 else (key or "(not set)")

    def _refresh(self):
        ss = _ss_api_key()
        osk = _os_api_key()
        auto = "ON" if _cfg_bool("auto_subtitle", False) else "OFF"
        self["key_yellow"].setText("Auto-Attach: %s" % auto)
        txt = (
            "SubSource API Key:\n  %s\n\n"
            "OpenSubtitles API Key:\n  %s\n\n"
            "Subtitle Folder:\n  %s\n\n"
            "Auto-Attach on Play: %s\n"
            "  (remembered subtitles + sync are ALWAYS re-attached)\n\n"
            "Free keys: subsource.net / opensubtitles.com\n"
            "Search is Arabic-first, English-second.\n\n"
            "During playback, SUBTITLE / TEXT key opens the menu:\n"
            "  online search / local browse / sync +/-250 ms / Studio\n\n"
            "OK or BLUE here = clear subtitle cache + memory\n"
            "EXIT = close"
        ) % (self._mask(ss), self._mask(osk),
             _cfg("subtitle_dir", "/media/hdd/subtitles"), auto)
        self["body"].setText(txt)

    _KEY_MAP = {
        "subsource": "subsource_api_key",
        "opensubtitles": "opensubtitles_api_key",
        "os_user": "opensubtitles_user",
        "os_pass": "opensubtitles_pass",
    }

    def _chooseKey(self):
        entries = [
            ("SubSource API Key", "subsource"),
            ("OpenSubtitles API Key", "opensubtitles"),
            ("OpenSubtitles username (for downloads)", "os_user"),
            ("OpenSubtitles password (for downloads)", "os_pass"),
        ]
        self.session.openWithCallback(self._keyProviderChosen, ChoiceBox,
                                      title="API Keys", list=entries)

    def _keyProviderChosen(self, choice):
        if not choice or VirtualKeyBoard is None:
            return
        which = choice[1]
        current = str(_cfg(self._KEY_MAP[which], "")).strip()
        self.session.openWithCallback(
            lambda v: self._keyCb(which, v), VirtualKeyBoard,
            title=choice[0], text=current)

    def _keyCb(self, which, value):
        if value is not None and str(value).strip():
            _cfg_set(self._KEY_MAP[which], str(value).strip())
        self._refresh()

    def _editDir(self):
        # Browse instead of typing — VKB path entry was typo-prone on a remote.
        if FileList is not None:
            try:
                self.session.openWithCallback(self._dirCb, NovaFolderBrowser,
                                              _cfg("subtitle_dir", "/media/hdd/subtitles"))
                return
            except Exception:
                pass
        if VirtualKeyBoard is None:
            return
        self.session.openWithCallback(self._dirCb, VirtualKeyBoard,
            title="Subtitle folder path",
            text=_cfg("subtitle_dir", "/media/hdd/subtitles"))

    def _dirCb(self, value=None):
        # Called from BOTH the VirtualKeyBoard (value = typed string,
        # possibly None on cancel) and NovaFolderBrowser (value = selected
        # directory string). Some images also re-fire the callback with
        # no arguments during processDelay — tolerate all shapes.
        try:
            if value is not None:
                d = str(value).strip()
                if d:
                    if os.path.isdir(d):
                        _cfg_set("subtitle_dir", d)
                    else:
                        try:
                            os.makedirs(d)
                            _cfg_set("subtitle_dir", d)
                        except Exception:
                            pass
        except Exception:
            pass
        self._refresh()

    def _toggleAuto(self):
        current = _cfg_bool("auto_subtitle", False)
        _cfg_set("auto_subtitle", "false" if current else "true")
        self._refresh()

    def _clearCache(self):
        """Delete all cached downloaded subtitles + the subtitle memory file,
        reset in-session subtitle state, then close."""
        freed, n = 0, 0
        try:
            cache_dir = _ss_cache_dir()
            for name in os.listdir(cache_dir):
                full = os.path.join(cache_dir, name)
                try:
                    if os.path.isfile(full):
                        freed += os.path.getsize(full)
                        os.remove(full)
                        n += 1
                except Exception:
                    pass
        except Exception:
            pass
        try:
            mem = _subs_memory_path()
            if os.path.exists(mem):
                freed += os.path.getsize(mem)
                os.remove(mem)
                n += 1
        except Exception:
            pass
        # Reset in-session subtitle state IN PLACE — the engine holds a
        # reference to the same dict, so reassigning it here would leave
        # the engine's _CURRENT_SUB untouched.
        _CURRENT_SUB.clear()
        _CURRENT_SUB.update({"item_url": "", "path": "", "offset_ms": 0})
        msg = "Cleared %d file(s)\n%.1f MB freed" % (n, freed / 1024.0 / 1024.0)
        try:
            self.session.openWithCallback(lambda a: self.close(), MessageBox,
                                          msg, MessageBox.TYPE_INFO, timeout=6)
        except Exception:
            self.close()
