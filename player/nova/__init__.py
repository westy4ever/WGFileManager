# -*- coding: utf-8 -*-
"""WGFileManager -- the Nova player (local edition of NovaPlay's player).

The player screen and its parts are NovaPlay's (plugin_screen_player.py and
player_*.py), copied with package-relative imports so they never clash with
an installed NovaPlay. Streaming-only modules are small stand-ins here
(plugin_state, novaplay_proxy, plugin_server_rank, ...).

A local file is handed to the player as its playback "candidates"
(service 4097, then 5002 / 5001 as fallbacks), so the player's own
start / confirm / resume / end-of-file handling runs unchanged.

Folder = series: the other videos in the same folder (or the playlist given)
are the "episodes" -- EPG lists them, Smart GREEN / the countdown card play
the next one, "Are you still watching?" works as in NovaPlay.

    play_file(session, path)                 one file (+ its folder as episodes)
    play_playlist(session, paths, start=0)    an explicit list
    play_directory(session, folder)           every video in a folder
"""
import os
import re

try:
    from ...constants import VIDEO_EXTENSIONS
except Exception:                                       # tests
    VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.ts', '.m2ts', '.mts', '.mov', '.wmv',
                        '.flv', '.webm', '.mpg', '.mpeg', '.vob', '.divx', '.asf',
                        '.3gp', '.ogv', '.m4v']

from .plugin_common import my_log

_SERVICE_TYPES = ((4097, "GStreamer"), (5002, "ExtePlayer3"), (5001, "Exteplayer"))


def is_video(path):
    return os.path.splitext(path or "")[1].lower() in VIDEO_EXTENSIONS


def _natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s or "")]


def folder_videos(folder):
    """the videos in a folder, in natural order (E2 before E10)"""
    try:
        names = [n for n in os.listdir(folder) if is_video(n) and not n.startswith(".")]
    except Exception:
        return []
    names.sort(key=_natural_key)
    return [os.path.join(folder, n) for n in names]


def _title_of(path):
    return os.path.splitext(os.path.basename(path or ""))[0]


def _episode(path):
    return {"title": _title_of(path), "url": path, "type": "episode"}


def local_candidates(path):
    """the player's candidate tuples: (service type, address, label, uses proxy)"""
    return [(t, path, label, False) for t, label in _SERVICE_TYPES]


def _find_poster(path):
    """a poster image next to the video (<name>.jpg / poster.jpg / folder.jpg /
    cover.jpg); otherwise a TMDb lookup by the file name, done in the
    background by plugin_imagecache (needs the TMDb key in api_keys.conf)"""
    base, folder = os.path.splitext(path)[0], os.path.dirname(path)
    for cand in (base + ".jpg", base + ".png", os.path.join(folder, "poster.jpg"),
                 os.path.join(folder, "folder.jpg"), os.path.join(folder, "cover.jpg")):
        if os.path.isfile(cand):
            return cand
    from .plugin_imagecache import tmdb_address
    return tmdb_address(path)


def _open(session, path, playlist, resume_pos):
    from .local_player import NovaLocalPlayer
    from .player_base import _capture_previous_service
    idx = playlist.index(path) if path in playlist else -1
    nxt = _episode(playlist[idx + 1]) if 0 <= idx < len(playlist) - 1 else None
    prev = _episode(playlist[idx - 1]) if idx > 0 else None
    episodes = [_episode(p) for p in playlist] if len(playlist) > 1 else []

    def on_next(ep):
        target = (ep or {}).get("url") or ""
        if target and os.path.isfile(target):
            play_playlist(session, playlist, playlist.index(target) if target in playlist else 0)

    my_log("nova: play {} ({} in the list)".format(path, len(playlist)))
    session.open(NovaLocalPlayer, _title_of(path), local_candidates(path),
                 _capture_previous_service(session), prev_episode=prev, resume_pos=resume_pos,
                 item_url=path, next_episode=nxt, on_next=on_next if len(playlist) > 1 else None,
                 poster_url=_find_poster(path), episodes=episodes)


def _start(session, path, playlist):
    if not os.path.isfile(path):
        from Screens.MessageBox import MessageBox
        session.open(MessageBox, "File not found:\n%s" % path, MessageBox.TYPE_ERROR)
        return
    from .plugin_state import _get_saved_position
    pos = _get_saved_position(path)
    if pos <= 30:
        _open(session, path, playlist, 0)
        return
    from Screens.MessageBox import MessageBox
    hhmm = "%d:%02d:%02d" % (pos // 3600, pos % 3600 // 60, pos % 60) if pos >= 3600 else "%d:%02d" % (pos // 60, pos % 60)

    def _ans(yes):
        _open(session, path, playlist, pos if yes else 0)
    session.openWithCallback(_ans, MessageBox, "Resume from %s?" % hhmm, MessageBox.TYPE_YESNO)


def play_file(session, path):
    """one video; the other videos in its folder are its episodes"""
    lst = folder_videos(os.path.dirname(path)) or [path]
    if path not in lst:
        lst = [path]
    _start(session, path, lst)


def play_playlist(session, paths, start=0):
    lst = [p for p in (paths or []) if p and os.path.isfile(p) and is_video(p)]
    if not lst:
        from Screens.MessageBox import MessageBox
        session.open(MessageBox, "No video files to play", MessageBox.TYPE_INFO)
        return
    _start(session, lst[max(0, min(int(start or 0), len(lst) - 1))], lst)


def play_directory(session, folder, recursive=False):
    lst = []
    if recursive:
        for root, _d, _f in os.walk(folder):
            lst.extend(folder_videos(root))
    else:
        lst = folder_videos(folder)
    play_playlist(session, lst, 0)
