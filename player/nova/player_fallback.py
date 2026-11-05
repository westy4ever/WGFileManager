# -*- coding: utf-8 -*-
"""NovaPlay player -- trying the playback methods one after another: stall watchdog, next
candidate, confirmed / failed / EOF / timeout handling.

Part of NovaPlaySimplePlayer (plugin_screen_player.py), split out
2026-10-23 without changing behaviour. Methods use the player's widgets
and state through self; module-level helpers come from player_base.
"""
from .player_base import *  # noqa: F401,F403


class PlayerFallback(object):
    _STALL_TICK_MS = 5000
    _STALL_TICKS = 3
    _STALL_MAX_KICKS = 2

    def _pl_stallWatchdog(self):
        try:
            if not getattr(self, "_play_confirmed", False):
                return
            if self._paused or getattr(self, "_autonext_active", False):
                self._stall_last_pts = -1
                self._stall_count = 0
                return
            if getattr(self, "_stall_recovering", False):
                return
            if getattr(self, "_net_waiting", False) or getattr(self, "_net_checking", False):
                return
            svc = self.session.nav.getCurrentService()
            if not svc:
                return
            seek = svc.seek()
            if not seek:
                return
            r = seek.getPlayPosition()
            if not r or r[0] != 0 or r[1] <= 0:
                return
            pts = r[1]
            last = self._stall_last_pts
            self._stall_last_pts = pts
            if last <= 0:
                return
            advanced = pts - last
            if advanced < 0 or advanced > 30 * 90000:
                self._stall_count = 0
                return
            if advanced >= 90000:
                self._stall_count = 0
                self._stall_fail_count = 0
                return
            self._stall_count += 1
            my_log("Stall watchdog: frozen (count {}/{})".format(
                self._stall_count, self._STALL_TICKS))
            if self._stall_count >= self._STALL_TICKS:
                # [net 2026-10-28] no internet -> wait for it instead of
                # lowering quality / switching servers (player_netwait)
                def _act(pts=pts):
                    if self._lowerQualityOnBuffering(pts):
                        return
                    if self._stall_fail_count >= self._STALL_MAX_KICKS:
                        self._pl_stallSwitchCandidate(pts)
                    else:
                        self._pl_stallRecover(pts)
                self._pl_netStall(pts, _act)
        except Exception as e:
            my_log("stall watchdog error: {}".format(e))

    _LOWER_AFTER = 2            # buffering stops within ...
    _LOWER_WINDOW = 300         # ... seconds -> a lower quality when there is one

    def _lowerQualityOnBuffering(self, frozen_pts):
        """[auto-quality 2026-10-28] YouTube-style: the stream keeps stopping
        to buffer and the server has a lower resolution -> switch to it at the
        same place. True when a switch was started."""
        now = time.time()
        hist = [t for t in getattr(self, "_buffer_stops", []) if now - t < self._LOWER_WINDOW]
        hist.append(now)
        self._buffer_stops = hist
        if len(hist) < self._LOWER_AFTER:
            return False
        try:
            from .plugin_util import quality_key
            res = lambda l: int(quality_key(l)[:-1]) if quality_key(l)[:-1].isdigit() else 0
            dead = getattr(self, "_quality_dead_urls", set())
            cur_url = getattr(self, "_quality_current_url", "")
            vs = [(l, u) for (l, u) in (getattr(self, "_quality_variants", []) or [])
                  if u not in dead and u != cur_url and res(l) > 0]
            if not vs:
                return False
            cur = res(getattr(self, "_quality_current_label", ""))
            if cur <= 0:
                # playing the "auto" link: players start on its top quality,
                # so "lower" = below the best one listed
                cur = max(res(l) for l, _u in vs)
            lower = sorted([(res(l), l, u) for l, u in vs if res(l) < cur], reverse=True)
            if not lower or lower[0][0] < 360:
                return False
            _r, label, url = lower[0]
        except Exception as e:
            my_log("auto quality: {}".format(e))
            return False
        pos = int(frozen_pts // 90000)
        my_log("auto quality: buffering {} times in {}s -- {} -> {} at {}s".format(
            len(hist), self._LOWER_WINDOW, getattr(self, "_quality_current_label", "?"), label, pos))
        self._buffer_stops = []
        self._stall_count = 0
        self._stall_fail_count = 0
        self._stall_last_pts = -1
        self._switch_kind = "auto"          # not saved as this title's preferred quality
        self._pl_qualitySwitch(label, url, resume=pos,
                               status=u"Lower quality ({}) to stop buffering".format(label))
        return True

    def _pl_stallKick(self, target_secs):
        try:
            svc = self.session.nav.getCurrentService()
            if not svc:
                return False
            sk = svc.seek()
            if not sk:
                return False
            t = max(0, int(target_secs))
            _tot = self._total_secs
            if _tot > 0:
                t = min(t, _tot - 3)
            sk.seekTo(t * 90000)
            with novaplay_tracker._GLOBAL_POS_LOCK:
                novaplay_tracker._GLOBAL_LAST_SEEK_TARGET = t
                novaplay_tracker._GLOBAL_PLAY_START_POS = max(0, t - 2)
                novaplay_tracker._GLOBAL_PLAY_START_WALL = time.time()
            if self._paused:
                self._paused_elapsed = t
            return True
        except Exception as e:
            my_log("stall kick error: {}".format(e))
            return False

    def _pl_stallRecover(self, frozen_pts):
        self._stall_fail_count += 1
        self._stall_recovering = True
        self._stall_count = 0
        self._stall_recover_target = frozen_pts // 90000
        my_log("Stall watchdog: frozen ~{}s — kicking pipeline (attempt {})".format(
            self._stall_recover_target, self._stall_fail_count))
        try:
            self["status"].setText("Restoring playback…")
            self._pl_showOSD(True)
        except Exception:
            pass
        if self._pl_stallKick(self._stall_recover_target + 7):
            self._stall_kick_timer.start(1500, True)
        else:
            self._stall_recovering = False

    def _pl_stallKickBack(self):
        if not getattr(self, "_stall_recovering", False):
            return
        try:
            t = getattr(self, "_stall_recover_target", 0)
            if t > 0 and self._pl_stallKick(t):
                my_log("Stall watchdog: playback restored at {}s".format(t))
                try:
                    self["status"].setText("Restored")
                    self._pl_showOSD(True)
                except Exception:
                    pass
        finally:
            self._stall_recovering = False
            self._stall_last_pts = -1
            self._stall_count = 0

    def _pl_stallSwitchCandidate(self, frozen_pts):
        frozen = int(frozen_pts // 90000)
        my_log("Stall watchdog: dead stream — switching candidate (resume at {}s)".format(frozen))
        try:
            self._stall_timer.stop()
        except Exception:
            pass
        try:
            self._stall_kick_timer.stop()
        except Exception:
            pass
        self._stall_recovering = False
        self._stall_count = 0
        self._stall_fail_count = 0
        self._stall_last_pts = -1
        self._resume_pos = frozen
        self._autosub_gen = getattr(self, "_autosub_gen", 0) + 1
        try:
            self["status"].setText("🔄 Switching server…")
            self._pl_showOSD(True)
        except Exception:
            pass
        self._pl_playNext()

    def _skipDeadHostCandidates(self):
        """[2026-10-21] after a failed attempt: if the proxy saw this stream's
        server answer as down (Cloudflare 52x / gateway 502/504), the other
        ways of playing it would only fail too -- skip them (Street Fighter's
        LuluStream copy on a dead node spun ~90 s through six methods)."""
        try:
            idx = self._candidate_idx
            if idx < 0 or idx >= len(self.candidates):
                return
            up = _upstream_of(self.candidates[idx][1])
            code = novaplay_proxy.dead_host(up) if up else 0
            if not code:
                return
            host = novaplay_proxy._host_of(up)
            rest = [c for c in self.candidates[idx + 1:]
                    if novaplay_proxy._host_of(_upstream_of(c[1])) == host]
            if rest:
                my_log("candidates: {} is down (HTTP {}) -- skipping the other {} method(s)".format(
                    host, code, len(rest)))
                self.candidates = self.candidates[:idx + 1] + [
                    c for c in self.candidates[idx + 1:] if c not in rest]
        except Exception as e:
            my_log("dead-host check failed (non-fatal): {}".format(e))

    def _pl_playNext(self):
        if getattr(self, "_is_advancing", False): return
        # [net 2026-10-28] an attempt failed: first make sure the box is
        # online -- without internet every other method fails too
        if self._candidate_idx >= 0 and not getattr(self, "_net_gate_passed", False):
            self._pl_netGate()
            return
        self._net_gate_passed = False
        self._is_advancing = True
        if not self._play_confirmed:
            self._recordPlayMemory(False)   # the attempt we are leaving didn't play
            self._skipDeadHostCandidates()
        self._candidate_idx += 1
        if self._candidate_idx >= len(self.candidates):
            if not getattr(self, "_exhausted", False):
                self._exhausted = True
                try:
                    from .plugin_server_rank import record_host_result, record_title_failed
                    record_host_result(self._server_url, False)
                    record_title_failed(self._item_url, self._server_url)
                except Exception as e:
                    my_log("server-rank record (exhausted) failed (non-fatal): {}".format(e))
                self._disarmSkipHint()
                self["status"].setText("Could not play the link after all attempts")
                def _fail_callback(ans):
                    if ans:
                        self._exhausted = False
                        self._candidate_idx = -1
                        self._play_confirmed = False
                        self._stall_last_pts = -1
                        self._stall_count = 0
                        self._stall_fail_count = 0
                        first = (self.candidates[0][1] if self.candidates else "")
                        if first:
                            self.candidates = _build_remote_play_candidates(first)
                            self.candidates = self._reorderCandidatesByPref(self.candidates)
                        self._pl_playNext()
                    else:
                        self._pl_onExit(clear_position=False)
                if getattr(self, "_quality_switch_in_flight", False):
                    self._quality_switch_in_flight = False
                    _tgt = getattr(self, "_quality_switch_target_url", "")
                    if _tgt and _tgt not in self._quality_dead_urls:
                        self._quality_dead_urls.add(_tgt)
                        my_log("quality: variant marked dead: {}…".format(_tgt[:70]))
                    _msg = (u"The new server did not play\nGo back to the previous server?"
                            if getattr(self, "_switch_kind", "") == "server" else
                            u"The new quality is not available (link expired)\nGo back to the previous quality?")
                    self.session.openWithCallback(
                        self._onQualityRetry, MessageBox, _msg,
                        MessageBox.TYPE_YESNO, timeout=10, default=True)
                else:
                    self.session.openWithCallback(
                        _fail_callback, MessageBox,
                        u"Could not play the link after all attempts\n\nTry again?",
                        MessageBox.TYPE_YESNO, timeout=8, default=True)
            self._is_advancing = False
            return

        p_type, svc_url, label, uses_proxy = self.candidates[self._candidate_idx]
        self._play_confirmed = False
        self._candidate_start_ts = time.time()
        self._candidate_uses_proxy = uses_proxy
        self._candidate_label = label
        if uses_proxy:
            novaplay_proxy._PROXY_LAST_HIT = 0
            novaplay_proxy._PROXY_LAST_BYTES = 0
        self.sref = eServiceReference(p_type, 0, svc_url)
        if sys.version_info[0] == 3:
            self.sref.setName(str(self.title))
        else:
            self.sref.setName(self.title.encode("utf-8", "ignore"))

        self["status"].setText("Playing... {}".format(label))
        self._pl_showOSD(False)
        my_log("Play attempt: {}".format(label))
        try:
            self.session.nav.stopService()
        except: pass
        try:
            _nav_play_unhooked(self.session.nav, self.sref)
            # proxy attempts that are broken fail within a second or two; one that is
            # still waiting on a slow CDN playlist gets 30 s (seen: 16-46 s on the box)
            self._retry_timer.start(30000 if uses_proxy else 12000, True)
            self._force_confirmation_timer.start(3000, True)
            self._armSkipHint()
        except Exception as e:
            my_log("SimplePlayer fallback error: {}".format(e))
            self._is_advancing = False
            self._pl_playNext()
            return
        self._is_advancing = False

    def _pl_onConfirmed(self):
        if self._play_confirmed: return
        self._play_confirmed = True
        self._confirmed_ts = time.time()
        try:
            self._retry_timer.stop()
            self._force_confirmation_timer.stop()
        except: pass
        self._disarmSkipHint()
        my_log("Play confirmed: {}".format(self._candidate_label))
        self._reapplySavedPep()
        self._recordPlayMemory(True)
        try:
            from .plugin_server_rank import record_host_result, record_title_working
            record_host_result(self._server_url, True)
            record_title_working(self._item_url, self._server_url)
        except Exception as e:
            my_log("server-rank record (confirmed) failed (non-fatal): {}".format(e))
        try:
            _pk = _candidate_pref_key(self._item_url)
            if _pk and self._candidate_label and \
                    str(_get_config(_pk, "") or "") != self._candidate_label:
                _set_config(_pk, self._candidate_label)
        except Exception:
            pass
        if getattr(self, "_quality_pending_pref", ""):
            try:
                _qk = _quality_pref_key(getattr(self, "_raw_title", "") or self.title)
                if _qk and not str(self._quality_pending_pref).lower().startswith("quality "):
                    _set_config(_qk, self._quality_pending_pref)
                    my_log("quality pref saved: {} = {}".format(_qk, self._quality_pending_pref))
            except Exception as e:
                my_log("quality pref save failed: {}".format(e))
            self._quality_pending_pref = ""
        self._quality_switch_in_flight = False
        self._switch_kind = "quality"
        self._server_prev = None
        start_pos_tracker(self.session, self._item_url, start_pos=self._resume_pos)
        try:
            # [2026-10-31] a new title starts without subtitles; a resumed one gets
            # its subtitle back if it was on when you stopped
            maybe_resume_subtitle(self.session, self.title, self._item_url)
        except Exception:
            pass
        try:
            self._studioTimer.start(100, False)
        except Exception:
            pass
        try:
            self._stall_last_pts = -1
            self._stall_count = 0
            self._stall_fail_count = 0
            self._stall_recovering = False
            self._stall_timer.start(self._STALL_TICK_MS, False)
        except Exception:
            pass
        # [series-prefs] the audio language of the last episode (tracks are
        # known a few seconds after the start)
        try:
            self._series_audio_timer = eTimer()
            self._series_audio_timer.callback.append(self._applySeriesAudio)
            self._series_audio_timer.start(4000, True)
        except Exception:
            pass
        if self._resume_pos > 30:
            self._seek_retry_count = 0
            self._seek_timer.start(6000, True)
        self["osd_title"].setText(self.title)
        self._osdTitleLookup()
        self["status"].setText(u"Playing")
        self._total_secs = 0
        self._watched_at_90_fired = False
        self._pl_showOSD(True)

    def _osdTitleLookup(self):
        """[2026-10-30] the bar's title: the clean name with year, rating and
        genre from TMDb ("The Hunted  ·  2026 · ★ 6.4 · Action"), in a thread
        (TMDb answers come from its disk cache most of the time)"""
        if getattr(self, "_osd_meta_done", False):
            return
        self._osd_meta_done = True
        raw = getattr(self, "_raw_title", "") or self.title
        try:
            from .plugin_util import split_card_title, title_year, _strip_arabic_from_english_title
            name, ep = split_card_title(re.sub(r"\s*\[\d+p\]\s*$", "", raw))
            name = _strip_arabic_from_english_title(name or raw) or name or raw
            q, year = title_year(name)
        except Exception:
            return
        kind = "tv" if ep else "movie"

        def _work():
            meta = {}
            try:
                from .plugin_tmdb import _tmdb_search_metadata, _tmdb_enabled
                if _tmdb_enabled():
                    meta = _tmdb_search_metadata(q, year, kind) or {}
            except Exception as e:
                my_log("osd title: {}".format(e))
            y = str(meta.get("year") or year or "")[:4]
            bits = [y]
            try:
                r = float(meta.get("rating") or 0)
                if r > 0:
                    bits.append(u"\u2605 %.1f" % r)
            except Exception:
                pass
            g = (meta.get("genres") or "").split(",")[0].strip()
            if g:
                bits.append(g)
            bits = [b_ for b_ in bits if b_]
            if not bits and q == raw:
                return

            def _show():
                self._osd_year = y            # [2026-11-04] for the subtitle search
                self._osd_tmdb = (meta.get("tmdb_id"), meta.get("tmdb_kind") or kind)
                self._osd_title_parts = (q, bits)
                self._osdTitlePaint()
            callInMainThread(_show)
        threading.Thread(target=_work, daemon=True).start()

    # [2026-10-31] the title uses the whole space up to the picture size
    # (766 px, ~52 characters); with an episode label (S01E02) next to it,
    # the first 576 px (~40). Too long: genre, then rating are left out
    # instead of cutting the line with "..."
    _OSD_TITLE_WIDE, _OSD_TITLE_NARROW = (766, 52), (576, 40)

    def _osdTitleWidth(self, narrow):
        narrow = bool(narrow)
        if getattr(self, "_osd_title_narrow", None) == narrow:
            return
        self._osd_title_narrow = narrow
        px = (self._OSD_TITLE_NARROW if narrow else self._OSD_TITLE_WIDE)[0]
        try:
            from .plugin_gridlist import sc
            inst = self["osd_title"].instance
            if inst is not None:
                inst.resize(eSize(sc(px), sc(40)))
        except Exception:
            pass
        self._osdTitlePaint()

    def _osdTitlePaint(self):
        parts = getattr(self, "_osd_title_parts", None)
        if not parts:
            return
        maxch = (self._OSD_TITLE_NARROW if getattr(self, "_osd_title_narrow", False) else self._OSD_TITLE_WIDE)[1]
        try:
            from .plugin_util import fit_title_line
            self["osd_title"].setText(fit_title_line(parts[0], parts[1], maxch))
        except Exception:
            pass

    def _pl_onFailed(self):
        if self._play_confirmed: return
        try:
            self._retry_timer.stop()
            self._force_confirmation_timer.stop()
        except: pass
        my_log("Play failed event: {}".format(self._candidate_label))
        self._pl_playNext()

    def _pl_onEOF(self):
        if (self._play_confirmed and getattr(self, "_candidate_uses_proxy", False)
                and time.time() - getattr(self, "_confirmed_ts", 0) < 180):
            # [FIX 2026-10-17] Box: a stream 'ended' 72 s after starting (the player gave up
            # waiting for a slow quality playlist). That was marked watched, the resume point
            # cleared and the player closed. A movie can't end within 3 minutes of starting:
            # treat it as a failure and try the next way of playing it.
            my_log("Early EOF {:.0f}s after start: treating as a failure ({})".format(
                time.time() - self._confirmed_ts, self._candidate_label))
            try:
                stop_pos_tracker()
            except Exception:
                pass
            try:
                from .plugin_server_rank import retract_title_working
                retract_title_working(self._item_url, self._server_url)
            except Exception as e:
                my_log("server-rank retract failed (non-fatal): {}".format(e))
            self._play_confirmed = False
            self._pl_playNext()
            return
        if self._play_confirmed:
            try:
                from .plugin_watched import mark_watched
                if self._item_url:
                    mark_watched(self._item_url)
            except Exception:
                pass
            if (self._next_episode and self._on_next
                    and self._next_prompt_enabled
                    and not getattr(self, "_eof_prompted", False)):
                self._eof_prompted = True
                my_log("EOF: next episode available — showing auto-next card")
                self._showAutoNextCard(self._next_episode)
                return
            if getattr(self, "_autonext_active", False):
                return
            my_log("Playback EOF reached, clearing resume position.")
            self._pl_onExit(clear_position=True)
            return
        self._pl_onFailed()

    def _pl_onTimeout(self):
        if self._play_confirmed: return
        if self._candidate_uses_proxy and novaplay_proxy._PROXY_LAST_HIT >= self._candidate_start_ts and novaplay_proxy._PROXY_LAST_BYTES > 50000:
            my_log("Play proxy confirmed by traffic: {} bytes".format(novaplay_proxy._PROXY_LAST_BYTES))
            self._pl_onConfirmed()
            return
        if (self._candidate_uses_proxy and novaplay_proxy.playlist_fetch_in_progress()
                and time.time() - self._candidate_start_ts < 150):
            my_log("Play: slow playlist still downloading or just arrived, waiting ({})".format(self._candidate_label))
            self._retry_timer.start(15000, True)
            return
        my_log("Play timeout: {}".format(self._candidate_label))
        self._pl_playNext()

    def _pl_forceConfirm(self):
        if self._play_confirmed: return
        if self._candidate_uses_proxy and novaplay_proxy._PROXY_LAST_HIT >= self._candidate_start_ts and novaplay_proxy._PROXY_LAST_BYTES > 50000:
            my_log("Play proxy confirmed early by traffic: {} bytes".format(novaplay_proxy._PROXY_LAST_BYTES))
            self._pl_onConfirmed()
