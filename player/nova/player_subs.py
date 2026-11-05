# -*- coding: utf-8 -*-
"""NovaPlay player -- subtitles: the Subtitles tab, YELLOW on/off, subtitle
actions and the sync studio.

Part of NovaPlaySimplePlayer (plugin_screen_player.py), split out
2026-10-23 without changing behaviour. Methods use the player's widgets
and state through self; module-level helpers come from player_base.
"""
from .player_base import *  # noqa: F401,F403
from .novaplay_theme import TH_GOLD, apply as _theme_apply  # [theme]


def _COLOR_NAMES():
    """[2026-10-31] the Studio's text colours, from novaplay_substudio (Gold removed)"""
    try:
        from .novaplay_substudio import _COLORS
        return [c[1] for c in _COLORS]
    except Exception:
        return ["White", "Yellow", "Cyan", "Red", "Green"]


class PlayerSubs(object):
    # ── [subs-panel] Blue: the Settings panel's Audio and Subtitles tabs ───
    def _audioTrackItems(self):
        items = []
        try:
            service = self.session.nav.getCurrentService()
            tracks = service and service.audioTracks()
            n = tracks.getNumberOfTracks() if tracks else 0
            cur = tracks.getCurrentTrack() if n else -1
            for i in range(n):
                name = ""
                try:
                    info = tracks.getTrackInfo(i)
                    name = " ".join(x for x in (info.getLanguage(), info.getDescription()) if x)
                except Exception:
                    pass
                if not name:
                    try:
                        name = tracks.getTrackName(i) or ""
                    except Exception:
                        name = ""
                items.append((name or u"Track {}".format(i + 1), i == cur))
        except Exception as e:
            my_log("audio tracks: {}".format(e))
        return items

    def _subsItems(self):
        """[2026-10-31] the one Subtitles tab: the loaded subtitle (if any), a
        Sync row when it isn't in the Studio, a "Style & sync ›" row that opens the
        Studio (2026-11-04), and where to find a subtitle. Subtitles start
        off; YELLOW turns them on / off."""
        st = get_subtitle_state() or {}
        path = st.get("path") or ""
        try:
            from .novaplay_substudio import STUDIO
            studio_on = STUDIO.is_attached()     # .srt in the Studio (always on)
        except Exception:
            studio_on = False
        rows, acts = [], []
        if path:
            rows.append((os.path.basename(st.get("_orig_path") or path)[:40], True)); acts.append(("cur", None))
            if not studio_on:
                # not in the Studio (not an .srt): one Sync row, ◀▶ ±0.5 s, OK resets
                off = int(st.get("offset_ms") or 0)
                # [2026-11-04] ◀ heard the voice first (earlier) · saw the subtitle first ▶ (later)
                rows.append((u"Sync: \u25c0 heard \u00b7 saw \u25b6", False, True,
                             {"adj": True, "tags": [u"%+.1f s" % (off / 1000.0)]}))
                acts.append(("sync", None))
        # [2026-11-04] Style & sync: the Studio (works with or without a subtitle)
        rows.append((u"Style & sync  \u203a", False)); acts.append(("studio", None))
        # [2026-11-05] the video's own subtitle tracks (local files): picking one
        # copies it out to an .srt, so sync and style work on it
        for r, a in self._embeddedRows(st):
            rows.append(r); acts.append(a)
        for name, key in ((u"SubSource", "subsource"), (u"SubDL", "subdl"),
                          (u"OpenSubtitles", "opensubtitles"), (u"Local files", "browse")):
            rows.append((name, False)); acts.append(("find", key))
        self._subs_acts = acts
        return rows

    # ── [2026-11-05] built-in subtitle tracks -> an .srt the Studio draws ──
    def _embeddedSource(self):
        """the local file being played, or '' (a stream: its tracks can't be reached)"""
        from .novaplay_embedsubs import local_source
        for u in (getattr(getattr(self, "sref", None), "getPath", lambda: "")(),
                  getattr(self, "_quality_current_url", ""), getattr(self, "_item_url", "")):
            try:
                p = local_source(u)
            except Exception:
                p = ""
            if p:
                return p
        return ""

    def _embeddedProbe(self):
        try:
            src = self._embeddedSource()
            if src:
                from .novaplay_embedsubs import probe
                probe(src)
        except Exception as e:
            my_log("built-in subtitles: {}".format(e))

    def _embeddedRows(self, st):
        """rows + actions for the Subtitles tab (nothing for a stream)"""
        try:
            from .novaplay_embedsubs import find_ffmpeg, tracks, probe, label, cache_file
            from .novaplay_subtitles import _ss_cache_dir
            src = self._embeddedSource()
            if not src:
                return []
            if not find_ffmpeg():
                return [((u"Built-in subtitles: needs ffmpeg", False),
                         ("embedded_info", u"Install ffmpeg to use the video's own subtitles: opkg install ffmpeg"))]
            tr = tracks(src)
            if tr is None:
                probe(src)
                return [((u"Built-in subtitles: reading the video\u2026", False),
                         ("embedded_info", u"Still reading the video's subtitle list - open this tab again in a moment"))]
            cur = st.get("_orig_path") or st.get("path") or ""
            folder = _ss_cache_dir()
            return [((u"Built-in: " + label(t), bool(cur) and cur == cache_file(src, t["index"], folder)),
                     ("embedded", t)) for t in tr]
        except Exception as e:
            my_log("built-in subtitles rows: {}".format(e))
            return []

    def _embeddedPick(self, t):
        from .novaplay_embedsubs import Extraction, label
        from .novaplay_subtitles import _ss_cache_dir
        if not t.get("text"):
            self["status"].setText(u"%s: picture subtitles - they can't be turned into text" % label(t).split(u" - ")[0])
            self._pl_showOSD(True)
            return
        src = self._embeddedSource()
        if not src:
            return
        old = getattr(self, "_emb_job", None)
        if old is not None and not old.done:
            self["status"].setText(u"Already copying subtitles out of the video\u2026")
            self._pl_showOSD(True)
            return
        self._emb_job = Extraction(src, t["index"], _ss_cache_dir())
        self._emb_label = label(t)
        my_log("built-in subtitles: picked track {} ({})".format(t["index"], self._emb_label))
        if self._emb_job.done:
            self._embeddedFinish()
            return
        if getattr(self, "_emb_timer", None) is None:
            self._emb_timer = eTimer()
            self._emb_timer.callback.append(self._embeddedPoll)
            self.onClose.append(self._emb_timer.stop)
        self._emb_timer.start(500, False)
        self._embeddedPoll()

    def _embeddedPoll(self):
        job = getattr(self, "_emb_job", None)
        if job is None:
            return
        if not job.done:
            self["status"].setText(u"Copying subtitles out of the video\u2026 %d s  (first time only)" % job.seconds())
            self._pl_showOSD(True)
            return
        try:
            self._emb_timer.stop()
        except Exception:
            pass
        self._embeddedFinish()

    def _embeddedFinish(self):
        job = self._emb_job
        if job.error:
            self["status"].setText(job.error)
        else:
            self._onSubtitlePicked(job.out)
            self["status"].setText(u"Subtitles: %s  -  BLUE \u203a Style & sync to sync" % self._emb_label)
        self._pl_showOSD(True)

    def _subsPanel(self):
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        # [2026-10-31] the one Settings panel, opened on its Subtitles tab
        self._pl_panelMenu(start="subs")

    def _pl_subsToggle(self):
        """[2026-10-31] YELLOW: subtitles on / off. Off keeps the file and its
        sync remembered for this title, so the next press brings it back; with
        nothing remembered, the Subtitles tab opens to find one."""
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        st = get_subtitle_state() or {}
        if st.get("path"):
            disable_subtitle(self.session)
            update_subtitle_state(path="", _orig_path="")
            try:
                from .novaplay_subtitles import set_subtitle_on
                set_subtitle_on(self._item_url, False)
            except Exception:
                pass
            my_log("yellow: subtitles off")
            self["status"].setText(u"CC off")
            self._pl_showOSD(True)
            return
        from .novaplay_subtitles import recall_subtitle, _apply_path_with_offset
        path, offset = recall_subtitle(self._item_url)
        if path:
            _apply_path_with_offset(self.session, self._item_url, path, offset)
            try:
                from .novaplay_subtitles import set_subtitle_on
                set_subtitle_on(self._item_url, True)
            except Exception:
                pass
            my_log("yellow: subtitles on ({})".format(os.path.basename(path)))
            self["status"].setText(u"CC on  \u00b7  {}".format(os.path.basename(path)[:40]))
            self._pl_showOSD(True)
            return
        my_log("yellow: no subtitle for this title yet -> Subtitles tab")
        self._subsPanel()

    def _subsLive(self, col, idx, d=0):
        """'stay' rows: run without closing the panel; the text goes on its help line.
        d: ◀ -1 / ▶ +1 on a value row, 0 for OK."""
        if col != "subs":
            return ""
        act = self._subs_acts[idx][0] if idx < len(getattr(self, "_subs_acts", [])) else ""
        if act != "sync":
            return ""
        msg = adjust_sync(self.session, 500 * d) if d else reset_sync(self.session)
        p = getattr(self, "_subs_panel", None)
        if p is not None:
            p.updateColumn("subs", self._subsItems())
        my_log("subs panel: sync {:+d} -> {}".format(500 * d, msg))
        return msg or u"\u2713"

    def _onSubsPanel(self, res):
        self._subs_panel = None
        if not res:
            return
        col, idx = res
        try:
            if col == "audio":
                if idx < getattr(self, "_audio_count", 0):
                    self._pl_audioPicked((u"", idx))
            elif col == "subs":
                act, data = self._subs_acts[idx]
                if act == "find":
                    self._onSubtitleAction((u"", data))
                elif act == "studio":
                    self._onSubtitleAction((u"", "studio_open"))
                elif act == "embedded":
                    self._embeddedPick(data)
                elif act == "embedded_info":
                    self["status"].setText(data)
                    self._pl_showOSD(True)
        except Exception as e:
            my_log("subs panel pick error: {}".format(e))

    def _onSubtitleAction(self, result):
        if not result:
            return
        choice = result[1]
        if choice == "studio_open":
            if not getattr(self, "_studioOverlayActive", False):
                self._showStudioOverlay()
            return
        if choice == "browse":
            self.session.openWithCallback(self._onSubtitlePicked,
                                          NovaSubtitleBrowser, "", self.title)
        elif choice in ("subsource", "subdl", "opensubtitles"):
            # [2026-11-04] with the film's year: "Resident Evil" alone found the
            # 2002 film's subtitles for the 2026 one
            q = self.title
            y = str(getattr(self, "_osd_year", "") or "")[:4]
            if y.isdigit() and y not in q:
                q = u"{} {}".format(q, y)
            try:
                from .novaplay_subtitles import set_search_hint
                _tid, _tk = getattr(self, "_osd_tmdb", (None, "movie"))
                set_search_hint(_tid, _tk, y)
            except Exception:
                pass
            self.session.openWithCallback(self._onSubtitlePicked,
                                          NovaOnlineSubsScreen, q,
                                          self._item_url, choice,
                                          _cfg(choice + "_api_key", ""))

    def _rememberSeriesSubs(self, path=None, off=False):
        """[series-prefs] the next episodes: same subtitle language, or none"""
        try:
            from .plugin_series_prefs import set_pref, subtitle_language
            if off:
                set_pref(self._raw_title or self.title, subs="off")
            elif path:
                set_pref(self._raw_title or self.title, subs=None, sub_lang=subtitle_language(path) or None)
        except Exception:
            pass

    def _onSubtitlePicked(self, path):
        try:
            from .novaplay_subtitles import to_srt
            path = to_srt(path)              # [2026-10-31] .ass/.vtt/.sub -> .srt (Studio + Sync)
        except Exception:
            pass
        if path and os.path.exists(path):
            self._rememberSeriesSubs(path)
            remember_subtitle(self._item_url, path, 0)
            update_subtitle_state(path=path, _orig_path=path, offset_ms=0)
            disable_subtitle(self.session)
            apply_subtitle(self.session, path)
            self._logSubtitleAttach("picked", path)

    def _logSubtitleAttach(self, how, path):
        """[WGFM 2026-11-05] which renderer has the subtitle (the sync rows
        depend on it) -- into /tmp/wgfilemanager.log"""
        try:
            from .novaplay_substudio import STUDIO
            size = os.path.getsize(path) if os.path.exists(path) else -1
            if STUDIO.is_attached():
                my_log("subtitle {}: {} ({} bytes) -> Studio, {} lines".format(
                    how, path, size, STUDIO.get_cue_count()))
            else:
                head = b""
                try:
                    with open(path, "rb") as fh:
                        head = fh.read(80)
                except Exception:
                    pass
                my_log("subtitle {}: {} ({} bytes) -> Enigma2 draws it, the Studio could not "
                       "read it; file starts {!r}".format(how, path, size, head))
        except Exception as e:
            my_log("subtitle {}: {} ({})".format(how, path, e))

    # ── Subtitle Studio overlay (v3) ─────────────────────────────────────
    def _studioItemsList(self):
        from .novaplay_substudio import STUDIO
        s = STUDIO.style
        align_lbl = ["Top", "Bottom", "Center"][s["align"]]
        font_lbl = os.path.basename(s.get("font_path") or "") or s.get("font_name") or "Default"
        try:
            _delay_val = int(get_subtitle_state().get("offset_ms") or 0)
        except Exception:
            _delay_val = int(STUDIO.get_offset() or 0)
        return [
            ("Delay", "%+d ms" % _delay_val, "delay", 250),
            ("Fine sync", "%+d ms" % _delay_val, "finedelay", 100),     # [2026-11-04]
            ("Size", "%d px" % s["size"], "size", 2),
            ("Font", font_lbl + "  ›", "font", 1),
            ("Color", _COLOR_NAMES()[s["color_idx"] % len(_COLOR_NAMES())], "color", 1),
            ("Outline", "On" if s["outline"] else "Off", "outline", 1),
            ("Bold", "On" if s.get("bold") else "Off", "bold", 1),
            ("Corners", "Rounded" if s.get("bg_round", True) else "Square", "corners", 1),
            ("Outline color", u"Black", "ocolor", 1),
            ("Background", "On" if s["bg"] else "Off", "bg", 1),
            ("Opacity", "%d%%" % int(round((255 - int(s["bg_alpha"])) * 100 / 255.0)), "bg_alpha", 16),
            ("Position", "%+d px" % int(s["offset_y"]), "offset_y", 10),
            ("Align", align_lbl, "align", 1),
            ("Spacing", str(s["spacing"]), "spacing", 2),
            ("Auto-wrap", "On" if s.get("auto_wrap", True) else "Off", "autowrap", 1),
            ("Cue position", "On" if s.get("use_cue_pos", True) else "Off", "cuepos", 1),
            ("Fix capitals", "On" if s.get("fix_caps") else "Off", "fixcaps", 1),      # [2026-11-04]
            ("Presets", "A / B / C  ›", "presets", 0),
            ("Pick line to sync", "OK  ›", "pickline", 0),
            ("Reset", "OK  ›", "reset", 0),
            ("Remove", "OK  ›", "remove", 0),
        ]

    def _showStudioOverlay(self):
        self._studioOverlayActive = True
        self._studioItems = self._studioItemsList()
        if self._studioIdx >= len(self._studioItems):
            self._studioIdx = 0
        # [FIX] keep the subtitles running under the overlay so every edit is
        # seen live on the real subtitle (the tick used to be stopped here)
        try:
            self._studioTimer.start(100, False)
        except Exception:
            pass
        for k in self._STUDIO_KEYS:
            try:
                self[k].show()
            except Exception:
                pass
        # [player-anim] drop the panel down from -320 → design
        self._studio_slide_p = 0.0
        self._studio_slide_target = 1.0
        self._applyStudioSlide()
        try:
            self._studio_slide_timer.start(20, False)
        except Exception:
            pass
        self._studioRefresh()

    def _hideStudioOverlay(self):
        self._studioOverlayActive = False
        try:
            self._studioTimer.start(100, False)
        except Exception:
            pass
        # [player-anim] slide the panel back off the top before hiding
        self._studio_slide_target = 0.0
        try:
            self._studio_slide_timer.start(20, False)
        except Exception:
            for k in self._STUDIO_KEYS:
                try: self[k].hide()
                except Exception: pass
        try:
            from .novaplay_substudio import STUDIO
            STUDIO.flush_style()
        except Exception:
            pass
        for k in ("safeTop", "safeBottom", "safeLeft", "safeRight"):
            try:
                self[k].hide()
            except Exception:
                pass

    # ── [studio-ui] tabs ────────────────────────────────────────────────
    def _studioGroupIdx(self, idx=None):
        idx = self._studioIdx if idx is None else idx
        try:
            key = self._studioItems[idx][2]
        except Exception:
            return 0
        for g, (_t, keys) in enumerate(self._STUDIO_GROUPS):
            if key in keys:
                return g
        return 0

    def _studioMembers(self, g):
        keys = self._STUDIO_GROUPS[g][1]
        pos = dict((it[2], i) for i, it in enumerate(self._studioItems))
        return [pos[k] for k in keys if k in pos]

    def _studioGroup(self, g):
        g %= len(self._STUDIO_GROUPS)
        members = self._studioMembers(g)
        if members:
            self._studioIdx = members[0]
        self._studioRefresh()

    def _studioRefresh(self):
        total = len(self._studioItems)
        if not total:
            return
        idx = max(0, min(self._studioIdx, total - 1))
        self._studioIdx = idx
        g = self._studioGroupIdx(idx)
        members = self._studioMembers(g)
        # tabs
        for t, tab in enumerate(self._STUDIO_TABS):
            try:
                self[tab].setText(self._STUDIO_GROUPS[t][0])
                inst = self[tab].instance
                if inst and parseColor is not None:
                    inst.setBackgroundColor(parseColor(TH_GOLD if t == g else "#171718"))
                    inst.setForegroundColor(parseColor("#0C1017" if t == g else "#8B949E"))
                    inst.invalidate()
            except Exception:
                pass
        # cards: this tab's settings, centred, the chosen one in gold
        n = len(members)
        start = (len(self._STUDIO_CARDS) - n) // 2
        from .novaplay_substudio import STUDIO, _COLORS
        for slot, card in enumerate(self._STUDIO_CARDS):
            j = slot - start
            if not (0 <= j < n):
                try:
                    self[card].hide()
                except Exception:
                    pass
                continue
            item_i = members[j]
            label, value, key, _s = self._studioItems[item_i]
            sel = item_i == idx
            txt = u"%s\n%s" % (label, value) if value else label
            fg = "#F0F6FC" if sel else "#D0D0D0"
            if key in ("color", "ocolor"):
                ci = STUDIO.style["color_idx" if key == "color" else "outline_color_idx"] % len(_COLORS)
                fg = "#" + _COLORS[ci][0][-6:]
            try:
                self[card].setText(txt)
                inst = self[card].instance
                if inst:
                    pos = inst.position()
                    inst.move(ePoint(self._STUDIO_SLOTS_X[slot], int(pos.y())))
                    if parseColor is not None:
                        inst.setBackgroundColor(parseColor("#5C4A12" if sel else "#171718"))
                        inst.setForegroundColor(parseColor(fg))
                        inst.invalidate()
                self[card].show()
            except Exception:
                pass
        try:
            pos_in = members.index(idx) + 1 if idx in members else 1
            self["studioStatus"].setText(u"%d / %d" % (pos_in, max(1, n)))
        except Exception:
            pass
        cur_key = self._studioItems[idx][2]
        try:
            self["studioPreview"].setText(self._STUDIO_HINTS.get(cur_key, u""))
        except Exception:
            pass
        try:
            self["studioPreviewBg"].hide()
        except Exception:
            pass
        show_safe = False            # [2026-10-31] guide lines removed
        for k in ("safeTop", "safeBottom", "safeLeft", "safeRight"):
            try:
                if show_safe:
                    self[k].show()
                else:
                    self[k].hide()
            except Exception:
                pass

    def _studioChKey(self, d):
        if getattr(self, "_studioOverlayActive", False):
            self._studioGroup(self._studioGroupIdx() + d)

    def _studioMove(self, step):
        """◀ ▶ inside the current tab."""
        if not self._studioItems:
            return
        g = self._studioGroupIdx()
        members = self._studioMembers(g)
        if self._studioIdx not in members:
            self._studioGroup(g)
            return
        # [2026-10-28] past the last (first) setting of a tab -> the next
        # (previous) tab, its first (last) setting; 1-4 still pick a tab
        j = members.index(self._studioIdx) + step
        if 0 <= j < len(members):
            self._studioIdx = members[j]
        else:
            ng = (g + (1 if step > 0 else -1)) % len(self._STUDIO_GROUPS)
            nm = self._studioMembers(ng)
            if nm:
                self._studioIdx = nm[0] if step > 0 else nm[-1]
        self._studioRefresh()

    def _studioDelayTotal(self):
        try:
            return int(get_subtitle_state().get("offset_ms") or 0)
        except Exception:
            try:
                from .novaplay_substudio import STUDIO
                return int(STUDIO.get_offset() or 0)
            except Exception:
                return 0

    def _studioSetDelay(self, new_off):
        from .novaplay_substudio import STUDIO
        new_off = int(new_off)
        self._studioSyncMsg = None
        if not STUDIO.is_attached():
            st0 = get_subtitle_state()
            p0 = st0.get("_orig_path") or st0.get("path") or ""
            if p0 and os.path.exists(p0) and p0.lower().endswith(".srt") and STUDIO.attach(p0):
                # [WGFM 2026-11-05] the file is readable: the Studio draws it from now on
                try:
                    svc = self.session.nav.getCurrentService()
                    sub = svc and svc.subtitle()
                    if sub:
                        sub.disableSubtitle()
                except Exception:
                    pass
                my_log("sync: Studio took over {}".format(p0))
            else:
                msg = adjust_sync(self.session, new_off - self._studioDelayTotal())
                my_log("sync ({} ms) without the Studio: {} [subtitle {!r}]".format(new_off, msg, p0))
                ok = msg.startswith("Sync: ") and msg[6:7] in "+-0123456789"
                self._studioSyncMsg = None if ok else {
                    "No subtitle active": u"No subtitle file on - BLUE › Subtitles: a Built-in track, a search, or Local files",
                    "Sync: SRT files only": u"This subtitle type can't be synced - only text subtitles (.srt / .ass / .vtt)",
                }.get(msg, u"Could not shift this subtitle file - see /tmp/wgfilemanager.log")
                return
        st = get_subtitle_state()
        base_path = st.get("_orig_path") or st.get("path") or ""
        if base_path and os.path.exists(base_path) and base_path != STUDIO.get_path():
            STUDIO.attach(base_path)
        STUDIO.set_offset(new_off)
        STUDIO._last_rendered = None
        if base_path:
            update_subtitle_state(path=base_path, _orig_path=base_path,
                                  offset_ms=new_off)
            if st.get("item_url"):
                try:
                    remember_subtitle(st["item_url"], base_path, new_off)
                except Exception:
                    pass
        my_log("studio delay: {:+d} ms".format(new_off))

    def _studioAdjust(self, step):
        if not (0 <= self._studioIdx < len(self._studioItems)):
            return
        from .novaplay_substudio import STUDIO
        label, value, key, stp = self._studioItems[self._studioIdx]
        s = STUDIO.style
        if key in ("delay", "finedelay"):
            self._studioSetDelay(self._studioDelayTotal() + int(stp * step))
        elif key == "size":
            s["size"] = max(22, min(80, s["size"] + stp * step))
            STUDIO._layout_static()
        elif key == "color":
            s["color_idx"] = (s["color_idx"] + step) % len(_COLOR_NAMES())
            STUDIO._layout_static()
        elif key == "bg":
            s["bg"] = not s["bg"]
        elif key == "bg_alpha":
            s["bg_alpha"] = max(0, min(224, s["bg_alpha"] + stp * step))
            STUDIO._layout_static()
        elif key == "offset_y":
            from .novaplay_substudio import offset_limits
            _lo, _hi = offset_limits(s["align"])
            s["offset_y"] = max(_lo, min(_hi, s["offset_y"] + stp * step))
        elif key == "spacing":
            s["spacing"] = max(0, min(120, s["spacing"] + stp * step))
        elif key == "outline":
            s["outline"] = not s["outline"]
        elif key == "ocolor":
            s["outline_color_idx"] = 0
            STUDIO._layout_static()
        elif key == "align":
            s["align"] = (s["align"] + step) % 3
        elif key == "autowrap":
            s["auto_wrap"] = not s.get("auto_wrap", True)
        elif key == "cuepos":
            s["use_cue_pos"] = not s.get("use_cue_pos", True)
            STUDIO._last_rendered = None
        elif key == "presets":
            self._studioPresetMenu()
            return
        elif key == "font":
            self._studioFontBrowser()
            return
        elif key == "reset":
            STUDIO.reset_style()
        elif key == "remove":
            turn_off_subtitle(self.session, self._item_url)
        elif key == "pickline":
            self._studioPickLine()
            return
        try:
            STUDIO.refresh()
        except Exception:
            pass
        self._studioItems = self._studioItemsList()
        self._studioRefresh()

    def _studioPickLine(self):
        from .novaplay_substudio import STUDIO
        if not STUDIO.is_attached():
            return
        self._hideStudioOverlay()
        entries = []
        for i, (start, end, body, _, _) in enumerate(STUDIO._cues):
            lines_preview = " / ".join(body[:2])
            entries.append((lines_preview[:60], i))
        self.session.openWithCallback(
            self._onStudioPickLine, ChoiceBox,
            "Pick the line being spoken now", entries)

    def _onStudioPickLine(self, choice):
        from .novaplay_substudio import STUDIO
        from .novaplay_subtitles import get_subtitle_state, remember_subtitle
        if not choice:
            self._showStudioOverlay()
            return
        idx = choice[1] if isinstance(choice, (tuple, list)) and len(choice) > 1 else choice
        cue = STUDIO._cues[idx]
        self._studioSetDelay(int(self._studioNowMs() - cue[0]))
        self._studioItems = self._studioItemsList()
        self._showStudioOverlay()

    def _studioOk(self):
        if not (0 <= self._studioIdx < len(self._studioItems)):
            return
        label, value, key, stp = self._studioItems[self._studioIdx]
        if key == "presets":
            self._studioPresetMenu()
            return
        if key == "font":
            self._studioFontBrowser()
            return
        if key == "pickline":
            self._studioPickLine()
            return
        if key in ("delay", "size", "bg_alpha", "offset_y", "spacing", "color", "bg",
                   "outline", "ocolor", "align"):
            choices = []
            if key == "delay":
                choices = [("%+d ms" % v, v) for v in range(-5000, 5001, 250)]
            elif key == "size":
                choices = [(str(v), v) for v in range(22, 81, 2)]
            elif key == "color":
                choices = [(n, i) for i, n in enumerate(_COLOR_NAMES())]
            elif key == "bg":
                choices = [("On", 1), ("Off", 0)]
            elif key == "bg_alpha":
                choices = [(str(v), v) for v in range(0, 225, 16)]
            elif key == "offset_y":
                choices = [(str(v), v) for v in range(-250, 121, 10)]
            elif key == "spacing":
                choices = [(str(v), v) for v in range(0, 121, 2)]
            elif key == "outline":
                choices = [("On", 1), ("Off", 0)]
            elif key == "ocolor":
                choices = [(u"Black", 0)]          # [2026-10-31] outline is always black
            elif key == "align":
                choices = [("Top", 0), ("Bottom", 1), ("Center", 2)]
            self._studioChoiceKey = key
            self._hideStudioOverlay()
            self.session.openWithCallback(self._onStudioChoice, ChoiceBox,
                                          title=label, list=choices)
            return
        self._studioAdjust(1)

    def _onStudioChoice(self, choice):
        if not choice:
            self._showStudioOverlay()
            return
        value = choice[1] if isinstance(choice, (tuple, list)) and len(choice) > 1 else choice
        key = getattr(self, "_studioChoiceKey", "")
        from .novaplay_substudio import STUDIO
        s = STUDIO.style
        try:
            if key == "delay":
                self._studioSetDelay(int(value))
            elif key == "size":
                s["size"] = int(value)
                STUDIO._layout_static()
            elif key == "color":
                s["color_idx"] = int(value) % len(_COLOR_NAMES())
                STUDIO._layout_static()
            elif key == "bg":
                s["bg"] = bool(value)
            elif key == "bg_alpha":
                s["bg_alpha"] = int(value)
                STUDIO._layout_static()
            elif key == "offset_y":
                from .novaplay_substudio import clamp_offset
                s["offset_y"] = int(value)
                clamp_offset(s)
            elif key == "spacing":
                s["spacing"] = int(value)
            elif key == "outline":
                s["outline"] = bool(value)
            elif key == "ocolor":
                s["outline_color_idx"] = 0
                STUDIO._layout_static()
            elif key == "align":
                s["align"] = int(value) % 3
        except Exception:
            pass
        try:
            STUDIO.refresh()
        except Exception:
            pass
        self._studioItems = self._studioItemsList()
        self._showStudioOverlay()

    def _studioPresetMenu(self):
        items = []
        for slot in ("A", "B", "C"):
            items.append(("Load %s" % slot, "load_" + slot))
            items.append(("Save %s" % slot, "save_" + slot))
        self._hideStudioOverlay()
        self.session.openWithCallback(self._onStudioPreset, ChoiceBox,
                                      "Style Presets", items)

    def _onStudioPreset(self, choice):
        from .novaplay_substudio import STUDIO
        if not choice:
            self._showStudioOverlay()
            return
        action = choice[1] if isinstance(choice, (tuple, list)) and len(choice) > 1 else choice
        slot = str(action)[-1] if action else "A"
        if str(action).startswith("save_"):
            STUDIO.save_preset(slot)
            STUDIO.flush_style()
        elif str(action).startswith("load_"):
            STUDIO.load_preset(slot)
        self._studioItems = self._studioItemsList()
        self._showStudioOverlay()

    def _studioFontBrowser(self):
        try:
            from Components.FileList import FileList
        except Exception:
            FileList = None
        if FileList is None:
            self["status"].setText("Font browser unavailable")
            self._pl_showOSD(True)
            return
        self._hideStudioOverlay()

        class _FontPick(Screen):
            skin = _theme_apply("""
            <screen name="NovaFontPick" position="center,center" size="1500,860" backgroundColor="transparent" title="Select Font" flags="wfNoBorder">
                <eLabel theme="panel" position="0,0" size="1500,860" backgroundColor="#121822" cornerRadius="18" zPosition="0" />
        <eLabel position="40,78" size="140,4" backgroundColor="#F2C230" cornerRadius="2" zPosition="2" />
                <widget name="path" position="40,18" size="1420,44" font="Bold;30" foregroundColor="#F2C230" transparent="1" zPosition="2" />
                <widget name="list" position="30,100" size="1440,680" scrollbarMode="showOnDemand" foregroundColor="#D6DCE5" foregroundColorSelected="#F2C230" backgroundColor="#121822" backgroundColorSelected="#2B3648" zPosition="2" />
                <widget name="hint" position="40,800" size="1420,36" font="Regular;24" foregroundColor="#A3ADBB" transparent="1" zPosition="2" />
            </screen>""")
            def __init__(self2, session, start_dir):
                Screen.__init__(self2, session)
                self2["path"] = Label(start_dir)
                self2["list"] = FileList(start_dir, showDirectories=True,
                                         showFiles=True,
                                         matchingPattern=r"^.*\.(ttf|otf|ttc)$")
                self2["hint"] = Label("OK select  |  EXIT back  |  YELLOW default font")
                self2["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
                    "ok": self2._ok,
                    "cancel": lambda: self2.close("__keep__"),
                    "yellow": lambda: self2.close(""),
                    "up": lambda: self2["list"].up(),
                    "down": lambda: self2["list"].down(),
                    "left": lambda: self2["list"].pageUp(),
                    "right": lambda: self2["list"].pageDown(),
                }, -1)
            def _ok(self2):
                try:
                    if self2["list"].canDescent():
                        self2["list"].descent()
                        try:
                            self2["path"].setText(str(self2["list"].getCurrentDirectory() or ""))
                        except Exception:
                            pass
                        return
                except Exception:
                    pass
                try:
                    sel = self2["list"].getFilename()
                    if sel:
                        self2.close(sel)
                except Exception:
                    pass

        start = "/media/hdd" if os.path.exists("/media/hdd") else "/"
        self.session.openWithCallback(self._onStudioFontPicked, _FontPick, start)

    def _onStudioFontPicked(self, path=None):
        from .novaplay_substudio import STUDIO
        try:
            if path == "__keep__" or path is None:
                pass
            elif path:
                STUDIO.register_font(path)
            else:
                STUDIO.use_default_font()
        except Exception:
            pass
        self._studioItems = self._studioItemsList()
        self._showStudioOverlay()


# ─── [PATCH 32a] per-site candidate memory key ──────────────────────────────

    # ── [series-prefs 2026-10-28] start like the last episode of this series ──
    def _applySeriesAudio(self):
        try:
            from .plugin_series_prefs import get
            want = str(get(self._raw_title or self.title).get("audio") or "").lower()[:3]
            if not want or getattr(self, "_closed_flag", False):
                return
            svc = self.session.nav.getCurrentService()
            tracks = svc and svc.audioTracks()
            n = tracks.getNumberOfTracks() if tracks else 0
            if n < 2:
                return
            cur = tracks.getCurrentTrack()
            for i in range(n):
                try:
                    lang = (tracks.getTrackInfo(i).getLanguage() or "").lower()[:3]
                except Exception:
                    lang = ""
                if lang == want:
                    if i != cur:
                        tracks.selectTrack(i)
                        my_log("series prefs: audio track {} ({}) like the last episode".format(i + 1, lang))
                        self["status"].setText(u"Audio: {} (as last episode)".format(lang))
                    return
        except Exception as e:
            my_log("series prefs audio: {}".format(e))

