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
    # the sample line: never on the Sync tab; a gap while styling shows a real line
    p._onSubtitlePicked(os.path.join(d, "utf8.srt"))
    seen = []
    for tab, pos in (("Sync", 8000), ("Style", 8000)):
        p._studioTab = list(U.TABS).index(tab)
        p._studioRefresh()
        SS.STUDIO.update(pos)
        r = SS.STUDIO._last_rendered
        seen.append(r if r is None else r[0])
    expect("pause between lines: empty on Sync, the nearest real line on Style", seen, [None, "near"])
    SS.STUDIO.detach()
    p._studioTab = list(U.TABS).index("Sync")
    p._studioOnTabs = False
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


def check_audio():
    """the audio player (ui/audio_player.py)"""
    print("\n[6] audio player")
    import time
    import xml.etree.ElementTree as ET
    name = PKG + ".ui.audio_player"
    __import__(name)
    A = sys.modules[name]
    d = tempfile.mkdtemp()
    A.STATE_FILE = os.path.join(d, "audio.json")
    tracks = [os.path.join(d, "%02d - Artist - Song %d.mp3" % (i, i)) for i in range(1, 6)]
    for t in tracks:
        open(t, "w").close()
    p = A.AudioPlaylistPlayer(Dummy(), tracks, 1, None)
    ET.fromstring(p.skin)
    w = widgets_of(p.skin)
    c = set(k for k in p._hw if not k.lower().endswith("actions"))
    expect("screen builds; widgets in code == widgets in the skin", (sorted(c - w), sorted(w - c)), ([], []))
    # nothing may be opened (the Resume question) while Enigma2 is still opening the screen
    opened = []
    sess = Dummy()
    A.remember_place(d, tracks[3], 151)
    q = A.AudioPlaylistPlayer(type("S", (), {"open": lambda s, *a, **k: opened.append(a),
                                              "openWithCallback": lambda s, *a, **k: opened.append(a),
                                              "nav": sess})(), tracks, 0, None)
    for f in q.onLayoutFinish:
        f()
    expect("no question opened while the screen is opening (the Resume one waits for a timer)", opened, [])
    expect("... and the timer runs the start", q.start_timer.callback is not None and q._first_start.__name__, "_first_start")
    expect("file names without tags -> title / artist",
           [A.name_tags(x) for x in ("03 - Artist - Title.mp3", "Artist - Title.flac", "Just A Song.mp3", "07_Song.mp3")],
           [("Title", "Artist"), ("Title", "Artist"), ("Just A Song", ""), ("Song", "")])
    for n in ("10 - Song.mp3", "2 - Song.flac", ".hidden.mp3", "scan.png", "notes.txt"):
        open(os.path.join(d, n), "w").close()
    expect("OK on a music file: the folder's music is the playlist, 2 before 10, no pictures / hidden",
           [os.path.basename(x) for x in A.folder_audio(d)],
           ["01 - Artist - Song 1.mp3", "02 - Artist - Song 2.mp3", "2 - Song.flac", "03 - Artist - Song 3.mp3",
            "04 - Artist - Song 4.mp3", "05 - Artist - Song 5.mp3", "10 - Song.mp3"])
    expect("seek steps when held: 10, 30, 60 s", [A.step_for_hold(n) for n in (1, 2, 4, 5, 9)], [10, 30, 30, 60, 60])
    expect("times", [A.fmt_time(x) for x in (5, 151, 3725)], ["0:05", "2:31", "1:02:05"])
    open(os.path.join(d, "Folder.JPG"), "w").close()
    e = tempfile.mkdtemp()
    open(os.path.join(e, "song.mp3"), "w").close()
    open(os.path.join(e, "Footloose.jpg"), "w").close()
    expect("cover: no guessing from a folder's only picture (mixed folders)", A.folder_cover(os.path.join(e, "song.mp3")), "")
    expect("cover: the folder picture", os.path.basename(A.folder_cover(tracks[0])), "Folder.JPG")
    # play order / repeat
    p.start_playback = lambda resume=0: None
    expect("in order: up next after track 2", p.upcoming(3), [2, 3, 4])
    p.repeat = "off"
    p._jump_to(4)
    expect("last track, repeat off: nothing next", p.upcoming(3), [])
    p.repeat = "all"
    expect("last track, repeat all: back to the first", p.upcoming(2), [0, 1])
    p.repeat = "one"
    p._eof_done = False
    p._on_eof()
    expect("repeat one: the same track again", p.current_index, 4)
    p.repeat = "all"
    p._eof_done = False
    p._on_eof()
    expect("repeat all at the end: the first track", p.current_index, 0)
    p.toggle_shuffle()
    expect("shuffle: current track first, every track once", (p.order[0], sorted(p.order)), (0, [0, 1, 2, 3, 4]))
    expect("shuffle and repeat remembered", (A._load_state()["shuffle"], A._load_state()["repeat"]), (True, "all"))
    o = A.new_round(5, 3)
    expect("a new shuffle round doesn't start with the track just played", (o[0] != 3, sorted(o)), (True, [0, 1, 2, 3, 4]))
    # resume
    A.remember_place(d, tracks[3], 151)
    expect("resume offered for the folder: track 4 at 2:31", A.resume_offer(tracks, 0), (3, 151))
    A.remember_place(d, tracks[0], 4)
    expect("no offer when it's the same track near the start", A.resume_offer(tracks, 0), None)
    # sleep
    p._sleep_picked((u"30 minutes", 30))
    expect("sleep timer set", 1700 < p._sleep_end - time.time() <= 1800, True)
    p._sleep_picked((u"At the end of this track", -1))
    closed = []
    p.close = lambda *a: closed.append(1)
    p._eof_done = False
    p._on_eof()
    expect("sleep at the end of the track: closes the player", closed, [1])


