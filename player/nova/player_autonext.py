# -*- coding: utf-8 -*-
"""NovaPlay player -- the next-episode card and its countdown.

Part of NovaPlaySimplePlayer (plugin_screen_player.py), split out
2026-10-23 without changing behaviour. Methods use the player's widgets
and state through self; module-level helpers come from player_base.
"""
from .player_base import *  # noqa: F401,F403


class PlayerAutoNext(object):
    # ── [A3] next-episode delay, from config ────────────────────────────
    def _nextDelaySecs(self):
        """[A3] read next_episode_delay from config; clamped 5-60s."""
        try:
            v = int(_get_config("next_episode_delay", str(self._AUTONEXT_SECONDS_DEFAULT)) or self._AUTONEXT_SECONDS_DEFAULT)
        except Exception:
            v = self._AUTONEXT_SECONDS_DEFAULT
        return max(5, min(60, v))

    # ─── auto-next card ──────────────────────────────────────────────────
    def _showAutoNextCard(self, nxt):
        _delay = self._nextDelaySecs()
        # [still-watching] after N episodes in a row with no key pressed:
        # ask first; no answer within a minute = stop (nothing plays all night)
        self._autonext_ask = AUTO_CHAIN[0] >= STILL_WATCHING_AFTER
        if self._autonext_ask:
            _delay = 60
            my_log("still watching? asked after {} episodes in a row".format(AUTO_CHAIN[0]))
        self._autonext_nxt = nxt
        self._autonext_secs = _delay
        try:
            # [2026-11-04] the next episode of the same series: the series poster the
            # player already has (an episode's own picture is a wide scene shot)
            poster = getattr(self, "_poster_url", "") or (nxt or {}).get("poster") or ""
            path = ""
            if poster:
                path = plugin_imagecache.getCachedImage(poster, target_size=(100, 150))
                if not path:
                    try:
                        from .plugin_util import _get_cached_poster
                        path = _get_cached_poster(poster) or ""
                    except Exception:
                        path = ""
                if not path:
                    plugin_imagecache.requestImageAsyncPriority(poster, target_size=(100, 150))
                    try:
                        path = plugin_imagecache.getCachedImage(poster) or ""
                    except Exception:
                        path = ""
            if not path:
                path = placeholder_for_item(nxt) or ""
            if path:
                self["autoNextPoster"].instance.setScale(1)
                self["autoNextPoster"].instance.setPixmapFromFile(path)
                self["autoNextPoster"].show()
            else:
                self["autoNextPoster"].hide()
        except Exception:
            self["autoNextPoster"].hide()
        self["autoNextTitle"].setText(_single_line_text(
            (nxt or {}).get("title") or "", width=30, fallback="Next episode"))
        if self._autonext_ask:
            self["autoNextEpisode"].setText("Are you still watching?")
            self["autoNextText"].setText("Stopping in %d seconds" % _delay)
            self["autoNextHelp"].setText("OK = play next episode    EXIT = stop")
        else:
            self["autoNextEpisode"].setText("Next episode")
            self["autoNextText"].setText("Playing automatically in %d seconds" % _delay)
            self["autoNextHelp"].setText("OK = play now    EXIT = cancel")
        try:
            self["autoNextProgress"].setRange((0, _delay))
            self["autoNextProgress"].setValue(_delay)
        except Exception:
            pass
        self._autonext_slide_p = 0.0
        for w in self._AUTONEXT_WIDGETS:
            try:
                inst = self[w].instance
                if inst:
                    dx = self._AUTONEXT_DESIGN_X.get(w, 1110)
                    inst.move(ePoint(dx + self._AUTONEXT_SLIDE_OFFSET,
                                     inst.position().y()))
            except Exception:
                pass
        for w in self._AUTONEXT_WIDGETS:
            try: self[w].show()
            except Exception: pass
        self._autonext_active = True
        self._autonext_poster_url = poster if poster else ""
        self._autonext_poster_polls = 8
        try: self._autonext_timer.stop()
        except Exception: pass
        self._autonext_timer.start(1000, False)
        self._startAutoNextSlide(1.0)

    def _hideAutoNextCard(self):
        self._autonext_active = False
        self._autonext_poster_polls = 0
        try: self._autonext_timer.stop()
        except Exception: pass
        self._startAutoNextSlide(0.0)

    def _pl_autonextTick(self):
        if not getattr(self, "_autonext_active", False):
            return
        if getattr(self, "_autonext_poster_polls", 0) > 0 and getattr(self, "_autonext_poster_url", ""):
            self._autonext_poster_polls -= 1
            try:
                p = plugin_imagecache.getCachedImage(self._autonext_poster_url, target_size=(100, 150)) \
                    or plugin_imagecache.getCachedImage(self._autonext_poster_url)
                if p:
                    self._autonext_poster_polls = 0
                    self["autoNextPoster"].instance.setScale(1)
                    self["autoNextPoster"].instance.setPixmapFromFile(p)
                    self["autoNextPoster"].show()
            except Exception:
                pass
        self._autonext_secs -= 1
        if self._autonext_secs <= 0:
            self._hideAutoNextCard()
            if getattr(self, "_autonext_ask", False):
                # nobody answered "still watching?": stop here
                my_log("still watching? no answer -- stopping")
                AUTO_CHAIN[0] = 0
                self._pl_nextAnswer(False, self._autonext_nxt)
                return
            self._pl_nextAnswer(True, self._autonext_nxt, auto=True)
            return
        try:
            self["autoNextText"].setText(("Stopping in %d seconds" if getattr(self, "_autonext_ask", False)
                                          else "Playing automatically in %d seconds") % self._autonext_secs)
            self["autoNextProgress"].setValue(self._autonext_secs)
            if self._autonext_secs <= 3:
                _c = "#FF6B6B" if (self._autonext_secs % 2) else "#E8E8E8"
                try:
                    if parseColor is not None:
                        self["autoNextText"].instance.setForegroundColor(parseColor(_c))
                except Exception:
                    pass
            else:
                try:
                    if parseColor is not None:
                        self["autoNextText"].instance.setForegroundColor(parseColor("#E8E8E8"))
                except Exception:
                    pass
        except Exception:
            pass

    def _pl_nextAnswer(self, ans, nxt, auto=False):
        # [still-watching] count episodes started by the countdown alone
        AUTO_CHAIN[0] = (AUTO_CHAIN[0] + 1) if auto else 0
        if ans and self._on_next:
            self._skip_restore = True
            cb = self._on_next
            self._pl_onExit(clear_position=True)
            _defer_open_next(cb, nxt)
        else:
            self._pl_onExit(clear_position=True)

    # ── [episodes 2026-10-28] the season's episodes over the video (EPG key) ──
    def _showEpisodes(self):
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        eps = getattr(self, "_episodes", None) or []
        if len(eps) < 2 or not self._on_next:
            self["status"].setText(u"No episode list for this title")
            self._pl_showOSD(True)
            return
        try:
            from .plugin_watched import is_watched
        except Exception:
            is_watched = lambda u: False
        items, cur = [], 0
        for i, ep in enumerate(eps):
            url = ep.get("url", "")
            title = _single_line_text(ep.get("title") or "Episode %d" % (i + 1), width=60, fallback="Episode")
            if url and url == self._item_url:
                cur = i
                label = u"\u25b6  " + title + u"   (playing)"
            else:
                mark = u"\u2713  " if (url and is_watched(url)) else u"     "
                pos = 0
                try:
                    pos = int(_get_saved_position(url) or 0) if url else 0
                except Exception:
                    pos = 0
                label = mark + title + ((u"   \u21ba " + self._clockText(pos)) if pos > 30 else u"")
            items.append((label, i))
        self._episode_cur = cur
        self.session.openWithCallback(self._onEpisodePicked, ChoiceBox,
                                      title=u"Episodes  \u00b7  \u2713 watched   \u21ba resume point",
                                      list=items, selection=cur)

    def _onEpisodePicked(self, choice):
        if not choice:
            return
        try:
            i = int(choice[1])
        except Exception:
            return
        if i == getattr(self, "_episode_cur", -1) or not (0 <= i < len(self._episodes)):
            return
        ep = self._episodes[i]
        my_log("episodes: switching to {}".format((ep.get("title") or "")[:60]))
        AUTO_CHAIN[0] = 0
        self._skip_restore = True
        cb = self._on_next
        self._pl_onExit(clear_position=False)        # keeps this episode's resume point
        _defer_open_next(cb, ep)

