#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YELLOW marking on OpenATV's REAL FileList (run on a PC):

    python3 tests/run_openatv_filelist.py /path/to/openatv-enigma2

Needs a checkout of https://github.com/openatv/enigma2 (only
lib/python/Components/FileList.py is used); the file is not copied into this
repo. Without it the test is skipped. Exit code 0 = passed / skipped.
"""
import sys, os, types, tempfile, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
ATV = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OPENATV_ENIGMA2", "")
ATV_FL = os.path.join(ATV, "lib", "python", "Components", "FileList.py")
if not os.path.isfile(ATV_FL):
    print("skipped: no OpenATV checkout (give its path as the argument)")
    sys.exit(0)
sys.path.insert(0, HERE); import e2stubs
# --- what OpenATV's FileList.py needs, minimal and real enough ---
class _L(object):
    def __init__(self): self.items = []
    def setList(self, l): self.items = l
    def setFont(self, *a): pass
    def setItemHeight(self, *a): pass
class MenuList(object):
    def __init__(self, menuList, enableWrapAround=None, content=None):
        self.list = menuList; self.l = _L(); self.idx = 0; self.instance = None
    def setList(self, menuList):
        self.list = menuList; self.l.setList(self.list)
    def getCurrentIndex(self): return self.idx
    def getSelectionIndex(self): return self.idx
    def moveToIndex(self, i): self.idx = i
    def setCurrentIndex(self, i): self.idx = i
    def getSelection(self): return self.list[self.idx][0] if self.list else None
    def getCurrent(self): return self.list[self.idx] if self.list else None
ml = types.ModuleType("Components.MenuList"); ml.MenuList = MenuList; sys.modules["Components.MenuList"] = ml
si = types.ModuleType("Components.SkinIcon")
class SkinIcon(object): pass
si.SkinIcon = SkinIcon; si.loadSkinIcon = lambda *a: "ICON"; sys.modules["Components.SkinIcon"] = si
sk = types.ModuleType("skin"); sk.fonts = {}; sk.parameters = {}; sys.modules["skin"] = sk
hd = types.ModuleType("Components.Harddisk")
class _HDM(object):
    on_partition_list_change = []
    def getMountedPartitions(self, *a, **k): return []
hd.harddiskmanager = _HDM(); sys.modules["Components.Harddisk"] = hd
import builtins; builtins._ = lambda s: s
import enigma as en
for n, v in (("BT_SCALE", 1), ("BT_VALIGN_CENTER", 2), ("RT_HALIGN_LEFT", 0), ("RT_VALIGN_CENTER", 4)):
    setattr(en, n, v)
class _MC(object):
    TYPE_TEXT, TYPE_PIXMAP_ALPHABLEND, TYPE_PIXMAP_ALPHATEST = 1, 6, 5
en.eListboxPythonMultiContent = _MC
class _SC(object):
    @staticmethod
    def getInstance(): return _SC()
en.eServiceCenter = _SC
en.eServiceReference = type("eServiceReference", (), {})
en.eServiceReferenceFS = type("eServiceReferenceFS", (), {})
en.gFont = lambda *a: None
spec = importlib.util.spec_from_file_location("Components.FileList", ATV_FL)
FL = importlib.util.module_from_spec(spec); sys.modules["Components.FileList"] = FL
spec.loader.exec_module(FL)
class _Val(object):
    def __init__(self, v): self.value = v
class _Any(object):
    def __getattr__(self, k): return _Val(0)
FL.config = type("C", (), {"usage": _Any()})()
# the folder
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "sub"))
for n in ("a.mkv", "b.mp3", "c.srt"):
    open(os.path.join(d, n), "w").close()
FL.FileListBase.getMountPointLink = lambda self, p: "/"
FL.FileListBase.getMountPoint = lambda self, p: "/"
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPO))
PKG = os.path.basename(REPO)
MS = importlib.import_module(PKG + ".ui.main_screen")
assert MS.FileList is FL.FileList, "main_screen uses the real OpenATV FileList"
FI = importlib.import_module(PKG + ".ui.file_icons")
FI._icon = lambda kind, marked=False: ("LIT:" if marked else "PNG:") + kind
fl = MS.EnhancedFileList(d + "/", showDirectories=True, showFiles=True)
FAILS = []
def expect(label, got, want):
    print(("  ok    " if got == want else "  FAIL  ") + label + ("" if got == want else ": got %r, want %r" % (got, want)))
    if got != want:
        FAILS.append(label)
expect("multi-select is on (rows can be marked)", fl.multiSelect, True)
names = [str(it[0][4]) for it in fl.list]
expect("one 'up' row (OpenATV's own), no second '..'", [n for n in names if n.startswith("<") or n == ".."], ["<Parent Directory>"])
idx = [i for i, it in enumerate(fl.list) if str(it[0][0]).endswith("a.mkv")][0]
fl.moveToIndex(idx)
fl.markSelected()
expect("YELLOW marks the file: lit icon, plain name (no tick)",
       ([os.path.basename(p) for p in fl.markedPaths()], fl.list[idx][1][5], fl.list[idx][2][7]), (["a.mkv"], "LIT:video", "a.mkv"))
fl.markSelected()
expect("YELLOW again unmarks it", fl.markedPaths(), [])
fl.markSelected()
fl.changeDir(os.path.join(d, "sub") + "/")
fl.changeDir(d + "/")
expect("the mark is still there after leaving the folder and coming back", [os.path.basename(p) for p in fl.markedPaths()], ["a.mkv"])
expect("hold YELLOW clears it", (fl.clearMarks(), fl.markedPaths()), (1, []))
print("\n" + ("ALL PASSED" if not FAILS else "%d FAILED" % len(FAILS)))
sys.exit(1 if FAILS else 0)
