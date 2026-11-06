# -*- coding: utf-8 -*-
"""WGFileManager -- the file browser's rows with the theme's line icons.

Enigma2's FileList builds each row with the skin's small extension icons. After
it has, restyle_rows() redraws every row's LOOK only -- the row's data (path,
is-folder, name, marked; item[0]) is left exactly as it was, so selecting,
marking, copying and moving behave as before:

    [data, icon (32x32 in the theme colour), name (centred in the 48 px row;
     a marked file: "✓ name" in the theme colour)]

Icons: player/nova/images/theme/<colour>/icon_<kind>.png (tools/make_theme_icons.py).
If an icon is missing the row keeps the look Enigma2 gave it.
"""
import os

from ..constants import ARCHIVE_EXTENSIONS, AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, TEXT_EXTENSIONS, VIDEO_EXTENSIONS
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

SUBTITLE_EXTENSIONS = (".srt", ".sub", ".ssa", ".ass", ".vtt", ".idx", ".smi")
ROW_H = 48
ICON = 32
_cache = {}


def icon_kind(path, is_dir, name=""):
    """folder / up / video / audio / image / archive / subtitle / text / file"""
    if name == ".." or (is_dir and str(name).startswith("<")):
        return "up"
    if is_dir:
        return "folder"
    low = (path or name or "").lower()
    if low.endswith(tuple(ARCHIVE_EXTENSIONS)):                  # .tar.gz before .gz
        return "archive"
    ext = os.path.splitext(low)[1]
    if ext in SUBTITLE_EXTENSIONS:
        return "subtitle"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in TEXT_EXTENSIONS:
        return "text"
    return "file"


def _icon(kind):
    if kind in _cache:
        return _cache[kind]
    png = None
    try:
        from ..player.nova.novaplay_theme import FRAME_DIR, theme_name
        path = os.path.join(FRAME_DIR, theme_name(), "icon_%s.png" % kind)
        if os.path.isfile(path):
            from Tools.LoadPixmap import LoadPixmap
            png = LoadPixmap(path)
    except Exception as e:
        logger.debug("file icon %s: %s", kind, e)
    _cache[kind] = png
    return png


def _row_name(item):
    """the text Enigma2 put in the row (its name), else the file name"""
    for part in item[1:]:
        if isinstance(part, tuple) and len(part) > 7 and isinstance(part[7], str):
            return part[7]
        if isinstance(part, str):
            return part
    data = item[0]
    return os.path.basename(str(data[0]).rstrip("/")) if data and data[0] else ""


def restyle_row(item, width):
    """one row -> [data, icon, name]; the data part is not touched"""
    from enigma import eListboxPythonMultiContent as M, RT_HALIGN_LEFT, RT_VALIGN_CENTER
    data = item[0]
    if not isinstance(data, tuple) or not data:
        return item
    path, is_dir = data[0], bool(data[1]) if len(data) > 1 else False
    name = _row_name(item)
    marked = len(data) > 3 and data[3] is True
    png = _icon(icon_kind(path, is_dir, data[2] if len(data) > 2 and isinstance(data[2], str) else name))
    if png is None:
        return item
    from ..player.nova.novaplay_theme import TH_GOLD_INT
    text = (u"✓ " + name) if marked else name
    row = [data, (M.TYPE_PIXMAP_ALPHABLEND, 12, (ROW_H - ICON) // 2, ICON, ICON, png)]
    if marked:
        row.append((M.TYPE_TEXT, 56, 0, max(100, width - 70), ROW_H, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, text,
                    TH_GOLD_INT, 0xFFFFFF))
    else:
        row.append((M.TYPE_TEXT, 56, 0, max(100, width - 70), ROW_H, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, text))
    return row


def restyle_rows(filelist):
    """every row of a FileList, then show them"""
    try:
        width = 816
        try:
            width = filelist.instance.size().width() or width
        except Exception:
            pass
        filelist.list[:] = [restyle_row(it, width) for it in filelist.list]
        filelist.l.setList(filelist.list)
    except Exception as e:
        logger.error("file icons: %s", e)
