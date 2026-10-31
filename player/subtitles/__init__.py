# -*- coding: utf-8 -*-
"""WGFileManager player/subtitles — r95 port of the ORIGINAL engine.

The eight engine files are vendored VERBATIM from the working plugin.
This package adds only the glue the media player needs:

  * SubtitleManager — adapter with the player's SubtitleHandler
    surface (setService / toggleSubtitles / adjustDelay / resetDelay /
    isEnabled / selectedSubtitle / currentDelay / getSubtitleList /
    close), so the player and hotkey_manager work unchanged.
  * SubtitleStudioOverlay — full-screen transparent dialog the STUDIO
    singleton binds to (the original bound to a full-screen player
    screen; this player's window is the 1400x220 bar, so subtitles
    get their own layer at zPosition 500 — the bar slides OVER them).
  * StudioSettingsScreen — the styling overlay (guide §4).

Auto-attach pipeline on each track (guide §1):
    per-file memory -> sidecar next to the video -> engine's
    subtitle-folder scan (+3.5 s) -> silent SubSource search (+6.5 s).
"""

import os
import sys

from enigma import eTimer

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .engine import (
    apply_subtitle, disable_subtitle, adjust_sync, reset_sync,
    get_subtitle_state, update_subtitle_state, remember_subtitle,
    recall_subtitle, maybe_resume_subtitle, _apply_path_with_offset,
    _cfg, _cfg_bool, _cfg_set,
)
from .studio import STUDIO
from .autosub import auto_subtitle_async
from .menu import SubtitleMenuScreen
from .screens import NovaSubtitleSettings as SubtitleSettingsScreen
from .studio_settings import StudioSettingsScreen

if sys.version_info[0] >= 3:
    _UNICODE = str
else:
    _UNICODE = unicode  # noqa: F821
_STRING_TYPES = (str, _UNICODE)

_SUB_EXTS = (".srt", ".ass", ".ssa", ".sub", ".txt")

# FIX (merge): Studio mode OFF by default. The overlay dialog it
# creates (a full-screen transparent Screen with no ActionMap) blocks
# the player's color-button key dispatch on some Enigma2 images
# (confirmed on Vu+ / OpenATV). The user can turn it on in Subtitle
# Settings → Studio if they want the live-styled renderer.
if str(_cfg("substudio_mode", "")).strip() == "":
    _cfg_set("substudio_mode", "false")


def show_subtitle_settings(session, **kwargs):
    session.open(SubtitleSettingsScreen)


