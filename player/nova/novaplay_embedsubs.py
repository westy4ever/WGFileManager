# -*- coding: utf-8 -*-
"""Built-in subtitle tracks (inside an .mkv / .mp4) -> an .srt the Studio draws.

Enigma2 draws a track inside the video itself, so the Studio can't sync or
style it. Here ffmpeg (on the box: /usr/bin/ffmpeg, `opkg install ffmpeg`)
lists the video's subtitle tracks and copies one TEXT track (SRT / ASS /
WebVTT / mp4 text) out to an .srt in the subtitle cache; the player then
loads that file like a downloaded subtitle, so SYNC TO AUDIO, FINE SYNC and
every style work, and it comes back next time like any remembered subtitle.

Picture subtitles (Blu-ray PGS, DVD, DVB) are images, not text: they are
listed but can't be copied out.

Only local files (a path on the box): a stream would have to be downloaded
whole to reach its subtitles.

    find_ffmpeg()                     path or ""
    local_source(url)                 the local file behind a play address, or ""
    probe(path) / tracks(path)        list the tracks (background) / the result, None while reading
    Extraction(path, index)           copy one track out in the background:
        .done  .out  .error  .seconds()
"""
import hashlib
import os
import re
import subprocess
import threading
import time

from .plugin_common import my_log

_FFMPEG_PATHS = ("/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/bin/ffmpeg", "/opt/bin/ffmpeg")

# codecs that are text (can become an .srt)
TEXT_CODECS = ("subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text", "microdvd", "subviewer", "jacosub")

_LANGS = {
    "ara": u"Arabic", "ar": u"Arabic", "eng": u"English", "en": u"English", "fre": u"French", "fra": u"French",
    "fr": u"French", "ger": u"German", "deu": u"German", "de": u"German", "spa": u"Spanish", "es": u"Spanish",
    "ita": u"Italian", "it": u"Italian", "por": u"Portuguese", "pt": u"Portuguese", "tur": u"Turkish",
    "tr": u"Turkish", "rus": u"Russian", "ru": u"Russian", "dut": u"Dutch", "nld": u"Dutch", "per": u"Persian",
    "fas": u"Persian", "heb": u"Hebrew", "hin": u"Hindi", "urd": u"Urdu", "chi": u"Chinese", "zho": u"Chinese",
    "jpn": u"Japanese", "kor": u"Korean", "gre": u"Greek", "ell": u"Greek", "pol": u"Polish", "swe": u"Swedish",
    "nor": u"Norwegian", "dan": u"Danish", "fin": u"Finnish", "rum": u"Romanian", "ron": u"Romanian",
    "hun": u"Hungarian", "cze": u"Czech", "ces": u"Czech", "ind": u"Indonesian", "may": u"Malay", "msa": u"Malay",
    "tha": u"Thai", "vie": u"Vietnamese", "ukr": u"Ukrainian", "bul": u"Bulgarian", "hrv": u"Croatian",
    "srp": u"Serbian", "slv": u"Slovenian", "slo": u"Slovak", "slk": u"Slovak", "kur": u"Kurdish",
}
_CODEC_NAMES = {"subrip": "SRT", "srt": "SRT", "ass": "ASS", "ssa": "SSA", "webvtt": "WebVTT",
                "mov_text": "MP4 text", "hdmv_pgs_subtitle": "PGS picture", "dvd_subtitle": "DVD picture",
                "dvb_subtitle": "DVB picture", "dvb_teletext": "Teletext"}

_STREAM_RE = re.compile(r"^\s*Stream #\d+:(\d+)(?:\[[^\]]*\])?(?:\(([A-Za-z]{2,3})\))?[^:]*:\s*Subtitle:\s*([A-Za-z0-9_]+)(.*)$")
_TITLE_RE = re.compile(r"^\s+title\s*:\s*(.+?)\s*$", re.I)

_lock = threading.Lock()
_tracks = {}            # key -> list of dicts, or None while reading
_busy = set()


def find_ffmpeg():
    for p in _FFMPEG_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    for d in (os.environ.get("PATH") or "").split(os.pathsep):
        p = os.path.join(d, "ffmpeg")
        if d and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return ""


def local_source(url):
    """a path on the box behind a play address ('/media/..', 'file:///media/..'), or ''"""
    u = str(url or "").strip()
    if u.startswith("file://"):
        u = u[len("file://"):]
    try:
        from urllib.parse import unquote
    except ImportError:                                  # py2
        from urllib import unquote
    if u.startswith("/") and "%" in u and not os.path.isfile(u):
        u = unquote(u)
    return u if u.startswith("/") and os.path.isfile(u) else ""


def _key(path):
    try:
        st = os.stat(path)
        return "%s|%d|%d" % (path, st.st_size, int(st.st_mtime))
    except Exception:
        return path


