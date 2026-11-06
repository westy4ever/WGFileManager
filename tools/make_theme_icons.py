#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Make the file browser's line icons in every Theme Colour (run on a PC, needs Pillow):

    python3 tools/make_theme_icons.py

Writes player/nova/images/theme/<colour>/icon_<kind>.png (32 x 32, and a 48 x 48
set for big screens as icon48_<kind>.png): folder, up (the ".." entry), video,
audio, image, archive, subtitle, text, file. Lines in the theme colour with a
faint fill, drawn at 4x and scaled down so the strokes stay smooth.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "player", "nova", "images", "theme")
THEMES = (("green", (0x39, 0xFF, 0x6A)), ("blue", (0x1E, 0x9B, 0xFF)),
          ("red", (0xFF, 0x2A, 0x3A)), ("gold", (0xF2, 0xC2, 0x30)))
KINDS = ("folder", "up", "video", "audio", "image", "archive", "subtitle", "text", "file")
S = 128                                     # drawn at 128, saved at 32 / 48


def _page(d, c, fill, sw):
    d.polygon([(30, 12), (78, 12), (100, 34), (100, 116), (30, 116)], fill=fill)
    d.line([(30, 12), (78, 12), (100, 34), (100, 116), (30, 116), (30, 12)], fill=c, width=sw, joint="curve")
    d.line([(78, 12), (78, 34), (100, 34)], fill=c, width=sw, joint="curve")


def draw(kind, rgb):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = rgb + (255,)
    fill = rgb + (46,)
    sw = 8
    if kind in ("folder", "up"):
        d.polygon([(10, 30), (50, 30), (60, 42), (118, 42), (118, 108), (10, 108)], fill=fill)
        d.line([(10, 30), (50, 30), (60, 42), (118, 42), (118, 108), (10, 108), (10, 30)], fill=c, width=sw, joint="curve")
        d.line([(10, 54), (118, 54)], fill=c, width=sw - 3)
        if kind == "up":                                        # an arrow up inside
            d.line([(64, 98), (64, 66)], fill=c, width=sw)
            d.line([(48, 80), (64, 64), (80, 80)], fill=c, width=sw, joint="curve")
    elif kind == "video":
        d.rounded_rectangle([10, 22, 118, 106], radius=14, fill=fill, outline=c, width=sw)
        d.polygon([(52, 44), (88, 64), (52, 84)], fill=c)
    elif kind == "audio":
        d.line([(46, 96), (46, 26), (106, 14), (106, 84)], fill=c, width=sw, joint="curve")
        d.line([(46, 44), (106, 32)], fill=c, width=sw)
        d.ellipse([18, 80, 52, 110], fill=fill, outline=c, width=sw)
        d.ellipse([78, 68, 112, 98], fill=fill, outline=c, width=sw)
    elif kind == "image":
        d.rounded_rectangle([10, 20, 118, 108], radius=12, fill=fill, outline=c, width=sw)
        d.line([(16, 96), (48, 62), (72, 86), (88, 70), (114, 96)], fill=c, width=sw, joint="curve")
        d.ellipse([78, 34, 98, 54], fill=c)
    elif kind == "archive":
        d.polygon([(64, 10), (116, 34), (116, 92), (64, 118), (12, 92), (12, 34)], fill=fill)
        d.line([(64, 10), (116, 34), (116, 92), (64, 118), (12, 92), (12, 34), (64, 10)], fill=c, width=sw, joint="curve")
        d.line([(12, 34), (64, 58), (116, 34)], fill=c, width=sw, joint="curve")
        d.line([(64, 58), (64, 118)], fill=c, width=sw)
    elif kind == "subtitle":
        d.rounded_rectangle([8, 20, 120, 108], radius=14, fill=fill, outline=c, width=sw)
        d.line([(26, 72), (60, 72)], fill=c, width=sw)
        d.line([(72, 72), (102, 72)], fill=c, width=sw)
        d.line([(26, 90), (84, 90)], fill=c, width=sw)
    elif kind == "text":
        _page(d, c, fill, sw)
        for y in (56, 74, 92):
            d.line([(44, y), (86, y)], fill=c, width=sw - 2)
    else:                                                        # any other file
        _page(d, c, fill, sw)
    # a soft glow under the lines
    glow = im.split()[3].filter(ImageFilter.GaussianBlur(5)).point(lambda v: int(v * 0.45))
    base = Image.merge("RGBA", [Image.new("L", (S, S), v) for v in rgb] + [glow])
    return Image.alpha_composite(base, im)


def main():
    n = 0
    for name, rgb in THEMES:
        folder = os.path.join(OUT, name)
        os.makedirs(folder, exist_ok=True)
        for kind in KINDS:
            big = draw(kind, rgb)
            big.resize((32, 32), Image.LANCZOS).save(os.path.join(folder, "icon_%s.png" % kind), optimize=True)
            big.resize((48, 48), Image.LANCZOS).save(os.path.join(folder, "icon48_%s.png" % kind), optimize=True)
            n += 2
    print("%d icons made" % n)


if __name__ == "__main__":
    sys.exit(main())
