"""Animated "subscribe" banner, burnt over a road insert, a card or the user's own spoken call to subscribe.

The user (17.11.2026): no scripted "subscribe" line in every film. Instead this banner, and where he
asked viewers to subscribe himself, that voice line laid over a road insert or a statistics card with
the banner on top (burn_in.py "subscribe"); see SKILL.md, "Subscribe call".

The banner (about 4.6 s): a red pill button with the film's language word and, under it, the second
language (Polish) slides in at the lower right, a cursor clicks it, it turns grey ("subscribed"), the
cursor clicks the bell beside it, the bell rings, and everything slides out.

    python subscribe.py <out_dir> [pl]      # renders <out_dir>/subscribe_<langs>.mov and a check frame sheet

From code: subscribe.banner(folder, second_lang) -> mov path (cached); subscribe.add(src_mov, out_mov, t0)
burns it into a finished HLG insert (filmkit does this for an EDL item with {"subscribe": t0}).
"""
import math
import os
import subprocess
import sys

import vfconfig as vf

W, H = 1920, 1080
FPS = 30
CLICK, BELL = 1.6, 2.7     # s into the banner: the cursor clicks the button, then the bell
BANNER_LEN = 4.6           # with the default bell time
BW, BH = 760, 190          # the banner's own canvas; placed at the lower right of the frame
X, Y = W - BW - 40, H - BH - 250   # above the caption band (bottom 230 px), clear of the right edge
HLG_WHITE = 0.75           # graphics white in HLG sits at ~75 % signal (captions use 0xBFBFBF)

TEXT = {"uk": ("ПІДПИСАТИСЯ", "ВИ ПІДПИСАНІ"), "pl": ("Subskrybuj", "Subskrybujesz"),
        "en": ("SUBSCRIBE", "SUBSCRIBED")}
RED, GREY = (204, 0, 0), (96, 96, 96)


def _ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _bell(d, cx, cy, r, fill, angle=0.0, s=1):
    """A bell centred at (cx, cy), radius r, rotated by angle (deg) around its top."""
    pts = []
    # dome + flared skirt, as a polygon (local coordinates, top at (0, -r))
    for i in range(0, 181, 10):
        a = math.radians(180 + i)
        pts.append((0.62 * r * math.cos(a), -0.35 * r + 0.62 * r * math.sin(a)))
    pts += [(0.62 * r, 0.35 * r), (0.95 * r, 0.62 * r), (-0.95 * r, 0.62 * r), (-0.62 * r, 0.35 * r)]
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    pivot = (0, -r)

    def rot(p):
        x, y = p[0] - pivot[0], p[1] - pivot[1]
        return (cx + pivot[0] + x * ca - y * sa, cy + pivot[1] + x * sa + y * ca)
    poly = [rot(p) for p in pts]
    if fill:
        d.polygon(poly, fill=(255, 255, 255, 255))
    else:
        d.line(poly + [poly[0]], fill=(255, 255, 255, 255), width=5 * s, joint="curve")
    kx, ky = rot((0, 0.82 * r))
    d.ellipse((kx - 0.16 * r, ky - 0.16 * r, kx + 0.16 * r, ky + 0.16 * r), fill=(255, 255, 255, 255))
    tx, ty = rot((0, -r - 0.05 * r))
    d.ellipse((tx - 0.1 * r, ty - 0.1 * r, tx + 0.1 * r, ty + 0.1 * r), fill=(255, 255, 255, 255))


def _cursor(d, x, y, s, press):
    """Mouse pointer with its tip at (x, y); press makes it a little smaller (the click)."""
    k = (0.85 if press else 1.0) * s
    p = [(0, 0), (0, 46), (11, 35), (19, 54), (27, 50), (19, 32), (34, 32)]
    poly = [(x + px * k, y + py * k) for px, py in p]
    d.polygon(poly, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=int(3 * s))