def lang_name(code):
    return _LANGS.get((code or "").lower(), (code or "").upper() or u"Unknown language")


def label(t):
    """'Arabic · SRT · Forced'  (picture tracks: '... · PGS picture - can't use')"""
    parts = [lang_name(t.get("lang"))]
    if t.get("title") and t["title"].lower() != parts[0].lower():
        parts.append(t["title"][:24])
    parts.append(_CODEC_NAMES.get(t.get("codec"), (t.get("codec") or "").upper()))
    s = u" · ".join(parts)
    if not t.get("text"):
        s += u" - can't use"
    return s


def parse_ffmpeg_info(stderr_text):
    """ffmpeg -i output -> [{index, lang, codec, title, default, forced, text}]"""
    out, cur = [], None
    for line in (stderr_text or "").splitlines():
        m = _STREAM_RE.match(line)
        if m:
            rest = m.group(4) or ""
            cur = {"index": int(m.group(1)), "lang": (m.group(2) or "").lower(),
                   "codec": m.group(3).lower(), "title": u"",
                   "default": "(default)" in rest, "forced": "(forced)" in rest}
            cur["text"] = cur["codec"] in TEXT_CODECS
            out.append(cur)
            continue
        if re.match(r"^\s*Stream #", line):
            cur = None                                    # an audio / video stream
            continue
        if cur is not None:
            t = _TITLE_RE.match(line)
            if t and not cur["title"]:
                cur["title"] = t.group(1)
    return out


def _run(cmd, timeout):
    """run, return (exit code, stderr text); kills it after timeout seconds"""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timer = threading.Timer(timeout, lambda: p.kill())
    timer.start()
    try:
        _o, e = p.communicate()
    finally:
        timer.cancel()
    return p.returncode, (e or b"").decode("utf-8", "replace")


def _probe_thread(path, k):
    res = []
    try:
        ff = find_ffmpeg()
        if ff:
            _rc, err = _run([ff, "-hide_banner", "-nostdin", "-i", path], 60)
            res = parse_ffmpeg_info(err)
            my_log("built-in subtitles: {} -> {}".format(
                os.path.basename(path), ", ".join(label(t) for t in res) or "none"))
    except Exception as e:
        my_log("built-in subtitles: probe failed for {}: {}".format(path, e))
    finally:
        with _lock:
            _tracks[k] = res
            _busy.discard(k)


def probe(path):
    """start reading the track list in the background (once per file)"""
    if not path or not find_ffmpeg():
        return
    k = _key(path)
    with _lock:
        if k in _tracks or k in _busy:
            return
        _busy.add(k)
        _tracks[k] = None
    t = threading.Thread(target=_probe_thread, args=(path, k))
    t.daemon = True
    t.start()


def tracks(path):
    """the subtitle tracks of a file: a list, [] for none, None while reading / not asked"""
    if not path:
        return []
    with _lock:
        return _tracks.get(_key(path))


def cache_file(path, index, folder):
    h = hashlib.md5(_key(path).encode("utf-8")).hexdigest()[:10]
    base = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", os.path.splitext(os.path.basename(path))[0])[:60] or "video"
    return os.path.join(folder, "%s_builtin%d_%s.srt" % (base, int(index), h))


class Extraction(object):
    """copy one text track out to an .srt in the background; the player polls .done"""

    def __init__(self, path, index, folder):
        self.path, self.index = path, int(index)
        self.out = cache_file(path, index, folder)
        self.error = ""
        self.done = False
        self._t0 = time.time()
        if os.path.isfile(self.out) and os.path.getsize(self.out) > 0:
            self.done = True                              # copied before
            return
        t = threading.Thread(target=self._work)
        t.daemon = True
        t.start()

    def seconds(self):
        return int(time.time() - self._t0)

    def _work(self):
        tmp = self.out + ".part.srt"
        try:
            ff = find_ffmpeg()
            if not ff:
                self.error = u"ffmpeg is not installed (opkg install ffmpeg)"
                return
            folder = os.path.dirname(self.out)
            if not os.path.isdir(folder):
                os.makedirs(folder)
            rc, err = _run([ff, "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", self.path,
                            "-map", "0:%d" % self.index, "-c:s", "srt", "-f", "srt", tmp], 900)
            if rc != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
                self.error = u"Could not copy the subtitles out of the video"
                my_log("built-in subtitles: ffmpeg exit {} for track {} of {}: {}".format(
                    rc, self.index, self.path, (err or "").strip()[-300:]))
                return
            os.rename(tmp, self.out)
            my_log("built-in subtitles: track {} of {} -> {} ({} bytes, {} s)".format(
                self.index, os.path.basename(self.path), self.out, os.path.getsize(self.out), self.seconds()))
        except Exception as e:
            self.error = u"Could not copy the subtitles out of the video"
            my_log("built-in subtitles: extraction failed: {}".format(e))
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            self.done = True
