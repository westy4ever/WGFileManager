# -*- coding: utf-8 -*-
"""SubtitleManager - orchestrates auto-attach, memory, Studio, providers.

Keeps the old SubtitleHandler surface (setService / toggleSubtitles /
adjustDelay / resetDelay / isEnabled / selectedSubtitle / currentDelay /
getSubtitleList / close) so the player and hotkey_manager work unchanged.
"""
import json
import os
import re
import threading

from enigma import eTimer, eServiceReference

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from . import srt
from .providers import SubSourceProvider, OpenSubtitlesProvider
from .studio import SubtitleStudioScreen, DEFAULT_STYLE

SUB_EXTS = (".srt", ".ass", ".ssa", ".sub", ".txt")
STATE_DIR = "/media/hdd/WGFileManager/subtitles"
CACHE_DIR = "/media/hdd/WGFileManager/cache/subsource"
MEMORY_FILE = "/media/hdd/WGFileManager/cache/subtitle_memory.json"
STATE_FILE = STATE_DIR + "/state.json"
STREAM_REF_TYPES = ("4097", "5001", "5002", "8193")

DEFAULT_STATE = {
    "subsource_key": "", "opensub_key": "", "opensub_user": "",
    "opensub_pass": "", "subtitle_folder": "/media/hdd/subtitles",
    "auto_attach": True, "studio": True, "skip_intro": 90,
    "style": dict(DEFAULT_STYLE), "presets": {},
}


def _load_json(path, fallback):
    try:
        with open(path, "r") as f:
            v = json.load(f)
        if isinstance(v, dict):
            return v
    except Exception:
        pass
    return fallback


def _save_json(path, data):
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("[Sub] save %s failed: %s", path, e)


def _connect_once(timer, cb):
    try:
        timer.timeout.connect(cb)
        return True
    except Exception:
        pass
    try:
        timer.callback.append(cb)
        return True
    except Exception:
        return False


