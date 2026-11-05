# -*- coding: utf-8 -*-
"""WGFileManager -- the audio player (Nova style, 2026-11-05).

Same look as the Nova video player: a gold-framed panel with the seek bar,
elapsed / remaining time, the time bubble while seeking and the colour keys;
above it the cover, title / artist / album (from the file's tags) and what
plays next.

Keys
  ◀ ▶            seek (hold: 10 s, then 30 s, then 60 s a press)
  ▲ ▼            volume
  PLAY / PAUSE   play / pause
  RED            previous (after 3 s: back to the start of this track)
  GREEN / CH+    next          CH-  previous
  YELLOW         shuffle on / off
  BLUE           repeat: off -> all -> one
  OK             the list: jump to any track
  MENU           sleep timer, audio track, shuffle, repeat, keys
  INFO           the keys
  EXIT / STOP    close (the TV channel you were on comes back)

Remembered (/etc/enigma2/wgfilemanager_audio.json): the track and position
per folder ("Resume track 5 at 2:31?" next time), shuffle and repeat.
"""
import json
import os
import random
import re
import time

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components.Pixmap import Pixmap
from Components.ServiceEventTracker import ServiceEventTracker
from enigma import eServiceReference, eTimer, iPlayableService, iServiceInformation, ePoint

from ..utils.logging_config import get_logger
from ..player.nova.plugin_gridlist import scale_skin_xml, sc

logger = get_logger(__name__)

STATE_FILE = "/etc/enigma2/wgfilemanager_audio.json"
COVER_TMP = "/tmp/.id3coverart"          # where servicemp3 puts a file's embedded picture
_COVER_NAMES = ("cover.jpg", "folder.jpg", "front.jpg", "album.jpg", "albumart.jpg",
                "cover.png", "folder.png", "front.png")
REPEAT_MODES = ("off", "all", "one")
REPEAT_NAMES = {"off": u"Off", "all": u"All", "one": u"One"}
SLEEP_CHOICES = ((u"Off", 0), (u"15 minutes", 15), (u"30 minutes", 30), (u"60 minutes", 60),
                 (u"90 minutes", 90), (u"At the end of this track", -1))
BAR_X, BAR_W = 184, 1552                 # seek bar (1920-wide design units)


# ── small helpers (no Enigma2 needed: tested on a PC) ──────────────────────
def fmt_time(seconds):
    s = max(0, int(seconds or 0))
    return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60) if s >= 3600 else "%d:%02d" % (s // 60, s % 60)


def name_tags(path):
    """(title, artist) from a file name when the file has no tags:
    '03 - Artist - Title.mp3' / 'Artist - Title.mp3' / 'Title.mp3'"""
    base = os.path.splitext(os.path.basename(path or ""))[0]
    base = re.sub(r"^\s*\d{1,3}\s*[-._)]\s*", "", base).replace("_", " ").strip()
    parts = [p.strip() for p in re.split(r"\s+-\s+", base) if p.strip()]
    if len(parts) >= 2:
        return parts[-1], parts[-2]
    return base, u""


def folder_cover(path):
    """a picture next to the track: <name>.jpg, or cover / folder / front.jpg.
    [2026-11-05] no "the folder's only picture" guess: in a mixed folder it put
    one album's cover on every song"""
    folder = os.path.dirname(path or "")
    stem = os.path.splitext(path or "")[0]
    for c in (stem + ".jpg", stem + ".png"):
        if os.path.isfile(c):
            return c
    try:
        names = os.listdir(folder)
    except Exception:
        return ""
    low = dict((n.lower(), n) for n in names)
    for c in _COVER_NAMES:
        if c in low:
            return os.path.join(folder, low[c])
    return ""


def folder_audio(folder):
    """the music files in a folder, in natural order (2 before 10), no hidden files"""
    try:
        from ..constants import AUDIO_EXTENSIONS
    except Exception:
        AUDIO_EXTENSIONS = [".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma", ".opus", ".ac3", ".dts"]
    exts = tuple(e.lower() for e in AUDIO_EXTENSIONS)
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith(exts) and not n.startswith(".")
                 and os.path.isfile(os.path.join(folder, n))]
    except Exception:
        return []
    names.sort(key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)])
    return [os.path.join(folder, n) for n in names]


