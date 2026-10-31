"""Animated route maps from the iPhone GPS tags: outbound (old Yaris) and return (rented Hybrid).

usage: python make_route.py            -> film/route_out_sdr.mkv, film/route_back_sdr.mkv (SDR, 1080p30)
build_film.py turns them into HLG inserts ("anim" items).

Waypoints are the GPS tags of the clips and photos (see scan_meta.py / meta.json); the roads between
them come from OSRM (OpenStreetMap data), cached in out.json / back.json / day2.json. The line starts
at the petrol station in Starogard, never at home.
Backdrop: Sentinel-2 cloudless 2016 by EOX (CC BY 4.0), tiles cached in tiles/.
"""
import json
import math
import os
import subprocess
import urllib.request

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "C:/Data/yaris-video/film"
TILE_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
Z = 9
W, H, FPS = 1920, 1080, 30
LAT_TOP, LAT_BOT = 54.78, 50.12          # vertical extent of the frame
ROUTE_X, ROUTE_LON = 700, 18.9           # where this longitude sits on screen (info panel on the right)

BLUE, AMBER = (66, 133, 244), (255, 176, 32)
FONT_B = "C:/Windows/Fonts/segoeuib.ttf"
FONT_R = "C:/Windows/Fonts/segoeui.ttf"
FONT_L = "C:/Windows/Fonts/segoeuil.ttf"

# (name, lat, lon, side): towns on the route get their name on the left, away from the line
CITIES = [("Гданськ", 54.352, 18.646, "r"), ("Старогард-Гданський", 53.966, 18.530, "l"),
          ("Бидгощ", 53.123, 18.008, "l"), ("Торунь", 53.013, 18.598, "l"), ("Варшава", 52.230, 21.012, "r"),
          ("Лодзь", 51.759, 19.456, "l"), ("Ченстохова", 50.811, 19.120, "r"), ("Катовіце", 50.264, 19.023, "r"),
          ("Познань", 52.406, 16.925, "r")]


def world(lat, lon):
    n = 256 * 2 ** Z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


Y0, Y1 = world(LAT_TOP, 0)[1], world(LAT_BOT, 0)[1]
SCALE = H / (Y1 - Y0)
X0 = world(0, ROUTE_LON)[0] - ROUTE_X / SCALE


def screen(lat, lon):
    x, y = world(lat, lon)
    return (x - X0) * SCALE, (y - Y0) * SCALE


def backdrop():
    cache = os.path.join(HERE, "backdrop.png")
    if os.path.exists(cache):
        return np.array(Image.open(cache).convert("RGB"))
    os.makedirs(os.path.join(HERE, "tiles"), exist_ok=True)
    x_end = X0 + W / SCALE
    tx0, tx1, ty0, ty1 = int(X0 // 256), int(x_end // 256), int(Y0 // 256), int(Y1 // 256)
    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            path = os.path.join(HERE, "tiles", "%d_%d_%d.jpg" % (Z, ty, tx))
            if not os.path.exists(path):
                req = urllib.request.Request(TILE_URL.format(z=Z, x=tx, y=ty), headers={"User-Agent": "yaris-video"})
                with urllib.request.urlopen(req) as r, open(path, "wb") as f:
                    f.write(r.read())
            mosaic.paste(Image.open(path).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    box = (X0 - tx0 * 256, Y0 - ty0 * 256, x_end - tx0 * 256, Y1 - ty0 * 256)
    img = mosaic.resize((W, H), Image.LANCZOS, box=box)
    a = np.array(img).astype(np.float32)
    grey = a.mean(axis=2, keepdims=True)
    a = (grey + (a - grey) * 0.8) * 0.72            # a little calmer, so lines and text stand out
    # darker on the right, under the info panel
    ramp = np.clip((np.arange(W) - 1150) / 300, 0, 1)[None, :, None]
    a *= 1 - 0.45 * ramp
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT_R, 24)
    for name, lat, lon, side in CITIES:
        x, y = screen(lat, lon)
        d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(235, 235, 235))
        tx = x + 10 if side == "r" else x - 10 - d.textlength(name, font=f)
        d.text((tx, y - 16), name, font=f, fill=(235, 235, 235), stroke_width=3, stroke_fill=(20, 20, 20))
    small = ImageFont.truetype(FONT_L, 17)
    note = "Sentinel-2 cloudless 2016 © EOX IT Services GmbH (Copernicus Sentinel data) · дороги © OpenStreetMap, OSRM"
    d.text((W - 16 - d.textlength(note, font=small), H - 30), note, font=small, fill=(200, 200, 200))
    img.save(cache)
    return np.array(img)


