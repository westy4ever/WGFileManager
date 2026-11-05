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
    S._set_config("next_episode_prompt", "false")
    S._cache["state"] = None
    expect("settings are kept in WGFileManager's own file", S._get_config("next_episode_prompt", "true"), "false")


def main():
    check_imports()
    check_screen()
    check_logic()
    print("\n" + ("ALL PASSED" if not FAILS else "%d FAILED" % len(FAILS)))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
