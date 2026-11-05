#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Make the Theme Colour frame pictures (run on a PC, needs Pillow):

    python3 tools/make_theme_frames.py            # every frame the skins ask for
    python3 tools/make_theme_frames.py --check    # only list what is missing

Every skin element marked theme="panel" / theme="card" asks for a picture of
its size (novaplay_theme.REQUESTED, filled while the screens are imported with
the fake Enigma2 modules of tests/e2stubs.py). For each size and each of the
four colours this draws an armoured plate -- cut corners, a dark metal body
with a light top bevel, a neon edge with an inner glow; panels also get the
lit notch on top and the side lights -- into images/theme/<colour>/.

The same file is used by WGFileManager (its copy of the Nova player):
    python3 tools/make_theme_frames.py --repo /path/to/WGFileManager --pkg player.nova --scan ui
"""
import argparse
import importlib
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

SS = 2                          # drawn at 2x, then scaled down (smooth edges)


def _chamfer_poly(w, h, c, notch=None):
    """the outline: cut corners; notch = (x0, x1, depth, slant) on the top edge"""
    pts = [(c, 0)]
    if notch:
        x0, x1, d, s = notch
        pts += [(x0, 0), (x0 + s, d), (x1 - s, d), (x1, 0)]
    pts += [(w - c, 0), (w, c), (w, h - c), (w - c, h), (c, h), (0, h - c), (0, c)]
    return pts


def render(kind, w, h, accent):
    W, H = w * SS, h * SS
    panel = kind == "panel"
    c = int(max(14, min(40, min(w, h) * 0.18)) if panel else max(8, min(22, min(w, h) * 0.10))) * SS
    edge = (3 if panel else 2) * SS
    notch = None
    short = h < 320                       # a short panel (the player's): text starts near the top
    if panel and w >= 500:
        nw = int(w * (0.18 if short else 0.22)) * SS
        x0 = (W - nw) // 2
        notch = (x0, x0 + nw, (7 if short else 14) * SS, (14 if short else 26) * SS)
    outer = _chamfer_poly(W, H, c, notch)

    # body: dark metal, light at the top (bevel), slightly see-through
    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("RGBA", (1, H))
    for y in range(H):
        t = y / float(max(1, H - 1))
        if t < 0.12:
            k = t / 0.12
            col = (int(44 - 22 * k), int(50 - 24 * k), int(58 - 28 * k))
        else:
            k = (t - 0.12) / 0.88
            col = (int(22 - 11 * k), int(26 - 12 * k), int(30 - 13 * k))
        grad.putpixel((0, y), col + (236,))
    grad = grad.resize((W, H))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(outer, fill=255)
    body.paste(grad, (0, 0), mask)

    # inner glow along the edge, kept inside the plate
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).line(outer + [outer[0]], fill=255, width=edge * 4)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=(10 if panel else 6) * SS))
    glow = Image.composite(glow, Image.new("L", (W, H), 0), mask).point(lambda v: int(v * 0.55))
    body = Image.alpha_composite(body, Image.merge("RGBA", [Image.new("L", (W, H), v) for v in accent] + [glow]))

    # top bevel highlight (a thin light line just inside the top)
    d = ImageDraw.Draw(body)
    d.line([(c, edge + SS), (W - c, edge + SS)], fill=(255, 255, 255, 34), width=SS)

    # inner metal rim (the raised armour look): a lighter line and a dark one, inset
    inset = (9 if panel else 6) * SS
    ci = max(SS, c - inset // 2)
    rim = [(inset + x * (W - 2 * inset) / float(W), inset + y * (H - 2 * inset) / float(H))
           for x, y in _chamfer_poly(W, H, ci)]
    d.line(rim + [rim[0]], fill=(96, 106, 120, 150), width=SS)
    rim2 = [(x + SS, y + SS) for x, y in rim]
    d.line(rim2 + [rim2[0]], fill=(0, 0, 0, 150), width=SS)

    # neon edge
    d.line(outer + [outer[0]], fill=accent + (255,), width=edge, joint="curve")

    if panel:
        lit = accent + (255,)
        if notch and not short:                                 # lit strip under the notch
            x0, x1, nd, s = notch
            y = nd + 12 * SS
            d.rounded_rectangle([x0 + s + 10 * SS, y, x1 - s - 10 * SS, y + 4 * SS], radius=2 * SS, fill=lit)
        if h >= 160:                                            # side lights
            bl = int(min(60, h * 0.14)) * SS
            for x in (10 * SS, W - 16 * SS):
                for k in (0, 1):
                    y0 = H // 2 - bl - 4 * SS + k * (bl + 8 * SS)
                    d.rounded_rectangle([x, y0, x + 6 * SS, y0 + bl], radius=3 * SS, fill=lit)
    # soft bloom on the lights and the edge
    bloom = Image.new("L", (W, H), 0)
    bd = ImageDraw.Draw(bloom)
    bd.line(outer + [outer[0]], fill=200, width=edge)
    bloom = bloom.filter(ImageFilter.GaussianBlur(radius=3 * SS))
    bloom = Image.composite(bloom, Image.new("L", (W, H), 0), mask).point(lambda v: int(v * 0.6))
    body = Image.alpha_composite(body, Image.merge("RGBA", [Image.new("L", (W, H), v) for v in accent] + [bloom]))
    return body.resize((w, h), Image.LANCZOS)


def collect(repo, pkg, scan=()):
    """import every screen (fake Enigma2) so each skin reports the frames it uses"""
    sys.path.insert(0, os.path.join(repo, "tests"))
    import e2stubs                                              # noqa: F401
    if pkg:
        sys.path.insert(0, os.path.dirname(repo))
        base = os.path.basename(repo) + "." + pkg
        folder = os.path.join(repo, *pkg.split("."))
    else:
        sys.path.insert(0, repo)
        base, folder = "", repo
    names = sorted(f[:-3] for f in os.listdir(folder) if f.endswith(".py") and f != "__init__.py")
    theme = importlib.import_module((base + "." if base else "") + "novaplay_theme")
    for n in names:
        try:
            importlib.import_module((base + "." if base else "") + n)
        except Exception as e:
            print("  (skipped %s: %s)" % (n, e))
    # skins built only when a screen opens: their fixed sizes, read from the source
    import re
    rx = re.compile(r'theme="(panel|card)"[^>]*?size="(\d+),(\d+)"|size="(\d+),(\d+)"[^>]*?theme="(panel|card)"')
    files = [os.path.join(folder, n + ".py") for n in names]
    for extra in scan:                                          # more folders (WGFileManager's ui/)
        d = os.path.join(repo, extra)
        files += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".py")]
    for path in files:
        try:
            src = open(path, encoding="utf-8").read()
        except Exception:
            continue
        for m in rx.finditer(src):
            kind, w, h = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(4), m.group(5))
            if int(w) >= 60 and int(h) >= 40:
                theme.REQUESTED.add((kind, int(w), int(h)))
    return theme


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--pkg", default="")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--scan", action="append", default=[], help="another folder whose skins use theme= (repeatable)")
    a = ap.parse_args()
    theme = collect(a.repo, a.pkg, a.scan)
    want = sorted(theme.REQUESTED)
    print("%d frame sizes asked for" % len(want))
    missing = 0
    for name, _label, accent in theme.THEMES:
        for kind, w, h in want:
            path = theme.frame_path(kind, w, h, name)
            if os.path.isfile(path):
                continue
            missing += 1
            if a.check:
                print("  missing", path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            render(kind, w, h, accent).save(path, optimize=True)
    for name, _label, accent in theme.THEMES:              # the general frames (run-time sizes)
        for kind, (w, h) in theme.GENERIC.items():
            path = os.path.join(theme.FRAME_DIR, name, "%s_any.png" % kind)
            if not os.path.isfile(path):
                missing += 1
                if not a.check:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    render(kind, w, h, accent).save(path, optimize=True)
    print(("%d missing" if a.check else "%d made") % missing)
    return 1 if (a.check and missing) else 0


if __name__ == "__main__":
    sys.exit(main())