def frame(t, langs, s=2, bell=BELL):
    """RGBA banner image at time t (seconds into the banner); bell: when the cursor clicks the bell."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGBA", (BW * s, BH * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    main, sub = TEXT[langs[0]], TEXT[langs[1]] if len(langs) > 1 else None
    fb = ImageFont.truetype(vf.FONT_BOLD, 46 * s)
    fs = ImageFont.truetype(vf.FONT_BOLD, 30 * s)
    t_in, t_out = 0.45, length(bell) - 0.45
    click1, click2 = CLICK, bell
    done = t >= click1 + 0.08
    # slide in from the right, slide out to the right
    off = (1 - _ease(t / t_in)) * BW * s if t < t_in else _ease((t - t_out) / 0.45) * BW * s if t > t_out else 0
    k = 0.94 if click1 <= t < click1 + 0.16 else 1.0     # the button dips when clicked
    word, word2 = (main[1], sub[1] if sub else None) if done else (main[0], sub[0] if sub else None)
    # one width for both states, so the button does not jump when it turns grey
    tw = max([d.textlength(w, font=fb) for w in main] + [d.textlength(w, font=fs) for w in (sub or ())])
    bw_, bh_ = tw + 80 * s, (150 if sub else 110) * s
    bx0 = BW * s - 180 * s - bw_ + off
    by0 = (BH * s - bh_) / 2
    cx, cy = bx0 + bw_ / 2, by0 + bh_ / 2
    box = (cx - bw_ * k / 2, cy - bh_ * k / 2, cx + bw_ * k / 2, cy + bh_ * k / 2)
    d.rounded_rectangle((box[0] + 6 * s, box[1] + 8 * s, box[2] + 6 * s, box[3] + 8 * s), radius=bh_ / 2,
                        fill=(0, 0, 0, 110))          # soft shadow, readable on bright road
    d.rounded_rectangle(box, radius=bh_ * k / 2, fill=(*(GREY if done else RED), 255))
    if sub:
        d.text((cx, cy - 22 * s), word, font=fb, fill=(255, 255, 255, 255), anchor="mm")
        d.text((cx, cy + 36 * s), word2, font=fs, fill=(235, 235, 235, 255), anchor="mm")
    else:
        d.text((cx, cy), word, font=fb, fill=(255, 255, 255, 255), anchor="mm")
    # the bell in a dark circle to the right of the button
    bcx, bcy, br = BW * s - 95 * s + off, BH * s / 2, 62 * s
    d.ellipse((bcx - br, bcy - br, bcx + br, bcy + br), fill=(30, 30, 30, 200))
    rung = t >= click2 + 0.08
    ang = 18 * math.sin((t - click2) * 26) * math.exp(-(t - click2) * 2.2) if rung else 0.0
    _bell(d, bcx, bcy + 6 * s, 34 * s, rung, ang, s)
    # the cursor: comes in, clicks the button, moves to the bell, clicks, leaves
    path = [(0.5, (BW * s + 40 * s, BH * s + 60 * s)), (click1, (cx + 20 * s, cy + 10 * s)),
            (click1 + 0.35, (cx + 20 * s, cy + 10 * s)), (click2, (bcx + 4 * s, bcy + 8 * s)),
            (click2 + 0.6, (bcx + 4 * s, bcy + 8 * s)), (t_out, (BW * s + 60 * s, BH * s + 80 * s))]
    if path[0][0] <= t <= path[-1][0]:
        for (ta, pa), (tb, pb) in zip(path[:-1], path[1:]):
            if ta <= t <= tb:
                e = _ease((t - ta) / max(tb - ta, 1e-3))
                px, py = pa[0] + (pb[0] - pa[0]) * e, pa[1] + (pb[1] - pa[1]) * e
                press = click1 <= t < click1 + 0.16 or click2 <= t < click2 + 0.16
                _cursor(d, px, py, s, press)
                break
    return im.resize((BW, BH), Image.LANCZOS)


def length(bell=BELL):
    return bell + BANNER_LEN - BELL


def timing(at):
    """Burn-in entry -> (start second, bell time in the banner). at: the second the button is clicked
    (on the word "subscribe"), or [that second, the second of the word "bell"] to click the bell on it."""
    sub, bell = (at[0], at[1]) if isinstance(at, (list, tuple)) else (at, at + BELL - CLICK)
    return sub - CLICK, max(CLICK + 0.6, bell - sub + CLICK)


def banner(folder, second_lang=None, first_lang="uk", bell=BELL):
    """Render (once) the banner as a mov with alpha, colours at HLG graphics white; returns its path."""
    from PIL import Image
    langs = [first_lang] + ([second_lang] if second_lang and second_lang != first_lang else [])
    out = "%s/subscribe_%s_%d.mov" % (folder, "_".join(langs), round(bell * 10))
    if os.path.exists(out):
        return out
    seq = "%s/subscribe_frames" % folder
    os.makedirs(seq, exist_ok=True)
    for i in range(int(length(bell) * FPS)):
        im = frame(i / FPS, langs, bell=bell)
        r, g, b, a = im.split()
        im = Image.merge("RGBA", [c.point(lambda v: int(v * HLG_WHITE)) for c in (r, g, b)] + [a])
        im.save("%s/%04d.png" % (seq, i))
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-framerate", str(FPS), "-i", seq + "/%04d.png",
                    "-c:v", "png", "-pix_fmt", "rgba", out], check=True)
    return out


def graph(i, t0, prev, out, bell=BELL):
    """filter_complex pieces: input i (the banner mov) over stream [prev] from t0 on -> [out]."""
    return ("[%d:v]scale=out_color_matrix=bt2020:out_range=tv,format=yuva444p10le,"
            "setpts=PTS-STARTPTS+%s/TB[sb%d];" % (i, t0, i) +
            "[%s][sb%d]overlay=x=%d:y=%d:format=yuv444p10:eof_action=pass:repeatlast=0:"
            "enable='between(t,%s,%s)'[%s];" % (prev, i, X, Y, t0, t0 + length(bell), out))


def add(src_mov, out_mov, t0, second_lang=None):
    """Burn the banner into a finished HLG insert, starting at second t0 (re-encodes the insert)."""
    folder = os.path.dirname(os.path.abspath(out_mov)).replace("\\", "/")
    b = banner(folder, second_lang)
    g = "[0:v]format=yuv444p10le[v0];" + graph(1, t0, "v0", "v1") + "[v1]format=yuv420p10le[out]"
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-i", src_mov, "-i", b, "-filter_complex", g,
                    "-map", "[out]", "-an", *vf.hevc_args(),
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    out_mov], check=True)


if __name__ == "__main__":
    folder = sys.argv[1].replace("\\", "/")
    os.makedirs(folder, exist_ok=True)
    langs = ["uk"] + sys.argv[2:3]
    from PIL import Image
    times = [0.2, 1.0, 1.65, 2.2, 2.9, 3.4]
    sheet = Image.new("RGBA", (BW * 2, BH * 3), (70, 90, 70, 255))
    for k, t in enumerate(times):
        im = frame(t, langs)
        sheet.alpha_composite(im, ((k % 2) * BW, (k // 2) * BH))
    sheet.save("%s/subscribe_sheet.png" % folder)
    print(banner(folder, langs[1] if len(langs) > 1 else None))
