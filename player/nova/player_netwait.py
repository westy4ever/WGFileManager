# -*- coding: utf-8 -*-
"""NovaPlay player -- riding out internet drops (2026-10-28).

When playback stalls (stall watchdog) or an attempt fails, the player first
checks whether the box is online (plugin_netstatus, in a thread). If it is
not, it does NOT try the next server -- every server would fail the same
way. It shows "Waiting for internet..." and checks again every 5 s; when the
internet is back it restarts the same server at the same place.

    _pl_netGate()        before moving on to the next playback method
    _pl_netStall(pts)    from the stall watchdog, before kicking / switching
"""
from .player_base import *  # noqa: F401,F403


class PlayerNetWait(object):
    _NET_POLL_MS = 5000

    def _pl_netCheck(self, then):
        """plugin_netstatus.check() in a thread; then(online) on the main thread"""
        def _worker():
            try:
                from . import plugin_netstatus
                online = plugin_netstatus.check()[0] == "online"
            except Exception:
                online = True                  # can't tell: behave as before
            callInMainThread(then, online)
        threading.Thread(target=_worker, daemon=True).start()

    def _pl_netPos(self, pts=None):
        if pts:
            return int(pts // 90000)
        try:
            svc = self.session.nav.getCurrentService()
            r = svc.seek().getPlayPosition() if svc and svc.seek() else None
            if r and r[0] == 0 and r[1] > 0:
                return int(r[1] // 90000)
        except Exception:
            pass
        return int(getattr(self, "_resume_pos", 0) or 0)

    # ── entry points ────────────────────────────────────────────────────
    def _pl_netGate(self):
        """an attempt failed: online -> next method as usual; offline -> wait"""
        if getattr(self, "_net_checking", False) or getattr(self, "_net_waiting", False):
            return
        self._net_checking = True
        was_playing = bool(getattr(self, "_play_confirmed", False) or getattr(self, "_net_had_play", False))
        pos = self._pl_netPos() if was_playing else None

        def _then(online):
            self._net_checking = False
            if getattr(self, "_closing_net", False):
                return
            if online:
                self._net_gate_passed = True
                self._pl_playNext()
            else:
                self._pl_netWait(pos)
        self._pl_netCheck(_then)

    def _pl_netStall(self, pts, act):
        """the picture froze: online -> act() (kick / lower quality / switch);
        offline -> wait"""
        if getattr(self, "_net_checking", False) or getattr(self, "_net_waiting", False):
            return
        self._net_checking = True

        def _then(online):
            self._net_checking = False
            if getattr(self, "_closing_net", False):
                return
            if online:
                act()
            else:
                self._pl_netWait(self._pl_netPos(pts))
        self._pl_netCheck(_then)

    # ── waiting ─────────────────────────────────────────────────────────
    def _pl_netWait(self, pos):
        self._net_waiting = True
        self._net_wait_pos = pos
        self._net_wait_since = time.time()
        my_log("No internet: waiting before trying again (position {}s)".format(pos or 0))
        for t in ("_retry_timer", "_force_confirmation_timer", "_stall_kick_timer"):
            try:
                getattr(self, t).stop()
            except Exception:
                pass
        self._stall_count = 0
        self._stall_recovering = False
        self._pl_netShowWaiting()
        if not getattr(self, "_net_timer", None):
            self._net_timer = eTimer()
            self._net_timer.callback.append(self._pl_netPoll)
        self._net_timer.start(self._NET_POLL_MS, True)

    def _pl_netShowWaiting(self):
        mins = int((time.time() - getattr(self, "_net_wait_since", time.time())) // 60)
        try:
            self["status"].setText(u"No internet - waiting to continue" +
                                   (u" ({} min)".format(mins) if mins else u"..."))
            self._pl_showOSD(True)
            self._hide_timer.stop()            # keep the panel up while waiting
        except Exception:
            pass

    def _pl_netPoll(self):
        if not getattr(self, "_net_waiting", False) or getattr(self, "_closing_net", False):
            return

        def _then(online):
            if not getattr(self, "_net_waiting", False) or getattr(self, "_closing_net", False):
                return
            if online:
                self._pl_netBack()
            else:
                self._pl_netShowWaiting()
                self._net_timer.start(self._NET_POLL_MS, True)
        self._pl_netCheck(_then)

    def _pl_netBack(self):
        """internet is back: the same playback method again, at the same place"""
        self._net_waiting = False
        pos = getattr(self, "_net_wait_pos", None)
        my_log("Internet is back after {:.0f}s: restarting {} at {}s".format(
            time.time() - getattr(self, "_net_wait_since", time.time()),
            getattr(self, "_candidate_label", "?"), pos or 0))
        if pos:
            self._resume_pos = pos
            self._net_had_play = True
        try:
            self["status"].setText(u"Internet is back - continuing")
        except Exception:
            pass
        self._play_confirmed = False
        self._stall_last_pts = -1
        self._stall_count = 0
        self._stall_fail_count = 0
        self._candidate_idx = max(-1, self._candidate_idx - 1)   # the same method again
        self._net_gate_passed = True
        self._pl_playNext()

    def _pl_netStop(self):
        self._closing_net = True
        try:
            self._net_timer.stop()
        except Exception:
            pass