class SubtitleManager(object):
    """Player-facing surface over the vendored engine. The player keeps
    the attribute name 'subtitleHandler', so hotkey_manager's resolver
    and every existing call keep working."""

    def __init__(self, session, player=None):
        self.session = session
        self.player = player
        self.subtitleList = []
        self.externalSubtitles = []
        self.selectedSubtitle = None   # plain attrs: the player's
        self.currentDelay = 0          # self-test writes them back
        self.enabled = False
        self._embedded = None
        self._overlay = None
        self._autosub_timer = None
        self._closed = False
        self._sync_attrs()

    # ------------------------------------------------------------ utils
    @staticmethod
    def _is_string(obj):
        return isinstance(obj, _STRING_TYPES)

    def _sync_attrs(self):
        st = get_subtitle_state()
        self.selectedSubtitle = st.get("path") or (self._embedded or None)
        self.currentDelay = int(st.get("offset_ms") or 0)
        self.enabled = bool(st.get("path")) or self._embedded is not None

    def isEnabled(self):
        self._sync_attrs()
        return self.enabled

    def close(self):
        self._closed = True
        if self._autosub_timer is not None:
            try:
                self._autosub_timer.stop()
            except Exception:
                pass
            self._autosub_timer = None
        try:
            disable_subtitle(self.session)
        except Exception:
            pass
        if self._overlay is not None:
            try:
                self._overlay.hide()
                self._overlay.doClose()
            except Exception:
                pass
            self._overlay = None

    # ----------------------------------------------------------- layer
    def _ensure_overlay(self):
        if self._overlay is None:
            from .overlay import SubtitleStudioOverlay
            self._overlay = self.session.instantiateDialog(SubtitleStudioOverlay)
            STUDIO.bind(self._overlay)
            self._overlay.show()   # transparent; paints nothing until cues
        return self._overlay

    def _video_path(self):
        try:
            ref = self.session.nav.getCurrentlyPlayingServiceReference()
            if ref and ref.getPath():
                return ref.getPath()
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------ scans
    def _scan_embedded(self):
        self.subtitleList = []
        try:
            svc = self.session.nav.getCurrentService()
            if svc:
                sub = svc.subtitle()
                if sub:
                    self.subtitleList = sub.getSubtitleList() or []
        except Exception:
            self.subtitleList = []

    def _scan_sidecars(self):
        self.externalSubtitles = []
        vp = self._video_path()
        if not vp:
            return
        d = os.path.dirname(vp)
        for root in [d] + [os.path.join(d, s) for s in ("subtitles", "Subs", "Sub")]:
            if not os.path.isdir(root):
                continue
            try:
                for f in os.listdir(root):
                    if f.lower().endswith(_SUB_EXTS):
                        self.externalSubtitles.append(os.path.join(root, f))
            except Exception:
                continue
        self.externalSubtitles.sort()

    def _sidecar(self):
        vp = self._video_path()
        if not vp or not self.externalSubtitles:
            return None
        stem = os.path.splitext(os.path.basename(vp))[0].lower()
        best, bs = None, 0
        for p in self.externalSubtitles:
            n = os.path.basename(p).lower()
            s = 0
            if n.startswith(stem):
                s += 100
            if stem and stem in n:
                s += 50
            if s > bs:
                best, bs = p, s
        return best if bs > 0 else None

    # --------------------------------------------------------- service
    def setService(self, service):
        try:
            if self._autosub_timer is not None:
                self._autosub_timer.stop()
        except Exception:
            pass
        self._embedded = None
        # Drop the previous track's cues/state immediately (no stale
        # subtitle bleeding into the next video).
        try:
            if STUDIO.is_attached():
                STUDIO.detach()
        except Exception:
            pass
        item_url = getattr(self.player, "_item_url", "") or ""
        update_subtitle_state(item_url=item_url, path="",
                              _orig_path="", offset_ms=0)
        if not service:
            self._sync_attrs()
            return
        # FIX (merge): only create the overlay when Studio mode is on.
        # The overlay is a full-screen transparent dialog that can
        # block the player's key dispatch on some images. When Studio
        # is off (the new default), the player's color buttons work
        # normally; subtitles render through the service layer instead.
        if _cfg_bool("substudio_mode", False):
            self._ensure_overlay()
        self._scan_embedded()
        self._scan_sidecars()

        title = getattr(self.player, "title", "") or ""
        # 1) per-file memory (chosen subtitle + sync offset)
        path, off = recall_subtitle(item_url)
        if path:
            _apply_path_with_offset(self.session, item_url, path, off)
            self._sync_attrs()
        else:
            # 2) sidecar next to the video (guide §1)
            side = self._sidecar()
            if side:
                apply_subtitle(self.session, side)
                remember_subtitle(item_url, side, 0)
                self._sync_attrs()
            else:
                # 3) engine pipeline: configured subtitle-folder scan (+3.5 s)
                maybe_resume_subtitle(self.session, title, item_url)
        # 4) silent SubSource fallback (+6.5 s; self-skips if attached)
        self._schedule_autosub()

    def _schedule_autosub(self):
        if not _cfg_bool("autosub", True):
            return
        if not str(_cfg("subsource_api_key", "")).strip():
            return
        t = eTimer()

        def _go():
            if self._closed:
                return
            if get_subtitle_state().get("path") or self._embedded is not None:
                return          # local / memory won
            player = self.player
            if player is None:
                return
            auto_subtitle_async(player, getattr(player, "_autosub_gen", 0))
        try:
            t.timeout.connect(_go)
        except Exception:
            t.callback.append(_go)
        t.start(6500, True)
        self._autosub_timer = t

    # -------------------------------------------------------- selection
    def _enable_embedded(self, subtitle):
        try:
            svc = self.session.nav.getCurrentService()
            if not svc:
                return False
            ss = svc.subtitle()
            if not ss:
                return False
            for args in ((subtitle, True), (subtitle,)):
                try:
                    ss.enableSubtitles(*args)
                    self._embedded = subtitle
                    self._sync_attrs()
                    return True
                except TypeError:
                    continue
                except Exception:
                    break
            return False
        except Exception:
            return False

    def selectSubtitle(self, subtitle):
        if subtitle is None:
            self._embedded = None
            disable_subtitle(self.session)
            self._sync_attrs()
            return True
        if self._is_string(subtitle) and os.path.exists(subtitle):
            item_url = getattr(self.player, "_item_url", "") or ""
            ok = apply_subtitle(self.session, subtitle)
            if ok:
                remember_subtitle(item_url, subtitle, 0)
            self._sync_attrs()
            return ok
        return self._enable_embedded(subtitle)

    def toggleSubtitles(self):
        self._sync_attrs()
        if self.enabled:
            self._embedded = None
            disable_subtitle(self.session)
            self._sync_attrs()
            return False
        item_url = getattr(self.player, "_item_url", "") or ""
        path, off = recall_subtitle(item_url)
        if not path:
            path = self._sidecar()
            off = 0
        if path:
            _apply_path_with_offset(self.session, item_url, path, off)
            self._sync_attrs()
            return bool(get_subtitle_state().get("path"))
        if self.subtitleList and self._enable_embedded(self.subtitleList[0]):
            return True
        if self.externalSubtitles:
            p = self.externalSubtitles[0]
            if apply_subtitle(self.session, p):
                remember_subtitle(item_url, p, 0)
                self._sync_attrs()
                return True
        return False

    # -------------------------------------------------------------- sync
    def adjustDelay(self, offset):
        if self._embedded is not None:
            try:
                svc = self.session.nav.getCurrentService()
                ss = svc and svc.subtitle()
                if ss and hasattr(ss, "setSubtitleDelay"):
                    self.currentDelay += int(offset)
                    ss.setSubtitleDelay(self.currentDelay / 1000.0)
                    return self.currentDelay
            except Exception:
                pass
            return self.currentDelay
        adjust_sync(self.session, int(offset))
        self._sync_attrs()
        return self.currentDelay

    def resetDelay(self):
        if self._embedded is not None:
            try:
                svc = self.session.nav.getCurrentService()
                ss = svc and svc.subtitle()
                if ss and hasattr(ss, "setSubtitleDelay"):
                    ss.setSubtitleDelay(0)
            except Exception:
                pass
            self.currentDelay = 0
            return 0
        reset_sync(self.session)
        self._sync_attrs()
        return self.currentDelay

    # ----------------------------------------------------------- listing
    def getSubtitleList(self):
        result = [(None, "Disabled", "", "", False)]
        st = get_subtitle_state()
        cur = st.get("path") or ""
        for sub in self.subtitleList:
            lang = sub[4] if len(sub) > 4 else "und"
            pid = str(sub[1]) if len(sub) > 1 else ""
            result.append((sub, "Embedded - %s" % lang, lang, pid,
                           self._embedded == sub))
        for p in self.externalSubtitles:
            result.append((p, "External - %s" % os.path.basename(p), "", p,
                           p == cur))
        return result


__all__ = ["SubtitleManager", "SubtitleMenuScreen",
           "StudioSettingsScreen", "SubtitleSettingsScreen",
           "show_subtitle_settings"]