class SubtitleManager(object):
    def __init__(self, session, player=None):
        self.session = session
        self.player = player
        self.state = _load_json(STATE_FILE, dict(DEFAULT_STATE))
        if "style" not in self.state:
            self.state["style"] = dict(DEFAULT_STYLE)
        self.memory = _load_json(MEMORY_FILE, {})
        self.subtitleList = []
        self.externalSubtitles = []
        self.selectedSubtitle = None
        self.enabled = False
        self.currentDelay = 0
        self.mode = None          # "studio" | "service" | "embedded"
        self._studio = None
        self._timers = []
        self._closed = False
        self._subsource = SubSourceProvider(self.state)
        self._opensub = OpenSubtitlesProvider(self.state)

    # ------------------------------------------------------- compat API
    @staticmethod
    def _is_string(obj):
        return isinstance(obj, str) or isinstance(obj, getattr(__builtins__, "unicode", str))

    def isEnabled(self):
        return self.enabled

    def close(self):
        self._closed = True
        for t in self._timers:
            try:
                t.stop()
            except Exception:
                pass
        self._timers = []
        self._hide_studio()
        self.subtitleList = []
        self.externalSubtitles = []

    # ------------------------------------------------------------ state
    def save_state(self):
        _save_json(STATE_FILE, self.state)

    def _remember(self, video, sub, delay):
        if not video:
            return
        self.memory[video] = {"sub": sub or "", "delay": int(delay or 0)}
        if len(self.memory) > 400:
            k = next(iter(self.memory))
            del self.memory[k]
        _save_json(MEMORY_FILE, self.memory)

    def _video_path(self):
        try:
            ref = self.session.nav.getCurrentlyPlayingServiceReference()
            if ref and ref.getPath():
                return ref.getPath()
        except Exception:
            pass
        return ""

    # ----------------------------------------------------------- studio
    def _ensure_studio(self):
        if self._studio is None:
            self._studio = self.session.instantiateDialog(SubtitleStudioScreen)
            self._studio.hide()
        return self._studio

    def _hide_studio(self):
        if self._studio is not None:
            try:
                self._studio.hide()
                self._studio.doClose()
            except Exception:
                pass
            self._studio = None

    def studio_on(self):
        return bool(self.state.get("studio", True))

    # ------------------------------------------------------- background
    def _bg(self, fn, cb):
        box = {"done": False, "res": None}

        def work():
            try:
                box["res"] = fn()
            except Exception as e:
                box["res"] = e
            box["done"] = True
        threading.Thread(target=work).start()
        t = eTimer()

        def poll():
            if box["done"]:
                t.stop()
                if not self._closed:
                    cb(box["res"])
        _connect_once(t, poll)
        t.start(300, False)
        self._timers.append(t)

    def _later(self, ms, fn):
        t = eTimer()
        _connect_once(t, fn)
        t.start(ms, True)
        self._timers.append(t)

    # ------------------------------------------------------- setService
    def setService(self, service):
        for t in self._timers:
            try:
                t.stop()
            except Exception:
                pass
        self._timers = []
        self.enabled = False
        self.selectedSubtitle = None
        self.currentDelay = 0
        self.mode = None
        self.subtitleList = []
        self.externalSubtitles = []
        if self._studio is not None:
            try:
                self._studio.set_cues([])
            except Exception:
                pass
        if not service:
            return

        self._scan_embedded()
        self._scan_external()

        # Deferred rescan + auto-attach pipeline.
        def _rescan():
            self._scan_embedded()
            self._scan_external()
            self._auto_attach()
        self._later(2000, _rescan)
        self._later(1200, self._auto_attach)

    def _scan_embedded(self):
        try:
            svc = self.session.nav.getCurrentService()
            if svc:
                sub = svc.subtitle()
                if sub:
                    self.subtitleList = sub.getSubtitleList() or []
        except Exception:
            self.subtitleList = []

    def _scan_external(self):
        vp = self._video_path()
        if not vp or not os.path.exists(vp):
            return
        d = os.path.dirname(vp)
        stem = os.path.splitext(os.path.basename(vp))[0]
        found = []
        for root in [d] + [os.path.join(d, s) for s in ("subtitles", "Subs", "Sub")]:
            if not os.path.isdir(root):
                continue
            try:
                for f in os.listdir(root):
                    if f.lower().endswith(SUB_EXTS) and \
                            f.lower().startswith(stem.lower()[:8]):
                        found.append(os.path.join(root, f))
            except Exception:
                continue
        self.externalSubtitles = sorted(found)

    def best_sidecar(self):
        vp = self._video_path()
        if not vp:
            return None
        best, bs = None, None
        for p in self.externalSubtitles:
            s = srt.score(os.path.basename(vp), os.path.basename(p))
            if bs is None or s > bs:
                best, bs = p, s
        if best is not None and bs is not None and bs > 0:
            return best
        return None

    def _auto_attach(self):
        if self._closed or self.enabled:
            return
        vp = self._video_path()
        if not vp:
            return
        mem = self.memory.get(vp)
        if mem:
            sub, delay = mem.get("sub", ""), mem.get("delay", 0)
            self.currentDelay = int(delay or 0)
            if sub == "embedded" and self.subtitleList:
                if self._enable_embedded(self.subtitleList[0]):
                    return
            elif sub and os.path.exists(sub):
                if self.attach(sub):
                    return
        best = self.best_sidecar()
        if best:
            self.attach(best)
            return
        if self.state.get("auto_attach", True) and self.state.get("subsource_key"):
            self._search_attach_silent()

    def _search_attach_silent(self):
        vp = self._video_path()
        if not vp:
            return
        stem = os.path.splitext(os.path.basename(vp))[0]
        stem = re.sub(r"[\._]", " ", stem)

        def work():
            return self._subsource.search(stem)
        self._bg(work, self._silent_pick)

    def _silent_pick(self, results):
        if self._closed or self.enabled:
            return
        if isinstance(results, Exception) or not results:
            logger.info("[Sub] auto-search: no result")
            return
        result = results[0]
        self._download_to_cache(result, lambda p: p and self.attach(p))

    # ------------------------------------------------------------ attach
    def attach(self, path, remember=True):
        """Attach an external subtitle file (Studio or service layer)."""
        if not path or not os.path.exists(path):
            return False
        ext = os.path.splitext(path)[1].lower()
        if self.studio_on() and ext in (".srt", ".txt"):
            try:
                text, _enc = srt.read_text(path)
                cues = srt.parse_srt(text)
            except Exception as e:
                logger.warning("[Sub] parse failed %s: %s", path, e)
                cues = []
            if cues:
                st = self._ensure_studio()
                st.refresh_style(self.state.get("style"))
                st.set_delay(self.currentDelay)
                st.set_cues(cues)
                st.show()
                self.mode = "studio"
                self.enabled = True
                self.selectedSubtitle = path
                if remember:
                    self._remember(self._video_path(), path, self.currentDelay)
                logger.info("[Sub] Studio attached: %s (%d cues)", path, len(cues))
                return True
            # fall through to service layer on parse failure
        if ext in SUB_EXTS:
            ok = self._attach_service(path)
            if ok:
                self.mode = "service"
                self.selectedSubtitle = path
                if remember:
                    self._remember(self._video_path(), path, self.currentDelay)
            return ok
        return False

    def _attach_service(self, subPath):
        """Image-independent external attach: replay ref with |sub."""
        try:
            currentRef = self.session.nav.getCurrentlyPlayingServiceReference()
            if not currentRef:
                return False
            rs = currentRef.toString()
            rt = rs.split(":", 1)[0] if ":" in rs else ""
            if rt not in STREAM_REF_TYPES:
                logger.warning("[Sub] service attach needs stream ref (got %s)", rt)
                return False
            pos = 0
            svc = self.session.nav.getCurrentService()
            if svc:
                sk = svc.seek()
                if sk:
                    r = sk.getPlayPosition()
                    if not r[0]:
                        pos = r[1]
            newRef = eServiceReference(4097, 0, currentRef.getPath() + "|" + subPath)
            newRef.setName(currentRef.getName())
            self.session.nav.playService(newRef)
            if pos:
                def restore():
                    svc2 = self.session.nav.getCurrentService()
                    if svc2:
                        sk2 = svc2.seek()
                        if sk2:
                            sk2.seekTo(pos)
                self._later(1000, restore)
            self.enabled = True
            return True
        except Exception as e:
            logger.error("[Sub] service attach failed: %s", e)
            return False

    def _enable_embedded(self, subtitle):
        try:
            svc = self.session.nav.getCurrentService()
            if not svc:
                return False
            ss = svc.subtitle()
            if not ss:
                return False
            for args in ((subtitle, True), (subtitle,),):
                try:
                    ss.enableSubtitles(*args)
                    self.enabled = True
                    self.mode = "embedded"
                    self.selectedSubtitle = subtitle
                    self._remember(self._video_path(), "embedded", self.currentDelay)
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
            return self.disable()
        if isinstance(subtitle, str) and os.path.exists(subtitle):
            return self.attach(subtitle)
        return self._enable_embedded(subtitle)

    def disable(self):
        self.enabled = False
        self.selectedSubtitle = None
        self.mode = None
        if self._studio is not None:
            try:
                self._studio.set_cues([])
                self._studio.hide()
            except Exception:
                pass
        try:
            svc = self.session.nav.getCurrentService()
            if svc:
                ss = svc.subtitle()
                if ss:
                    ss.disableSubtitles()
        except Exception:
            pass
        return True

    def toggleSubtitles(self):
        if self.enabled:
            self.disable()
            return False
        if self.selectedSubtitle and isinstance(self.selectedSubtitle, str) \
                and os.path.exists(self.selectedSubtitle):
            if self.attach(self.selectedSubtitle):
                return True
        best = self.best_sidecar()
        if best and self.attach(best):
            return True
        if self.subtitleList and self._enable_embedded(self.subtitleList[0]):
            return True
        if self.externalSubtitles and self.attach(self.externalSubtitles[0]):
            return True
        return False

    # ------------------------------------------------------------- sync
    def adjustDelay(self, offset):
        self.currentDelay += int(offset)
        self._apply_sync()
        return self.currentDelay

    def resetDelay(self):
        self.currentDelay = 0
        self._apply_sync()
        return 0

    def _apply_sync(self):
        if self.mode == "studio" and self._studio is not None:
            self._studio.set_delay(self.currentDelay)  # live, no file churn
        elif self.mode == "service" and isinstance(self.selectedSubtitle, str):
            # Image-independent: write a shifted copy and re-attach.
            try:
                text, _ = srt.read_text(self.selectedSubtitle)
                shifted = srt.shifted_copy_text(text, self.currentDelay)
                if shifted:
                    stem = re.sub(r'[^A-Za-z0-9_.-]', '_',
                                  os.path.basename(self.selectedSubtitle))[:50]
                    p = os.path.join(CACHE_DIR, "%s_sync%d.srt"
                                     % (stem, self.currentDelay))
                    if not os.path.isdir(CACHE_DIR):
                        os.makedirs(CACHE_DIR)
                    with open(p, "w") as f:
                        f.write(shifted.encode("utf-8"))
                    self._attach_service(p)
            except Exception as e:
                logger.warning("[Sub] sync shift failed: %s", e)
        self._remember(self._video_path(),
                       "embedded" if self.mode == "embedded" else self.selectedSubtitle,
                       self.currentDelay)

    # ---------------------------------------------------------- search
    def search(self, provider_id, query, cb):
        prov = self._subsource if provider_id == "subsource" else self._opensub
        stem = re.sub(r"[\._]", " ", query)

        def work():
            return prov.search(stem)
        self._bg(work, cb)

    def download_and_attach(self, result, cb=None):
        def done(path):
            ok = bool(path and self.attach(path))
            if cb:
                cb(ok)
        self._download_to_cache(result, done)

    def _download_to_cache(self, result, cb):
        prov = self._subsource if result["provider"] == "subsource" else self._opensub

        def work():
            text = prov.download(result)
            if not os.path.isdir(CACHE_DIR):
                os.makedirs(CACHE_DIR)
            safe = re.sub(r'[^A-Za-z0-9_.-]', '_', result["label"])[:60]
            p = os.path.join(CACHE_DIR, "%s.srt" % safe)
            with open(p, "w") as f:
                f.write(text.encode("utf-8"))
            return p
        self._bg(work, lambda p: cb(None if isinstance(p, Exception) else p))

    def list_local(self):
        """Current video dir + one level of subfolders; [BEST] first."""
        vp = self._video_path()
        if not vp:
            return []
        d = os.path.dirname(vp)
        out = []
        for root, dirs, files in os.walk(d):
            if root.count(os.sep) - d.count(os.sep) > 1:
                dirs[:] = []
                continue
            for f in files:
                if f.lower().endswith(SUB_EXTS):
                    out.append(os.path.join(root, f))
        scored = sorted(out, key=lambda p: -srt.score(os.path.basename(vp),
                                                      os.path.basename(p)))
        items = []
        best = self.best_sidecar()
        for p in scored:
            label = os.path.basename(p)
            if p == best:
                label = "[BEST] " + label
            items.append((label, p))
        return items

    # ------------------------------------------------------------ misc
    def getSubtitleList(self):
        """Compat surface for the player's file-info screen."""
        result = [(None, "Disabled", "", "", False)]
        for sub in self.subtitleList:
            pid = sub[1] if len(sub) > 1 else 0
            lang = sub[4] if len(sub) > 4 else "und"
            result.append((sub, "Embedded - %s" % lang, lang, str(pid),
                           self.selectedSubtitle == sub))
        for p in self.externalSubtitles:
            result.append((p, "External - %s" % os.path.basename(p), "", p,
                           self.selectedSubtitle == p))
        return result

    def clear_cache(self):
        try:
            if os.path.isdir(CACHE_DIR):
                for f in os.listdir(CACHE_DIR):
                    try:
                        os.remove(os.path.join(CACHE_DIR, f))
                    except Exception:
                        pass
            if os.path.exists(MEMORY_FILE):
                os.remove(MEMORY_FILE)
        except Exception as e:
            logger.warning("[Sub] clear cache: %s", e)
        self.memory = {}
        self.disable()