def load_route(fname):
    coords = json.load(open(os.path.join(HERE, fname)))["routes"][0]
    legs = [l["distance"] / 1000 for l in coords["legs"]]
    pts = np.array([screen(lat, lon) for lon, lat in coords["geometry"]["coordinates"]])
    km = [0.0]
    lonlat = coords["geometry"]["coordinates"]
    for (lo1, la1), (lo2, la2) in zip(lonlat, lonlat[1:]):
        dx = math.radians(lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2))
        km.append(km[-1] + 6371 * math.hypot(dx, math.radians(la2 - la1)))
    km = np.array(km) * (sum(legs) / km[-1])       # match OSRM's own length
    return pts, km, np.cumsum([0] + legs)


def upto(pts, km, d):
    """The polyline cut at d km, end point interpolated."""
    i = int(np.searchsorted(km, d))
    if i <= 0:
        return pts[:1]
    if i >= len(km):
        return pts
    f = (d - km[i - 1]) / max(km[i] - km[i - 1], 1e-9)
    return np.vstack([pts[:i], pts[i - 1] + (pts[i] - pts[i - 1]) * f])


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def line(img, poly, color, width=6, alpha=1.0):
    if len(poly) < 2:
        return img
    p = np.round(poly * 4).astype(np.int32).reshape(-1, 1, 2)    # 2 bits of sub-pixel precision
    layer = img.copy()
    cv2.polylines(layer, [p], False, (25, 25, 25), width + 5, cv2.LINE_AA, shift=2)
    cv2.polylines(layer, [p], False, color, width, cv2.LINE_AA, shift=2)
    return layer if alpha >= 1 else cv2.addWeighted(layer, alpha, img, 1 - alpha, 0)


def dot(img, xy, color, r=11):
    c = (int(round(xy[0] * 4)), int(round(xy[1] * 4)))
    cv2.circle(img, c, (r + 4) * 4, (255, 255, 255), -1, cv2.LINE_AA, shift=2)
    cv2.circle(img, c, r * 4, color, -1, cv2.LINE_AA, shift=2)


class Overlay:
    """Text drawn with PIL on a transparent layer, blended per frame with its own opacity."""

    def __init__(self):
        self.items = []

    def add(self, draw_fn, t_in, t_out=None):
        layer = Image.new("RGBA", (W, H))
        draw_fn(ImageDraw.Draw(layer))
        a = np.array(layer).astype(np.float32) / 255
        self.items.append((a[..., :3] * 255, a[..., 3:], t_in, t_out))

    def apply(self, frame, t):
        out = frame.astype(np.float32)
        for rgb, alpha, t_in, t_out in self.items:
            k = ease((t - t_in) / 0.5)
            if t_out is not None:
                k *= 1 - ease((t - t_out) / 0.5)
            if k > 0:
                a = alpha * k
                out = out * (1 - a) + rgb * a
        return out.astype(np.uint8)


def pin_label(x, y, title, sub, side="right"):
    fb, fr = ImageFont.truetype(FONT_B, 30), ImageFont.truetype(FONT_R, 25)

    def draw(d):
        tw = max(d.textlength(title, font=fb), d.textlength(sub, font=fr))
        bx = x + 26 if side == "right" else x - 26 - tw - 28
        by = y - 40
        d.rounded_rectangle((bx, by, bx + tw + 28, by + 82), 12, fill=(15, 15, 15, 200))
        d.text((bx + 14, by + 6), title, font=fb, fill=(255, 255, 255, 255))
        d.text((bx + 14, by + 44), sub, font=fr, fill=(215, 215, 215, 255))
    return draw


def panel(lines):
    def draw(d):
        for font, size, text, color, y in lines:
            d.text((1290, y), text, font=ImageFont.truetype(font, size), fill=color + (255,))
    return draw


def counter(km_value, color):
    f = ImageFont.truetype(FONT_B, 110)
    layer = Image.new("RGBA", (560, 140))
    ImageDraw.Draw(layer).text((0, 0), "%d км" % km_value, font=f, fill=color + (255,))
    return np.array(layer)


def blend_counter(frame, km_value, color, y):
    c = counter(km_value, color).astype(np.float32) / 255
    region = frame[y:y + 140, 1290:1850].astype(np.float32)
    a = c[..., 3:]
    frame[y:y + 140, 1290:1850] = (region * (1 - a) + c[..., :3] * 255 * a).astype(np.uint8)


def encode(name, frames_iter, n):
    path = "%s/%s_sdr.mkv" % (OUT, name)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", "%dx%d" % (W, H), "-r", str(FPS), "-i", "-", "-c:v", "ffv1",
                            "-pix_fmt", "yuv444p", "-color_primaries", "bt709", "-color_trc", "bt709",
                            "-colorspace", "bt709", path], stdin=subprocess.PIPE)
    for k in range(n):
        enc.stdin.write(next(frames_iter).tobytes())
    enc.stdin.close()
    enc.wait()
    print("wrote", path)


