#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nova player checks -- run on a PC before pushing (not on the box):

    python3 tests/run_nova_checks.py

1. every file of player/nova compiles and imports (fake Enigma2 modules)
2. the player screen builds; every widget the code creates is in its skin
   and the other way round (a missing one is a "skin error" crash on the box)
3. small logic tests (local candidates, folder episodes, resume store)

Exit code 0 = all passed, 1 = something failed.
"""
from __future__ import print_function

import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import e2stubs                                   # noqa: E402  (must come first)
from e2stubs import Dummy, widgets_of            # noqa: E402

REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
PKG = os.path.basename(REPO)                     # "wgfilemanager" here, "WGFileManager" on the box

FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  FAIL  " + msg)


def ok(msg):
    print("  ok    " + msg)


def expect(label, got, want):
    if got == want:
        ok(label)
    else:
        fail("%s: got %r, want %r" % (label, got, want))


def nova(mod=""):
    name = PKG + ".player.nova" + (("." + mod) if mod else "")
    __import__(name)
    return sys.modules[name]


def check_imports():
    print("\n[1] imports")
    folder = os.path.join(REPO, "player", "nova")
    mods = sorted(f[:-3] for f in os.listdir(folder) if f.endswith(".py") and f != "__init__.py")
    for m in [""] + mods + ["extractors.base", "extractors.htmlmedia"]:
        try:
            nova(m)
        except Exception as e:
            fail("player.nova%s: %r" % (("." + m) if m else "", e))
            traceback.print_exc(limit=3)
    ok("%d modules import" % (len(mods) + 1))


def check_screen():
    print("\n[2] player screen")
    P = nova("local_player")
    try:
        obj = P.NovaLocalPlayer(Dummy(), "Film", nova().local_candidates("/media/hdd/a.mkv"),
                                item_url="/media/hdd/a.mkv", prev_episode=None)
    except Exception as e:
        fail("player: could not build (%r)" % (e,))
        traceback.print_exc(limit=4)
        return
    skin = getattr(obj, "skin", None) or type(obj).skin
    import xml.etree.ElementTree as ET
    try:
        ET.fromstring(skin)
    except Exception as e:
        fail("player: skin is not valid XML (%s)" % e)
        return
    w = widgets_of(skin)
    c = set(k for k in obj._hw if not k.lower().endswith("actions"))
    problems = []
    if c - w:
        problems.append("in code, not in skin: %s" % sorted(c - w)[:8])
    if w - c:
        problems.append("in skin, not in code: %s" % sorted(w - c)[:8])
    bad = [f for f in obj.onLayoutFinish if not hasattr(f, "__self__")]
    if bad:
        problems.append("%d non-method onLayoutFinish entries" % len(bad))
    if problems:
        fail("player: " + "; ".join(problems))
    else:
        ok("player builds, %d widgets match the skin" % len(w))


def check_logic():
    print("\n[3] logic")
    N = nova()
    expect("local file -> GStreamer, then the two exteplayers",
           [c[0] for c in N.local_candidates("/x/a.mkv")], [4097, 5002, 5001])
    d = tempfile.mkdtemp()
    for n in ("Show E10.mkv", "Show E2.mkv", "Show E1.mkv", "notes.txt", ".hidden.mkv"):
        open(os.path.join(d, n), "w").close()
    expect("folder videos in natural order (E2 before E10), no hidden / non-video",
           [os.path.basename(p) for p in N.folder_videos(d)], ["Show E1.mkv", "Show E2.mkv", "Show E10.mkv"])
    S = nova("plugin_state")
    S._STATE_FILE = os.path.join(d, "state.json")
    S._cache["state"] = None
    S._save_position("/x/a.mkv", 20)
    S._save_position("/x/b.mkv", 754)
    S._save_total_duration("/x/b.mkv", 5400)
    S._cache["state"] = None                    # read back from the file
    expect("resume: under 30 s not kept; position and length read back",
           (S._get_saved_position("/x/a.mkv"), S._get_saved_position("/x/b.mkv"), S.position_info("/x/b.mkv")),
           (0, 754, (754, 5400)))
    L = nova("local_player").NovaLocalPlayer
    fake = type("F", (), {})()
    fake._sleep_minutes = 0
    fake._record_task = None
    expect("MENU › Timer for a local file: Sleep and Chapters, no Record",
           [r[0] for r in L._menuTimerItems(fake)], [u"Sleep", u"Chapters"])
    IC = nova("plugin_imagecache")
    expect("poster: title / year / kind from release-style file names",
           [IC.poster_query(n) for n in ("Dune.Part.Two.2024.1080p.WEB-DL.x264.mkv",
                                          "The.Bear.S03E05.720p.HDTV.mkv",
                                          "Blade Runner 2049 (2017).mp4",
                                          "1917.mkv",
                                          "Show Name 2x07.avi")],
           [("Dune Part Two", "2024", "movie"), ("The Bear", "", "tv"),
            ("Blade Runner 2049", "2017", "movie"), ("1917", "", "movie"), ("Show Name", "", "tv")])
    kf = os.path.join(d, "keys.conf")
    open(kf, "w").write("# keys\nsubdl_api_key=ABC\ntmdb_api_key=\n")
    S._OWN_KEYS_FILE, S._PLUGINS_DIR = kf, os.path.join(d, "none")
    S._keys_cache.update(at=0, keys=None)
    expect("API keys come from the keys file (empty ones ignored), not the repo",
           (S._get_config("subdl_api_key", ""), S._get_config("tmdb_api_key", "")), ("ABC", ""))
    S._set_config("next_episode_prompt", "false")
    S._cache["state"] = None
    expect("settings are kept in WGFileManager's own file", S._get_config("next_episode_prompt", "true"), "false")


def check_sync():
    """a downloaded subtitle: ◀ ▶ on SYNC TO AUDIO / FINE SYNC move it"""
    print("\n[4] subtitle sync")
    N = nova()
    NS, SS, U = nova("novaplay_subtitles"), nova("novaplay_substudio"), nova("player_studio_ui")
    d = tempfile.mkdtemp()
    body = u"1\n00:00:05,000 --> 00:00:07,000\nمرحبا\n\n2\n00:00:10,000 --> 00:00:12,000\nWorld\n\n"
    files = {"utf8.srt": body.encode("utf-8"), "utf16.srt": body.encode("utf-16")}
    for name, data in sorted(files.items()):
        path = os.path.join(d, name)
        open(path, "wb").write(data)
        p = nova("local_player").NovaLocalPlayer(Dummy(), "Film", N.local_candidates("/x/a.mkv"),
                                                item_url="/x/a.mkv", prev_episode=None)
        p._onSubtitlePicked(path)
        p._showStudioOverlay()
        p._studioTab = list(U.TABS).index("Sync")
        p._studioOnTabs, p._studioRow = False, p._studioKeysNow().index("delay")
        p._pl_navRightKey()
        p._studioRow = p._studioKeysNow().index("finedelay")
        p._pl_navLeftKey()
        expect(name + ": Studio reads it; ▶ +0.5 s then FINE ◀ -0.1 s = +0.4 s",
               (SS.STUDIO.get_cue_count(), SS.STUDIO.get_offset(), NS.get_subtitle_state().get("offset_ms")),
               (2, 400, 400))
        SS.STUDIO.detach()
    # no subtitle file on (a track inside the video): say so instead of nothing
    NS.update_subtitle_state(path="", _orig_path="", offset_ms=0)
    p._studioSyncMsg = None
    p._studioRow = p._studioKeysNow().index("delay")
    p._pl_navRightKey()
    expect("no subtitle file: the panel says why sync can't move it",
           (p._studioSyncMsg or "").startswith(u"No subtitle file on"), True)


def check_builtin_subs():
    """a track inside the video: listed in the Subtitles tab, copied out, synced"""
    print("\n[5] built-in subtitle tracks")
    import subprocess
    import time
    E, NS, SS, U = nova("novaplay_embedsubs"), nova("novaplay_subtitles"), nova("novaplay_substudio"), nova("player_studio_ui")
    if not E.find_ffmpeg():
        ok("(no ffmpeg on this PC: skipped)")
        return
    d = tempfile.mkdtemp()
    srt = os.path.join(d, "in.srt")
    open(srt, "wb").write(u"1\n00:00:01,000 --> 00:00:03,000\nمرحبا\n\n2\n00:00:04,000 --> 00:00:05,500\nSecond\n\n".encode("utf-8"))
    mkv = os.path.join(d, "Film 2024.mkv")
    subprocess.call(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=6", "-i", srt,
                     "-map", "0", "-map", "1", "-c:v", "mpeg4", "-c:s", "srt", "-metadata:s:s:0", "language=ara", mkv])
    NS._ss_cache_dir = lambda: os.path.join(d, "cache")
    p = nova("local_player").NovaLocalPlayer(Dummy(), "Film", nova().local_candidates(mkv), item_url=mkv, prev_episode=None)
    NS.update_subtitle_state(item_url=mkv, path="", _orig_path="", offset_ms=0)
    p._embeddedProbe()
    t0 = time.time()
    while E.tracks(mkv) is None and time.time() - t0 < 20:
        time.sleep(0.1)
    expect("Subtitles tab lists the video's track",
           [r[0] for r in p._subsItems() if r[0].startswith(u"Built-in")], [u"Built-in: Arabic · SRT"])
    p._embeddedPick([a for a in p._subs_acts if a[0] == "embedded"][0][1])
    t0 = time.time()
    while not p._emb_job.done and time.time() - t0 < 30:
        time.sleep(0.1)
    p._embeddedPoll()
    p._showStudioOverlay()
    p._studioTab = list(U.TABS).index("Sync")
    p._studioOnTabs, p._studioRow = False, p._studioKeysNow().index("delay")
    p._pl_navRightKey()
    expect("copied out, drawn by the Studio, SYNC TO AUDIO moves it",
           (p._emb_job.error, SS.STUDIO.get_cue_count(), SS.STUDIO.get_offset()), (u"", 2, 500))
    SS.STUDIO.detach()


def main():
    check_imports()
    check_screen()
    check_logic()
    check_sync()
    check_builtin_subs()
    print("\n" + ("ALL PASSED" if not FAILS else "%d FAILED" % len(FAILS)))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