def check_file_manager():
    """file manager fixes (2026-11-05 audit)"""
    print("\n[7] file manager")
    import threading
    import shutil
    MS = sys.modules.get(PKG + ".ui.main_screen") or __import__(PKG + ".ui.main_screen", fromlist=["x"])
    FO = __import__(PKG + ".core.file_operations", fromlist=["x"])
    MT = __import__(PKG + ".utils.mainthread", fromlist=["x"])
    # 1. the ".." entry is never an operation target
    fl = object.__new__(MS.EnhancedFileList)
    fl.getCurrentDirectory = lambda: "/media/hdd/Movies/"
    fl.list = [(("/media/hdd/", True, "..", True), ".."), (("/media/hdd/Movies/a.mkv", False, "a.mkv", True), "a"),
               (("/media/hdd/Movies/b.mkv", False, "b.mkv", False), "b")]
    fl.getSelectionIndex = lambda: 0
    fl.getSelection = lambda: ("/media/hdd/", True)
    expect("'..' recognised (by name and by path), files are not",
           (fl.isParentSelected(), fl.isParentPath("/media/hdd"), fl.isParentPath("/media/hdd/Movies/a.mkv")),
           (True, True, False))
    expect("marked list never holds '..' (it was marked here)", fl.markedPaths(), ["/media/hdd/Movies/a.mkv"])
    # 2. a folder into itself is refused (it used to fill the disk)
    d = tempfile.mkdtemp()
    src = os.path.join(d, "Movies")
    os.makedirs(os.path.join(src, "2024"))
    open(os.path.join(src, "x.txt"), "w").close()
    ops = object.__new__(FO.FileOperations)
    ops.config, ops.cache, ops.trash_path = None, None, None
    got = []
    for fn, dst in ((ops.copy, os.path.join(src, "2024")), (ops.copy, src), (ops.move, os.path.join(src, "2024"))):
        try:
            fn(src, dst)
            got.append("done")
        except Exception as e:
            got.append("into itself" in str(e))
    expect("copy / move a folder into itself or its subfolder: refused", got, [True, True, True])
    other = os.path.join(d, "Backup")
    os.makedirs(other)
    ops.copy(src, other)
    expect("a normal folder copy still works", sorted(os.listdir(os.path.join(other, "Movies"))), ["2024", "x.txt"])
    # 3. copy / move: the worker only records; the main thread reports, failures included
    m = object.__new__(MS.WGFileManagerMain)
    m.operation_lock = threading.Lock()
    m.file_ops = ops
    m.operation_in_progress = True
    m.operation_current = 0
    t = threading.Thread(target=m._run_file_jobs, args=("paste", "cp", [os.path.join(src, "x.txt"), "/nonexistent/y"], other))
    t.start()
    t.join()
    expect("worker result: 1 copied, 1 failed, nothing shown from the thread",
           (m._op_result[2], len(m._op_result[3]), m.operation_in_progress), (1, 1, False))
    shown = []
    m.operation_timer = type("T", (), {"stop": lambda s: None})()
    m.active_pane = m.inactive_pane = type("P", (), {"refresh": lambda s: None})()
    m.update_ui = lambda: None
    m.dialogs = type("D", (), {"show_message": lambda s, text, type="info", timeout=0: shown.append((type, text.split(":")[0]))})()
    m.clipboard, m.clipboard_mode = ["x"], "cut"
    m.finish_file_jobs()
    expect("main thread: the failure is reported (was always 'Paste complete!')", shown, [("error", "Copied 1, failed 1")])
    # 5. archives: a tar can't write outside its folder; FILE.ZIP works
    import tarfile, io, zipfile
    AR = __import__(PKG + ".core.archive", fromlist=["x"])
    am = object.__new__(AR.ArchiveManager) if hasattr(AR, "ArchiveManager") else None
    def mk_tar(path, entries):
        with tarfile.open(path, "w") as tf:
            for name, kind, link in entries:
                ti = tarfile.TarInfo(name)
                if kind == "sym":
                    ti.type, ti.linkname = tarfile.SYMTYPE, link
                    tf.addfile(ti)
                else:
                    ti.size = 2
                    tf.addfile(ti, io.BytesIO(b"hi"))
    res = []
    for entries in ([("../../evil.txt", "file", "")], [("/tmp/evil_abs.txt", "file", "")], [("l", "sym", "/etc/passwd")],
                    [("ok/a.txt", "file", ""), ("ok/l", "sym", "a.txt")]):
        p = os.path.join(d, "t.tar")
        mk_tar(p, entries)
        try:
            out = am.extract_archive(p, d)
            res.append("extracted" if os.path.exists(os.path.join(out, "ok", "a.txt")) else "?")
        except Exception as e:
            res.append("refused" if "Unsafe" in str(e) else repr(e)[:60])
    expect("tar: '../', '/abs' and links out are refused; a normal one extracts", res,
           ["refused", "refused", "refused", "extracted"])
    zp = os.path.join(d, "PACK.ZIP")
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("x.txt", "x")
    expect("an upper-case .ZIP extracts", os.path.isfile(os.path.join(am.extract_archive(zp, d), "x.txt")), True)
    # 4. the main-thread helper
    seen = []
    t = threading.Thread(target=lambda: seen.append(MT.call_on_main(lambda: threading.current_thread().name)))
    t.start()
    t.join()
    expect("call_on_main from a worker without a reactor still runs (tests)", len(seen), 1)
    shutil.rmtree(d, ignore_errors=True)


def main():
    check_imports()
    check_screen()
    check_logic()
    check_sync()
    check_builtin_subs()
    check_audio()
    check_file_manager()
    print("\n" + ("ALL PASSED" if not FAILS else "%d FAILED" % len(FAILS)))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