def step_for_hold(n):
    """the n-th quick press in a row: 10 s, then 30 s, then 60 s (as the video player)"""
    return 10 if n <= 1 else (30 if n <= 4 else 60)


def make_order(count, current, shuffle, rng=random):
    """play order: in order, or shuffled with the current track first"""
    order = list(range(count))
    if shuffle and count > 1:
        rest = [i for i in order if i != current]
        rng.shuffle(rest)
        order = [current] + rest
    return order


def new_round(count, just_played, rng=random):
    """a fresh shuffle for the next round, not starting with the track just played"""
    order = list(range(count))
    rng.shuffle(order)
    if count > 1 and order[0] == just_played:
        order[0], order[-1] = order[-1], order[0]
    return order


def _load_state(path=None):
    try:
        with open(path or STATE_FILE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(d, path=None):
    path = path or STATE_FILE
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.rename(tmp, path)
    except Exception as e:
        logger.warning("audio state not saved: %s", e)


def remember_place(folder, track, pos, path=None):
    d = _load_state(path)
    places = d.setdefault("folders", {})
    places[folder] = {"track": track, "pos": int(pos or 0), "t": int(time.time())}
    if len(places) > 200:                                   # keep the newest 200 folders
        for k, _v in sorted(places.items(), key=lambda kv: kv[1].get("t", 0))[:len(places) - 200]:
            places.pop(k, None)
    _save_state(d, path)


def resume_offer(playlist, start, path=None):
    """(index, seconds) to offer as "Resume ...?", or None"""
    if not playlist:
        return None
    place = (_load_state(path).get("folders") or {}).get(os.path.dirname(playlist[0]))
    if not place or place.get("track") not in playlist:
        return None
    idx, pos = playlist.index(place["track"]), int(place.get("pos") or 0)
    if idx == start and pos <= 10:
        return None
    if len(playlist) == 1 and pos <= 10:
        return None
    return idx, (pos if pos > 10 else 0)


SKIN = """
<screen name="WGFMAudioPlayer" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#0D1117">
    <eLabel position="0,0" size="1920,1080" backgroundColor="#0D1117" zPosition="0" />
    <widget name="coverBox" position="180,130" size="560,560" font="Regular;220" halign="center" valign="center" foregroundColor="#2A3240" backgroundColor="#161B22" cornerRadius="24" transparent="0" zPosition="1" />
    <widget name="cover" position="180,130" size="560,560" alphatest="blend" scale="1" zPosition="2" />
    <widget name="title" position="800,160" size="940,72" font="Regular;54" foregroundColor="#F2C230" transparent="1" zPosition="2" />
    <widget name="artist" position="800,244" size="940,52" font="Regular;38" foregroundColor="#F0F6FC" transparent="1" zPosition="2" />
    <widget name="album" position="800,302" size="940,44" font="Regular;30" foregroundColor="#A3ADBB" transparent="1" zPosition="2" />
    <widget name="trackline" position="800,372" size="940,40" font="Regular;26" foregroundColor="#A3ADBB" transparent="1" zPosition="2" />
    <eLabel position="800,440" size="940,1" backgroundColor="#2A3240" zPosition="2" />
    <widget name="upnextHead" position="800,462" size="940,36" font="Regular;24" foregroundColor="#F2C230" transparent="1" zPosition="2" />
    <widget name="upnext0" position="800,506" size="940,42" font="Regular;30" foregroundColor="#E5E7EB" transparent="1" zPosition="2" />
    <widget name="upnext1" position="800,554" size="940,42" font="Regular;30" foregroundColor="#C9D1D9" transparent="1" zPosition="2" />
    <widget name="upnext2" position="800,602" size="940,42" font="Regular;30" foregroundColor="#8B949E" transparent="1" zPosition="2" />
    <widget name="overlay_bg" position="160,868" size="1600,200" backgroundColor="#1A121822" borderWidth="2" borderColor="#F2C230" cornerRadius="20" zPosition="10" />
    <widget name="osd_title" position="184,880" size="1400,40" font="Regular;30" foregroundColor="#F2C230" transparent="1" zPosition="12" halign="left" valign="center" />
    <widget name="osd_clock" position="1610,880" size="130,40" font="Regular;28" foregroundColor="#FFFFFF" transparent="1" zPosition="12" halign="right" valign="center" />
    <widget name="seekFrame" position="182,930" size="1556,22" zPosition="11" backgroundColor="#1A2A3240" cornerRadius="11" />
    <widget name="seekbar" position="184,932" size="1552,18" zPosition="12" backgroundColor="#1A1C2333" foregroundColor="#F2C230" cornerRadius="9" />
    <widget name="osd_elapsed" position="184,958" size="330,40" font="Regular;28" foregroundColor="#E5D1A6" transparent="1" zPosition="12" valign="center" />
    <widget name="osd_state" position="520,958" size="60,40" font="Regular;30" foregroundColor="#39D98A" transparent="1" zPosition="12" halign="center" valign="center" />
    <widget name="status" position="590,958" size="640,40" font="Regular;24" foregroundColor="#FFFFFF" transparent="1" zPosition="12" halign="center" valign="center" />
    <widget name="osd_durtext" position="1240,958" size="500,40" font="Regular;26" foregroundColor="#FFFFFF" transparent="1" zPosition="12" halign="right" valign="center" />
    <widget name="osd_divider" position="184,1004" size="1552,1" backgroundColor="#1A2A3240" zPosition="11" />
    <widget name="keyDotR" position="184,1027" size="16,16" backgroundColor="#E5484D" cornerRadius="8" zPosition="12" />
    <widget name="keyRed" position="208,1016" size="185,38" font="Regular;23" halign="left" valign="center" foregroundColor="#F0F6FC" transparent="1" zPosition="12" />
    <widget name="keyDotG" position="399,1027" size="16,16" backgroundColor="#30A46C" cornerRadius="8" zPosition="12" />
    <widget name="keyGreen" position="423,1016" size="185,38" font="Regular;23" halign="left" valign="center" foregroundColor="#F0F6FC" transparent="1" zPosition="12" />
    <widget name="keyDotY" position="614,1027" size="16,16" backgroundColor="#F2C230" cornerRadius="8" zPosition="12" />
    <widget name="keyYellow" position="638,1016" size="205,38" font="Regular;23" halign="left" valign="center" foregroundColor="#F0F6FC" transparent="1" zPosition="12" />
    <widget name="keyDotB" position="851,1027" size="16,16" backgroundColor="#3E7BFA" cornerRadius="8" zPosition="12" />
    <widget name="keyBlue" position="875,1016" size="205,38" font="Regular;23" halign="left" valign="center" foregroundColor="#F0F6FC" transparent="1" zPosition="12" />
    <widget name="osd_keys" position="1090,1016" size="650,38" font="Regular;22" foregroundColor="#A3ADBB" transparent="1" zPosition="12" halign="right" valign="center" />
    <widget name="seekBubble" position="184,886" size="150,40" font="Regular;24" foregroundColor="#0C1017" backgroundColor="#F2C230" cornerRadius="10" halign="center" valign="center" transparent="0" zPosition="14" />
</screen>"""


class AudioPlaylistPlayer(Screen):
    """the audio player; (session, playlist, current_index, main_screen_ref) as before"""

    def __init__(self, session, playlist, current_index=0, main_screen_ref=None):
        Screen.__init__(self, session)
        self.skin = scale_skin_xml(SKIN)
        self.playlist = [p for p in (playlist or []) if p]
        self.main_screen_ref = main_screen_ref
        st = _load_state()
        self.shuffle = bool(st.get("shuffle", False))
        self.repeat = st.get("repeat", "all") if st.get("repeat") in REPEAT_MODES else "all"
        start = max(0, min(int(current_index or 0), max(0, len(self.playlist) - 1)))
        self.order = make_order(len(self.playlist), start, self.shuffle)
        self.pos_in_order = self.order.index(start) if self.playlist else 0
        self.current_index = start
        self.is_paused = False
        self._eof_done = False
        self._resume_at = 0
        self._sleep_end = 0          # time.time() when the sleep timer stops; 0 = off
        self._sleep_at_track_end = False
        self._hold_last_t, self._hold_count = 0.0, 0
        self._stall = (None, 0)
        self._cover_path = ""
        self._prev_service = None
        try:
            self._prev_service = session.nav.getCurrentlyPlayingServiceOrGroup()
        except Exception:
            try:
                self._prev_service = session.nav.getCurrentlyPlayingServiceReference()
            except Exception:
                self._prev_service = None

        for n in ("coverBox", "title", "artist", "album", "trackline", "upnextHead", "upnext0", "upnext1",
                  "upnext2", "osd_title", "osd_clock", "osd_elapsed", "osd_state", "status", "osd_durtext",
                  "keyRed", "keyGreen", "keyYellow", "keyBlue", "osd_keys", "seekBubble"):
            self[n] = Label(u"")
        for n in ("overlay_bg", "seekFrame", "osd_divider", "keyDotR", "keyDotG", "keyDotY", "keyDotB"):
            self[n] = Label(u"")
        self["cover"] = Pixmap()
        self["seekbar"] = ProgressBar()
        self["coverBox"].setText(u"♫")
        self["upnextHead"].setText(u"Up next")
        self["keyRed"].setText(u"Previous")
        self["keyGreen"].setText(u"Next")
        self["osd_keys"].setText(u"OK list  ·  MENU options  ·  INFO keys")

        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "MediaPlayerActions",
                                     "MoviePlayerActions", "ChannelSelectBaseActions",
                                     "MenuActions", "InfoActions", "InfobarAudioSelectionActions"], {
            "ok": self.show_list,
            "cancel": self.exit_player,
            "exit": self.exit_player,
            "stop": self.exit_player,
            "red": self.previous_track,
            "green": self.next_track,
            "yellow": self.toggle_shuffle,
            "blue": self.cycle_repeat,
            "play": self.toggle_play_pause,
            "playpause": self.toggle_play_pause,
            "pause": self.toggle_play_pause,
            "left": lambda: self.seek_key(-1),
            "right": lambda: self.seek_key(+1),
            "up": self.volume_up,
            "down": self.volume_down,
            "nextBouquet": self.next_track,
            "prevBouquet": self.previous_track,
            "channelUp": self.next_track,
            "channelDown": self.previous_track,
            "menu": self.show_menu,
            "mainMenu": self.show_menu,
            "info": self.show_keys,
            "audioSelection": self.choose_audio_track,
        }, -1)

        events = {iPlayableService.evEOF: self._on_eof, iPlayableService.evUpdatedInfo: self._on_info}
        try:
            events[iPlayableService.evUser + 13] = self._on_embedded_cover   # servicemp3: cover -> /tmp/.id3coverart
        except Exception:
            pass
        self.__events = ServiceEventTracker(screen=self, eventmap=events)
        self.position_timer = eTimer()
        self.position_timer.callback.append(self.update_position)
        self.bubble_timer = eTimer()
        self.bubble_timer.callback.append(self._hide_bubble)
        # [2026-11-05] the first step (it may ask "Resume ...?") runs just AFTER the
        # screen is open: opening a question while Enigma2 is still opening this
        # screen fails ("Modal open are allowed only from a screen which is modal")
        self.start_timer = eTimer()
        self.start_timer.callback.append(self._first_start)
        self.onLayoutFinish.append(self._schedule_start)
        self.onClose.append(self._on_close)

    # ── start ────────────────────────────────────────────────────────────
    def _schedule_start(self):
        self["seekBubble"].hide()
        self.start_timer.start(50, True)

    def _first_start(self):
        self["seekBubble"].hide()
        self._paint_modes()
        if not self.playlist:
            self.session.open(MessageBox, "No tracks to play!", MessageBox.TYPE_ERROR)
            self.close()
            return
        offer = resume_offer(self.playlist, self.current_index)
        if not offer:
            self.start_playback()
            return
        idx, pos = offer
        q = (u"Resume at %s?" % fmt_time(pos)) if idx == self.current_index else \
            (u"Resume track %d at %s?\n%s" % (idx + 1, fmt_time(pos), os.path.basename(self.playlist[idx])))

        def _ans(yes):
            if yes:
                self._jump_to(idx, resume=pos)
            else:
                self.start_playback()
        self.session.openWithCallback(_ans, MessageBox, q, MessageBox.TYPE_YESNO)

    def _jump_to(self, idx, resume=0):
        self.current_index = idx
        if idx in self.order:
            self.pos_in_order = self.order.index(idx)
        self.start_playback(resume)

    def start_playback(self, resume=0):
        try:
            path = self.playlist[self.current_index]
            try:
                if os.path.exists(COVER_TMP):
                    os.remove(COVER_TMP)            # the previous track's picture
            except Exception:
                pass
            ref = eServiceReference(4097, 0, path)
            ref.setName(os.path.splitext(os.path.basename(path))[0])
            self.session.nav.playService(ref)
            self.is_paused = False
            self._eof_done = False
            self._stall = (None, 0)
            self._resume_at = int(resume or 0)
            self._tags = {}
            self._paint_track()
            self._set_cover(folder_cover(path))
            self.position_timer.start(1000, False)
            self.update_position()
            logger.info("audio: track %d/%d %s", self.current_index + 1, len(self.playlist), path)
        except Exception as e:
            logger.error("audio: could not start: %s", e)
            self["status"].setText(u"Could not play this file")

    # ── what is shown ────────────────────────────────────────────────────
    def _tag(self, which):
        try:
            info = self.session.nav.getCurrentService().info()
            v = info.getInfoString(which) if info else ""
            return (v or "").strip()
        except Exception:
            return ""

    def _paint_track(self):
        path = self.playlist[self.current_index]
        ftitle, fartist = name_tags(path)
        title = self._tag(iServiceInformation.sTagTitle) or ftitle
        artist = self._tag(iServiceInformation.sTagArtist) or fartist
        album = self._tag(iServiceInformation.sTagAlbum)
        self["title"].setText(title)
        self["artist"].setText(artist)
        self["album"].setText(album)
        # [2026-11-05] no artist / album in the tags: the lines below move up (no gap)
        y = 244
        for name, used, h in (("artist", artist, 58), ("album", album, 58), ("trackline", True, 0)):
            try:
                inst = self[name].instance
                if inst is not None:
                    inst.move(ePoint(sc(800), sc(y + (12 if name == "trackline" else 0))))
            except Exception:
                pass
            if used:
                y += h
        self["osd_title"].setText(u"♫  " + (u"%s  —  %s" % (artist, title) if artist else title))
        self._paint_modes()
        self._paint_upnext()

    def _paint_modes(self):
        bits = [u"Track %d of %d" % (self.current_index + 1, len(self.playlist))] if self.playlist else []
        if self.shuffle:
            bits.append(u"Shuffle")
        if self.repeat != "off":
            bits.append(u"Repeat " + REPEAT_NAMES[self.repeat].lower())
        if self._sleep_at_track_end:
            bits.append(u"Sleep after this track")
        elif self._sleep_end:
            bits.append(u"Sleep in %d min" % max(1, int((self._sleep_end - time.time() + 59) // 60)))
        self["trackline"].setText(u"  ·  ".join(bits))
        self["keyYellow"].setText(u"Shuffle: " + (u"On" if self.shuffle else u"Off"))
        self["keyBlue"].setText(u"Repeat: " + REPEAT_NAMES[self.repeat])

    def upcoming(self, n=3):
        """the next n tracks (indexes) in play order, as repeat would play them"""
        out, k = [], self.pos_in_order
        if self.repeat == "one":
            return [self.current_index] * min(n, 1)
        for _ in range(n):
            k += 1
            if k >= len(self.order):
                if self.repeat != "all" or len(self.order) < 2:
                    break
                k = 0
            out.append(self.order[k])
        return out

    def _paint_upnext(self):
        nxt = self.upcoming(3)
        for i in range(3):
            self["upnext%d" % i].setText(
                u"%d.  %s" % (nxt[i] + 1, name_tags(self.playlist[nxt[i]])[0]) if i < len(nxt) else u"")
        self["upnextHead"].setText(u"Up next" if nxt else u"Last track")

    def _set_cover(self, path):
        self._cover_path = path or ""
        try:
            if path and self["cover"].instance is not None:
                self["cover"].instance.setPixmapFromFile(path)
                self["cover"].show()
                self["coverBox"].setText(u"")
                return
        except Exception as e:
            logger.debug("audio cover %s: %s", path, e)
        self["cover"].hide()
        self["coverBox"].setText(u"♫")

    def _on_embedded_cover(self):
        if os.path.isfile(COVER_TMP) and os.path.getsize(COVER_TMP) > 0:
            self._set_cover(COVER_TMP)

    def _on_info(self):
        self._paint_track()
        if not self._cover_path or self._cover_path != COVER_TMP:
            self._on_embedded_cover()

    # ── the clock ───────────────────────────────────────────────────────
    def _seek(self):
        try:
            svc = self.session.nav.getCurrentService()
            return svc and svc.seek()
        except Exception:
            return None

    def _pos_len(self):
        s = self._seek()
        if not s:
            return 0, 0
        p, l = s.getPlayPosition(), s.getLength()
        pos = p[1] / 90000.0 if p and not p[0] and p[1] > 0 else 0
        length = l[1] / 90000.0 if l and not l[0] and l[1] > 0 else 0
        return pos, length

    def update_position(self):
        try:
            self["osd_clock"].setText(time.strftime("%H:%M"))
            if self._sleep_end and time.time() >= self._sleep_end:
                self._sleep_now()
                return
            pos, length = self._pos_len()
            if self._resume_at and length > 0:
                s = self._seek()
                if s:
                    s.seekTo(int(self._resume_at * 90000))
                self["status"].setText(u"Resumed at " + fmt_time(self._resume_at))
                self._resume_at = 0
                return
            self["osd_elapsed"].setText(fmt_time(pos))
            self["osd_state"].setText(u"❚❚" if self.is_paused else u"▶")
            if length > 0:
                self["osd_durtext"].setText(u"−%s  /  %s" % (fmt_time(length - pos), fmt_time(length)))
                self["seekbar"].setValue(int(min(100, pos * 100 / length)))
                # [safety] some images send no "end of file" for audio: stuck at the end -> next
                if not self.is_paused and pos >= length - 1.5:
                    last, n = self._stall
                    self._stall = (pos, n + 1 if last is not None and abs(pos - last) < 0.2 else 0)
                    if self._stall[1] >= 3:
                        self._on_eof()
            if self._sleep_end:
                self._paint_modes()
        except Exception as e:
            logger.debug("audio position: %s", e)

    # ── end of a track ───────────────────────────────────────────────────
    def _on_eof(self):
        if self._eof_done:
            return
        self._eof_done = True
        if self._sleep_at_track_end:
            self._sleep_now()
            return
        if self.repeat == "one":
            self.start_playback()
            return
        if self.pos_in_order + 1 < len(self.order):
            self.pos_in_order += 1
        elif self.repeat == "all":
            if self.shuffle:                                      # a fresh shuffle for the next round
                self.order = new_round(len(self.playlist), self.current_index)
            self.pos_in_order = 0
        else:
            self.position_timer.stop()
            self.session.nav.stopService()
            self["status"].setText(u"End of the list")
            self["osd_state"].setText(u"■")
            self._paint_upnext()
            return
        self.current_index = self.order[self.pos_in_order]
        self.start_playback()

    # ── keys ─────────────────────────────────────────────────────────────
    def next_track(self):
        if not self.playlist:
            return
        self.pos_in_order = (self.pos_in_order + 1) % len(self.order)
        self.current_index = self.order[self.pos_in_order]
        self.start_playback()

    def previous_track(self):
        if not self.playlist:
            return
        pos, _l = self._pos_len()
        if pos > 3:                                             # back to the start of this track
            s = self._seek()
            if s:
                s.seekTo(0)
            self["status"].setText(u"From the start")
            return
        self.pos_in_order = (self.pos_in_order - 1) % len(self.order)
        self.current_index = self.order[self.pos_in_order]
        self.start_playback()

    def toggle_play_pause(self):
        try:
            p = self.session.nav.getCurrentService().pause()
            if not p:
                return
            if self.is_paused:
                p.unpause()
                self.is_paused = False
                self["status"].setText(u"")
            else:
                p.pause()
                self.is_paused = True
                self["status"].setText(u"Paused")
            self.update_position()
        except Exception as e:
            logger.error("audio pause: %s", e)

    def seek_key(self, direction):
        now = time.time()
        self._hold_count = self._hold_count + 1 if now - self._hold_last_t < 0.6 else 1
        self._hold_last_t = now
        step = step_for_hold(self._hold_count) * direction
        s = self._seek()
        if not s:
            return
        pos, length = self._pos_len()
        target = max(0, pos + step)
        if length > 0:
            target = min(target, max(0, length - 2))
        s.seekTo(int(target * 90000))
        self._show_bubble(target, length, step)

    def _show_bubble(self, target, length, step):
        self["seekBubble"].setText(u"%s%d s  ·  %s" % ("+" if step > 0 else u"−", abs(step), fmt_time(target)))
        try:
            frac = (target / length) if length > 0 else 0
            x = BAR_X + int(frac * BAR_W) - 120
            x = max(BAR_X, min(BAR_X + BAR_W - 240, x))
            inst = self["seekBubble"].instance
            if inst is not None:
                from enigma import eSize
                inst.resize(eSize(sc(240), sc(40)))
                inst.move(ePoint(sc(x), sc(886)))
        except Exception:
            pass
        self["seekBubble"].show()
        self.bubble_timer.start(1500, True)

    def _hide_bubble(self):
        self["seekBubble"].hide()

    def volume_up(self):
        try:
            from Components.VolumeControl import VolumeControl
            VolumeControl.instance.volUp()
        except Exception:
            pass

    def volume_down(self):
        try:
            from Components.VolumeControl import VolumeControl
            VolumeControl.instance.volDown()
        except Exception:
            pass

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.order = make_order(len(self.playlist), self.current_index, self.shuffle)
        self.pos_in_order = self.order.index(self.current_index)
        self._remember_modes()
        self["status"].setText(u"Shuffle " + (u"on" if self.shuffle else u"off"))
        self._paint_modes()
        self._paint_upnext()

    def cycle_repeat(self):
        self.repeat = REPEAT_MODES[(REPEAT_MODES.index(self.repeat) + 1) % len(REPEAT_MODES)]
        self._remember_modes()
        self["status"].setText(u"Repeat: " + REPEAT_NAMES[self.repeat])
        self._paint_modes()
        self._paint_upnext()

    def _remember_modes(self):
        d = _load_state()
        d["shuffle"], d["repeat"] = self.shuffle, self.repeat
        _save_state(d)

    # ── OK: the list ─────────────────────────────────────────────────────
    def show_list(self):
        items = []
        for i in self.order:
            mark = u"▶ " if i == self.current_index else u"     "
            items.append((u"%s%d.  %s" % (mark, i + 1, name_tags(self.playlist[i])[0]), i))
        self.session.openWithCallback(self._list_picked, ChoiceBox,
                                      title=u"Tracks (%d)" % len(self.playlist), list=items,
                                      selection=self.order.index(self.current_index))

    def _list_picked(self, res):
        if res is not None and res[1] is not None:
            self._jump_to(res[1])

    # ── MENU ─────────────────────────────────────────────────────────────
    def show_menu(self):
        sleep = (u"after this track" if self._sleep_at_track_end else
                 (u"%d min left" % max(1, int((self._sleep_end - time.time() + 59) // 60)) if self._sleep_end else u"off"))
        items = [(u"Sleep timer: " + sleep, "sleep"),
                 (u"Audio track…", "audio"),
                 (u"Shuffle: " + (u"on" if self.shuffle else u"off"), "shuffle"),
                 (u"Repeat: " + REPEAT_NAMES[self.repeat].lower(), "repeat"),
                 (u"Keys", "keys")]
        self.session.openWithCallback(self._menu_picked, ChoiceBox, title=u"Audio player", list=items)

    def _menu_picked(self, res):
        act = res and res[1]
        if act == "sleep":
            self.session.openWithCallback(self._sleep_picked, ChoiceBox, title=u"Sleep timer",
                                          list=list(SLEEP_CHOICES))
        elif act == "audio":
            self.choose_audio_track()
        elif act == "shuffle":
            self.toggle_shuffle()
        elif act == "repeat":
            self.cycle_repeat()
        elif act == "keys":
            self.show_keys()

    def _sleep_picked(self, res):
        if res is None:
            return
        mins = res[1]
        self._sleep_at_track_end = mins == -1
        self._sleep_end = time.time() + mins * 60 if mins and mins > 0 else 0
        self["status"].setText(u"Sleep timer: " + res[0].lower() if mins else u"Sleep timer off")
        logger.info("audio: sleep timer %s", res[0])
        self._paint_modes()

    def _sleep_now(self):
        logger.info("audio: sleep timer -> stop")
        self._sleep_end, self._sleep_at_track_end = 0, False
        self.exit_player()

    def choose_audio_track(self):
        try:
            tracks = self.session.nav.getCurrentService().audioTracks()
            n = tracks.getNumberOfTracks() if tracks else 0
        except Exception:
            n = 0
        if n < 2:
            self["status"].setText(u"This file has one audio track")
            return
        cur = tracks.getCurrentTrack()
        items = []
        for i in range(n):
            info = tracks.getTrackInfo(i)
            desc = (info.getDescription() or u"").strip() if info else u""
            lang = (info.getLanguage() or u"").strip() if info else u""
            items.append(((u"▶ " if i == cur else u"     ") + (u"%d. %s %s" % (i + 1, lang, desc)).strip(), i))
        self.session.openWithCallback(lambda r: self._audio_picked(tracks, r), ChoiceBox,
                                      title=u"Audio track", list=items, selection=max(0, cur))

    def _audio_picked(self, tracks, res):
        if res is not None:
            try:
                tracks.selectTrack(res[1])
                self["status"].setText(u"Audio track %d" % (res[1] + 1))
            except Exception as e:
                logger.error("audio track: %s", e)

    def show_keys(self):
        self.session.open(MessageBox, u"\n".join((
            u"◀ ▶   seek (hold: 10 s, 30 s, 60 s)",
            u"▲ ▼   volume",
            u"PLAY / PAUSE   play / pause",
            u"RED   previous (after 3 s: start of this track)",
            u"GREEN / CH+   next      CH−   previous",
            u"YELLOW   shuffle      BLUE   repeat off / all / one",
            u"OK   the track list",
            u"MENU   sleep timer, audio track",
            u"EXIT / STOP   close")), MessageBox.TYPE_INFO)

    # ── close ────────────────────────────────────────────────────────────
    def _save_place(self):
        """remember where we are BEFORE playback stops (the old player read the
        position after stopping, so nothing was ever saved)"""
        if not self.playlist:
            return
        path = self.playlist[self.current_index]
        pos, length = self._pos_len()
        if length > 0 and pos >= length - 5:
            pos = 0                                          # finished: next time from the start
        remember_place(os.path.dirname(path), path, pos)
        if self.main_screen_ref is not None and pos > 0:
            try:
                self.main_screen_ref.save_resume_point(path, pos)
            except Exception:
                pass

    def exit_player(self):
        try:
            self._save_place()
        except Exception as e:
            logger.error("audio: saving the place failed: %s", e)
        self.close()

    def _on_close(self):
        for t in (self.position_timer, self.bubble_timer, self.start_timer):
            try:
                t.stop()
            except Exception:
                pass
        try:
            if self._prev_service:
                self.session.nav.playService(self._prev_service)   # the channel you were on
            else:
                self.session.nav.stopService()
        except Exception:
            pass
