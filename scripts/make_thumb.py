"""YouTube thumbnail: a frame (raw or improved in Gemini) + big outlined headline + smaller line.

usage: python make_thumb.py <image> <out.jpg> "<HEADLINE>" "<second line>" [--plate x0,y0,x1,y1]
Coordinates for --plate are in the source image's pixels. Output is 1280x720 JPEG under 2 MB.
"""
import argparse

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1280, 720
import vfconfig as vf

BLACK_FONT = vf.FONT_BLACK     # headline (Segoe UI Black on Windows)
BOLD_FONT = vf.FONT_BOLD
YELLOW = (255, 214, 0)


def fit_font(draw, text, path, max_w, start):
    size = start
    while size > 20:
        f = ImageFont.truetype(path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return ImageFont.truetype(path, size)


def make(src, out, headline, line2, plate=None):
    im = Image.open(src).convert("RGB")
    if plate:
        im.paste(im.crop(plate).filter(ImageFilter.GaussianBlur(14)), plate)
    im = ImageOps.fit(im, (W, H), Image.LANCZOS)
    # darken the top so white and yellow text read on a bright sky
    shade = Image.new("L", (W, H))
    sd = ImageDraw.Draw(shade)
    for y in range(H // 2):
        sd.line([(0, y), (W, y)], fill=int(150 * (1 - y / (H / 2))))
    im = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), im, shade)
    d = ImageDraw.Draw(im)
    f1 = fit_font(d, headline, BLACK_FONT, W - 80, 130)
    tw = d.textlength(headline, font=f1)
    d.text(((W - tw) / 2, 22), headline, font=f1, fill=YELLOW, stroke_width=8, stroke_fill=(0, 0, 0))
    if line2:
        f2 = fit_font(d, line2, BOLD_FONT, W - 120, 64)
        tw = d.textlength(line2, font=f2)
        d.text(((W - tw) / 2, 22 + f1.size + 18), line2, font=f2, fill=(255, 255, 255),
               stroke_width=5, stroke_fill=(0, 0, 0))
    im.save(out, quality=92)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("headline")
    ap.add_argument("line2", nargs="?", default="")
    ap.add_argument("--plate", help="x0,y0,x1,y1 to blur, in source pixels")
    a = ap.parse_args()
    make(a.src, a.out, a.headline, a.line2, tuple(int(v) for v in a.plate.split(",")) if a.plate else None)
