# -*- coding: utf-8 -*-
"""NovaPlay player -- remote keys: OK / EXIT, arrows, pause, seeks, restart, exit and stop;
green key, skip intro, automatic subtitle start.

Part of NovaPlaySimplePlayer (plugin_screen_player.py), split out
2026-10-23 without changing behaviour. Methods use the player's widgets
and state through self; module-level helpers come from player_base.
"""
from .player_base import *  # noqa: F401,F403


class PlayerControls(object):
    # ─── Studio tick ─────────────────────────────────────────────────────
    def _studioNowMs(self):
        try:
            svc = self.session.nav.getCurrentService()
            seek = svc and svc.seek()
            if seek:
                r = seek.getPlayPosition()
                if r and r[0] == 0 and r[1] > 0:
                    return int(r[1] // 90)
        except Exception:
            pass
        return current_play_ms()

    def _pl_studioTick(self):
        try:
            from .novaplay_substudio import STUDIO
            if STUDIO.is_attached() or STUDIO.sample_on:
                STUDIO.update(self._studioNowMs())
        except Exception:
            pass

    # ── [green] Skip intro early on, Next episode near the end ───────────
    def _isEpisode(self):
        """a series episode (S01E05 / "الحلقة 5" in the title, or a next
        episode is known) -- movies have no separate intro to skip"""
        if self._next_episode:
            return True
        t = self._raw_title or ""
        return bool(re.search(r"\bS\d{1,2}\s*E\d{1,3}\b", t, re.I)
                    or re.search(u"(?:\u0627\u0644\u062d\u0644\u0642\u0629|\u062d\u0644\u0642\u0629)\\s*[\\d\u0660-\u0669]+", t))

    def _greenPhase(self):
        """[smart green 2026-10-28] episode: Skip intro (first 10 min) ->
        Chapters -> Next episode (near the end); movie: Skip +Ns (first
        5 min: logos, opening titles) -> Chapters"""
        try:
            pos = self._paused_elapsed if self._paused else current_play_secs()
        except Exception:
            pos = 0
        total = int(self._total_secs or 0)
        if (self._next_episode and self._on_next and total > 0
                and total - pos <= max(300, int(total * 0.10))):
            return "next"
        if self._isEpisode():
            if pos < 600:
                return "intro"
        elif pos < 300:
            # [2026-10-28] movie: studio logos / opening titles -> plain skip
            return "skip"
        return "chapters"

    def _greenLabel(self):
        ph = self._greenPhase()
        if ph == "next":
            return u"Next episode ⏭"
        if ph == "intro":
            return u"Skip intro"
        if ph == "skip":
            try:
                secs = max(10, min(600, int(_get_config("skip_intro_secs", "90") or 90)))
            except Exception:
                secs = 90
            return u"Skip +{}s".format(secs)
        return u"Chapters"

    def _pl_greenKey(self):
        if getattr(self, "_studioOverlayActive", False):
            return
        if getattr(self, "_autonext_active", False):
            nxt = getattr(self, "_autonext_nxt", None) or self._next_episode
            if nxt:
                self._hideAutoNextCard()
                self._pl_nextAnswer(True, nxt)
            return
        ph = self._greenPhase()
        if ph == "next":
            my_log("green: next episode")
            self._pl_nextAnswer(True, self._next_episode)
            return
        if ph == "chapters":
            self._showChapters()
            return
        self._pl_skipIntro()

    def _pl_skipIntro(self):
        if getattr(self, "_studioOverlayActive", False) or getattr(self, "_autonext_active", False):
            return
        try:
            secs = int(_get_config("skip_intro_secs", "90") or 90)
        except Exception:
            secs = 90
        secs = max(10, min(600, secs))
        my_log("skip intro: +{}s".format(secs))
        self._pl_seek(+secs)

    def _autoSubNotify(self, msg):
        try:
            self["status"].setText(msg)
            self._pl_showOSD(True)
            self._hide_timer.start(3000, True)
        except Exception:
            pass

    # ─── key routing (studio → autonext → normal) ───────────────────────
    def _pl_onOkKey(self):
        if getattr(self, "_studioOverlayActive", False):
            self._studioOk()
            return
        if getattr(self, "_autonext_active", False):
            self._hideAutoNextCard()
            self._pl_nextAnswer(True, self._autonext_nxt)
            return
        self._pl_togglePause()

    def _pl_onCancelKey(self):
        if getattr(self, "_studioOverlayActive", False):
            self._hideStudioOverlay()
            self._pl_panelMenu(start="subs")   # [2026-11-04] back to the Subtitles tab
            return
        if getattr(self, "_autonext_active", False):
            self._hideAutoNextCard()
            self._pl_onExit(clear_position=True)
            return
        if getattr(self, "_is_preview", False):
            # [detail-trailer] skip the near-end mark/save/next prompt
            # entirely for a trailer -- there's nothing to mark, save or
            # queue, so exit should just exit.
            self._pl_onExit()
            return
        # [player-ux] near-end exit prompt
        total = self._total_secs
        try:
            elapsed = (self._paused_elapsed if self._paused
                       else current_play_secs())
        except Exception:
            elapsed = 0
        near_end = (total > 0 and elapsed > 0
                    and float(elapsed) / float(total) >= 0.90)

        if near_end or (self._next_episode and self._next_prompt_enabled
                        and total > 0 and elapsed > 0
                        and float(elapsed) / float(total) >= 0.80):
            items = []
            if self._next_episode:
                items.append((u"▶ Next episode", "next"))
            items.append((u"✓ Mark as watched and exit", "mark"))
            items.append((u"↵ Save position and exit", "save"))
            items.append((u"✕ Cancel", "cancel"))
            self.session.openWithCallback(
                self._onExitChoice, ChoiceBox,
                title=u"Near the end — what now?",
                list=items)
            return
        self._pl_onExit()

    def _onExitChoice(self, choice):
        if not choice:
            return
        action = choice[1] if isinstance(choice, (tuple, list)) and len(choice) > 1 else choice
        if action == "next":
            try:
                from .plugin_watched import mark_watched
                if self._item_url:
                    mark_watched(self._item_url)
            except Exception:
                pass
            self._hideAutoNextCard()
            self._pl_nextAnswer(True, self._next_episode)
        elif action == "mark":
            try:
                from .plugin_watched import mark_watched
                if self._item_url:
                    mark_watched(self._item_url)
            except Exception:
                pass
            self._pl_onExit(clear_position=True)
        elif action == "save":
            self._pl_onExit(clear_position=False)
        elif action == "cancel":
            return

    def _pl_studioDedup(self, direction):
        try:
            now = time.time()
        except Exception:
            return False
        if direction == getattr(self, "_studioNavDir", 0) and \
                (now - getattr(self, "_studioNavT", 0.0)) < 0.15:
            return True
        self._studioNavDir = direction
        self._studioNavT = now
        return False

    def _pl_studioAdjustVKey(self, direction):
        if not getattr(self, "_studioOverlayActive", False):
            return
        if not (0 <= self._studioIdx < len(self._studioItems)):
            return
        key = self._studioItems[self._studioIdx][2]
        if key in ("font", "presets", "pickline", "reset", "remove"):
            return
        self._studioAdjust(direction)

    # ── [player-ux] hold-to-accelerate seek ────────────────────────────
    def _stepForHold(self, direction):
        now = time.time()
        if direction != getattr(self, "_hold_dir", 0) or \
                (now - getattr(self, "_hold_last_t", 0.0)) > 1.2:
            self._hold_dir = direction
            self._hold_count = 1
        else:
            self._hold_count = min(self._hold_count + 1, 30)
        self._hold_last_t = now
        n = self._hold_count
        if n <= 1:
            return 10
        if n <= 4:
            return 30
        return 60

    def _pl_navLeftKey(self):
        if self._studioOverlayActive:
            self._studioMove(-1)
            return
        if not self._pl_studioDedup(-1):
            self._pl_seek(-self._stepForHold(-1))

    def _pl_navRightKey(self):
        if self._studioOverlayActive:
            self._studioMove(+1)
            return
        if not self._pl_studioDedup(+1):
            self._pl_seek(+self._stepForHold(+1))

    def _pl_navUpKey(self):
        if self._studioOverlayActive:
            if not self._pl_studioDedup(-2):
                self._pl_studioAdjustVKey(+1)
            return
        if not self._pl_studioDedup(-2):
            self._pl_seek(-60)

    def _pl_navDownKey(self):
        if self._studioOverlayActive:
            if not self._pl_studioDedup(+2):
                self._pl_studioAdjustVKey(-1)
            return
        if not self._pl_studioDedup(+2):
            self._pl_seek(+60)

    def _pl_navSeekFwdKey(self):
        if getattr(self, "_studioOverlayActive", False):
            return      # ◀ ▶ already arrive as left/right; acting here too skipped a card
        if getattr(self, "_autonext_active", False):
            return
        if not self._pl_studioDedup(+1):
            self._pl_seek(+self._stepForHold(+1))

    def _pl_navSeekBackKey(self):
        if getattr(self, "_studioOverlayActive", False):
            return      # ◀ ▶ already arrive as left/right; acting here too skipped a card
        if getattr(self, "_autonext_active", False):
            return
        if not self._pl_studioDedup(-1):
            self._pl_seek(-self._stepForHold(-1))

    def _pausePaint(self):
        """[2026-11-04] the big pause sign is gone (asked for): the bar's own
        pause mark and "Paused" stay"""
        try:
            self["pauseBig"].hide()
        except Exception:
            pass

    def _pl_togglePause(self):
        if getattr(self, "_speed", 1) != 1:
            # first press while fast/slow: back to normal speed
            self._cancelSpeed()
            self["status"].setText(u"Playing")
            self._pl_showOSD(True)
            return
        try:
            svc = self.session.nav.getCurrentService()
            if not svc:
                self._pl_showOSD(True); return
            p = svc.pause()
            if not p:
                self._pl_showOSD(True); return
            if self._paused:
                p.unpause()
                self._paused = False
                with novaplay_tracker._GLOBAL_POS_LOCK:
                    novaplay_tracker._GLOBAL_IS_PAUSED = False
                    novaplay_tracker._GLOBAL_PLAY_START_POS = self._paused_elapsed
                    novaplay_tracker._GLOBAL_PLAY_START_WALL = time.time()
                self["status"].setText(u"Playing")
            else:
                with novaplay_tracker._GLOBAL_POS_LOCK:
                    wall = novaplay_tracker._GLOBAL_PLAY_START_WALL
                    base = novaplay_tracker._GLOBAL_PLAY_START_POS
                    if wall:
                        elapsed = int((time.time() - wall) + base)
                    else:
                        elapsed = 0
                    self._paused_elapsed = max(0, elapsed)
                p.pause()
                self._paused = True
                with novaplay_tracker._GLOBAL_POS_LOCK:
                    novaplay_tracker._GLOBAL_PLAY_START_POS = self._paused_elapsed
                    novaplay_tracker._GLOBAL_IS_PAUSED = True
                self["status"].setText(u"Paused")
                self._pl_updateOSD()      # the ❚❚ sign in the panel at once
            self._pausePaint()           # [2026-10-30] the big pause sign
            # [osd-ui] paused: stays on screen; playing again: slides away at once
            if self._paused:
                self._pl_showOSD(False)
                try:
                    self._hide_timer.stop()
                except Exception:
                    pass
            else:
                self._pl_hideOSD()
        except Exception as e:
            my_log("togglePause error: {}".format(e))
            self._pl_showOSD(True)

    def _pl_seek(self, delta_secs):
        self._cancelSpeed()
        try:
            self._last_seek_step = abs(int(delta_secs)) or self._last_seek_step  # [POLISH v1]
        except Exception:
            pass
        try:
            svc = self.session.nav.getCurrentService()
            if not svc: return
            sk = svc.seek()
            if not sk: return
            with novaplay_tracker._GLOBAL_POS_LOCK:
                _wall = novaplay_tracker._GLOBAL_PLAY_START_WALL
                _base = novaplay_tracker._GLOBAL_PLAY_START_POS
                if _wall:
                    elapsed = time.time() - _wall
                else:
                    elapsed = 0
                current_est = int(_base + elapsed)
                target = max(0, current_est + int(delta_secs))
                _tot = self._total_secs
                if _tot > 0:
                    target = min(target, _tot - 3)
                target = max(0, target)
                sk.seekTo(target * 90000)
                novaplay_tracker._GLOBAL_LAST_SEEK_TARGET = target
                novaplay_tracker._GLOBAL_PLAY_START_POS = max(0, target - 2)
                novaplay_tracker._GLOBAL_PLAY_START_WALL = time.time()
                if self._paused:
                    self._paused_elapsed = target
            my_log("seek: delta={}s → target={}s".format(int(delta_secs), target))
            _th = target // 3600; _tm = (target % 3600) // 60; _ts = target % 60
            _arr = u"➡" if delta_secs > 0 else u"⬅"
            self["status"].setText(u"{} {:02d}:{:02d}:{:02d}".format(_arr, _th, _tm, _ts))
            self._showSeekFlash(1 if delta_secs > 0 else -1, delta_secs, target)
            self._pl_showOSD(True)
            self._showSeekBubble(target)
            self._hide_timer.start(2500, True)
        except Exception as e:
            my_log("seek error: {}".format(e))

    def _pl_seekPct(self, pct):
        if getattr(self, "_studioOverlayActive", False):
            # [studio-ui] 1-4 pick a tab while the studio is open
            if pct in (10, 20, 30, 40):          # [2026-10-31] 4 tabs: Style / Box / Position / Sync
                self._studioGroup(pct // 10 - 1)
            return
        self._cancelSpeed()
        try:
            now = time.time()
            if pct == getattr(self, "_seekPctLastPct", None) and \
                    (now - getattr(self, "_seekPctLastT", 0.0)) < 0.30:
                return
            self._seekPctLastPct = pct
            self._seekPctLastT = now

            total = self._total_secs
            if not total:
                try:
                    svc = self.session.nav.getCurrentService()
                    seek = svc and svc.seek()
                    if seek:
                        r = seek.getLength()
                        if r and r[0] == 0 and r[1] > 0:
                            total = r[1] // 90000
                            self._total_secs = total
                except Exception:
                    pass
            cur = current_play_secs()
            my_log("seekPct: key={}%, total={}s, current={}s".format(pct, total, cur))
            if not total:
                self["status"].setText("Duration not known yet…")
                self._pl_showOSD(True)
                return
            self._pl_seek(int(total * pct / 100) - cur)
        except Exception as e:
            my_log("seekPct error: {}".format(e))

    def _pl_onRestart(self):
        if getattr(self, "_studioOverlayActive", False):
            return
        if getattr(self, "_autonext_active", False):
            return
        my_log("Restart+Resume requested by green button")
        if self._item_url:
            try:
                if self._paused:
                    secs = self._paused_elapsed
                else:
                    secs = current_play_secs()
                if secs > 30:
                    _save_position(self._item_url, secs, force=True)
                    self._resume_pos = secs
                    my_log("Restart: saved pos={}s, will re-seek after restart".format(secs))
            except Exception as e:
                my_log("Restart pos-save error: {}".format(e))
        try:
            self._seek_timer.stop()
            self._seek_verify_timer.stop()
        except: pass
        self._play_confirmed = False
        self._seek_retry_count = 0
        try:
            self.session.nav.stopService()
        except: pass
        self._candidate_idx = -1
        self["status"].setText(u"Restarting + resuming from {}:{:02d}...".format(
            self._resume_pos // 60, self._resume_pos % 60) if self._resume_pos > 30 else u"Restarting...")
        self._pl_showOSD(True)
        try:
            if getattr(self, "_restart_timer", None):
                self._restart_timer.stop()
        except Exception:
            pass
        self._restart_timer = eTimer()
        self._restart_timer.callback.append(self._pl_playNext)
        self._restart_timer.start(500, True)

    def _pl_onExit(self, clear_position=False):
        try:
            self._hideAutoNextCard()
        except Exception:
            pass
        try:
            self._hideStudioOverlay()
        except Exception:
            pass
        try:
            self._disarmSkipHint()
        except Exception:
            pass
        stop_pos_tracker()
        try:
            self._restoreSystemAspect()
        except Exception:
            pass
        _saved_secs = 0
        try:
            if self._item_url:
                if clear_position:
                    _save_position(self._item_url, 0, force=True)
                    my_log("Exit save: cleared position (EOF)")
                else:
                    if self._paused:
                        secs = self._paused_elapsed
                    else:
                        secs = current_play_secs()
                    _tot = self._total_secs
                    if _tot > 0:
                        secs = min(secs, _tot - 5)
                    secs = max(0, secs)
                    _floor = getattr(novaplay_tracker, "_GLOBAL_SAVE_FLOOR", 0)
                    if 30 < secs < _floor:
                        my_log("Exit save: kept {}s (resume jump failed, at {}s)".format(_floor, int(secs)))
                    elif secs > 30:
                        _save_position(self._item_url, secs, force=True)
                        _saved_secs = int(secs)
                        my_log("Exit save: {}s".format(secs))
                        if _tot > 0:
                            try:
                                from .plugin_state import _save_total_duration
                                _save_total_duration(self._item_url, _tot)
                            except Exception:
                                pass
        except Exception as e:
            my_log("Exit save error: {}".format(e))
        if _saved_secs > 30:
            try:
                _t = _saved_secs // 3600
                _m = (_saved_secs % 3600) // 60
                _s = _saved_secs % 60
                _label = u"✓ Saved at {:02d}:{:02d}:{:02d}".format(_t, _m, _s) \
                    if _t else u"✓ Saved at {:02d}:{:02d}".format(_m, _s)
                self["seekFlash"].setText(_label)
                self["seekFlash"].show()
            except Exception:
                pass
        try:                         # [2026-10-31] free the player's reads first
            from . import novaplay_proxy
            novaplay_proxy.abort_open_streams()
        except Exception:
            pass
        _t_stop = time.time()
        try:
            self.session.nav.stopService()
        except: pass
        my_log("player exit: stopService took {:.1f}s".format(time.time() - _t_stop))
        try:
            from .novaplay_substudio import STUDIO
            STUDIO.unbind()
        except Exception:
            pass
        if not getattr(self, "_skip_restore", False):
            _restore_previous_service(self.session, self.previous_service)
        self.close()

    def _pl_stop(self):
        self._closed_flag = True
        try:
            my_log("playback end")
            set_play_id("")
        except Exception:
            pass
        _tr_call("resume_later")
        self._pl_hideOSD()
        try:
            self._restoreSystemAspect()
        except Exception:
            pass
        self._autosub_gen = getattr(self, "_autosub_gen", 0) + 1
        for t in ("_seek_timer","_seek_verify_timer","_retry_timer","_hide_timer",
                  "_osd_update_timer","_force_confirmation_timer","_restart_timer",
                  "_sleep_timer","_autonext_timer",
                  "_studioTimer","_rec_blink_timer",
                  "_stall_timer","_stall_kick_timer",
                  "_osd_slide_timer","_autonext_slide_timer",
                  "_seek_flash_timer","_quality_wipe_timer",
                  "_skip_hint_timer",
                  "_aspect_anim_timer","_studio_slide_timer",
                  "_sync_toast_timer"):
            try:
                timer = getattr(self, t, None)
                if timer: timer.stop()
            except Exception: pass

    def _pl_doSeek(self):
        if not self._resume_pos or self._resume_pos <= 30:
            my_log("Seek skipped: resume_pos={}".format(self._resume_pos))
            return
        try:
            svc = self.session.nav.getCurrentService()
            seek = svc and svc.seek()
            if not seek:
                self._seek_retry_count += 1
                if self._seek_retry_count <= 3:
                    my_log("doSeek: no seek interface, retry {}/3 in 4s".format(self._seek_retry_count))
                    self._seek_timer.start(4000, True)
                else:
                    my_log("doSeek: giving up after 3 retries")
                return
            seek.seekTo(self._resume_pos * 90000)
            my_log("Resume seekTo: {}s (attempt {})".format(self._resume_pos, self._seek_retry_count + 1))
            self._total_secs = 0
            self._seek_verify_timer.start(4000, True)
            if self._osd_visible:
                self._pl_updateOSD()
        except Exception as e:
            my_log("doSeek failed: {} — retry {}/3".format(e, self._seek_retry_count))
            self._seek_retry_count += 1
            if self._seek_retry_count <= 3:
                self._seek_timer.start(4000, True)

    def _pl_verifySeek(self):
        if not self._resume_pos or self._resume_pos <= 30: return
        try:
            svc = self.session.nav.getCurrentService()
            seek = svc and svc.seek()
            actual_pos = -1
            if seek:
                try:
                    r = seek.getPlayPosition()
                    if r and r[0] == 0 and r[1] > 0:
                        actual_pos = int(r[1] // 90000)
                except Exception: pass
            if actual_pos >= 0:
                # [2026-10-21] "-60" called 10 s a success for a 68 s target;
                # the tolerance now scales with the target (max 60 s)
                if actual_pos >= max(0, self._resume_pos - min(60, max(10, self._resume_pos // 3))):
                    with novaplay_tracker._GLOBAL_POS_LOCK:
                        novaplay_tracker._GLOBAL_PLAY_START_POS = actual_pos
                        novaplay_tracker._GLOBAL_PLAY_START_WALL = time.time()
                        novaplay_tracker._GLOBAL_LAST_SEEK_TARGET = actual_pos
                    if self._paused:
                        self._paused_elapsed = actual_pos
                    my_log("verifySeek OK via PTS: actual={}s target={}s".format(actual_pos, self._resume_pos))
                else:
                    if seek and self._seek_retry_count < 3:
                        self._seek_retry_count += 1
                        seek.seekTo(self._resume_pos * 90000)
                        my_log("verifySeek double-tap {}/3: actual={}s target={}s".format(self._seek_retry_count, actual_pos, self._resume_pos))
                        self._seek_verify_timer.start(3000, True)
                    else:
                        with novaplay_tracker._GLOBAL_POS_LOCK:
                            novaplay_tracker._GLOBAL_PLAY_START_POS = max(0, int(actual_pos))
                            novaplay_tracker._GLOBAL_PLAY_START_WALL = time.time()
                            novaplay_tracker._GLOBAL_LAST_SEEK_TARGET = int(actual_pos)
                            # keep the saved place: until playback really passes it,
                            # don't overwrite 229 s with 19 s (box 2026-10-21)
                            novaplay_tracker._GLOBAL_SAVE_FLOOR = int(self._resume_pos)
                        my_log("verifySeek giving up — TRUSTING DEMUXER at {}s (target {}s not reached)".format(
                            actual_pos, self._resume_pos))
            else:
                if self._seek_retry_count <= 2:
                    if seek:
                        seek.seekTo(self._resume_pos * 90000)
                    self._seek_retry_count += 1
                    with novaplay_tracker._GLOBAL_POS_LOCK:
                        novaplay_tracker._GLOBAL_PLAY_START_POS = max(0, self._resume_pos - 2)
                        novaplay_tracker._GLOBAL_PLAY_START_WALL = time.time()
                        novaplay_tracker._GLOBAL_LAST_SEEK_TARGET = self._resume_pos
                    if self._paused:
                        self._paused_elapsed = self._resume_pos
                    my_log("verifySeek double-tap {}/3 (no PTS), target={}s".format(self._seek_retry_count, self._resume_pos))
                    self._seek_verify_timer.start(3000, True)
                else:
                    my_log("verifySeek: max retries reached, target={}s".format(self._resume_pos))
        except Exception as e:
            my_log("verifySeek error: {}".format(e))
