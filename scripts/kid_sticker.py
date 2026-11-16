"""Cover a child's face (the son in the back seat) with an animated smiley: bobbing, tilting, blinking.

usage: python kid_sticker.py <spec.json> [clip ...]   -> <film>/<clip>_kid.mov for each clip (or only those named)
spec: {"film": "C:/Data/<name>-video/film",
       "clips": {"IMG_8004": {"src": "IMG_8004_land.mov",            # in film/ (or an absolute path)
                              "spans": [[null, null, 245, 630, 300]]}, # from, to (null = whole clip), centre x, y, diameter
                 "IMG_2715": {"src": "IMG_2715_over.mov",
                              "spans": [[405.8, 409.0, [[405.8, 400, 480], [406.9, 375, 460], [409.0, 450, 485]], null, 230]]}}}
A moving span gives keys [t, x, y] instead of x (and null for y): straight lines between them (from a face tracker).
Then point the project's CLIP_SRC at film/<clip>_kid.mov, and burn later pictures or captions (burn_in.py) into
the _kid copy, never into _land, or the smiley is lost.

Users (Helm 2026-11-11, Diesel 2026-11-14): "лице сина закриваємо смайликом, можна анімованим, але щоб моє лице не
закривало". Place: kid_faces.py finds the second face; a sticker a bit larger than the face (hair, headphones) and
kept left (or right) of the driver's face box. Check frames of every clip: a child turns his head and peeks out.
The smiley is drawn in SDR and converted to HLG (SDR white at HLG 0.75), so it is not glaring next to the face.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

import vfconfig as vf

W, H, FPS = 1920, 1080, 30
D = 400                       # loop smiley diameter, px (each place scales it)
BOX = 520                     # sticker canvas (room for the bob and tilt)
LOOP = 11.4                   # s: bob 1.9, tilt 2.85, blink 3.8 all repeat in it

TO2020 = np.array([[0.6274, 0.3293, 0.0433], [0.0691, 0.9195, 0.0114], [0.0164, 0.0880, 0.8956]])


def hlg(rgb8):
    """sRGB 8-bit -> BT.2020 HLG 16-bit, SDR white at HLG 0.75."""
    x = rgb8.astype(np.float64) / 255
    lin = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    e = np.clip(lin @ TO2020.T, 0, 1) * 0.2647
    a, b, c = 0.17883277, 0.28466892, 0.55991073
    v = np.where(e <= 1 / 12, np.sqrt(3 * e), a * np.log(np.maximum(12 * e - b, 1e-9)) + c)
    return np.round(v * 65535).astype(np.uint16)


def face(blink):
    s = 2 * D
    im = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(im)
    d.ellipse((8, 8, s - 8, s - 8), fill=(255, 205, 40, 255), outline=(200, 130, 0, 255), width=18)
    d.ellipse((40, 30, s - 40, s - 40), outline=(255, 222, 100, 255), width=10)
    for ex in (s * 0.34, s * 0.66):
        if blink:
            d.line((ex - 50, s * 0.40, ex + 50, s * 0.40), fill=(60, 35, 10, 255), width=22)
        else:
            d.ellipse((ex - 38, s * 0.30, ex + 38, s * 0.46), fill=(60, 35, 10, 255))
            d.ellipse((ex - 14, s * 0.32, ex + 8, s * 0.36), fill=(255, 255, 255, 255))
    d.arc((s * 0.24, s * 0.30, s * 0.76, s * 0.78), 20, 160, fill=(60, 35, 10, 255), width=26)
    d.ellipse((s * 0.14, s * 0.55, s * 0.28, s * 0.65), fill=(255, 150, 90, 160))   # cheeks
    d.ellipse((s * 0.72, s * 0.55, s * 0.86, s * 0.65), fill=(255, 150, 90, 160))
    return im.resize((D, D), Image.LANCZOS)


def frame(t, faces):
    """Sticker canvas at time t (s): RGBA 16-bit HLG."""
    blink = (t % 3.8) < 0.16
    im = faces[blink].rotate(7 * math.sin(2 * math.pi * t / 2.85), Image.BICUBIC)
    can = Image.new("RGBA", (BOX, BOX))
    dy = int(round(14 * math.sin(2 * math.pi * t / 1.9)))
    can.alpha_composite(im, ((BOX - D) // 2, (BOX - D) // 2 + dy))
    a = np.array(can)
    out = np.empty(a.shape, np.uint16)
    out[..., :3] = hlg(a[..., :3])
    out[..., 3] = a[..., 3].astype(np.uint16) * 257
    return out


def make_loop(loop_dir):
    """The sticker animation once, as 16-bit RGBA PNG frames in a .mov; ffmpeg loops it over each clip."""
    os.makedirs(loop_dir, exist_ok=True)
    faces = {False: face(False), True: face(True)}
    for i in range(int(LOOP * FPS)):
        # PIL has no 16-bit RGBA: write raw and let ffmpeg pack the PNGs
        frame(i / FPS, faces).astype("<u2").tofile("%s/f%03d.raw" % (loop_dir, i))
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-f", "image2", "-pattern_type", "sequence", "-framerate", str(FPS),
                    "-s", "%dx%d" % (BOX, BOX), "-pix_fmt", "rgba64le", "-vcodec", "rawvideo", "-i", loop_dir + "/f%03d.raw",
                    "-c:v", "png", "-pix_fmt", "rgba64be", loop_dir + "/loop.mov"], check=True)
    for f in os.listdir(loop_dir):
        if f.endswith(".raw"):
            os.remove(os.path.join(loop_dir, f))


def lerp(keys, k, box):
    """overlay x or y expression: keys[i][k] at keys[i][0], straight between, minus half the sticker box."""
    e = "%d" % (keys[-1][k] - box // 2)
    for (t0, *p0), (t1, *p1) in reversed(list(zip(keys, keys[1:]))):
        v0, v1 = p0[k - 1] - box // 2, p1[k - 1] - box // 2
        e = "if(lt(t,%s),%d+(%d)*(t-%s)/%s,%s)" % (t1, v0, v1 - v0, t0, round(t1 - t0, 3), e)
    return "if(lt(t,%s),%d,%s)" % (keys[0][0], keys[0][k] - box // 2, e)


def render(film, clip, src, spans, loop):
    src = src if os.path.isabs(src) else "%s/%s" % (film, src)
    n = len(spans)
    parts = ["[0:v]format=yuv444p10le[v0]"]
    parts.append("[1:v]split=%d%s" % (n, "".join("[k%d]" % i for i in range(n))) if n > 1 else "[1:v]null[k0]")
    for i, (a, b, cx, cy, d) in enumerate(spans):
        box = int(round(BOX * d / D / 2)) * 2
        enable = "" if a is None else ":enable='between(t,%s,%s)'" % (a, b)
        if isinstance(cx, list):            # moving: piecewise linear in t
            x, y = lerp(cx, 1, box), lerp(cx, 2, box)
        else:
            x, y = cx - box // 2, cy - box // 2
        parts.append("[k%d]scale=%d:%d:out_range=tv:out_color_matrix=bt2020,format=yuva444p10le[s%d]" % (i, box, box, i))
        parts.append("[v%d][s%d]overlay=x='%s':y='%s':shortest=1:format=yuv444p10%s[v%d]" % (i, i, x, y, enable, i + 1))
    graph = ";".join(parts) + ";[v%d]format=yuv420p10le" % n
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-i", src, "-stream_loop", "-1", "-i", loop,
                    "-filter_complex", graph, "-map", "0:a:0?", "-c:a", "copy", *vf.hevc_args(),
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    "%s/%s_kid.mov" % (film, clip)], check=True)
    print(clip, flush=True)


def main():
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    film = spec["film"]
    loop_dir = film + "/kid_loop"
    if not os.path.exists(loop_dir + "/loop.mov"):
        make_loop(loop_dir)
    for c in sys.argv[2:] or spec["clips"]:
        render(film, c, spec["clips"][c]["src"], spec["clips"][c]["spans"], loop_dir + "/loop.mov")


if __name__ == "__main__":
    main()