def outbound(base):
    pts, km, wp = load_route("out.json")
    length, n = 10.0, int(10.0 * FPS)
    # route draws from 1.0 s to 7.6 s, holding 0.7 s at the Orlen stop (end of leg 3)
    stop_km = wp[3]
    t_a, t_stop, t_b, t_end = 1.0, 4.6, 5.3, 7.6
    ov = Overlay()
    ov.add(panel([(FONT_B, 54, "Туди", (255, 255, 255), 110),
                  (FONT_R, 32, "20 вересня 2025, субота", (220, 220, 220), 185),
                  (FONT_R, 32, "старий Yaris 2013, механіка", (220, 220, 220), 230)]), 0.3)
    ov.add(panel([(FONT_L, 30, "за маршрутом на карті", (200, 200, 200), 440)]), 1.0)
    sx, sy = screen(53.958, 18.5417)
    ox, oy = screen(51.1077, 19.3889)
    ax, ay = screen(50.4708, 19.0723)
    ov.add(pin_label(sx, sy, "Старт · 13:17", "заправка в Старогарді"), 0.6)
    ov.add(pin_label(ox, oy, "Orlen · 16:33", "357 км від дому, 32,24 л"), t_stop)
    ov.add(pin_label(ax, ay, "Аеропорт Катовіце · 17:45", "Яріс передаємо водію до Сум", "left"), t_end - 0.2)

    def gen():
        for f in range(n):
            t = f / FPS
            if t < t_stop:
                d = stop_km * ease((t - t_a) / (t_stop - t_a))
            elif t < t_b:
                d = stop_km
            else:
                d = stop_km + (km[-1] - stop_km) * ease((t - t_b) / (t_end - t_b))
            img = line(base.copy(), upto(pts, km, d), BLUE)
            tip = upto(pts, km, d)[-1]
            dot(img, tip, BLUE)
            img = ov.apply(img, t)
            if t >= 1.0:
                blend_counter(img, round(d), (255, 255, 255), 300)
            yield fade(img, t, length)
    encode("route_out", gen(), n)


def inbound(base):
    out_pts, out_km, _ = load_route("out.json")
    pts, km, wp = load_route("back.json")
    p2, km2, _ = load_route("day2.json")
    length, n = 12.0, int(12.0 * FPS)
    stop_km = wp[3]                      # night Orlen, end of leg 3
    t_a, t_stop, t_b, t_home, t_c, t_end = 1.0, 5.4, 6.0, 7.0, 8.2, 9.8
    ov = Overlay()
    ov.add(panel([(FONT_B, 54, "Назад", (255, 255, 255), 110),
                  (FONT_R, 32, "20-21 вересня 2025", (220, 220, 220), 185),
                  (FONT_R, 32, "орендований Yaris Hybrid", (220, 220, 220), 230)]), 0.3)
    ov.add(panel([(FONT_L, 30, "за маршрутом на карті", (200, 200, 200), 440)]), 1.0, t_end)
    ov.add(panel([(FONT_L, 30, "516 км за одометром", (200, 200, 200), 440)]), t_end)
    ov.add(panel([(FONT_B, 40, "21 вересня", AMBER, 560),
                  (FONT_R, 30, "повертаю машину в Гданську", (220, 220, 220), 615)]), t_home + 0.3)
    kx, ky = screen(50.4614, 19.0835)
    nx, ny = screen(53.7407, 18.6394)
    hx, hy = screen(53.958, 18.5417)
    gx, gy = screen(54.3810, 18.4692)
    ov.add(pin_label(kx, ky, "Катовіце · 18:30", "беру Yaris Hybrid в оренду", "left"), 0.6)
    ov.add(pin_label(nx, ny, "Orlen · 23:28", "нічна заправка, 28,84 л"), t_stop)
    ov.add(pin_label(hx, hy, "Старогард · 00:01", "вдома опівночі", "left"), t_home - 0.2, t_c + 0.3)
    ov.add(pin_label(gx, gy, "Аеропорт Гданськ · 17:21", "долив 6,15 л і здаю машину", "left"), t_end - 0.2)

    def gen():
        for f in range(n):
            t = f / FPS
            if t < t_stop:
                d = stop_km * ease((t - t_a) / (t_stop - t_a))
            elif t < t_b:
                d = stop_km
            else:
                d = stop_km + (km[-1] - stop_km) * ease((t - t_b) / (t_home - t_b))
            d2 = km2[-1] * ease((t - t_c) / (t_end - t_c))
            img = line(base.copy(), out_pts, BLUE, 5, 0.45)
            img = line(img, upto(pts, km, d), AMBER)
            if d2 > 0:
                img = line(img, upto(p2, km2, d2), AMBER)
                dot(img, upto(p2, km2, d2)[-1], AMBER)
            else:
                dot(img, upto(pts, km, d)[-1], AMBER)
            img = ov.apply(img, t)
            if t >= 1.0:
                blend_counter(img, round(d + d2), (255, 255, 255), 300)
            yield fade(img, t, length)
    encode("route_back", gen(), n)


def fade(img, t, length):
    k = min(1.0, t / 0.4, (length - t) / 0.4)
    return img if k >= 1 else (img.astype(np.float32) * max(k, 0)).astype(np.uint8)


if __name__ == "__main__":
    base = backdrop()
    outbound(base)
    inbound(base)
