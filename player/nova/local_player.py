# -*- coding: utf-8 -*-
"""WGFileManager -- the Nova player for local files.

A thin subclass of NovaPlay's player (plugin_screen_player.py), so the copied
NovaPlay files stay as close to NovaPlay's own as possible and are easy to
update. Only what makes no sense for a file on disk changes:

  * RED   "Next server"     -> "Previous": the previous video in the folder
  * MENU  Timer tab          -> no "Record stream" row (the file is already here)
"""
from .plugin_screen_player import NovaPlaySimplePlayer
from .plugin_common import my_log


class NovaLocalPlayer(NovaPlaySimplePlayer):

    def __init__(self, session, title, candidates, previous_service=None, prev_episode=None, **kw):
        NovaPlaySimplePlayer.__init__(self, session, title, candidates, previous_service, **kw)
        self._prev_episode = prev_episode
        try:
            self["keyRed"].setText(u"Previous" if prev_episode else u"")
            if not prev_episode:
                self["keyDotR"].hide()
        except Exception:
            pass

    # ── RED: previous file in the folder ─────────────────────────────────
    def _pl_nextServer(self):
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        prev = getattr(self, "_prev_episode", None)
        if not prev or not self._on_next:
            self["status"].setText(u"This is the first file")
            self._pl_showOSD(True)
            return
        my_log("nova: previous file {}".format(prev.get("url", "")))
        self._pl_nextAnswer(True, prev)

    # ── MENU › Timer: Sleep, Chapters (no recording for a local file) ────
    def _menuTimerItems(self):
        rows = NovaPlaySimplePlayer._menuTimerItems(self)
        return [rows[0], rows[2]] if len(rows) >= 3 else rows

    def _onMenuPanel(self, res):
        if res and res[0] == "timer" and res[1] == 1:
            res = ("timer", 2)                      # row 1 here is Chapters
        return NovaPlaySimplePlayer._onMenuPanel(self, res)
