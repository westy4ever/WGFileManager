# -*- coding: utf-8 -*-
"""NovaPlay player -- audio tracks, stream info, sleep timer, recording, the MENU panel
(picture, timer, settings), chapters, help, self-test, aspect ratio.

Part of NovaPlaySimplePlayer (plugin_screen_player.py), split out
2026-10-23 without changing behaviour. Methods use the player's widgets
and state through self; module-level helpers come from player_base.
"""
from .player_base import *  # noqa: F401,F403


class PlayerMenus(object):
    # ── [player-ux] labelled audio-track entries ────────────────────────
    def _pl_audioSelect(self):
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        if AudioSelection is not None:
            try:
                self.session.open(AudioSelection, self)
                return
            except Exception as e:
                my_log("AudioSelection failed ({}), using list".format(e))
        try:
            service = self.session.nav.getCurrentService()
            if not service:
                return
            tracks = service.audioTracks()
            if not tracks:
                self["status"].setText("Audio: N/A")
                return
            n = tracks.getNumberOfTracks()
            if n <= 1:
                self["status"].setText("Audio: 1 track only")
                return
            cur = tracks.getCurrentTrack()
            entries = []
            for i in range(n):
                try:
                    name = tracks.getTrackName(i) or ""
                except Exception:
                    name = ""
                extra = ""
                for probe in ("getTrackLanguage", "getTrackCodec"):
                    try:
                        fn = getattr(tracks, probe, None)
                        if fn:
                            v = fn(i)
                            if v:
                                extra = (extra + " · " + str(v)).strip(" ·")
                    except Exception:
                        pass
                if extra:
                    label = u"Track {} — {}{}{}".format(
                        i + 1, name, (u" · " + extra) if name else u"", u" ▶" if i == cur else u"")
                else:
                    label = u"Track {}: {}{}".format(i + 1, name, u" ▶" if i == cur else u"")
                entries.append((label, i))
            self.session.openWithCallback(self._pl_audioPicked, ChoiceBox, "Audio", entries)
        except Exception as e:
            my_log("audioSelect error: {}".format(e))

    def _pl_audioPicked(self, choice):
        if not choice:
            return
        idx = choice[1] if isinstance(choice, (tuple, list)) and len(choice) > 1 else choice
        try:
            service = self.session.nav.getCurrentService()
            if service:
                tracks = service.audioTracks()
                if tracks:
                    tracks.selectTrack(int(idx))
                    self["status"].setText("Audio: track %d" % (int(idx) + 1))
                    self._pl_showOSD(True)
                    # [series-prefs] the next episodes start on this language
                    try:
                        lang = tracks.getTrackInfo(int(idx)).getLanguage() or ""
                        if lang:
                            from .plugin_series_prefs import set_pref
                            set_pref(self._raw_title or self.title, audio=lang)
                    except Exception:
                        pass
        except Exception as e:
            my_log("audioPicked error: {}".format(e))

    def _pl_streamInfo(self):
        try:
            service = self.session.nav.getCurrentService()
            info = service.info() if service else None
            lines = [u"Stream info"]
            if info is not None and iServiceInformation is not None:
                try:
                    x = info.getInfo(iServiceInformation.sWidth)
                    y = info.getInfo(iServiceInformation.sHeight)
                    if x > 0 and y > 0:
                        lines.append(u"Resolution: {}x{}".format(x, y))
                except Exception:
                    pass
                try:
                    fr = info.getInfo(iServiceInformation.sFrameRate)
                    if fr > 0:
                        lines.append(u"Frame rate: {} fps".format(fr))
                except Exception:
                    pass
            lines.append(u"Candidate: {} ({})".format(
                self._candidate_label or "-",
                (self._candidate_idx + 1) if self._candidate_idx >= 0 else "-"))
            try:
                st = novaplay_proxy.get_stats()
                lines.append(u"Proxy: {} req / {} errors / {} manifests".format(
                    st.get("requests", 0), st.get("upstream_errors", 0), st.get("manifests_rewritten", 0)))
            except Exception:
                pass
            self.session.open(MessageBox, u"\n".join(lines), MessageBox.TYPE_INFO, timeout=10)
        except Exception as e:
            my_log("streamInfo error: {}".format(e))

    def _sleepLabel(self):
        return "off" if not self._sleep_minutes else "%d min" % self._sleep_minutes

    def _pl_sleepMenu(self):
        entries = [("Off", 0), ("15 min", 15), ("30 min", 30), ("60 min", 60), ("90 min", 90)]
        self.session.openWithCallback(self._pl_sleepPicked, ChoiceBox, "Sleep timer", entries)

    def _pl_sleepPicked(self, choice):
        if not choice:
            return
        mins = choice[1] if isinstance(choice, (tuple, list)) and len(choice) > 1 else choice
        self._sleep_minutes = int(mins or 0)
        try:
            if self._sleep_timer is not None:
                self._sleep_timer.stop()
        except Exception:
            pass
        self._sleep_timer = None
        if self._sleep_minutes > 0:
            self._sleep_timer = eTimer()
            self._sleep_timer.callback.append(self._pl_sleepExpired)
            self._sleep_timer.start(self._sleep_minutes * 60000, True)
            self["status"].setText("Sleep: %d min" % self._sleep_minutes)
        else:
            self["status"].setText("Sleep: off")
        self._pl_showOSD(True)

    def _pl_sleepExpired(self):
        my_log("Sleep timer expired — exiting playback")
        self._pl_onExit()

    def _pl_recordCurrentStream(self):
        if getattr(self, "_record_task", None) and self._record_task.status == "downloading":
            self["status"].setText("Recording already running")
            self._pl_showOSD(True)
            return
        # [player-ux] disk-space guard
        try:
            _target = "/media/hdd"
            if not os.path.exists(_target):
                _target = "/"
            st = os.statvfs(_target)
            free_mb = (st.f_bavail * st.f_frsize) // (1024 * 1024)
            if free_mb < 500:
                self.session.open(
                    MessageBox,
                    u"Not enough disk space to record\nFree: {} MB (minimum 500 MB)".format(free_mb),
                    MessageBox.TYPE_WARNING, timeout=6)
                self._pl_showOSD(True)
                return
        except Exception as e:
            my_log("record disk-space check skipped: {}".format(e))
        # [2026-11-04] record what is playing NOW (the current candidate), with
        # its headers: it used to take the first proxied candidate only, and
        # for a direct one the "#Referer=..." headers were lost (403)
        url, referer = self._recordSource()
        if not url or not url.startswith("http"):
            self["status"].setText("Recording: no stream URL")
            self._pl_showOSD(True)
            return
        try:
            from .plugin_downloads import DownloadTask, download_manager
            task = DownloadTask(title=self.title, url=url, referer=referer, item_url=self._item_url)
            task.status = "downloading"     # [2026-11-04] REC shows at once (was "queued" here)
            self._record_task = task
            self["status"].setText("Recording started...")
            self._updateRecBlink()
            self._pl_showOSD(True)

            def _bg():
                try:
                    dest = download_manager(task, title_hint=self.title)
                    my_log("record: saved {}".format(dest))
                    callInMainThread(self._pl_recDone, u"Recorded: {}".format(os.path.basename(dest)))
                except Exception as e:
                    my_log("record failed: {} ({})".format(e, url[:100]))
                    if task.status != "cancelled":
                        callInMainThread(self._pl_recDone, u"Recording failed: {}".format(str(e)[:40]))
                finally:
                    callInMainThread(self._updateRecBlink)

            _t = threading.Thread(target=_bg)
            _t.daemon = True
            _t.start()
        except Exception as e:
            my_log("record error: {}".format(e))
            self["status"].setText("Recording unavailable")
            self._pl_showOSD(True)

    def _recordSource(self):
        """-> (stream url with "|Header=value" headers, referer) for the
        candidate that is playing"""
        from urllib.parse import urlparse, parse_qs, unquote
        cands = list(self.candidates or [])
        i = getattr(self, "_candidate_idx", -1)
        order = ([cands[i]] if 0 <= i < len(cands) else []) + cands
        for cand in order:
            svc = str(cand[1] if len(cand) > 1 else "")
            if not svc:
                continue
            try:
                p = urlparse(svc)
                if p.hostname in ("127.0.0.1", "localhost") and p.path == "/stream":
                    qs = parse_qs(p.query or "")
                    u = unquote((qs.get("url") or [""])[0]).strip()
                    ref = unquote((qs.get("referer") or [""])[0]).strip()
                    if u.startswith("http"):
                        return u, ref
                    continue
                if p.hostname in ("127.0.0.1", "localhost"):
                    svc = svc.split("/", 3)[3] if svc.count("/") >= 3 else ""
                if "#" in svc and "|" not in svc:
                    base, frag = svc.split("#", 1)
                    if "=" in frag:
                        svc = base + "|" + frag            # "#Referer=x&User-Agent=y" -> pipe form
                ref = ""
                if "|" in svc:
                    for kv in svc.split("|", 1)[1].split("&"):
                        if kv.lower().startswith("referer="):
                            ref = unquote(kv.split("=", 1)[1])
                if svc.startswith("http"):
                    return svc, ref
            except Exception:
                continue
        try:
            u = str(self.sref.getPath() or "").strip()
            return (u.split("#")[0], "") if u.startswith("http") else ("", "")
        except Exception:
            return "", ""

    def _pl_stopRecording(self):
        task = getattr(self, "_record_task", None)
        if task and task.status == "downloading":
            task.cancel()
            self["status"].setText("Recording stopped")
        else:
            self["status"].setText("Not recording")
        self._updateRecBlink()
        self._pl_showOSD(True)

    def _pl_recDone(self, msg):
        try:
            self["status"].setText(msg)
            self._pl_showOSD(True)
        except Exception:
            pass

    def _updateRecBlink(self):
        try:
            task = getattr(self, "_record_task", None)
            if task is not None and task.status == "downloading":
                self._rec_blink_on = True
                self["recBlink"].setText("● REC")
                self["recBlink"].show()
                try: self._rec_blink_timer.start(650, True)
                except Exception: pass
            else:
                try: self._rec_blink_timer.stop()
                except Exception: pass
                self["recBlink"].hide()
        except Exception:
            pass

    def _pl_tickRecBlink(self):
        try:
            task = getattr(self, "_record_task", None)
            if task is None or task.status != "downloading":
                self._updateRecBlink()
                return
            self._rec_blink_on = not self._rec_blink_on
            if self._rec_blink_on:
                self["recBlink"].show()
            else:
                self["recBlink"].hide()
            self._rec_blink_timer.start(650, True)
        except Exception:
            pass

    def _pl_subtitleDelayBack(self):
        if getattr(self, "_studioOverlayActive", False):
            return
        if getattr(self, "_autonext_active", False):
            return
        try:
            adjust_sync(self.session, -SYNC_STEP_MS)
            state = get_subtitle_state()
            off = int(state.get("offset_ms") or 0)
            self["status"].setText("Subtitles: %+d ms" % off)
            self._showSyncToast("%+d ms" % off)
        except Exception as e:
            my_log("subtitle delay error: {}".format(e))
        self._pl_showOSD(True)

    def _playerMenu(self):
        """[menu-panel] Menu: Picture | Timer and record | Settings."""
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        from .plugin_player_panel import NovaMenuPanel
        self._pl_hideOSD()
        self._menu_panel = self.session.openWithCallback(
            self._onMenuPanel, NovaMenuPanel, self._menuPictureItems(), self._menuTimerItems(),
            self._menuSettingsItems(), live_cb=self._menuLive)

    _SLEEP_STEPS = (0, 30, 60, 90, 120)
    _SKIP_STEPS = (30, 45, 60, 75, 90, 120, 150, 180)   # [2026-11-04] same steps as Settings > Skip Intro

    def _picExtras(self):
        try:
            from . import novaplay_picture
            return novaplay_picture.available()
        except Exception as e:
            my_log("picture modes: {}".format(e))
            return []

    def _menuPictureItems(self):
        """[2026-10-31] Picture tab: Preset, then one ◀▶ row per setting the box
        has (brightness, contrast, colour, hue, sharpness, noise reduction,
        dynamic contrast; OK puts that one back to normal), then Reset all.
        _pic_pep_rows: ("preset",) / ("pep", key) / ("raw", key) / None."""
        rows = []
        self._pic_pep_rows = []
        try:
            from . import novaplay_picture as NP
            peps = NP.pep_available()
            # [2026-11-04] Noise reduction / Dynamic contrast removed from the
            # menu (no visible difference on these streams)
            raws = []
            if peps:
                pi = str(_get_config("pep_preset", "") or "")
                if pi.isdigit() and int(pi) < len(NP.PRESETS):
                    name = NP.PRESETS[int(pi)][0]
                elif all(NP.pep_get(k) == NP.pep_default(k) for k, _l in peps) and \
                        not any(NP.raw_get(k) for k in raws):
                    name = NP.PRESETS[0][0]
                else:
                    name = u"Custom"
                rows.append((u"Preset", False, True, {"adj": True, "tags": [u"\u25c0 {} \u25b6".format(name)]}))
                self._pic_pep_rows.append(("preset",))
            for key, lbl in peps:
                rows.append((lbl, False, True, {"adj": True,
                             "tags": [u"\u25c0 {}% \u25b6".format(NP.pep_percent(key))]}))
                self._pic_pep_rows.append(("pep", key))
            for key in raws:
                rows.append((NP.RAW[key][2], False, True, {"adj": True,
                             "tags": [u"\u25c0 {} \u25b6".format(NP.LEVELS[NP.raw_get(key)])]}))
                self._pic_pep_rows.append(("raw", key))
            if peps or raws:
                rows.append((u"Reset all (normal)", False, True))
                self._pic_pep_rows.append(None)
        except Exception as e:
            my_log("picture pep: {}".format(e))
        if not rows:
            rows = [(u"Not supported by this box", False)]
        return rows

    def _applyPep(self, j, d=0):
        """d: +1 / -1 one step, 0 back to normal (this row, or all on Reset)"""
        from . import novaplay_picture as NP
        row = self._pic_pep_rows[j]
        if row is None:
            NP.apply_preset(0)
            for k, _l in NP.pep_available():
                _set_config("pep_" + k, "")
            for k in NP.raw_available():
                _set_config("pep_" + k, "")
            _set_config("pep_preset", "0")
            return u"Picture: normal"
        if row[0] == "preset":
            pi = str(_get_config("pep_preset", "") or "")
            cur = int(pi) if pi.isdigit() else 0
            new = 0 if not d else max(0, min(len(NP.PRESETS) - 1, cur + d))
            NP.apply_preset(new)
            for k, _l in NP.pep_available():
                v = NP.pep_get(k)
                _set_config("pep_" + k, "" if v == NP.pep_default(k) else str(v))
            for k in NP.raw_available():
                v = NP.raw_get(k)
                _set_config("pep_" + k, "" if not v else str(v))
            _set_config("pep_preset", str(new))
            return u"Picture: {}".format(NP.PRESETS[new][0])
        _set_config("pep_preset", "")                     # changed by hand -> Custom
        if row[0] == "raw":
            key = row[1]
            idx = max(0, min(len(NP.LEVELS) - 1, NP.raw_get(key) + d)) if d else 0
            ok = NP.raw_set(key, idx)
            if ok:
                _set_config("pep_" + key, "" if not idx else str(idx))
            lbl = NP.RAW[key][2]
            return (u"{}: {}".format(lbl, NP.LEVELS[idx]) if ok
                    else u"{}: not supported by this box".format(lbl))
        key = row[1]
        lvl = NP.pep_get(key) + d * NP.PEP_STEP if d else NP.pep_default(key)
        ok = NP.pep_set(key, lvl)
        if ok:
            _set_config("pep_" + key, "" if NP.pep_get(key) == NP.pep_default(key) else str(NP.pep_get(key)))
        lbl = dict(NP.PEP).get(key, key)
        return (u"{}: {}%".format(lbl, NP.pep_percent(key)) if ok
                else u"{}: not supported by this box".format(lbl))

    def _reapplySavedPep(self):
        """Picture values picked in an earlier film (empty = normal)."""
        try:
            from . import novaplay_picture as NP
            for key, _l in NP.pep_available():
                v = (_get_config("pep_" + key, "") or "").strip()
                if v.isdigit() and int(v) != NP.pep_default(key):
                    NP.pep_set(key, int(v))
            # [2026-11-04] those two are gone from the menu: switched off once
            for key in NP.raw_available():
                v = (_get_config("pep_" + key, "") or "").strip()
                if (v.isdigit() and int(v)) or NP.raw_get(key):     # (a preset could have set it)
                    NP.raw_set(key, 0)
                    _set_config("pep_" + key, "")
        except Exception as e:
            my_log("picture pep reapply: {}".format(e))

    def _applyPictureExtra(self, j):
        """Box display modes (letterbox / pan & scan / stretch / zoom) from
        novaplay_picture -> status text."""
        from . import novaplay_picture
        label, kind, value = self._pic_extra_list[j]
        self._aspect_idx = 0
        self._applyAspectMode()            # bars off, system aspect back
        ok = novaplay_picture.apply(kind, value)
        self._pic_extra = j if ok else None
        my_log("picture: {} ({} {}) -> {}".format(label, kind, value, "ok" if ok else "refused"))
        return u"Picture: {}".format(label) if ok else u"Picture: {} — not supported by this box".format(label)

    def _menuTimerItems(self):
        """[2026-10-31] Timer · Rec: Sleep (◀▶ Off/30/60/90/120), Record, Chapters"""
        m = self._sleep_minutes or 0
        rows = [(u"Sleep", bool(m), True, {"adj": True,
                 "tags": [u"\u25c0 {} \u25b6".format(u"Off" if not m else u"{} min".format(m))]})]
        rec_on = (getattr(self, "_record_task", None) is not None
                  and self._record_task.status == "downloading")
        rows.append((u"\u25a0 Stop recording" if rec_on else u"\u25cf Record stream", rec_on))
        rows.append((u"Chapters", False))
        return rows

    def _skipSecs(self):
        try:
            return int(_get_config("skip_intro_secs", "90") or 90)
        except Exception:
            return 90

    def _menuSettingsItems(self):
        """[2026-10-31] Settings: next-episode prompt, Skip intro length (◀▶)
        and Skip intro now together, Help, Self-test"""
        # [2026-11-04] skip intro length + next-episode prompt moved to BLUE >
        # Playback settings
        skip = self._skipSecs()
        return [(u"Skip intro now  +{} s".format(skip), False),
                (u"Help", False)]       # [2026-10-31] Self-test left the MENU

    @staticmethod
    def _stepIn(steps, cur, d, default):
        """next value of a ◀▶ row; d=0 -> default"""
        if not d:
            return default
        i = steps.index(cur) if cur in steps else steps.index(default)
        return steps[max(0, min(len(steps) - 1, i + d))]

    def _menuLive(self, col, idx, d=0):
        msg = u""
        if col == "picture":
            if idx < len(getattr(self, "_pic_pep_rows", []) or []):
                msg = self._applyPep(idx, d)
                try:
                    self["status"].setText(msg)
                except Exception:
                    pass
        elif col == "timer" and idx == 0:
            m = self._stepIn(self._SLEEP_STEPS, self._sleep_minutes or 0, d, 0)
            self._pl_sleepPicked((u"", m))
            msg = u"Sleep: {}".format(self._sleepLabel())
        p = getattr(self, "_menu_panel", None)
        if p is not None:
            builders = {"picture": self._menuPictureItems, "timer": self._menuTimerItems,
                        "settings": self._menuSettingsItems}
            if col in builders:
                p.updateColumn(col, builders[col]())
        return msg

    def _onMenuPanel(self, res):
        self._menu_panel = None
        if not res:
            return
        col, idx = res
        try:
            if col == "timer" and idx == 1:
                rec_on = (getattr(self, "_record_task", None) is not None
                          and self._record_task.status == "downloading")
                if rec_on:
                    self._pl_stopRecording()
                else:
                    self._pl_recordCurrentStream()
            elif col == "timer" and idx == 2:
                self._showChapters()
            elif col == "settings":
                if idx == 0:
                    self._pl_skipIntro()
                elif idx == 1:
                    self._showHelp()
        except Exception as e:
            my_log("menu panel pick error: {}".format(e))

    def _onPlayerMenuChoice(self, choice):
        if not choice:
            return
        action = choice[1] if isinstance(choice, (tuple, list)) and len(choice) > 1 else choice
        if action == "subs":
            self._subsPanel()
        elif action == "audio":
            self._pl_audioSelect()
        elif action == "info":
            self._pl_streamInfo()
        elif action == "chapters":
            self._showChapters()
        elif action == "selftest":
            self._runSelfTest()
        elif action == "help":
            self._showHelp()
        elif action == "nxtep":
            self._next_prompt_enabled = not self._next_prompt_enabled
            _set_config("next_episode_prompt", "true" if self._next_prompt_enabled else "false")
            self["status"].setText("Next-episode: %s" % ("ON" if self._next_prompt_enabled else "OFF"))
            self._pl_showOSD(True)
        elif action == "sleep":
            self._pl_sleepMenu()
        elif action == "record":
            self._pl_recordCurrentStream()
        elif action == "stoprec":
            self._pl_stopRecording()

    # ── [player-ux] chapters / jump points ──────────────────────────────
    # Streams here have no real chapter markers (remote URLs, not local
    # files we could ffprobe), so this mirrors the WGFileManager player's
    # fallback path directly: synthetic quarter-marks across the known
    # duration, plus the saved resume point as an extra entry when one
    # exists. Reuses _pl_seek()'s existing OSD-flash + tracker bookkeeping
    # by converting the chosen absolute target into a relative delta.
    @staticmethod
    def _fmtChapterTime(secs):
        secs = max(0, int(secs))
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return u"{:d}:{:02d}:{:02d}".format(h, m, s) if h else u"{:d}:{:02d}".format(m, s)

    def _showChapters(self):
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        total = self._total_secs
        if not total or total <= 60:
            self["status"].setText(u"Duration not known yet — no jump points")
            self._pl_showOSD(True)
            return
        marks = [
            (u"Start", 0),
            (u"25%", total * 0.25),
            (u"Halfway", total * 0.5),
            (u"75%", total * 0.75),
            (u"End", max(0, total - 10)),
        ]
        items = [(u"{}   {}".format(name, self._fmtChapterTime(t)), int(t))
                 for name, t in marks]
        try:
            saved = _get_saved_position(self._item_url) if self._item_url else 0
        except Exception:
            saved = 0
        if saved and saved > 30:
            items.append((u"↺ Resume point   {}".format(
                self._fmtChapterTime(saved)), int(saved)))
        self.session.openWithCallback(self._onChapterChosen, ChoiceBox,
                                      title=u"Jump to", list=items)

    def _onChapterChosen(self, choice):
        if not choice:
            return
        target = choice[1] if isinstance(choice, (tuple, list)) and len(choice) > 1 else choice
        try:
            target = int(target)
        except Exception:
            return
        try:
            cur = int(self._paused_elapsed if self._paused else current_play_secs())
        except Exception:
            cur = 0
        self._pl_seek(target - cur)

    # ── [player-ux] on-device help / keymap reference ───────────────────
    def _showHelp(self):
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        lines = [
            u"Player Controls",
            u"",
            u"Playback",
            u"OK            Play / Pause",
            u"STOP          Exit straight to TV",
            u"EXIT/CANCEL   Exit — near the end: next / mark / save / cancel",
            u"",
            u"Seeking",
            u"LEFT / RIGHT     Seek (hold to speed up 10s→30s→60s)",
            u"UP / DOWN        Seek 60 seconds",
            u"FF / REW         Seek (same hold speed-up)",
            u"0-9              Jump to 0%/10%/20%/…/90% of the runtime (0 = start)",
            u"",
            u"Tracks & Subtitles",
            u"BLUE / SUBTITLE  Settings panel: Server · Quality · Speed · Audio · Subtitles",
            u"YELLOW           Subtitles on / off",
            u"AUDIO            Audio track selection",
            u"",
            u"Quality & Info",
            u"RED           Next server",
            u"GREEN         Episode: skip intro (10 min) / chapters / next ep. -- Movie: skip (5 min) / chapters",
            u"INFO          Stream info",
            u"",
            u"MENU          Picture (brightness / contrast / colour) · Sleep timer & recording ·",
            u"              Settings (next episode, skip intro, help) · Chapters under Timer",
        ]
        self.session.open(MessageBox, u"\n".join(lines), MessageBox.TYPE_INFO)

    # ── [player-ux] non-destructive self-test ────────────────────────────
    # Mostly read-only queries (service/seek reachability, track counts,
    # subtitle state, proxy stats, OSD widget attachment). The only real
    # actions are a pause/unpause round-trip and a tiny +5s/-5s seek
    # round-trip, both of which restore the original state -- same
    # convention as the WGFileManager player's self-test, scaled down
    # since this is a live/remote stream rather than a local file.
    def _selfTestAudioQuery(self):
        svc = self.session.nav.getCurrentService()
        if not svc:
            return False
        tracks = svc.audioTracks()
        return bool(tracks and tracks.getNumberOfTracks() >= 1)

    def _selfTestSubtitleQuery(self):
        state = get_subtitle_state()
        if self._item_url:
            has_subtitle_for(self._item_url)
        return isinstance(state, dict)

    def _selfTestPauseRoundtrip(self):
        was_paused = self._paused
        self._pl_togglePause()
        self._pl_togglePause()
        return self._paused == was_paused

    def _selfTestSeekRoundtrip(self):
        if not self._total_secs or self._total_secs < 20:
            return True
        before = self._paused_elapsed if self._paused else current_play_secs()
        self._pl_seek(5)
        self._pl_seek(-5)
        after = self._paused_elapsed if self._paused else current_play_secs()
        return abs(after - before) <= 3

    def _selfTestOSDRoundtrip(self):
        was_visible = self._osd_visible
        self._pl_showOSD(True)
        shown = self._osd_visible
        if not was_visible:
            self._pl_hideOSD()
        return shown is True

    def _runSelfTest(self):
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        results = []

        def t(name, fn):
            try:
                r = fn()
                results.append((name, "OK" if r is not False else "returned False"))
            except Exception as e:
                results.append((name, "FAIL: {}".format(e)))

        t("service-reachable", lambda: self.session.nav.getCurrentService() is not None)
        t("seek-object", lambda: bool(self.session.nav.getCurrentService() and
                                       self.session.nav.getCurrentService().seek()))
        t("duration-known", lambda: self._total_secs > 0)
        t("audio-tracks-query", self._selfTestAudioQuery)
        t("subtitle-state-query", self._selfTestSubtitleQuery)
        t("proxy-stats", lambda: bool(novaplay_proxy.get_stats()))
        t("osd-widgets-attached", lambda: all(
            self[n].instance is not None for n in self._OSD_WIDGETS))
        t("pause-roundtrip", self._selfTestPauseRoundtrip)
        t("seek-roundtrip", self._selfTestSeekRoundtrip)
        t("osd-show-hide", self._selfTestOSDRoundtrip)

        ok = sum(1 for _, r in results if r == "OK")
        for name, r in results:
            my_log("[SelfTest] {:22s} {}".format(name, r))
        self["status"].setText(u"Self-test: {}/{}".format(ok, len(results)))
        self._pl_showOSD(True)
        # Bilingual header, same precedent as _pl_streamInfo: an Arabic
        # header over technical/diagnostic lines left in English, since
        # the check names themselves (service-reachable, osd-widgets-
        # attached, …) are debug labels, not end-user copy.
        lines = [u"Self-test: {}/{} passed".format(ok, len(results)), u""]
        for name, r in results:
            mark = u"✓" if r == "OK" else u"✗"
            lines.append(u"{} {}".format(mark, name) if r == "OK"
                         else u"{} {} — {}".format(mark, name, r))
        self.session.open(MessageBox, u"\n".join(lines), MessageBox.TYPE_INFO, timeout=15)

    def _aspectLabel(self):
        try:
            idx = getattr(self, "_aspect_idx", 0)
            n_fake = len(self._ASPECT_MODES)
            if idx < n_fake:
                return self._ASPECT_MODES[idx][0]
            return self._AV_PROBE_MODES[idx - n_fake][0]
        except Exception:
            return "Full"

    def _pl_cycleAspect(self):
        if getattr(self, "_studioOverlayActive", False):
            return
        if getattr(self, "_autonext_active", False):
            return
        total = len(self._ASPECT_MODES) + len(self._AV_PROBE_MODES)
        self._aspect_idx = (getattr(self, "_aspect_idx", 0) + 1) % total
        self._applyAspectMode()

    def _applyAspectMode(self):
        idx = getattr(self, "_aspect_idx", 0)
        n_fake = len(self._ASPECT_MODES)
        if idx < n_fake:
            self._restoreSystemAspect()
            label, bar = self._ASPECT_MODES[idx]
            # [player-anim] slide the bars from 0 → bar width over 150 ms
            self._aspect_anim_from = 0
            self._aspect_anim_to = int(bar)
            self._aspect_anim_p = 0.0
            try:
                self["aspect_bar_l"].show()
                self["aspect_bar_r"].show()
                self._aspect_anim_timer.start(20, False)
            except Exception as e:
                my_log("aspect slide start failed: {}".format(e))
                try:
                    if bar:
                        self["aspect_bar_l"].instance.resize(eSize(bar, 1080))
                        self["aspect_bar_l"].instance.move(ePoint(0, 0))
                        self["aspect_bar_r"].instance.resize(eSize(bar, 1080))
                        self["aspect_bar_r"].instance.move(ePoint(1920 - bar, 0))
                        self["aspect_bar_l"].show()
                        self["aspect_bar_r"].show()
                    else:
                        self["aspect_bar_l"].hide()
                        self["aspect_bar_r"].hide()
                except Exception:
                    pass
            self["status"].setText("Aspect: %s" % label)
        else:
            try:
                self["aspect_bar_l"].hide()
                self["aspect_bar_r"].hide()
            except Exception:
                pass
            plabel, av_value = self._AV_PROBE_MODES[idx - n_fake]
            ok = self._setSystemAspect(av_value)
            self["status"].setText("Aspect PROBE: %s → %s" % (
                plabel, "applied" if ok else "eAVSwitch FAILED"))
        self._pl_showOSD(True)

    def _setSystemAspect(self, value):
        if eAVSwitch is None:
            return False
        try:
            eAVSwitch.getInstance().setAspectRatio(int(value))
            self._av_aspect_dirty = True
            my_log("aspect: eAVSwitch.setAspectRatio({})".format(value))
            return True
        except Exception as e:
            my_log("aspect: eAVSwitch error: {}".format(e))
            return False

    def _restoreSystemAspect(self):
        try:
            from . import novaplay_picture
            novaplay_picture.restore()
        except Exception:
            pass
        if not getattr(self, "_av_aspect_dirty", False):
            return
        saved = getattr(self, "_saved_av_aspect", None)
        if saved is None:
            return
        try:
            if eAVSwitch is not None:
                eAVSwitch.getInstance().setAspectRatio(int(saved))
            my_log("aspect: system aspect restored to {}".format(saved))
        except Exception as e:
            my_log("aspect: restore error: {}".format(e))
        self._av_aspect_dirty = False
