#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Custom Media Player with AjPanel-Style PlayerBar - WGFileManager edition
=========================================================================
Round-95.

Round-95 (subtitle system - ORIGINAL engine vendored):
  The r94 subpackage (rewritten engine) is replaced by the player's
  ORIGINAL subtitle files, vendored verbatim under player/subtitles/
  (engine / studio / autosub / config / http / thread / menu /
  screens), plus three new glue files: __init__.py (SubtitleManager
  adapter with the player's SubtitleHandler surface), overlay.py
  (full-screen transparent dialog the STUDIO singleton binds to,
  zPosition 500 - below the bar's 1000, so the bar slides OVER
  subtitles and the panel itself is untouched), and studio_settings.py
  (the styling overlay). The r94 rewrite had guessed the SubSource API
  shape and was wrong (real flow: movies/search -> movieId ->
  subtitles?movieId&language -> subtitles/{id}/download with X-API-Key
  headers and a recursive JSON normalizer) - the vendored engine is
  the proven implementation.
  - Auto-attach pipeline per track: per-file memory -> sidecar next to
    the video -> engine's subtitle-folder scan (+3.5 s) -> silent
    SubSource search (+6.5 s, self-skips if anything attached).
  - The player exposes title / _item_url / _autosub_gen (the engine's
    autosub worker and menu read these off the player).
  - showSubtitleMenu constructs the vendored menu helper (it opens its
    own ChoiceBox; it is NOT a Screen - never session.open it) and no
    longer re-runs the auto-attach pipeline on every menu open.
  - SubtitleManager keeps the legacy surface so hotkey_manager's
    resolver and every existing player call keep working.
  - RED Stop now exits directly to TV (the earlier "keep red button as
    exit directly to TV" requirement): stop() stops, restores the
    pre-player service and closes - no confirmation dialog. EXIT keeps
    the r93 behaviour (restore early, deferred close).

Round-94 (carried): attribute name 'subtitleHandler' shared by old and
  new backends; handler-agnostic self-test restore.

Round-93 (carried): exit-to-TV - lastServiceRef captured once in
  __init__; handleExit() restores immediately; onClosePlayer() is the
  one-shot safety net.

Round-92 (carried): inverted-alpha fix - all 8-digit colours carry the
  00 (opaque) prefix.

Round-91 (carried): progress area on the AJ-Panel pattern - five EMPTY
  bar Labels, colours in the skin (BAR_COLORS + P()), Python only
  resizes (fill) and moves (marker); z-pinned stacking; gate suite.

Round-88 fixes (carried): subtitle selection contexts; subtitle
  handler timer teardown + ref verification; chapter extraction
  timeout guard; non-destructive self-test; single-attach timer
  helper; _is_string() for Py2 unicode; empty-list close; label
  clearing; playlist dedupe; monotonic fallback.
"""

from __future__ import print_function
import os
import glob
import sys
import re
import fnmatch
import json
import subprocess
import time as _time_mod

from enigma import (
    getDesktop, ePoint, eSize, gFont, eTimer, gRGB, iServiceInformation,
    eServiceReference, iPlayableService,
)

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.AudioSelection import AudioSelection
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.MenuList import MenuList
from Components.ActionMap import ActionMap
from Components.ServiceEventTracker import ServiceEventTracker
from Components.config import config, ConfigSubsection, ConfigInteger, ConfigYesNo
from Tools.BoundFunction import boundFunction as BF
from Tools.LoadPixmap import LoadPixmap
from Tools.ISO639 import LanguageCodes

# FIX (r95): the ORIGINAL subtitle engine is vendored under
# player/subtitles/ (engine / studio / autosub / config / http /
# thread / menu / screens — verbatim from the working plugin) plus
# glue (__init__ adapter, overlay, studio_settings). NOTE:
# SubtitleMenuScreen is menu.py's helper object, NOT a Screen —
# construct it, never session.open it.
try:
    from .subtitles import (SubtitleManager, SubtitleMenuScreen,
                            StudioSettingsScreen)
except ImportError:
    try:
        from subtitles import (SubtitleManager, SubtitleMenuScreen,
                               StudioSettingsScreen)
    except ImportError:
        SubtitleManager = SubtitleMenuScreen = StudioSettingsScreen = None

if sys.version_info[0] >= 3:
    unicode = str
    long = int

# FIX (r88): Py2 unicode string check used in several subtitle paths.
_STRING_TYPES = (str, unicode)

# FIX (r88): time.monotonic is 3.3+; fall back to time.time on Py2.
try:
    _monotonic = _time_mod.monotonic
except AttributeError:
    _monotonic = _time_mod.time

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ============================================================================
# Timer helper
# ============================================================================
def _connect_timer_once(timer, callback):
    """
    FIX (r88): attach a callback to an eTimer EXACTLY ONCE.

    The previous code ran every setup twice:
        try:    timer.timeout.connect(cb)
        except: pass
        try:    timer.callback.append(cb)
        except: pass
    On builds where both APIs exist, the callback fired twice per
    timeout. Prefer the modern `timeout.connect` signal; fall back to
    the legacy `callback` list only if that first form is unavailable.
    Returns True on success.
    """
    try:
        timer.timeout.connect(callback)
        return True
    except Exception:
        pass
    try:
        timer.callback.append(callback)
        return True
    except Exception:
        return False


# ============================================================================
# Configuration (namespaced - Bug 66)
# ============================================================================
if not hasattr(config.plugins, 'wgfilemanager'):
    config.plugins.wgfilemanager = ConfigSubsection()
_pc = config.plugins.wgfilemanager
if not hasattr(_pc, 'playerShowTimeRemaining'):
    _pc.playerShowTimeRemaining = ConfigYesNo(default=True)
if not hasattr(_pc, 'playerRepeatPlaylist'):
    _pc.playerRepeatPlaylist = ConfigYesNo(default=False)
if not hasattr(_pc, 'playerShufflePlaylist'):
    _pc.playerShufflePlaylist = ConfigYesNo(default=False)
if not hasattr(_pc, 'playerResumePlayback'):
    _pc.playerResumePlayback = ConfigYesNo(default=True)
if not hasattr(_pc, 'playerRememberPosition'):
    _pc.playerRememberPosition = ConfigYesNo(default=True)
if not hasattr(_pc, 'playerBarPosition'):
    _pc.playerBarPosition = ConfigInteger(default=0, limits=(0, 1))
if not hasattr(_pc, 'playerJumpSeconds'):
    _pc.playerJumpSeconds = ConfigInteger(default=300, limits=(10, 1800))
if not hasattr(_pc, 'playerShowProgressPercent'):
    _pc.playerShowProgressPercent = ConfigYesNo(default=True)
if not hasattr(_pc, 'playerBarAutoHide'):
    _pc.playerBarAutoHide = ConfigYesNo(default=True)
if not hasattr(_pc, 'playerBarHideSeconds'):
    _pc.playerBarHideSeconds = ConfigInteger(default=5, limits=(2, 60))

MEDIA_EXTENSIONS = [
    '*.mp4', '*.mkv', '*.avi', '*.mov', '*.ts', '*.m2ts',
    '*.wmv', '*.flv', '*.mp3', '*.aac', '*.ogg', '*.m4v',
    '*.webm', '*.flac', '*.wav', '.m4a', '*.3gp', '*.wma',
    '*.opus', '*.vob', '*.mpeg', '*.mpg', '*.divx'
]
SUBTITLE_EXTENSIONS = ['.srt', '.ass', '.ssa', '.sub', '.idx', '.txt']


def getScreenSize():
    try:
        s = getDesktop(0).size()
        w, h = int(s.width()), int(s.height())
        if w > 0 and h > 0:
            return (w, h)
    except Exception:
        pass
    return (1920, 1080)


SCREEN_W, SCREEN_H = getScreenSize()
SCALE_W = SCREEN_W / 1920.0
SCALE_H = SCREEN_H / 1080.0


def scaleX(val):
    return int(val * SCALE_W)


def scaleY(val):
    return int(val * SCALE_H)


def formatTime(seconds):
    if seconds is None or seconds < 0:
        return "00:00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return "%02d:%02d:%02d" % (h, m, s)
    return "%02d:%02d" % (m, s)


# ============================================================================
# Playlist Manager
# ============================================================================
class PlaylistManager:
    def __init__(self):
        self.items = []
        self.currentIndex = -1
        self.shuffle = _pc.playerShufflePlaylist.value
        self.repeat = _pc.playerRepeatPlaylist.value
        self.playback_positions = {}

    def addFile(self, filePath):
        if os.path.exists(filePath):
            # FIX (r88): dedupe - playing the same folder twice used to
            # silently duplicate every entry.
            for existing in self.items:
                if existing[0] == filePath:
                    return False
            name = os.path.basename(filePath)
            ref = eServiceReference(4097, 0, filePath)
            ref.setName(name)
            self.items.append((filePath, name, ref))
            return True
        logger.warning("File not found: %s" % filePath)
        return False

    def addDirectory(self, dirPath, recursive=False, patterns=None):
        if not os.path.isdir(dirPath):
            return False
        if patterns is None:
            patterns = MEDIA_EXTENSIONS
        files = []
        try:
            for patt in patterns:
                if recursive:
                    for root, dirs, walk_files in os.walk(dirPath):
                        for f in fnmatch.filter(walk_files, patt):
                            files.append(os.path.join(root, f))
                else:
                    files.extend(glob.glob(os.path.join(dirPath, patt)))
            files.sort()
            for f in files:
                self.addFile(f)
            logger.info("Added %d files from directory: %s" % (len(files), dirPath))
            return len(files) > 0
        except Exception as e:
            logger.error("Error scanning directory %s: %s" % (dirPath, str(e)))
            return False

    def clear(self):
        self.items = []
        self.currentIndex = -1
        self.playback_positions.clear()

    def getCurrent(self):
        if 0 <= self.currentIndex < len(self.items):
            return self.items[self.currentIndex]
        return None

    def getNext(self):
        if not self.items:
            return None
        if self.shuffle:
            import random
            # FIX (r88): avoid repeating the same track back-to-back.
            if len(self.items) > 1:
                old = self.currentIndex
                for _ in range(8):
                    new = random.randint(0, len(self.items) - 1)
                    if new != old:
                        self.currentIndex = new
                        break
                else:
                    self.currentIndex = random.randint(0, len(self.items) - 1)
            else:
                self.currentIndex = 0
        else:
            self.currentIndex += 1
            if self.currentIndex >= len(self.items):
                if self.repeat:
                    self.currentIndex = 0
                else:
                    self.currentIndex = len(self.items) - 1
                    return None
        return self.items[self.currentIndex]

    def getPrevious(self):
        if not self.items:
            return None
        self.currentIndex -= 1
        if self.currentIndex < 0:
            if self.repeat:
                self.currentIndex = len(self.items) - 1
            else:
                self.currentIndex = 0
        return self.items[self.currentIndex]

    def setIndex(self, index):
        if 0 <= index < len(self.items):
            self.currentIndex = index
            return True
        return False

    def savePosition(self, filePath, position):
        if _pc.playerRememberPosition.value:
            self.playback_positions[filePath] = position

    def getPosition(self, filePath):
        return self.playback_positions.get(filePath, 0)

    def __len__(self):
        return len(self.items)


# ============================================================================
# Subtitle Handler (LEGACY - fallback when player/subtitles/ is absent)
# ============================================================================
class SubtitleHandler:
    FILE_EXTENSIONS = SUBTITLE_EXTENSIONS
    STREAM_REF_TYPES = ("4097", "5001", "5002", "8193")

    def __init__(self, session, screen=None):
        self.session = session
        self.screen = screen
        self.currentService = None
        self.subtitleList = []
        self.selectedSubtitle = None
        self.enabled = False
        self.externalSubtitles = []
        self.currentDelay = 0
        self._scanRetryTimer = None
        self._scanRetryTimer2 = None
        self._restoreTimer = None
        self.serviceRefString = None

    def _stopTimer(self, attr):
        t = getattr(self, attr, None)
        if t is not None:
            try:
                t.stop()
            except Exception:
                pass
            try:
                setattr(self, attr, None)
            except Exception:
                pass

    def _stopAllTimers(self):
        self._stopTimer("_scanRetryTimer")
        self._stopTimer("_scanRetryTimer2")
        self._stopTimer("_restoreTimer")

    def close(self):
        self._stopAllTimers()
        self.currentService = None
        self.screen = None

    def setService(self, service):
        self._stopAllTimers()
        self.currentService = service
        self.subtitleList = []
        self.selectedSubtitle = None
        self.externalSubtitles = []
        self.enabled = False
        self.currentDelay = 0
        self.serviceRefString = None
        if not service:
            return
        try:
            ref = self.session.nav.getCurrentlyPlayingServiceReference()
            if ref:
                self.serviceRefString = ref.toString()
        except Exception:
            pass

        self._getEmbeddedSubtitles()
        self._scanExternalSubtitles()

        if not self.subtitleList and not self.externalSubtitles:
            logger.info("[Sub] first scan empty - will retry in 2s")
            try:
                t = eTimer()
                self._scanRetryTimer2 = t

                def _rescan():
                    self._getEmbeddedSubtitles()
                    self._scanExternalSubtitles()
                    logger.info("[Sub] rescan: %d embedded, %d external",
                                len(self.subtitleList), len(self.externalSubtitles))

                _connect_timer_once(t, _rescan)
                t.start(2000, True)
            except Exception as e:
                logger.warning("[Sub] rescan setup failed: %s", e)

        try:
            self._restoreTimer = eTimer()

            def _doRestore():
                self._loadSubtitleState()

            _connect_timer_once(self._restoreTimer, _doRestore)
            self._restoreTimer.start(2500, True)
        except Exception as e:
            logger.warning("[Sub] restore timer setup failed: %s", e)

    def _getEmbeddedSubtitles(self):
        if not self.currentService:
            return
        subtitle = self.currentService.subtitle()
        if not subtitle:
            return
        self.subtitleList = subtitle.getSubtitleList() or []
        logger.debug("[Sub] %d embedded subtitles" % len(self.subtitleList))

    def _scanExternalSubtitles(self, _attempt=0):
        ref = self.session.nav.getCurrentlyPlayingServiceReference()
        if not ref or not ref.getPath() or not os.path.exists(ref.getPath()):
            if _attempt < 3:
                t = eTimer()
                self._scanRetryTimer = t

                def _retry():
                    self._scanExternalSubtitles(_attempt + 1)

                _connect_timer_once(t, _retry)
                t.start(1500, True)
            return
        videoPath = ref.getPath()
        videoDir = os.path.dirname(videoPath)
        videoName = os.path.splitext(os.path.basename(videoPath))[0]
        patterns = []
        for ext in self.FILE_EXTENSIONS:
            patterns.append(videoName + ext)
            patterns.append(videoName + ".*" + ext)
        found = []
        searchDirs = [videoDir] + [os.path.join(videoDir, s) for s in ('subtitles', 'Subs', 'Sub')]
        for d in searchDirs:
            if not os.path.isdir(d):
                continue
            try:
                for file in os.listdir(d):
                    for pattern in patterns:
                        if fnmatch.fnmatch(file, pattern):
                            full_path = os.path.join(d, file)
                            if os.path.exists(full_path):
                                found.append(full_path)
            except Exception:
                continue
        self.externalSubtitles = sorted(list(set(found)))
        logger.debug("[Sub] %d external subtitles" % len(self.externalSubtitles))

    def getSubtitleList(self):
        result = [(None, "Disabled", "", "", False)]
        for sub in self.subtitleList:
            subType = sub[0]
            pid = sub[1]
            langCode = sub[4] if len(sub) > 4 else "und"
            if langCode in LanguageCodes:
                langName = LanguageCodes[langCode][0]
            elif langCode == "und":
                langName = "Unknown"
            else:
                langName = langCode
            if subType == 0:
                desc, trackId = "DVB", "%x" % pid
            elif subType == 1:
                page = sub[2] if len(sub) > 2 else 0
                mag = sub[3] if len(sub) > 3 else 0
                desc, trackId = "Teletext", "%x%02x" % (mag, page)
            else:
                desc, trackId = "Embedded", str(pid)
            label = "%s - %s (%s)" % (desc, langName, trackId)
            result.append((sub, label, langName, trackId, self.selectedSubtitle == sub))
        for subFile in self.externalSubtitles:
            name = os.path.basename(subFile)
            ext = os.path.splitext(name)[1].upper()
            m = re.search(r'\.([a-z]{2,3})\.', name.lower())
            if m and m.group(1) in LanguageCodes:
                lang_name = LanguageCodes[m.group(1)][0]
            else:
                lang_name = "Unknown"
            label = "External %s - %s [%s]" % (ext, name, lang_name)
            is_active = self._is_string(self.selectedSubtitle) and self.selectedSubtitle == subFile
            result.append((subFile, label, lang_name, name, is_active))
        return result

    @staticmethod
    def _is_string(obj):
        return isinstance(obj, _STRING_TYPES)

    def selectSubtitle(self, subtitle):
        if subtitle is None:
            self.selectedSubtitle = None
            self.enabled = False
            self._disableSubtitles()
            self._saveSubtitleState()
            return True
        if self._is_string(subtitle) and os.path.exists(subtitle):
            ok = self._loadExternalSubtitle(subtitle)
        else:
            ok = self._enableEmbeddedSubtitle(subtitle)
        if ok:
            self.selectedSubtitle = subtitle
            self._saveSubtitleState()
        return ok

    def _enableEmbeddedSubtitle(self, subtitle):
        if not self.currentService:
            return False
        subtitleService = self.currentService.subtitle()
        if not subtitleService:
            logger.error("[Sub] no subtitle service")
            return False
        attempts = [((subtitle, True), "2arg(sub, True)")]
        widget = None
        if self.screen is not None:
            widget = getattr(self.screen, "instance", None)
        if widget is not None:
            attempts.append(((subtitle, widget), "2arg(sub, eWidget)"))
        attempts.append(((subtitle,), "1arg(sub)"))

        for args, label in attempts:
            try:
                subtitleService.enableSubtitles(*args)
                self.enabled = True
                self._applySubtitleDelay()
                logger.info("[Sub] enabled (API: %s)" % label)
                return True
            except TypeError as te:
                logger.debug("[Sub] %s rejected: %s" % (label, te))
                continue
            except Exception as e:
                logger.error("[Sub] enable failed (%s): %s" % (label, e))
                return False
        logger.error("[Sub] enableSubtitles: all signatures rejected")
        return False

    def _disableSubtitles(self):
        if not self.currentService:
            return
        subtitleService = self.currentService.subtitle()
        if subtitleService:
            try:
                subtitleService.disableSubtitles()
            except Exception:
                pass

    def _loadExternalSubtitle(self, subPath):
        try:
            currentRef = self.session.nav.getCurrentlyPlayingServiceReference()
            if not currentRef:
                return False
            ref_str = currentRef.toString()
            ref_type = ref_str.split(":", 1)[0] if ":" in ref_str else ""
            if ref_type not in self.STREAM_REF_TYPES:
                logger.warning("[Sub] external subtitle needs stream ref (got %s)" % ref_type)
                return False
            newRef = eServiceReference(4097, 0, currentRef.getPath() + "|" + subPath)
            newRef.setName(currentRef.getName())
            pos = 0
            if self.currentService:
                seek = self.currentService.seek()
                if seek:
                    r = seek.getPlayPosition()
                    if not r[0]:
                        pos = r[1]
            self.session.nav.playService(newRef)
            self.currentService = self.session.nav.getCurrentService()
            if pos:
                def restorePosition():
                    svc = self.session.nav.getCurrentService()
                    if svc:
                        sk = svc.seek()
                        if sk:
                            sk.seekTo(pos)

                t = eTimer()
                _connect_timer_once(t, restorePosition)
                t.start(1000, True)
            self.enabled = True
            self._applySubtitleDelay()
            logger.info("[Sub] loaded external: %s" % subPath)
            return True
        except Exception as e:
            logger.error("[Sub] external load failed: %s" % e)
            return False

    def toggleSubtitles(self):
        if self.enabled:
            self.selectSubtitle(None)
            return False
        if self.subtitleList:
            if self.selectSubtitle(self.subtitleList[0]):
                return True
            logger.warning("[Sub] embedded enable failed - trying external")
        if self.externalSubtitles:
            if self.selectSubtitle(self.externalSubtitles[0]):
                return True
        return False

    def adjustDelay(self, offset):
        self.currentDelay += offset
        self._applySubtitleDelay()
        self._saveSubtitleState()
        return self.currentDelay

    def _applySubtitleDelay(self):
        if not self.currentService or not self.enabled:
            return
        subtitleService = self.currentService.subtitle()
        if subtitleService and hasattr(subtitleService, 'setSubtitleDelay'):
            try:
                subtitleService.setSubtitleDelay(self.currentDelay / 1000.0)
            except Exception as e:
                logger.error("[Sub] delay apply failed: %s" % e)

    def resetDelay(self):
        self.currentDelay = 0
        self._applySubtitleDelay()
        self._saveSubtitleState()

    def isEnabled(self):
        return self.enabled

    def _getSubtitleStatePath(self):
        try:
            ref = self.session.nav.getCurrentlyPlayingServiceReference()
            if not ref:
                return ""
            path = ref.getPath()
            if path and os.path.exists(path):
                return path + ".ajp"
            name = ref.getName() or ""
            if name:
                safe = re.sub(r'[^A-Za-z0-9_.-]', '_', name)[:60]
                return "/tmp/wgfm_sub_" + safe + ".ajp"
            return ""
        except Exception:
            return ""

    def _saveSubtitleState(self):
        path = self._getSubtitleStatePath()
        if not path:
            return
        try:
            sub = self.selectedSubtitle
            ext_path = sub if self._is_string(sub) else ""
            with open(path, "w") as f:
                f.write("ext=%s\n" % ext_path)
                f.write("delay=%d\n" % self.currentDelay)
                f.write("enabled=%d\n" % (1 if self.enabled else 0))
        except Exception as e:
            logger.debug("[Sub] state save skipped: %s" % e)

    def _loadSubtitleState(self):
        cur = self.session.nav.getCurrentlyPlayingServiceReference()
        if not cur or not cur.getPath():
            return
        if self.serviceRefString is not None:
            try:
                if cur.toString() != self.serviceRefString:
                    logger.info("[Sub] deferred restore skipped: service changed")
                    return
            except Exception:
                pass
        path = self._getSubtitleStatePath()
        if not path or not os.path.exists(path):
            return
        ext = ""
        delay = 0
        enabled = 0
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ext="):
                        ext = line.split("=", 1)[1].strip()
                    elif line.startswith("delay="):
                        try:
                            delay = int(line.split("=", 1)[1].strip())
                        except Exception:
                            pass
                    elif line.startswith("enabled="):
                        try:
                            enabled = int(line.split("=", 1)[1].strip())
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("[Sub] state load skipped: %s" % e)
            return
        self.currentDelay = delay
        if ext and os.path.exists(ext):
            logger.info("[Sub] restoring external subtitle: %s" % ext)
            if self._loadExternalSubtitle(ext):
                self.selectedSubtitle = ext
        elif enabled and self.subtitleList:
            logger.info("[Sub] restoring embedded subtitle")
            if self._enableEmbeddedSubtitle(self.subtitleList[0]):
                self.selectedSubtitle = self.subtitleList[0]


# ============================================================================
# Subtitle Selection Screen (LEGACY - fallback when subpackage absent)
# ============================================================================
class SubtitleSelectionScreen(Screen):
    def __init__(self, session, subtitleHandler):
        self.skin = '''
        <screen name="SubtitleSelection" position="center,center" size="800,600" title="Select Subtitle">
            <widget name="list" position="20,20" size="760,500" scrollbarMode="showOnDemand" />
            <widget name="key_red" position="20,530" size="180,40" backgroundColor="#9f1313" font="Regular;20" halign="center" valign="center" />
            <widget name="key_green" position="220,530" size="180,40" backgroundColor="#1f771f" font="Regular;20" halign="center" valign="center" />
            <widget name="key_yellow" position="420,530" size="180,40" backgroundColor="#a08500" font="Regular;20" halign="center" valign="center" />
            <widget name="key_blue" position="620,530" size="180,40" backgroundColor="#18188b" font="Regular;20" halign="center" valign="center" />
        </screen>
        '''
        Screen.__init__(self, session)
        self.subtitleHandler = subtitleHandler
        self["list"] = MenuList([])
        self["key_red"] = Label("Disable")
        self["key_green"] = Label("Select")
        self["key_yellow"] = Label("Sync +")
        self["key_blue"] = Label("Sync -")
        self["subtitleSelectActions"] = ActionMap(
            ["CustomMediaPlayerColorActions", "DirectionActions", "OkCancelActions"],
            {
                "red":    self.disableSubtitle,
                "green":  self.selectSubtitle,
                "yellow": BF(self.adjustSync, 100),
                "blue":   BF(self.adjustSync, -100),
                "ok":     self.selectSubtitle,
                "cancel": self.close,
                "up":     self["list"].up,
                "down":   self["list"].down,
            }, -2)
        self.onShown.append(self.updateList)

    def updateList(self):
        subs = self.subtitleHandler.getSubtitleList()
        listItems = []
        for sub, label, lang, trackId, isActive in subs:
            marker = "* " if isActive else "  "
            listItems.append((marker + label, sub))
        self["list"].setList(listItems)

    def selectSubtitle(self):
        current = self["list"].getCurrent()
        if current:
            self.subtitleHandler.selectSubtitle(current[1])
        self.close()

    def disableSubtitle(self):
        self.subtitleHandler.selectSubtitle(None)
        self.close()

    def adjustSync(self, offset):
        new_delay = self.subtitleHandler.adjustDelay(offset)
        self.session.open(MessageBox, "Subtitle delay: %dms" % new_delay,
                          MessageBox.TYPE_INFO, timeout=2)


# ============================================================================
# Keymap Management
# ============================================================================
class KeymapManager:
    _keymap_path = None
    _reference_count = 0

    @classmethod
    def load(cls):
        if cls._keymap_path is not None:
            cls._reference_count += 1
            return cls._keymap_path
        try:
            from Components.ActionMap import loadKeymap
            import tempfile
            keymap_content = '''<?xml version="1.0" ?>
<keymap>
    <map context="CustomMediaPlayerColorActions">
        <key id="KEY_RED" mapto="red" flags="m" />
        <key id="KEY_GREEN" mapto="green" flags="m" />
        <key id="KEY_YELLOW" mapto="yellow" flags="m" />
        <key id="KEY_BLUE" mapto="blue" flags="m" />
    </map>
    <map context="CustomMediaPlayerNavActions">
        <key id="KEY_OK" mapto="ok" flags="m" />
        <key id="KEY_OK" mapto="okLong" flags="l" />
        <key id="KEY_MENU" mapto="menu" flags="m" />
        <key id="KEY_MENU" mapto="menuLong" flags="l" />
        <key id="KEY_EXIT" mapto="cancel" flags="m" />
        <key id="KEY_ESC" mapto="cancel" flags="m" />
        <key id="KEY_UP" mapto="up" flags="mr" />
        <key id="KEY_DOWN" mapto="down" flags="mr" />
        <key id="KEY_LEFT" mapto="left" flags="mr" />
        <key id="KEY_RIGHT" mapto="right" flags="mr" />
    </map>
    <map context="CustomMediaPlayerSeekActions">
        <key id="KEY_FASTFORWARD" mapto="seekFwd" flags="mr" />
        <key id="KEY_REWIND" mapto="seekBack" flags="mr" />
    </map>
    <map context="CustomMediaPlayerNumberActions">
        <key id="KEY_0" mapto="0" flags="m" />
        <key id="KEY_1" mapto="1" flags="m" />
        <key id="KEY_2" mapto="2" flags="m" />
        <key id="KEY_3" mapto="3" flags="m" />
        <key id="KEY_4" mapto="4" flags="m" />
        <key id="KEY_5" mapto="5" flags="m" />
        <key id="KEY_6" mapto="6" flags="m" />
        <key id="KEY_7" mapto="7" flags="m" />
        <key id="KEY_8" mapto="8" flags="m" />
        <key id="KEY_9" mapto="9" flags="m" />
    </map>
    <map context="CustomMediaPlayerInfoActions">
        <key id="KEY_INFO" mapto="showEventInfo" flags="m" />
        <key id="KEY_AUDIO" mapto="audioSelection" flags="m" />
    </map>
    <map context="CustomMediaPlayerSubtitleActions">
        <key id="KEY_SUBTITLE" mapto="subtitleSelection" flags="m" />
        <key id="KEY_TEXT" mapto="toggleSubtitle" flags="m" />
        <key id="KEY_EXIT" mapto="cancel" flags="m" />
        <key id="KEY_ESC" mapto="cancel" flags="m" />
    </map>
    <map context="CustomMediaPlayerSpeedActions">
        <key id="KEY_PLAY" mapto="playPause" flags="m" />
        <key id="KEY_PAUSE" mapto="playPause" flags="m" />
        <key id="KEY_PLAYPAUSE" mapto="playPause" flags="m" />
    </map>
    <map context="CustomMediaPlayerHelpActions">
        <key id="KEY_HELP" mapto="showHelp" flags="m" />
    </map>
    <map context="CustomMediaPlayerJumpActions">
        <key id="KEY_NEXT" mapto="nextTrack" flags="m" />
        <key id="KEY_PREVIOUS" mapto="previousTrack" flags="m" />
    </map>
</keymap>'''
            fd, temp_path = tempfile.mkstemp(suffix='.xml', prefix='wgfm_keymap_')
            try:
                os.write(fd, keymap_content.encode('utf-8'))
            finally:
                os.close(fd)
            loadKeymap(temp_path)
            cls._keymap_path = temp_path
            cls._reference_count = 1
            logger.info("Player keymap loaded: %s" % temp_path)
            return temp_path
        except Exception as e:
            logger.error("Error loading keymap: %s" % str(e))
            return None

    @classmethod
    def unload(cls):
        if cls._reference_count <= 0:
            return
        cls._reference_count -= 1
        if cls._reference_count <= 0 and cls._keymap_path:
            try:
                from Components.ActionMap import removeKeymap
                removeKeymap(cls._keymap_path)
                os.remove(cls._keymap_path)
                logger.info("Player keymap removed")
            except Exception as e:
                logger.error("Error removing keymap: %s" % str(e))
            finally:
                cls._keymap_path = None
                cls._reference_count = 0


# ============================================================================
# Help Screen
# ============================================================================
class PlayerHelpScreen(Screen):
    def __init__(self, session):
        self.skin = '''
        <screen name="PlayerHelpScreen" position="center,center" size="1000,700" title="Player Help">
            <widget name="helptext" position="20,20" size="960,660" font="Regular;22" />
        </screen>
        '''
        Screen.__init__(self, session)
        help_text = """AJPanel-Style Player - Remote Control

PLAYER BAR:
OK       Show/Hide the bar (auto-hides; toggle in BLUE menu)
EXIT     Exit player (stops playback, returns to plugin)

PLAYBACK:
GREEN    Play/Pause          RED     Stop - exit straight to TV
PLAY/PAUSE buttons also toggle

SEEKING:
LEFT/RIGHT   Seek -/+ jump time (hold = repeat)
FF/REW       Seek +/- 5 minutes
UP/DOWN      Previous/Next track
0-9          Set jump time (0 = 10 seconds)
PREV/NEXT    Jump to start / end
HOLD OK      Play whole folder as playlist

SUBTITLES:
YELLOW   Subtitle menu (search / browse / sync / Studio)
TEXT     Toggle subtitles on/off
SUBTITLE Subtitle menu
HOLD MENU  Subtitle menu

AUDIO / INFO:
AUDIO    Audio track selection
INFO     File information
HELP     This help

MENU     Player menu (hold: subtitles)
BLUE     Chapters/jump points"""
        self["helptext"] = Label(help_text)
        self["actions"] = ActionMap(["SetupActions"], {
            "cancel": self.close,
            "ok": self.close,
        }, -1)


# ============================================================================
# Base Player Class
# ============================================================================
class _CustomMediaPlayerBase(Screen):
    STATE_STOPPED = 0
    STATE_PLAYING = 1
    STATE_PAUSED = 2

    PANEL_BG = {
        "panelTop":     "#001B2A44",
        "panelMid":     "#001B2A44",
        "panelBottom":  "#001B2A44",
        "borderTop":    "#002E86C1",
        "borderLeft":   "#002E86C1",
        "borderRight":  "#002E86C1",
        "borderBottom": "#002E86C1",
        "posterBack":   "#00101826",
        "movieTitle":   "#001A5274",
        "keyRed":    "#009F1313",
        "keyGreen":  "#001F771F",
        "keyYellow": "#00A08500",
        "keyBlue":   "#0018188B",
    }

    PANEL_FG = {
        "panelTop":     "#001B2A44",
        "panelMid":     "#001B2A44",
        "panelBottom":  "#001B2A44",
        "borderTop":    "#002E86C1",
        "borderLeft":   "#002E86C1",
        "borderRight":  "#002E86C1",
        "borderBottom": "#002E86C1",
        "posterBack":   "#00101826",
        "movieTitle":         "#00FFFFFF",
        "clock":              "#00FFD24D",
        "playlistInfo":       "#00DDDDDD",
        "jumpInfo":           "#00FF9900",
        "subtitleIndicator":  "#00FFCC00",
        "progressPercent":    "#00FFFFFF",
        "currentTime":        "#00FFD24D",
        "remainingTime":      "#00FFD24D",
        "statusInfo":         "#00FFEE55",
        "videoInfo":          "#00DDDDDD",
        "totalTime":          "#00FFD24D",
        "fileType":           "#00DDDDDD",
        "keyRed":    "#00FFFFFF",
        "keyGreen":  "#00FFFFFF",
        "keyYellow": "#00FFFFFF",
        "keyBlue":   "#00FFFFFF",
    }

    BAR_COLORS = {
        "progressFrame":  "#002E86C1",
        "progressTrack":  "#001E2836",
        "progressFill":   "#0000E650",
        "progressMarker": "#00FF9A00",
        "percentBack":    "#00101826",
    }

    def __init__(self, session, filePath=None, playlist=None, startIndex=0, serviceRef=None):
        self.skin = self.generateSkin()
        Screen.__init__(self, session)
        self.session = session

        KeymapManager.load()

        self.playlist = playlist or PlaylistManager()
        if filePath:
            self.playlist.addFile(filePath)
            self.playlist.setIndex(len(self.playlist) - 1)
        if serviceRef:
            path = serviceRef.getPath()
            self.playlist.addFile(path)
            self.playlist.setIndex(len(self.playlist) - 1)
        if startIndex:
            self.playlist.setIndex(startIndex)

        self.state = self.STATE_STOPPED
        self.currentService = None
        self.manualSeekMode = False
        self.jumpSeconds = _pc.playerJumpSeconds.value
        self.showTimeRemaining = _pc.playerShowTimeRemaining.value
        self.showProgressPercent = _pc.playerShowProgressPercent.value
        self._delay_total = 0
        self._osd_visible = False

        # FIX (r95): attributes the vendored engine reads off the player
        # (autosub worker, menu, browser): display title, per-file key,
        # and the auto-subtitle generation counter (stale background
        # workers bail out when it changes).
        self.title = ""
        self._item_url = ""
        self._autosub_gen = 0

        # PlayerBar slide state
        self.playerBarVisible = False
        self.slideTimer = eTimer()
        _connect_timer_once(self.slideTimer, self._slideAnimation)
        self.slideDirection = None
        self.slideStep = scaleY(15)
        self.totalSlideSteps = 0
        self.currentSlideStep = 0

        bar_height = scaleY(220)
        if _pc.playerBarPosition.value == 0:
            self.barVisibleY = SCREEN_H - bar_height - scaleY(5)
            self.barHiddenY = SCREEN_H + scaleY(10)
        else:
            self.barVisibleY = scaleY(5)
            self.barHiddenY = -bar_height - scaleY(10)

        # FIX (r95): the ORIGINAL subtitle engine (vendored under
        # player/subtitles/) replaces the r94 rewrite. Same attribute
        # name ('subtitleHandler'), so hotkey_manager's resolver and
        # every existing player call keep working. Legacy in-file
        # SubtitleHandler is the fallback when the subpackage is absent.
        if SubtitleManager is not None:
            self.subtitleHandler = SubtitleManager(session, self)
        else:
            self.subtitleHandler = SubtitleHandler(session, self)

        # FIX (r93): remember what was on screen BEFORE the player was
        # opened (normally the live TV service), so exit can zap back.
        self.lastServiceRef = self._captureLastServiceRef()

        # ---- widget declarations ----
        _BLK = u"\u2588" * 200
        self["panelTop"] = Label(_BLK)
        self["panelMid"] = Label(_BLK)
        self["panelBottom"] = Label(_BLK)
        self["borderTop"] = Label(_BLK)
        self["borderLeft"] = Label(u"\u2588" * 70)
        self["borderRight"] = Label(u"\u2588" * 70)
        self["borderBottom"] = Label(_BLK)
        self["posterBack"] = Label(u"\u2588" * 36)
        self["progressFrame"] = Label()
        self["progressTrack"] = Label()
        self["progressFill"] = Label()
        self["progressMarker"] = Label()
        self["percentBack"] = Label()
        self["videoInfo"] = Label("")
        self["clock"] = Label("")
        self["movieTitle"] = Label("")
        self["progressPercent"] = Label("")
        self["currentTime"] = Label("00:00:00")
        self["remainingTime"] = Label("")
        self["totalTime"] = Label("")
        self["statusInfo"] = Label("")
        self["playlistInfo"] = Label("")
        self["subtitleIndicator"] = Label("")
        self["jumpInfo"] = Label(self._jumpLabel())
        self["fileType"] = Label("LOCAL MEDIA")
        self["keyRed"] = Label("Stop")
        self["keyGreen"] = Label("Play")
        self["keyYellow"] = Label("Subtitle")
        self["keyBlue"] = Label("Chapters")
        self["poster"] = Pixmap()

        # ---- action maps ----
        self["playerColorActions"] = ActionMap(["CustomMediaPlayerColorActions"], {
            "red": self.stop,
            "green": self.togglePlayPause,
            "yellow": self.showSubtitleMenu,
            "blue": self._showChapters,
        }, -1)

        self["playerNavActions"] = ActionMap(["CustomMediaPlayerNavActions", "OkCancelActions"], {
            "ok": self.togglePlayerBar,
            "okLong": self._playWholeFolder,
            "menu": self.showMenu,
            "menuLong": self.showSubtitleMenu,
            "cancel": self.handleExit,
            "up": self.previousTrack,
            "down": self.nextTrack,
            "left": BF(self.seek, -self.jumpSeconds),
            "right": BF(self.seek, self.jumpSeconds),
        }, -1)

        self["playerSeekActions"] = ActionMap(["CustomMediaPlayerSeekActions"], {
            "seekFwd": BF(self.seek, 300),
            "seekBack": BF(self.seek, -300),
        }, -1)

        self["playerNumberActions"] = ActionMap(["CustomMediaPlayerNumberActions"], {
            "0": BF(self.setJumpTime, 10),
            "1": BF(self.setJumpTime, 60),
            "2": BF(self.setJumpTime, 120),
            "3": BF(self.setJumpTime, 180),
            "4": BF(self.setJumpTime, 240),
            "5": BF(self.setJumpTime, 300),
            "6": BF(self.setJumpTime, 360),
            "7": BF(self.setJumpTime, 420),
            "8": BF(self.setJumpTime, 480),
            "9": BF(self.setJumpTime, 540),
        }, -1)

        self["playerInfoActions"] = ActionMap(["CustomMediaPlayerInfoActions"], {
            "showEventInfo": self.showFileInfo,
            "audioSelection": self.showAudioMenu,
        }, -1)

        self["playerSubtitleActions"] = ActionMap(["CustomMediaPlayerSubtitleActions"], {
            "subtitleSelection": self.showSubtitleMenu,
            "toggleSubtitle": self.toggleSubtitles,
        }, -1)

        self["playerSpeedActions"] = ActionMap(["CustomMediaPlayerSpeedActions"], {
            "playPause": self.togglePlayPause,
        }, -1)

        self["playerHelpActions"] = ActionMap(["CustomMediaPlayerHelpActions"], {
            "showHelp": self.showHelp,
        }, -1)

        self["playerJumpActions"] = ActionMap(["CustomMediaPlayerJumpActions"], {
            "nextTrack": self.jumpToEnd,
            "previousTrack": self.jumpToStart,
        }, -1)

        # ---- timers ----
        self.updateTimer = eTimer()
        _connect_timer_once(self.updateTimer, self.updateInfo)

        self.saveTimer = eTimer()
        _connect_timer_once(self.saveTimer, self.savePlaybackPosition)

        self.barHideTimer = eTimer()
        _connect_timer_once(self.barHideTimer, self._autoHideBar)

        self.eofTimer = eTimer()
        _connect_timer_once(self.eofTimer, self._eofAdvance)

        self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
            iPlayableService.evEOF: self._onEOF,
        })

        self.onShown.append(self.onFirstShow)
        self.onClose.append(self.onClosePlayer)

    # ---------------------------------------------------------------- skin
    def generateSkin(self):
        w, h = scaleX(1400), scaleY(220)
        x_pos, y_pos = (SCREEN_W - w) // 2, SCREEN_H

        def W(name, x, y, ww, hh, font=None, extra="", align=None):
            if align == "lt":
                av = ' halign="left" valign="top"'
            else:
                av = ' halign="center" valign="center"'
            if font:
                f = ' font="Regular;%d"%s transparent="0"' % (font, av)
            else:
                f = '%s transparent="0"' % av
            return '            <widget name="%s" position="%d,%d" size="%d,%d"%s%s />' % (
                name, scaleX(x), scaleY(y), scaleX(ww), scaleY(hh), f, extra)

        def P(name, x, y, ww, hh):
            return ('            <widget name="%s" position="%d,%d" '
                    'size="%d,%d" zPosition="2" backgroundColor="%s" />'
                    % (name, scaleX(x), scaleY(y), scaleX(ww), scaleY(hh),
                       self.BAR_COLORS[name]))

        L = []
        L.append('<screen name="CustomMediaPlayer" position="%d,%d" size="%d,%d" backgroundColor="#00102018" flags="wfNoBorder" zPosition="1000">'
                 % (x_pos, y_pos, w, h))

        L.append(W("borderTop",    0,    0,   1400, 4))
        L.append(W("borderBottom", 0,    216, 1400, 4))
        L.append(W("borderLeft",   0,    4,   4,    212))
        L.append(W("borderRight",  1396, 4,   4,    212))

        L.append(W("panelTop",    8, 8,   1384, 68))
        L.append(W("panelMid",    8, 76,  1384, 68))
        L.append(W("panelBottom", 8, 144, 1384, 68))

        L.append(W("movieTitle", 24,  16, 700, 32, scaleY(28)))
        L.append(W("clock",      740, 16, 280, 32, scaleY(24)))

        L.append(P("progressFrame",  20,  80, 1004, 36))
        L.append(P("progressTrack",  24,  86, 996,  24))
        L.append(P("progressFill",   24,  86, 2,    24))
        L.append(P("progressMarker", 24,  78, 6,    40))
        L.append(P("percentBack",    482, 56, 80,   22))
        L.append(W("progressPercent", 482, 56, 80, 22, scaleY(20),
                   extra=' zPosition="3"'))

        L.append(W("currentTime",   24,  118, 130, 28, scaleY(26)))
        L.append(W("remainingTime", 160, 118, 130, 28, scaleY(26)))
        L.append(W("statusInfo",    296, 118, 400, 28, scaleY(24)))
        L.append(W("videoInfo",     700, 118, 140, 28, scaleY(22)))
        L.append(W("totalTime",     850, 118, 170, 28, scaleY(26)))

        L.append(W("keyRed",    24,  154, 237, 38, scaleY(24)))
        L.append(W("keyGreen",  277, 154, 237, 38, scaleY(24)))
        L.append(W("keyYellow", 530, 154, 237, 38, scaleY(24)))
        L.append(W("keyBlue",   783, 154, 237, 38, scaleY(24)))

        L.append(W("playlistInfo",      1036, 16,  340, 28, scaleY(22)))
        L.append(W("jumpInfo",          1036, 50,  340, 28, scaleY(22)))
        L.append(W("subtitleIndicator", 1036, 84,  340, 28, scaleY(22)))
        L.append(W("posterBack",        1036, 118, 340, 60))
        L.append(W("poster",            1066, 122, 280, 52, extra=' alphatest="blend"'))
        L.append(W("fileType",          1036, 186, 340, 22, scaleY(16)))

        L.append("        </screen>")
        return chr(10).join(L)

    # ------------------------------------------------------------ colors
    def _set_widget_color(self, name, hexcol, fg):
        try:
            val = int(hexcol[2:10], 16)
        except Exception:
            return False
        try:
            w = self[name]
        except Exception:
            return False
        inst = getattr(w, "instance", None)
        if inst is not None:
            fn = getattr(inst, "setForegroundColor" if fg else "setBackgroundColor", None)
            if callable(fn):
                try:
                    fn(gRGB(val))
                    return True
                except Exception:
                    pass
        fn = getattr(w, "setForegroundColor" if fg else "setBackgroundColor", None)
        if callable(fn):
            try:
                fn(gRGB(val))
                return True
            except Exception:
                pass
        return False

    def _applyColors(self):
        ok_bg = sum(1 for n, c in self.PANEL_BG.items() if self._set_widget_color(n, c, False))
        ok_fg = sum(1 for n, c in self.PANEL_FG.items() if self._set_widget_color(n, c, True))
        if not getattr(self, "_color_cap_logged", False):
            self._color_cap_logged = True
            logger.info("[Player] runtime colors applied: %d backgrounds, %d foregrounds",
                        ok_bg, ok_fg)

    def _applyPanelPixmaps(self):
        try:
            item = self.playlist.getCurrent()
            if item:
                self.loadPoster(item[0])
        except Exception:
            pass

    def _buildProgressPixmaps(self):
        try:
            size = self["progressTrack"].instance.size()
            self._progGeom = (size.width(), size.height())
        except Exception:
            self._progGeom = (scaleX(996), scaleY(24))
        try:
            self["progressFill"].instance.resize(eSize(1, self._progGeom[1]))
        except Exception:
            pass
        try:
            track = self["progressTrack"].instance
            marker = self["progressMarker"].instance
            mp = marker.position()
            marker.move(ePoint(track.position().x() - 1, mp.y()))
        except Exception:
            pass
        self._lastBarPercent = 0.0
        logger.info("[Player] progress geometry: %s", self._progGeom)

    def _setProgressFill(self, percent):
        geom = getattr(self, "_progGeom", None)
        if not geom:
            return
        try:
            pct = 0.0 if percent is None else max(0.0, min(100.0, float(percent)))
        except (TypeError, ValueError):
            pct = 0.0
        self._lastBarPercent = pct
        width = max(1, int(geom[0] * pct / 100.0))
        try:
            self["progressFill"].instance.resize(eSize(width, geom[1]))
        except Exception as e:
            logger.debug("[Player] fill resize failed: %s", e)

    def _moveProgressMarker(self, seconds, duration):
        geom = getattr(self, "_progGeom", None)
        if not geom or not duration or duration <= 0:
            return
        try:
            track = self["progressTrack"].instance
            marker = self["progressMarker"].instance
            tp = track.position()
            mw = marker.size().width()
            min_left = tp.x() - 1
            max_left = tp.x() + geom[0] - mw + 1
            frac = max(0.0, min(1.0, float(seconds) / float(duration)))
            left = int(min_left + frac * (max_left - min_left))
            cur = marker.position()
            marker.move(ePoint(left, cur.y()))
        except Exception as e:
            logger.debug("[Player] marker move failed: %s", e)

    def _ensureBarAssets(self):
        pass

    def _runProgressGates(self):
        results = []

        def gate(name, ok, detail=""):
            ok = bool(ok)
            results.append(ok)
            logger.info("[Gate r91][%s] %s %s", "PASS" if ok else "FAIL",
                        name, detail)

        for n in ("progressFrame", "progressTrack", "progressFill",
                  "progressMarker", "percentBack"):
            try:
                txt = getattr(self[n], "message", None)
                if txt is None:
                    txt = getattr(self[n], "text", u"\u2588")
                gate("G1 empty:%s" % n, txt == "", repr(txt)[:16])
            except Exception as e:
                gate("G1 empty:%s" % n, False, str(e))

        try:
            f = self["progressFrame"].instance
            t = self["progressTrack"].instance
            fp, fs = f.position(), f.size()
            tp, ts = t.position(), t.size()
            ring = (tp.x() - fp.x(),
                    fp.x() + fs.width() - (tp.x() + ts.width()),
                    tp.y() - fp.y(),
                    fp.y() + fs.height() - (tp.y() + ts.height()))
            gate("G2 frame ring", all(1 <= r <= 8 for r in ring),
                 "ring=%s" % (ring,))
        except Exception as e:
            gate("G2 frame ring", False, str(e))

        try:
            skin = self.generateSkin()
            names = ("progressFrame", "progressTrack", "progressFill",
                     "progressMarker", "percentBack", "progressPercent")
            chain = [skin.find('name="%s"' % n) for n in names]
            gate("G3 skin order", -1 not in chain and chain == sorted(chain),
                 "")
            for n, col in self.BAR_COLORS.items():
                s = skin.find('name="%s"' % n)
                e = skin.find("/>", s)
                elem = skin[s:e] if (s >= 0 and e > s) else ""
                gate("G4 skin:%s" % n,
                     ('backgroundColor="%s"' % col) in elem
                     and "transparent" not in elem
                     and 'zPosition="2"' in elem, "")
            s = skin.find('name="progressPercent"')
            gate("G4 skin:progressPercent",
                 'zPosition="3"' in skin[s:skin.find("/>", s)], "")
        except Exception as e:
            gate("G3/G4 skin", False, str(e))

        geom = getattr(self, "_progGeom", None)
        if not geom:
            gate("G5 fill math", False, "no _progGeom (run after onFirstShow)")
        else:
            try:
                saved = getattr(self, "_lastBarPercent", 0.0)
                self._setProgressFill(50.0)
                ok50 = abs(self["progressFill"].instance.size().width()
                           - (geom[0] // 2)) <= 1
                self._setProgressFill(150.0)
                okclamp = (self["progressFill"].instance.size().width()
                           == geom[0])
                self._setProgressFill(-10.0)
                okfloor = (self["progressFill"].instance.size().width() == 1)
                gate("G5 fill math", ok50 and okclamp and okfloor, "")
                self._setProgressFill(saved)
            except Exception as e:
                gate("G5 fill math", False, str(e))

        try:
            m = self["progressMarker"].instance
            start = m.position()
            D = 1000.0
            self._moveProgressMarker(0, D)
            x_min = m.position().x()
            self._moveProgressMarker(D, D)
            x_max = m.position().x()
            self._moveProgressMarker(D / 2.0, D)
            x_mid = m.position().x()
            gate("G6 marker math",
                 x_min < x_mid < x_max and m.position().y() == start.y(),
                 "min=%d mid=%d max=%d" % (x_min, x_mid, x_max))
            m.move(ePoint(start.x(), start.y()))
        except Exception as e:
            gate("G6 marker math", False, str(e))

        stray = [k for k in self.PANEL_BG if k in self.BAR_COLORS]
        stray += [k for k in self.PANEL_FG if k in self.BAR_COLORS]
        gate("G7 palette single-source", not stray, "stray=%s" % stray)

        try:
            attached = all(self[n].instance is not None
                           for n in list(self.BAR_COLORS) + ["progressPercent"])
            detail = "attached=%s" % attached
            restored = False
            if geom:
                want = max(1, int(geom[0]
                                  * getattr(self, "_lastBarPercent", 0.0) / 100.0))
                got = self["progressFill"].instance.size().width()
                restored = (got == want)
                detail += " fill=%d/%d" % (got, want)
            gate("G8 attached/restored", attached and restored, detail)
        except Exception as e:
            gate("G8 attached/restored", False, str(e))

        ok = all(results)
        logger.info("[Gate r91] %d/%d gates passed", sum(results), len(results))
        try:
            self.session.open(MessageBox,
                              "Progress gates: %d/%d passed%s"
                              % (sum(results), len(results),
                                 "" if ok else " - see log"),
                              MessageBox.TYPE_INFO, timeout=4)
        except Exception:
            pass
        return ok

    # ------------------------------------------------------------ slide
    def _slideAnimation(self):
        _now = _monotonic()
        if _now - getattr(self, "_lastSlideTick", 0.0) < 0.005:
            return
        self._lastSlideTick = _now
        try:
            pos = self.instance.position()
        except Exception:
            return
        y = pos.y()
        if self.slideDirection == "up":
            if y <= self.barVisibleY + self.slideStep:
                self._finishSlide(self.barVisibleY, True)
                return
            y -= self.slideStep
        elif self.slideDirection == "down":
            if y >= self.barHiddenY - self.slideStep:
                self._finishSlide(self.barHiddenY, False)
                return
            y += self.slideStep
        else:
            self.slideTimer.stop()
            return
        try:
            self.instance.move(ePoint(pos.x(), y))
        except Exception:
            pass

    def _finishSlide(self, y, visible):
        try:
            self.slideTimer.stop()
            pos = self.instance.position()
            self.instance.move(ePoint(pos.x(), y))
        except Exception:
            pass
        self.playerBarVisible = visible
        self.slideDirection = None
        logger.info("[Player] slide %s: ARRIVED at y=%d visible=%s",
                    "up" if visible else "down", y, visible)

    def slideUp(self):
        if self.playerBarVisible:
            self._restartBarHideTimer()
            return
        try:
            pos = self.instance.position()
            self.instance.move(ePoint(pos.x(), self.barVisibleY + self.slideStep * 3))
            logger.info("[Player] slideUp: starting (first frame painted)")
        except Exception:
            pass
        self.slideDirection = "up"
        self.slideTimer.start(10)
        self._applyColors()
        self._restartBarHideTimer()

    def slideDown(self):
        if not self.playerBarVisible:
            return
        try:
            self.barHideTimer.stop()
        except Exception:
            pass
        self.slideDirection = "down"
        self.slideTimer.start(10)

    def _restartBarHideTimer(self):
        try:
            if _pc.playerBarAutoHide.value:
                self.barHideTimer.start(_pc.playerBarHideSeconds.value * 1000, True)
            else:
                self.barHideTimer.stop()
        except Exception:
            pass

    def _autoHideBar(self):
        if self.playerBarVisible:
            self.slideDown()

    def togglePlayerBar(self):
        if self.manualSeekMode:
            self.manualSeekMode = False
            self["statusInfo"].setText("")
            return
        if self.playerBarVisible:
            self.slideDown()
        else:
            self.slideUp()

    # ---------------------------------------------------------- lifecycle
    def onFirstShow(self):
        try:
            self.onShown.remove(self.onFirstShow)
        except ValueError:
            pass
        logger.info("[Player] screen %dx%d (scale %.2f/%.2f) barVisibleY=%s barHiddenY=%s",
                    SCREEN_W, SCREEN_H, SCALE_W, SCALE_H, self.barVisibleY, self.barHiddenY)
        try:
            x_pos = (SCREEN_W - self.instance.size().width()) // 2
            self.instance.move(ePoint(x_pos, self.barHiddenY))
        except Exception as e:
            logger.warning("[Player] onFirstShow move failed: %s", e)
        self.playerBarVisible = False
        self._applyColors()
        self._applyPanelPixmaps()
        self._buildProgressPixmaps()
        self.playCurrent()
        self.updateTimer.start(500, False)
        self.saveTimer.start(30000, False)

    def onClosePlayer(self):
        try:
            self._exitTimer.stop()
        except Exception:
            pass
        for t in (self.updateTimer, self.saveTimer, self.slideTimer,
                  self.eofTimer, self.barHideTimer):
            try:
                t.stop()
            except Exception:
                pass
        try:
            self.savePlaybackPosition()
        except Exception:
            pass
        logger.info("[Player] close: stopping service")
        self.stopService()
        logger.info("[Player] close: service stopped")
        # FIX (r93): one-shot safety net for close paths that don't run
        # handleExit (RED Stop, end-of-playlist EOF).
        self._restoreLastService()
        try:
            if self["poster"].instance is not None:
                self["poster"].instance.setPixmap(None)
        except Exception:
            pass
        try:
            if self.subtitleHandler is not None:
                self.subtitleHandler.close()
        except Exception:
            pass
        self.subtitleHandler = None
        self.playlist.clear()
        KeymapManager.unload()

    # ---------------------------------------------------------- playback
    def playCurrent(self):
        item = self.playlist.getCurrent()
        if not item:
            self["statusInfo"].setText("No items in playlist")
            return False
        path, name, ref = item
        self.resumePosition = 0
        if _pc.playerResumePlayback.value:
            self.resumePosition = self.playlist.getPosition(path)
            if self.resumePosition > 30:
                self.session.openWithCallback(self.confirmResume, MessageBox,
                    "Resume playback from %s?" % formatTime(self.resumePosition),
                    MessageBox.TYPE_YESNO, timeout=10)
                return True
            self.resumePosition = 0
        return self.doPlayCurrent(item)

    def confirmResume(self, confirmed):
        if not confirmed:
            self.resumePosition = 0
        item = self.playlist.getCurrent()
        if item:
            self.doPlayCurrent(item)

    def doPlayCurrent(self, item):
        path, name, ref = item
        self.stopService()
        self.session.nav.playService(ref)
        self.currentService = self.session.nav.getCurrentService()
        if self.resumePosition > 0 and self.currentService:
            seek = self.currentService.seek()
            if seek:
                seek.seekTo(int(self.resumePosition * 90000))
        self["movieTitle"].setText(name)
        self.state = self.STATE_PLAYING
        # FIX (r95): attributes the vendored engine's autosub worker and
        # menu read off the player; gen bump kills stale workers.
        self.title = name
        self._item_url = path
        self._autosub_gen += 1
        self.subtitleHandler.setService(self.currentService)
        self.updateSubtitleIndicator()
        self.updatePlaylistInfo()
        self.loadPoster(path)
        self["statusInfo"].setText("Playing...")
        self.updateButtons()
        return True

    def stopService(self):
        if self.currentService:
            self.session.nav.stopService()
            self.currentService = None
        self.state = self.STATE_STOPPED

    def _captureLastServiceRef(self):
        try:
            ref = self.session.nav.getCurrentlyPlayingServiceReference()
            if ref is not None:
                return ref
        except Exception as e:
            logger.warning("[Player] last-service capture failed: %s", e)
        try:
            from Screens.InfoBar import InfoBar
            return InfoBar.instance.servicelist.getCurrentSelection()
        except Exception:
            return None

    def _restoreLastService(self):
        ref = getattr(self, "lastServiceRef", None)
        if ref is None:
            return False
        self.lastServiceRef = None
        try:
            self.session.nav.playService(ref)
            logger.info("[Player] exit: restored previous service: %s",
                        ref.toString())
            return True
        except Exception as e:
            logger.warning("[Player] restore previous service failed: %s", e)
            return False

    # ------------------------------------------------- r95: RED = TV exit
    def stop(self):
        """FIX (r95): RED now exits directly to TV (the earlier
        requirement 'keep red button as exit directly to tv channel').
        Stops playback, restores the pre-player service, closes - no
        confirmation dialog. EXIT keeps the r93 behaviour (return to
        the plugin's folder view)."""
        try:
            self.savePlaybackPosition()
        except Exception:
            pass
        self.stopService()
        self._restoreLastService()
        self.close()

    def confirmStop(self, confirmed):
        # Kept for API compatibility (hotkey maps / old callers); the
        # r95 stop() no longer routes through here.
        if confirmed:
            self.stopService()
            self._restoreLastService()
            self.close()

    def togglePlayPause(self):
        if not self.currentService:
            return
        if self.state == self.STATE_PLAYING:
            p = self.currentService.pause()
            if p is not None:
                p.pause()
                self.state = self.STATE_PAUSED
                self["statusInfo"].setText("Paused")
        elif self.state == self.STATE_PAUSED:
            p = self.currentService.pause()
            if p is not None:
                p.unpause()
                self.state = self.STATE_PLAYING
                self["statusInfo"].setText("Playing")
        self.updateButtons()
        if not self.playerBarVisible:
            self.slideUp()

    def nextTrack(self):
        item = self.playlist.getNext()
        if item:
            self.playCurrent()
        else:
            self["statusInfo"].setText("End of playlist")

    def previousTrack(self):
        self.playlist.getPrevious()
        self.playCurrent()

    # ------------------------------------------------------------ seeking
    def seek(self, seconds):
        if not self.currentService:
            return
        seek = self.currentService.seek()
        if not seek:
            return
        r = seek.getPlayPosition()
        current = (r[1] / 90000.0) if not r[0] else 0.0
        r2 = seek.getLength()
        length = (r2[1] / 90000.0) if not r2[0] else 0.0
        if length <= 0:
            return
        newPos = max(0.0, min(length, current + seconds))
        seek.seekTo(int(newPos * 90000))
        direction = "+" if seconds > 0 else "-"
        a = abs(seconds)
        if a >= 60:
            self["statusInfo"].setText("Seek %s %d min" % (direction, a // 60))
        else:
            self["statusInfo"].setText("Seek %s %d sec" % (direction, a))
        if not self.playerBarVisible:
            self.slideUp()

    def _jumpLabel(self):
        a = self.jumpSeconds
        return "Jump: %dm" % (a // 60) if a >= 60 else "Jump: %ds" % a

    def setJumpTime(self, seconds):
        self.jumpSeconds = seconds
        self["statusInfo"].setText(self._jumpLabel())
        self["jumpInfo"].setText(self._jumpLabel())
        try:
            _pc.playerJumpSeconds.value = seconds
            _pc.playerJumpSeconds.save()
        except Exception:
            pass

    def jumpToStart(self):
        if not self.currentService:
            return
        seek = self.currentService.seek()
        if seek:
            seek.seekTo(0)
            self["statusInfo"].setText("Jump to start")
        if not self.playerBarVisible:
            self.slideUp()

    def jumpToEnd(self):
        if not self.currentService:
            return
        seek = self.currentService.seek()
        if not seek:
            return
        r = seek.getLength()
        length = r[1] if not r[0] else 0
        if length > 0:
            seek.seekTo(length - (5 * 90000))
            self["statusInfo"].setText("Jump to end")
        if not self.playerBarVisible:
            self.slideUp()

    # ------------------------------------------------------------ subtitles
    def showSubtitleMenu(self):
        if not self.currentService:
            return
        # FIX (r95): construct the vendored menu helper (it opens its
        # own ChoiceBox; it is NOT a Screen). No setService call here -
        # it would re-run the auto-attach pipeline on every menu open.
        if SubtitleMenuScreen is not None:
            SubtitleMenuScreen(self.session, self)
        else:
            self.session.open(SubtitleSelectionScreen, self.subtitleHandler)
        if not self.playerBarVisible:
            self.slideUp()

    def _open_studio_overlay(self):
        # FIX (r95): "Studio settings" entry of the subtitle menu.
        if StudioSettingsScreen is not None:
            self.session.open(StudioSettingsScreen)

    def toggleSubtitles(self):
        if not self.currentService:
            return
        result = self.subtitleHandler.toggleSubtitles()
        self.updateSubtitleIndicator()
        self["statusInfo"].setText("Subtitles: %s" % ("ON" if result else "OFF"))
        logger.info("[Player] subtitles now %s", "ON" if result else "OFF")

    # ------------------------------------------------------------ menus
    def showMenu(self):
        menu = [
            ("Repeat: %s" % ("On" if self.playlist.repeat else "Off"), "repeat"),
            ("Shuffle: %s" % ("On" if self.playlist.shuffle else "Off"), "shuffle"),
            ("Show Time Remaining: %s" % ("On" if self.showTimeRemaining else "Off"), "time"),
            ("Show Progress Percent: %s" % ("On" if self.showProgressPercent else "Off"), "percent"),
            ("Jump Time: %s" % self._jumpLabel(), "jump"),
            ("Player Bar Position: %s" % ("Bottom" if _pc.playerBarPosition.value == 0 else "Top"), "position"),
            ("Audio Tracks", "audio"),
            ("Subtitle Tracks", "subtitle"),
            ("File Information", "info"),
            ("Player Help", "help"),
            ("Clear Resume Positions", "clear_resume"),
            ("Bar Auto-Hide: %s" % ("On" if _pc.playerBarAutoHide.value else "Off"), "barautohide"),
            ("Bar Hide Timeout: %d s" % _pc.playerBarHideSeconds.value, "barhidetimeout"),
            ("Sub Sync -1 s", "sync-1000"),
            ("Sub Sync -100 ms", "sync-100"),
            ("Sub Sync +100 ms", "sync+100"),
            ("Sub Sync +1 s", "sync+1000"),
            ("Sub Sync Reset", "syncreset"),
            ("Chapters / Jump Points", "chapters"),
            ("Run Self-Test", "selftest"),
            ("Progress Gates (r91)", "proggates"),
            ("Stop Playback", "stop"),
        ]
        self.session.openWithCallback(self.onMenuSelect, ChoiceBox,
                                      title="Player Menu", list=menu)
        if not self.playerBarVisible:
            self.slideUp()

    def onMenuSelect(self, choice):
        if not choice:
            return
        action = choice[1]
        try:
            if action == "repeat":
                self.playlist.repeat = not self.playlist.repeat
                _pc.playerRepeatPlaylist.value = self.playlist.repeat
                _pc.playerRepeatPlaylist.save()
            elif action == "shuffle":
                self.playlist.shuffle = not self.playlist.shuffle
                _pc.playerShufflePlaylist.value = self.playlist.shuffle
                _pc.playerShufflePlaylist.save()
            elif action == "time":
                self.showTimeRemaining = not self.showTimeRemaining
                _pc.playerShowTimeRemaining.value = self.showTimeRemaining
                _pc.playerShowTimeRemaining.save()
            elif action == "percent":
                self.showProgressPercent = not self.showProgressPercent
                _pc.playerShowProgressPercent.value = self.showProgressPercent
                _pc.playerShowProgressPercent.save()
            elif action == "jump":
                self._chooseJumpTime()
            elif action == "position":
                new_pos = 1 if _pc.playerBarPosition.value == 0 else 0
                _pc.playerBarPosition.value = new_pos
                _pc.playerBarPosition.save()
                self["statusInfo"].setText("Restart player for position change")
            elif action == "audio":
                self.showAudioMenu()
            elif action == "subtitle":
                self.showSubtitleMenu()
            elif action == "info":
                self.showFileInfo()
            elif action == "help":
                self.showHelp()
            elif action == "clear_resume":
                self.playlist.playback_positions.clear()
                self["statusInfo"].setText("Resume positions cleared")
            elif action == "barautohide":
                _pc.playerBarAutoHide.value = not _pc.playerBarAutoHide.value
                _pc.playerBarAutoHide.save()
                self["statusInfo"].setText("Bar auto-hide: %s" % ("On" if _pc.playerBarAutoHide.value else "Off"))
                if not self.playerBarVisible:
                    self.slideUp()
            elif action == "barhidetimeout":
                opts = [("%d s" % s, s) for s in (3, 5, 8, 10, 15)]
                self.session.openWithCallback(self._barTimeoutChosen, ChoiceBox,
                                              title="Bar hide timeout", list=opts)
            elif action.startswith("sync"):
                if action == "syncreset":
                    self.subtitleHandler.resetDelay()
                    self["statusInfo"].setText("Sub sync reset")
                else:
                    d = self.subtitleHandler.adjustDelay(int(action[4:]))
                    self["statusInfo"].setText("Sub sync: %+d ms" % d)
                self.updateSubtitleIndicator()
            elif action == "chapters":
                self._showChapters()
            elif action == "selftest":
                self._runSelfTest()
            elif action == "proggates":
                self._runProgressGates()
            elif action == "stop":
                self.stop()
        except Exception as e:
            logger.error("Player menu action '%s' failed: %s" % (action, e))

    def _chooseJumpTime(self):
        options = [(self._jumpLabelFor(s), s) for s in (10, 30, 60, 120, 300, 600)]
        self.session.openWithCallback(self._jumpChosen, ChoiceBox,
                                      title="Select jump time", list=options)

    @staticmethod
    def _jumpLabelFor(seconds):
        return "%d sec" % seconds if seconds < 60 else "%d min" % (seconds // 60)

    def _jumpChosen(self, choice):
        if choice:
            self.setJumpTime(choice[1])

    def _barTimeoutChosen(self, choice):
        if choice:
            _pc.playerBarHideSeconds.value = choice[1]
            _pc.playerBarHideSeconds.save()
            self["statusInfo"].setText("Bar hides after %d s" % choice[1])

    # ------------------------------------------------------------ audio/info
    def showAudioMenu(self):
        try:
            self.session.open(AudioSelection, self)
        except Exception as e:
            logger.warning("Audio selection failed: %s" % e)
            self["statusInfo"].setText("Audio selection not available")
        if not self.playerBarVisible:
            self.slideUp()

    def getCurrentService(self):
        return self.session.nav.getCurrentService()

    def getCurrentlyPlayingServiceReference(self):
        return self.session.nav.getCurrentlyPlayingServiceReference()

    def showFileInfo(self):
        item = self.playlist.getCurrent()
        if not item:
            return
        path, name, ref = item
        info = []
        info.append("File: %s" % name)
        info.append("Path: %s" % os.path.dirname(path))
        try:
            size = os.path.getsize(path)
            if size < 1024 * 1024:
                info.append("Size: %.1f KB" % (size / 1024.0))
            else:
                info.append("Size: %.2f MB" % (size / (1024.0 * 1024.0)))
            ext = os.path.splitext(name)[1].upper()
            info.append("Type: %s" % (ext[1:] if len(ext) > 1 else "Unknown"))
        except Exception:
            pass
        try:
            subs = self.subtitleHandler.getSubtitleList()
            if len(subs) > 1:
                info.append("")
                info.append("Subtitles:")
                for sub, label, lang, trackId, isActive in subs[1:]:
                    marker = "* " if isActive else "  "
                    info.append(marker + label)
            else:
                info.append("")
                info.append("No subtitles found")
        except Exception:
            pass
        resume_pos = self.playlist.getPosition(path)
        if resume_pos > 0:
            info.append("")
            info.append("Resume position: %s" % formatTime(resume_pos))
        self.session.open(MessageBox, "\n".join(info), MessageBox.TYPE_INFO, timeout=10)
        if not self.playerBarVisible:
            self.slideUp()

    def showHelp(self):
        self.session.open(PlayerHelpScreen)

    # ------------------------------------------------------------ chapters
    def _showChapters(self):
        try:
            points = self._extractChapters()
            if not points:
                r2 = None
                try:
                    seek = self.session.nav.getCurrentService().seek()
                    if seek:
                        r2 = seek.getLength()
                except Exception:
                    pass
                duration = (r2[1] / 90000.0) if (r2 and not r2[0]) else 0
                if duration > 60:
                    marks = [("Start", 0.0),
                             ("1st Quarter", duration * 0.25),
                             ("Halfway", duration * 0.5),
                             ("3rd Quarter", duration * 0.75),
                             ("End", max(0.0, duration - 10))]
                    points = [(self._fmt_label(n, t), int(t * 90000)) for n, t in marks]
            try:
                item = self.playlist.getCurrent()
                if item:
                    rp = self.playlist.getPosition(item[0])
                    if rp > 30:
                        points.append(("Resume Point (%s)" % formatTime(rp), int(rp * 90000)))
            except Exception:
                pass
            if not points:
                self["statusInfo"].setText("No chapters")
                return
            self.session.openWithCallback(self._chapterChosen, ChoiceBox,
                                          title="Jump to", list=points)
        except Exception as e:
            logger.error("[Player] chapters failed: %s", e)

    def _extractChapters(self):
        points = []
        try:
            item = self.playlist.getCurrent()
            if not item:
                return points
            cmd = ["ffprobe", "-loglevel", "0", "-of", "json",
                   "-show_chapters", item[0]]
            kwargs = {}
            if sys.version_info[0] >= 3:
                kwargs["timeout"] = 10
            out = subprocess.check_output(cmd, **kwargs).decode("utf-8", "replace")
            for ch in json.loads(out).get("chapters", []):
                try:
                    st = float(ch.get("start_time", 0))
                    if st > 0:
                        name = ch.get("tags", {}).get("title", "")
                        points.append((self._fmt_label(name, st), int(st * 90000)))
                except Exception:
                    continue
        except Exception:
            pass
        return points

    @staticmethod
    def _fmt_label(name, t):
        label = name if name else "Chapter"
        return "%s   %s" % (label, formatTime(t))

    def _chapterChosen(self, choice):
        if not choice:
            return
        pts = choice[1]
        try:
            seek = self.session.nav.getCurrentService().seek()
            if seek:
                seek.seekTo(pts)
                self["statusInfo"].setText("Jumped to %s" % formatTime(pts / 90000.0))
        except Exception as e:
            logger.warning("[Player] chapter seek failed: %s", e)

    # ------------------------------------------------------------ self-test
    def _runSelfTest(self):
        originalIndex = self.playlist.currentIndex
        originalState = self.state
        originalSub = self.subtitleHandler.selectedSubtitle if self.subtitleHandler else None
        originalDelay = self.subtitleHandler.currentDelay if self.subtitleHandler else 0
        originalPos = 0.0
        try:
            seek = self.currentService.seek() if self.currentService else None
            if seek:
                r = seek.getPlayPosition()
                if not r[0]:
                    originalPos = r[1] / 90000.0
        except Exception:
            pass

        results = []

        def t(name, fn):
            try:
                r = fn()
                results.append((name, "OK" if r is not False else "returned False"))
            except Exception as e:
                results.append((name, "FAIL: %s" % e))

        t("pause-toggle", self.togglePlayPause)
        t("seek-30s", lambda: self.seek(-30))
        t("seek+300s", lambda: self.seek(300))
        t("jump-start", self.jumpToStart)
        t("jump-end", self.jumpToEnd)
        t("set-jump-10s", lambda: self.setJumpTime(10))
        t("sub-toggle", self.toggleSubtitles)
        t("sub-sync+100", lambda: self.subtitleHandler.adjustDelay(100))
        t("sub-sync-reset", self.subtitleHandler.resetDelay)
        t("bar-show", self.slideUp)
        t("next-track", self.nextTrack)
        t("prev-track", self.previousTrack)
        t("file-info-data", lambda: self.playlist.getCurrent() is not None)
        t("progress-geom", lambda: bool(getattr(self, "_progGeom", None)))
        t("colors-capable", lambda: self._applyColors() or True)

        try:
            self.playlist.currentIndex = originalIndex
            if self.state != originalState:
                if originalState == self.STATE_PLAYING and self.state == self.STATE_PAUSED:
                    try:
                        self.togglePlayPause()
                    except Exception:
                        pass
                elif originalState == self.STATE_PAUSED and self.state == self.STATE_PLAYING:
                    try:
                        self.togglePlayPause()
                    except Exception:
                        pass
            if self.currentService and originalPos > 0:
                seek = self.currentService.seek()
                if seek:
                    seek.seekTo(int(originalPos * 90000))
            if self.subtitleHandler is not None:
                try:
                    self.subtitleHandler.currentDelay = originalDelay
                    self.subtitleHandler.selectedSubtitle = originalSub
                    fn = getattr(self.subtitleHandler, "_applySubtitleDelay", None) \
                        or getattr(self.subtitleHandler, "_apply_sync", None)
                    if callable(fn):
                        fn()
                except Exception:
                    pass
        except Exception as e:
            logger.warning("[Player] self-test restore failed: %s", e)

        for name, res in results:
            logger.info("[Player] SELF-TEST %-16s %s", name, res)
        ok = sum(1 for _, r in results if r == "OK")
        try:
            self["statusInfo"].setText("Self-test: %d/%d OK (see log)" % (ok, len(results)))
        except Exception:
            pass
        logger.info("[Player] SELF-TEST SUMMARY: %d/%d OK", ok, len(results))

    # ------------------------------------------------------------ folder play
    def _playWholeFolder(self):
        try:
            item = self.playlist.getCurrent()
            if not item:
                return
            d = os.path.dirname(item[0])
            logger.info("[Player] folder play (from player): %s", d)
            new_pl = PlaylistManager()
            if new_pl.addDirectory(d):
                new_pl.setIndex(0)
                self.playlist = new_pl
                self.updatePlaylistInfo()
                self.playCurrent()
                self["statusInfo"].setText("Folder playlist: %d files" % len(new_pl))
        except Exception as e:
            logger.error("[Player] folder play failed: %s", e)

    # ------------------------------------------------------------ updates
    def _updateVideoInfo(self, service):
        try:
            info = service.info()
            text = ""
            if info is not None:
                try:
                    w = info.getInfo(iServiceInformation.sVideoWidth)
                    h = info.getInfo(iServiceInformation.sVideoHeight)
                    if w and h and w > 0:
                        text = "%dx%d" % (w, h)
                except Exception:
                    pass
                try:
                    fps = info.getInfo(iServiceInformation.sFrameRate)
                    if fps and fps > 0:
                        if fps > 1000:
                            fps = fps // 1000
                        text += "  %dfps" % fps if text else "%dfps" % fps
                except Exception:
                    pass
                try:
                    ar = info.getInfo(iServiceInformation.sAspect)
                    if ar and ar > 0:
                        ratios = {1: "4:3", 2: "16:9", 3: "14:9", 4: "2.21", 5: "20:9"}
                        label = ratios.get(ar, "%d" % ar)
                        text += "  %s" % label if text else label
                except Exception:
                    pass
            if text != getattr(self, "_lastVideoInfo", None):
                self._lastVideoInfo = text
                self["videoInfo"].setText(text)
        except Exception:
            pass

    def _updateClock(self):
        try:
            from datetime import datetime as _dt
            self["clock"].setText(_dt.now().strftime("%H:%M:%S"))
        except Exception:
            pass

    def updateInfo(self):
        try:
            service = self.session.nav.getCurrentService()
            if not service:
                return
            seek = service.seek()
            if not seek:
                return
            r = seek.getPlayPosition()
            if r[0]:
                return
            pos_s = r[1] / 90000.0
            r2 = seek.getLength()
            len_s = (r2[1] / 90000.0) if not r2[0] else 0.0
            self._updateVideoInfo(service)
            self._updateClock()
            self["currentTime"].setText(formatTime(pos_s))
            self["totalTime"].setText(formatTime(len_s))
            if self.showTimeRemaining and len_s:
                self["remainingTime"].setText("-%s" % formatTime(max(0, len_s - pos_s)))
            else:
                self["remainingTime"].setText("")
            if len_s > 0:
                pct = min(100, max(0, int(pos_s * 100 / len_s)))
                if self.showProgressPercent:
                    self["progressPercent"].setText("%d%%" % pct)
                else:
                    self["progressPercent"].setText("")
                self._setProgressFill(pct)
                self._moveProgressMarker(pos_s, len_s)
        except Exception:
            pass

    def updateButtons(self):
        self["keyGreen"].setText("Pause" if self.state == self.STATE_PLAYING else "Play")

    def updateSubtitleIndicator(self):
        try:
            if self.subtitleHandler and self.subtitleHandler.isEnabled():
                sel = self.subtitleHandler.selectedSubtitle
                if self.subtitleHandler._is_string(sel):
                    txt = "SUB: %s" % os.path.basename(sel)[:18]
                else:
                    txt = "SUB: embedded"
                d = getattr(self.subtitleHandler, "currentDelay", 0)
                if d:
                    txt += " %+dms" % d
            else:
                txt = "SUB: off"
            self["subtitleIndicator"].setText(txt)
        except Exception:
            pass

    def updatePlaylistInfo(self):
        n = len(self.playlist)
        if n > 1:
            self["playlistInfo"].setText("%d/%d" % (self.playlist.currentIndex + 1, n))
        else:
            self["playlistInfo"].setText("")

    def loadPoster(self, path):
        try:
            d = os.path.dirname(path)
            base = os.path.splitext(os.path.basename(path))[0]
            candidates = ["cover.jpg", "cover.png", "poster.jpg", "poster.png",
                          base + ".jpg", base + ".png"]
            for c in candidates:
                p = os.path.join(d, c)
                if os.path.exists(p):
                    pix = LoadPixmap(p)
                    if pix is not None and self["poster"].instance is not None:
                        self["poster"].instance.setPixmap(pix)
                        return
            inst = self["poster"].instance
            if inst is not None:
                inst.resize(eSize(0, 0))
        except Exception:
            pass

    def savePlaybackPosition(self):
        try:
            if not self.currentService or not _pc.playerRememberPosition.value:
                return
            seek = self.currentService.seek()
            if not seek:
                return
            r = seek.getPlayPosition()
            if r[0]:
                return
            current = r[1] / 90000.0
            r2 = seek.getLength()
            length = (r2[1] / 90000.0) if not r2[0] else 0.0
            if current < 30 or (length > 0 and current > length - 30):
                return
            now = _time_mod.time()
            if now - getattr(self, "lastPositionSaveTime", 0) < 10:
                return
            item = self.playlist.getCurrent()
            if item:
                self.playlist.savePosition(item[0], current)
                self.lastPositionSaveTime = now
        except Exception:
            pass

    # ------------------------------------------------------------ exit/EOF
    def handleExit(self):
        try:
            self.savePlaybackPosition()
        except Exception:
            pass
        try:
            logger.info("[Player] exit: stopping service")
            self.stopService()
        except Exception as e:
            logger.warning("[Player] exit: stop failed: %s", e)
        # FIX (r93): zap back NOW - don't wait for the deferred close
        # 200 ms later. This replaces the frozen movie frame with the
        # live picture immediately.
        self._restoreLastService()
        if not hasattr(self, "_exitTimer"):
            self._exitTimer = eTimer()

            def _closeOnce():
                if not getattr(self, "_wgClosed", False):
                    self._wgClosed = True
                    logger.info("[Player] exit: closing screen")
                    self.close()

            self._exitCloseOnce = _closeOnce
            _connect_timer_once(self._exitTimer, _closeOnce)
        self._exitTimer.start(200, True)

    def _onEOF(self):
        logger.info("[Player] end of file")
        self.eofTimer.start(300, True)

    def _eofAdvance(self):
        try:
            if len(self.playlist) > 1 and (self.playlist.repeat or
                                          self.playlist.currentIndex < len(self.playlist) - 1):
                self.nextTrack()
            else:
                self.close()
        except Exception as e:
            logger.error("[Player] EOF advance failed: %s", e)
            try:
                self.close()
            except Exception:
                pass


# ============================================================================
# Public player class
# ============================================================================
class CustomMediaPlayer(_CustomMediaPlayerBase):
    """WGFileManager's player (AjPanel-style)."""


# ============================================================================
# Convenience functions
# ============================================================================
def playFile(session, filePath):
    try:
        if not os.path.exists(filePath):
            session.open(MessageBox, "File not found:\n%s" % filePath, MessageBox.TYPE_ERROR)
            return
        ext = os.path.splitext(filePath)[1].lower()
        if not any(fnmatch.fnmatch('*' + ext, p) for p in MEDIA_EXTENSIONS):
            session.open(MessageBox, "Unsupported file format: %s" % ext, MessageBox.TYPE_WARNING)
            return
        session.open(CustomMediaPlayer, filePath=filePath)
    except Exception as e:
        logger.error("Error playing file %s: %s" % (filePath, str(e)))
        session.open(MessageBox, "Cannot play file:\n%s" % str(e), MessageBox.TYPE_ERROR)


def playPlaylist(session, fileList, startIndex=0):
    try:
        playlist = PlaylistManager()
        for f in fileList:
            if os.path.exists(f) and os.access(f, os.R_OK):
                playlist.addFile(f)
            else:
                logger.warning("Skipping invalid file: %s" % f)
        if len(playlist) > 0:
            session.open(CustomMediaPlayer, playlist=playlist, startIndex=startIndex)
        else:
            session.open(MessageBox, "No valid media files to play", MessageBox.TYPE_ERROR)
    except Exception as e:
        logger.error("Error playing playlist: %s" % str(e))
        session.open(MessageBox, "Error playing files:\n%s" % str(e), MessageBox.TYPE_ERROR)


def playDirectory(session, dirPath, recursive=False):
    try:
        if not os.path.isdir(dirPath):
            session.open(MessageBox, "Not a directory:\n%s" % dirPath, MessageBox.TYPE_ERROR)
            return
        playlist = PlaylistManager()
        if playlist.addDirectory(dirPath, recursive):
            session.open(CustomMediaPlayer, playlist=playlist)
        else:
            session.open(MessageBox, "No media files found", MessageBox.TYPE_INFO)
    except Exception as e:
        logger.error("Error playing directory %s: %s" % (dirPath, str(e)))
        session.open(MessageBox, "Error scanning directory:\n%s" % str(e), MessageBox.TYPE_ERROR)


def cleanupPlayer():
    KeymapManager._reference_count = 0
    KeymapManager.unload()