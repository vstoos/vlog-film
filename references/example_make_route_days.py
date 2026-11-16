"""Example (Diesel from Croatia, 2026-11-15/16): one animated map per day, PLAN first, then the REAL drive.

Phase 1 (0-5 s): white line start -> end and a "План перед виїздом" panel (Google time and km; the EV plan =
Google time + charging time, with green charger pins). Phase 2: the real drive leg by leg, a pin at every stop
with its time, length, reason and the charger there, a legs table that grows row by row, and a total with the
plan beside it. Copy and adapt: paths, bounds, day*() data. Uses day1.json/day2.json (OSRM routes with
waypoints, see example_make_route.py). Cut it in two pieces to show over the voice (SKILL.md).
"""
"""Diesel Mercedes from Croatia: route maps per day. Adapted from the Yaris example.

Animated route maps from the iPhone GPS tags: outbound (old Yaris) and return (rented Hybrid).

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
OUT = "C:/Data/diesel-cro-video/film"
TILE_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
Z = 9
W, H, FPS = 1920, 1080, 30
LAT_TOP, LAT_BOT = 54.75, 43.70          # vertical extent of the frame
ROUTE_X, ROUTE_LON = 640, 17.0           # where this longitude sits on screen (info panel on the right)

BLUE, AMBER = (66, 133, 244), (255, 176, 32)
FONT_B = "C:/Windows/Fonts/segoeuib.ttf"
FONT_R = "C:/Windows/Fonts/segoeui.ttf"
FONT_L = "C:/Windows/Fonts/segoeuil.ttf"

# (name, lat, lon, side): towns on the route get their name on the left, away from the line
CITIES = [("Гданськ", 54.352, 18.646, "r"), ("Торунь", 53.013, 18.598, "r"), ("Лодзь", 51.759, 19.456, "r"),
          ("Катовіце", 50.264, 19.023, "r"), ("Острава", 49.835, 18.282, "r"), ("Брно", 49.195, 16.607, "l"),
          ("Відень", 48.208, 16.373, "r"), ("Грац", 47.070, 15.439, "l"), ("Марибор", 46.554, 15.646, "l"),
          ("Загреб", 45.815, 15.982, "r"), ("Задар", 44.119, 15.231, "l")]


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
                req = urllib.request.Request(TILE_URL.format(z=Z, x=tx, y=ty), headers={"User-Agent": "vlog-route"})
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


def bolt(d, x, y, color, h=26):
    """A lightning bolt drawn as a polygon (no unicode glyph), top-left at (x, y)."""
    k = h / 26
    pts = [(10, 0), (2, 15), (9, 15), (5, 26), (17, 9), (10, 9), (14, 0)]
    d.polygon([(x + a * k, y + b * k) for a, b in pts], fill=color)


def pin_label(x, y, title, sub, side="right", charge=None, charge_ok=True):
    """Title, sub line, and an optional charger line with a bolt (green: a charger here, grey: none)."""
    fb, fr = ImageFont.truetype(FONT_B, 30), ImageFont.truetype(FONT_R, 25)

    def draw(d):
        tw = max(d.textlength(title, font=fb), d.textlength(sub, font=fr),
                 (d.textlength(charge, font=fr) + 26) if charge else 0)
        hh = 82 + (36 if charge else 0)
        bx = x + 26 if side == "right" else x - 26 - tw - 28
        by = y - 40
        d.rounded_rectangle((bx, by, bx + tw + 28, by + hh), 12, fill=(15, 15, 15, 200))
        d.text((bx + 14, by + 6), title, font=fb, fill=(255, 255, 255, 255))
        d.text((bx + 14, by + 44), sub, font=fr, fill=(215, 215, 215, 255))
        if charge:
            c = (110, 220, 120, 255) if charge_ok else (190, 190, 190, 255)
            bolt(d, bx + 14, by + 84, c, 24)
            d.text((bx + 40, by + 80), charge, font=fr, fill=c)
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


def fade(img, t, length):
    k = min(1.0, t / 0.4, (length - t) / 0.4)
    return img if k >= 1 else (img.astype(np.float32) * max(k, 0)).astype(np.uint8)


def stop_dot(img, xy):
    c = (int(round(xy[0] * 4)), int(round(xy[1] * 4)))
    cv2.circle(img, c, 9 * 4, (255, 255, 255), -1, cv2.LINE_AA, shift=2)
    cv2.circle(img, c, 6 * 4, (230, 60, 60), -1, cv2.LINE_AA, shift=2)


def legs_panel(rows, y0=310):
    """rows: (kind, text, t_in); kind 'leg' (white) / 'stop' (title amber) / 'why' (grey, under a stop)."""
    out, y = [], y0
    for kind, text, t_in in rows:
        if kind == "leg":
            out.append((panel([(FONT_R, 30, text, (255, 255, 255), y)]), t_in)); y += 50
        elif kind == "stop":
            out.append((panel([(FONT_B, 30, text, (255, 200, 90), y)]), t_in)); y += 40
        else:
            out.append((panel([(FONT_R, 27, text, (200, 200, 200), y)]), t_in)); y += 52
    return out, y


def note_box(x, y, lines):
    """A caption box: first line bold, then regular lines; (x, y) its top-left corner."""
    fb, fr = ImageFont.truetype(FONT_B, 28), ImageFont.truetype(FONT_R, 25)

    def draw(d):
        tw = max(d.textlength(t, font=fb if i == 0 else fr) for i, t in enumerate(lines))
        d.rounded_rectangle((x, y, x + tw + 28, y + 16 + 38 + 34 * (len(lines) - 1)), 12, fill=(15, 15, 15, 210))
        for i, t in enumerate(lines):
            d.text((x + 14, y + 6 + (0 if i == 0 else 40 + 34 * (i - 1))), t, font=fb if i == 0 else fr,
                   fill=(255, 200, 90, 255) if i == 0 else (225, 225, 225, 255))
    return draw


def run_day(name, base, json_name, length, moves, stops, head, rows, total, ends, under=None, color=BLUE,
            notes=(), plan=None):
    """moves: (t0, t1, km0, km1) pieces of the drive; stops: (km, t_in, t_out, title, why, side, charge, ok).
    plan: dict(t0, t1, t_out, lines, pins=[(km, title, sub, side)]): the planned route drawn white first."""
    pts, km, wp = load_route(json_name)
    n = int(length * FPS)
    ov = Overlay()
    ov.add(panel(head), 0.3)
    if plan:
        ov.add(panel(plan["lines"]), plan["t0"] - 0.2, plan["t_out"])
        for pkm, title, sub, side in plan.get("pins", []):
            xy = upto(pts, km, pkm)[-1]
            ov.add(pin_label(xy[0], xy[1], title, sub, side), plan["t1"] - 0.3, plan["t_out"])
    items, y = legs_panel(rows)
    for fn, t_in in items:
        ov.add(fn, t_in)
    ov.add(panel([(FONT_B, 32, total[0], (255, 255, 255), y + 24),
                  (FONT_R, 29, total[1], (220, 220, 220), y + 70)]
                 + ([(FONT_R, 27, total[3], (190, 190, 190), y + 112)] if len(total) > 3 else [])), total[2])
    for (lat, lon), title, sub, side, t_in, t_out in ends:
        x, yy = screen(lat, lon)
        ov.add(pin_label(x, yy, title, sub, side), t_in, t_out)
    for fn, t_in, t_out in notes:
        ov.add(fn, t_in, t_out)
    stop_xy = []
    for skm, t_in, t_out, title, why, side, charge, ok in stops:
        xy = upto(pts, km, skm)[-1]
        stop_xy.append((xy, t_in))
        ov.add(pin_label(xy[0], xy[1], title, why, side, charge, ok), t_in, t_out)
    plan_xy = [upto(pts, km, p[0])[-1] for p in (plan or {}).get("pins", [])]

    def dist(t):
        if t <= moves[0][0]:
            return moves[0][2]
        for t0, t1, k0, k1 in moves:
            if t <= t1:
                return k0 + (k1 - k0) * ease((t - t0) / (t1 - t0)) if t >= t0 else k0
        return moves[-1][3]

    def gen():
        for f in range(n):
            t = f / FPS
            d = dist(t)
            img = base.copy()
            if under is not None:
                img = line(img, under, BLUE, 5, 0.45)
            if plan and t >= plan["t0"]:
                pd = km[-1] * ease((t - plan["t0"]) / (plan["t1"] - plan["t0"]))
                img = line(img, upto(pts, km, pd), (245, 245, 245), 4, 0.85)
                if plan["t1"] - 0.3 <= t < plan["t_out"] + 0.5:
                    for xy in plan_xy:
                        c = (int(round(xy[0] * 4)), int(round(xy[1] * 4)))
                        cv2.circle(img, c, 9 * 4, (255, 255, 255), -1, cv2.LINE_AA, shift=2)
                        cv2.circle(img, c, 6 * 4, (80, 200, 100), -1, cv2.LINE_AA, shift=2)
            if not plan or t >= moves[0][0] - 0.3:
                img = line(img, upto(pts, km, d), color)
                for xy, t_in in stop_xy:
                    if t >= t_in - 0.05:
                        stop_dot(img, xy)
                dot(img, upto(pts, km, d)[-1], color)
            img = ov.apply(img, t)
            yield fade(img, t, length)
    encode(name, gen(), n)


S = 5.0      # the plan phase before the real drive


def plan_lines(rows):
    out, y = [(FONT_B, 34, "План перед виїздом", (255, 255, 255), 310)], 365
    for size, text, col in rows:
        out.append((FONT_R, size, text, col, y))
        y += 46 if size >= 30 else 40
    return out


def day1(base):
    # OSRM legs 320 / 137+77 / 103 km (637), car 618: per leg 310 / 208 / 100.
    # Tesla plan as the author makes it: Google's time + ABRP's charging (ABRP's driving is too optimistic).
    # ABRP (Tesla, 23.08 09:45): Ionity Vrankovec after 297 of 624 km, Ionity Pinkafeld after 508: scaled to OSRM.
    _, km, wp = load_route("day1.json")
    lb, sch, end = wp[1], wp[3], km[-1]
    f = end / 624
    run_day("route_d1", base, "day1.json", 14.0 + S,
            plan=dict(t0=0.8, t1=2.8, t_out=S,
                      lines=plan_lines([(30, "Google: 615 км · 6 год 22 хв", (255, 255, 255)),
                                        (30, "Тесла: + 28 хв зарядок = 6 год 50 хв", (255, 255, 255)),
                                        (27, "2 зарядки Ionity за ABRP: 28 хв, + 12 хв запасу", (110, 220, 120)),
                                        (25, "запас: батарея LG заряджається повільніше,", (190, 190, 190)),
                                        (25, "Ionity менш надійні, ніж Supercharger", (190, 190, 190))]),
                      pins=[(297 * f, "Ionity Vrankovec", "Тесла: 21 хв зарядки", "left"),
                            (508 * f, "Ionity Pinkafeld", "Тесла: 11 хв зарядки", "left")]),
            moves=[(S + 1.0, S + 3.6, 0, lb), (S + 5.2, S + 7.2, lb, sch), (S + 8.6, S + 9.8, sch, end)],
            stops=[(lb, S + 3.6, S + 5.8, "Lepa Bukva · 45 хв", "обід і відпочинок", "right",
                    "зарядка ELEN 50 кВт", True),
                   (sch, S + 7.2, S + 9.0, "Schäffern · 24 хв", "відпочинок після ремонту дороги", "right",
                    "зарядки немає; Ionity Pinkafeld поруч", False)],
            head=[(FONT_B, 54, "День 1", (255, 255, 255), 110),
                  (FONT_R, 32, "23 серпня 2024, п'ятниця", (220, 220, 220), 185),
                  (FONT_R, 32, "Mercedes GLC 220d, 4 людини", (220, 220, 220), 230)],
            rows=[("leg", "10:06-13:10 · 310 км · 3 год 04 хв", S + 1.0),
                  ("stop", "13:10-13:55 Lepa Bukva, 45 хв", S + 3.6),
                  ("why", "обід після хорватських заторів; без заправки", S + 3.6),
                  ("leg", "13:55-16:11 · 208 км · 2 год 16 хв", S + 5.2),
                  ("stop", "16:11-16:35 Schäffern, 24 хв", S + 7.2),
                  ("why", "відпочинок після 14 км вузької смуги", S + 7.2),
                  ("leg", "16:35-17:53 · 100 км · 1 год 18 хв", S + 8.6)],
            total=("618 км · 7 год 47 хв", "зупинки 1 год 09 хв, заправок 0", S + 10.2,
                   "план: Мерседес 6 год 22 хв, Тесла 6 год 50 хв"),
            notes=[(note_box(40, 598, ["Австрія: 14 км ремонту дороги",
                                      "вузька смуга між бетонними відбійниками,",
                                      "дуже нервово; краще було б їхати",
                                      "за фурами лівою смугою"]), S + 5.4, S + 9.0)],
            ends=[((44.2257, 15.5328), "Масленіца · 10:06", "старт, повний бак", "right", 0.4, S + 3.0),
                  ((48.2075, 16.1755), "Пуркерсдорф · 17:53", "ночівля біля Відня", "right", S + 9.8, None)])


def day2(base):
    # OSRM legs 152 / 240 / 477 km; car 155 to Brno (IMG_8051), 397 to the refuel, 471 after.
    # Google plan built by the user 15.11.2026 (usual traffic): 875 km, 8 h 20 min.
    p1, _, _ = load_route("day1.json")
    _, km, wp = load_route("day2.json")
    br, wi, end = wp[1], wp[2], km[-1]
    run_day("route_d2", base, "day2.json", 14.0 + S,
            plan=dict(t0=0.8, t1=2.8, t_out=S,
                      lines=plan_lines([(30, "Google: 875 км · 8 год 20 хв", (255, 255, 255)),
                                        (27, "у звичайному трафіку, без зупинок", (200, 200, 200)),
                                        (30, "Тесла: + 1 год 51 хв = 10 год 11 хв", (255, 255, 255)),
                                        (27, "2 зарядки, як Теслою у серпні 2025:", (110, 220, 120)),
                                        (27, "Острава 51 хв, Лодзь 60 хв", (110, 220, 120))]),
                      # TeslaFi 22-23.08.2025, Wien Stadlau -> home: Rudna Ostrava 20:08-20:59, GreenWay A1
                      # Rokicinska Lodz 23:19-00:19; on this route at 308 and 585 km (nearest point, 2 / 0.6 km off)
                      pins=[(308, "Supercharger Острава", "Тесла 2025: 51 хв зарядки", "left"),
                            (585, "GreenWay Лодзь", "Тесла 2025: 60 хв зарядки", "left")]),
            moves=[(S + 1.0, S + 3.0, 0, br), (S + 4.4, S + 6.6, br, wi), (S + 8.2, S + 10.0, wi, end)],
            stops=[(br, S + 3.0, S + 5.0, "Брно · 32 хв", "туалет, відпочинок", "right",
                    "зарядка PRE, CCS 75 кВт", True),
                   (wi, S + 6.6, S + 8.8, "Orlen Wiszowa · 66 хв", "обід і заправка", "right",
                    "зарядка Orlen Charge 100 кВт", True)],
            head=[(FONT_B, 54, "День 2", (255, 255, 255), 110),
                  (FONT_R, 32, "24 серпня 2024, субота", (220, 220, 220), 185),
                  (FONT_R, 32, "до Старогарда-Гданського", (220, 220, 220), 230)],
            rows=[("leg", "09:27-11:26 · 155 км · 1 год 59 хв", S + 1.0),
                  ("stop", "11:26-11:58 Брно, 32 хв", S + 3.0),
                  ("why", "туалет, відпочинок; без заправки", S + 3.0),
                  ("leg", "11:58-14:02 · 242 км · 2 год 04 хв", S + 4.4),
                  ("stop", "14:02-15:08 Orlen Wiszowa, 66 хв", S + 6.6),
                  ("why", "довгий обід і заправка; 397 км від Пуркерсдорфа", S + 6.6),
                  ("leg", "15:08-18:40 · 471 км · 3 год 32 хв", S + 8.2)],
            total=("868 км · 9 год 13 хв", "2 зупинки: 1 год 38 хв, заправка 1", S + 10.4,
                   "Мерседесом 471 км безперервно"),
            ends=[((48.2075, 16.1755), "Пуркерсдорф · 09:27", "старт", "right", 0.4, S + 2.6),
                  ((53.958, 18.5417), "Старогард · 18:40", "вдома", "left", S + 10.0, None)],
            under=p1, color=AMBER)


if __name__ == "__main__":
    base = backdrop()
    import sys
    if "--still" in sys.argv:
        Image.fromarray(base).save("backdrop_check.png")
    else:
        day1(base)
        day2(base)
