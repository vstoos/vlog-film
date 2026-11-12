"""Burn pictures and captions into a talking clip at its own seconds, so every cut keeps them in sync.

filmkit shows the talking clip only while it talks: what must appear over the speech (b-roll, a phone
screenshot, a caption) goes into the clip's picture. A portrait picture (phone screenshot, vertical clip,
portrait photo) stands at full frame height flush against the frame edge on the free side of the
speaker's face, which stays in view; a landscape
one covers the frame.

usage: python burn_in.py <clip.mov> <out.mov> <spec.json>
spec: {"broll": [[second, length, picture, second in the picture, speed?], ...],
       "captions": [[second, length, title, subtitle, "top"?], ...],   # "top": band at the top
       "mute": [[start, end], ...],          # a tongue click or knock in a pause: silenced, picture untouched
       "arrows": [[[t, x, y], ...], ...]}    # an arrow whose tip follows these points (track() makes them);
                                             # {"keys": [...], "side": "left"}: the arrow comes from the upper left
From a project script: import burn_in; burn_in.burn(clip, out, broll, captions).
"""
import json
import subprocess
import sys

import numpy as np

import vfconfig as vf

W, H = 1920, 1080
FADE = 0.3          # a portrait picture fades in and out; one right after another replaces it without a blink
HLG_TAGS = ["-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"]
SDR_TO_HLG = ("setparams=color_trc=bt709:color_primaries=bt709:colorspace=bt709:range=tv,format=yuv444p,"
              "libplacebo=colorspace=bt2020nc:color_primaries=bt2020:color_trc=arib-std-b67:range=tv:format=yuv420p10le,")
IMAGE = (".png", ".jpg", ".jpeg", ".heic")


def is_image(pic):
    return pic.lower().endswith(IMAGE)


def size(pic):
    """Displayed width and height: a phone clip's rotation tag swaps them."""
    st = json.loads(subprocess.run([vf.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height:stream_side_data=rotation", "-of", "json", pic],
                                   capture_output=True, text=True).stdout)["streams"][0]
    rot = next((abs(int(d["rotation"])) for d in st.get("side_data_list", []) if "rotation" in d), 0)
    return (st["height"], st["width"]) if rot in (90, 270) else (st["width"], st["height"])


def portrait(pic):
    w, h = size(pic)
    return h > w


def face_box(clip, t0, n, samples=3):
    """Left and right edge (px of a 1920 frame) of the speaker's face over [t0, t0+n]: the union of the
    largest face in a few frames. None when no face is found."""
    det, box = None, None
    for t in np.linspace(t0 + 0.2, t0 + n - 0.2, samples):
        raw = subprocess.run([vf.FFMPEG, "-v", "error", "-ss", "%.2f" % t, "-i", clip, "-frames:v", "1",
                              "-vf", "scale=640:360", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                             capture_output=True).stdout
        if len(raw) < 640 * 360 * 3:
            continue
        import cv2
        det = det or cv2.FaceDetectorYN.create(vf.FACE_MODEL, "", (640, 360), 0.6, 0.3, 50)
        _, fs = det.detect(np.frombuffer(raw, np.uint8).reshape(360, 640, 3))
        if fs is None:
            continue
        f = max(fs, key=lambda f: f[2] * f[3])
        a, b = f[0] * 3, (f[0] + f[2]) * 3
        box = (min(box[0], a), max(box[1], b)) if box else (a, b)
    return box


def side_x(clip, t0, n, pic_w):
    """Left edge for a portrait picture pic_w wide: flush against the frame edge on the wider free side of
    the face (user 2026-11-12: a picture set in from the edge covered part of the face), so it keeps as far
    from the face as it can. Without a face: the left edge."""
    box = face_box(clip, t0, n)
    if not box:
        return 0
    left, right = box[0], W - box[1]      # room left of the face, right of it
    return 0 if left >= right else W - pic_w


def pic_input(k, t0, n, pic, at, speed=1.0, fades=(True, True)):
    """Input args and filter for picture k shown from t0 for n seconds. A clip plays from `at` at `speed`;
    an SDR photo wider than the frame pans from top to bottom; a portrait picture is scaled to the full
    frame height and fades in and out (fades: (in, out)), to stand beside the face (see burn())."""
    if is_image(pic):
        args = ["-loop", "1", "-framerate", "30", "-t", str(n), "-i", pic]
    else:
        args = ["-ss", str(at), "-t", str(n / speed), "-i", pic]
    if portrait(pic):
        pre = "" if is_image(pic) else "setpts=PTS/%s," % speed
        pre += "scale=-2:%d:flags=lanczos," % H + (SDR_TO_HLG if is_image(pic) else "") + "format=yuva444p10le,"
        if fades[0]:
            pre += "fade=t=in:st=0:d=%s:alpha=1," % FADE
        if fades[1]:
            pre += "fade=t=out:st=%s:d=%s:alpha=1," % (n - FADE, FADE)
        return args, "[%d:v]%sfps=30,setsar=1,setpts=PTS-STARTPTS+%s/TB[b%d];" % (k, pre, t0, k)
    if is_image(pic):
        pre = "scale=%d:-2,crop=%d:%d:0:'(ih-%d)*t/%s'," % (W, W, H, H, n) + SDR_TO_HLG
    else:
        pre = "setpts=PTS/%s,scale=%d:%d," % (speed, W, H)
    return args, "[%d:v]%sfps=30,setsar=1,format=yuv444p10le,setpts=PTS-STARTPTS+%s/TB[b%d];" % (k, pre, t0, k)


def overlay(prev, k, t0, n, out, x=0):
    return "[%s][b%d]overlay=x=%d:y=0:format=yuv444p10:eof_action=pass:repeatlast=0:enable='between(t,%s,%s)'[%s];" % (
        prev, k, x, t0, t0 + n, out)


def text_file(folder, name, text):
    path = "%s/cap_%s.txt" % (folder, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path.replace(":", "\\:")


def caption(folder, name, t0, n, title, sub, where="bottom", white="0xBFBFBF"):
    """Band, title and subtitle between t0 and t0+n, on the absolute time of the stream. where="top" puts
    the band at the top of the frame, for a picture whose subject sits low (an arrow pointing there)."""
    alpha = "if(lt(t,{a}),0,if(lt(t,{b}),(t-{a})/0.5,if(lt(t,{c}),1,if(lt(t,{d}),({d}-t)/0.5,0))))".format(
        a=t0, b=t0 + 0.5, c=t0 + n - 0.5, d=t0 + n)
    en = "between(t,%s,%s)" % (t0, t0 + n)
    band, yt, ys = ("0", "30", "120") if where == "top" else ("ih-230", "h-200", "h-110")
    return ("drawbox=x=0:y={band}:w=iw:h=230:color=black@0.6:t=fill:enable='{en}',"
            "drawtext=fontfile='{fb}':textfile='{tt}':expansion=none:fontsize=60:fontcolor={w}:alpha='{a}':"
            "x=(w-text_w)/2:y={yt}:shadowcolor=black@0.6:shadowx=2:shadowy=2:enable='{en}',"
            "drawtext=fontfile='{fb}':textfile='{ts}':expansion=none:fontsize=46:fontcolor={w}:alpha='{a}':"
            "x=(w-text_w)/2:y={ys}:shadowcolor=black@0.6:shadowx=2:shadowy=2:enable='{en}',").format(
        en=en, fb=vf.ff_font(vf.FONT_BOLD), tt=text_file(folder, name + "t", title),
        ts=text_file(folder, name + "s", sub), w=white, a=alpha, band=band, yt=yt, ys=ys)


def plan(clip, broll):
    """(fades, x) for each b-roll item: portrait ones go beside the face; one that starts where another
    portrait one ends replaces it without fading."""
    port = [(s, s + n) for s, n, pic, *_ in broll if portrait(pic)]
    out = []
    for s, n, pic, *_ in broll:
        if not portrait(pic):
            out.append(((True, True), 0))
            continue
        w, h = size(pic)
        fades = (not any(abs(e - s) < 0.5 for _, e in port), not any(abs(b - s - n) < 0.5 for b, _ in port))
        out.append((fades, side_x(clip, s, n, round(w * H / h))))
    return out


def track(pic, at, n, x, y, speed=1.0, step=0.1, t0=0.0):
    """Follow the point (x, y) (px of a 1920x1080 frame) through `pic` from second `at`, for n seconds of
    film played at `speed`: Lucas-Kanade flow on features around the point, median move per frame.
    Returns keyframes [(t0 + film second, x, y), ...] every `step` s, for arrows=[...] in burn()."""
    import cv2
    w, h = 960, 540
    raw = subprocess.run([vf.FFMPEG, "-v", "error", "-ss", str(at), "-t", str(n * speed), "-i", pic, "-vf",
                          "fps=30,scale=%d:%d" % (w, h), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True).stdout
    frames = np.frombuffer(raw, np.uint8)[:len(raw) // (w * h) * w * h].reshape(-1, h, w)
    px, py = x / 2, y / 2
    pos = [(px, py)]
    for a, b in zip(frames[:-1], frames[1:]):
        mask = np.zeros_like(a)
        cv2.circle(mask, (int(px), int(py)), 40, 255, -1)
        pts = cv2.goodFeaturesToTrack(a, 40, 0.01, 4, mask=mask)
        if pts is not None:
            nxt, ok, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None, winSize=(31, 31), maxLevel=3)
            d = (nxt - pts)[ok.ravel() == 1].reshape(-1, 2)
            if len(d):
                px, py = px + float(np.median(d[:, 0])), py + float(np.median(d[:, 1]))
        pos.append((px, py))
    keys = []
    for k in range(int(n / step) + 1):
        i = min(len(pos) - 1, int(round(k * step * speed * 30)))
        keys.append((round(t0 + k * step, 3), round(pos[i][0] * 2, 1), round(pos[i][1] * 2, 1)))
    return keys


ARROW = 180   # px, tip at the bottom left: the arrow comes in from the upper right


def arrow_png(path, side="right"):
    """A yellow arrow with a dark outline on transparency, pointing to its bottom-left corner (coming in
    from the upper right); side="left": mirrored, coming in from the upper left to its bottom-right corner."""
    from PIL import Image, ImageDraw
    s = 4   # drawn large, then scaled down: smooth edges
    im = Image.new("RGBA", (ARROW * s, ARROW * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    a = ARROW * s
    head = [(0, a), (0.18 * a, 0.52 * a), (0.48 * a, 0.82 * a)]          # tip at (0, a)
    shaft = [(0.24 * a, 0.70 * a), (a * 0.96, 0.02 * a)]
    for width, colour in ((22 * s, (20, 20, 20, 230)), (12 * s, (255, 214, 0, 255))):
        d.line(shaft, fill=colour, width=width)
        d.polygon(head, fill=colour, outline=colour, width=width // 3 if colour[0] == 20 else 0)
    im = im.resize((ARROW, ARROW), Image.LANCZOS)
    (im.transpose(Image.FLIP_LEFT_RIGHT) if side == "left" else im).save(path)
    return path


def lerp_expr(keys, i):
    """ffmpeg expression of coordinate i (1 x, 2 y) of keyframes [(t, x, y), ...], linear between them."""
    e = "%s" % keys[-1][i]
    for (ta, *pa), (tb, *pb) in reversed(list(zip(keys[:-1], keys[1:]))):
        e = "if(lt(t,%s),%s+(%s)*(t-%s)/%s,%s)" % (tb, pa[i - 1], pb[i - 1] - pa[i - 1], ta, max(tb - ta, 1e-3), e)
    return e


def muted(clip, out_wav, mute, floor=0.03, ramp=0.005):
    """The clip's sound with each (start, end) of `mute` (clip seconds) brought down to `floor`, with
    `ramp` s edges: a tongue click or a knock in a pause, without cutting the picture (timing stays)."""
    import soundfile as sf
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-i", clip, "-vn", out_wav], check=True)
    x, sr = sf.read(out_wav, dtype="float32")
    t = np.arange(len(x)) / sr
    g = np.ones(len(x), np.float32)
    for a, b in mute:
        d = np.maximum(a - t, t - b)                  # < 0 inside, distance outside
        g = np.minimum(g, np.clip(floor + (1 - floor) * d / ramp, floor, 1))
    sf.write(out_wav, x * (g[:, None] if x.ndim > 1 else g), sr)
    return out_wav


def burn(clip, out, broll=(), captions=(), start=None, length=None, mute=(), arrows=()):
    """Write `out`: `clip` with the b-roll and captions burnt in at its own seconds, sound copied (or with
    the `mute` moments silenced, see muted()). arrows: keyframe lists from track(), an arrow whose tip
    follows them (fading in and out). start/length render only that window (a test); the items keep
    their clip times."""
    folder = out.replace("\\", "/").rsplit("/", 1)[0]
    cut = ["-ss", str(start), "-t", str(length)] if start is not None else []
    inputs, graph, prev = [*cut, "-i", clip], ["[0:v]format=yuv444p10le,setpts=PTS-STARTPTS+%s/TB[v0];" % (start or 0)], "v0"
    i = 0
    for (s, n, pic, at, *speed), (fades, x) in zip(broll, plan(clip, broll)):
        if start is not None and not (start - n < s < start + length):
            continue
        i += 1   # input number: only the pictures inside the window are inputs
        args, f = pic_input(i, s, n, pic, at, *speed, fades=fades)
        inputs += args
        graph += [f, overlay(prev, i, s, n, "v%d" % i, x)]
        prev = "v%d" % i
    for k, arrow in enumerate(arrows):
        # a keyframe list from track(), or {"keys": [...], "side": "left"} for an arrow from the upper left
        keys, side = (arrow["keys"], arrow.get("side", "right")) if isinstance(arrow, dict) else (arrow, "right")
        a, b = keys[0][0], keys[-1][0]
        if start is not None and not (start < b and a < start + length):
            continue
        i += 1
        inputs += ["-loop", "1", "-framerate", "30", "-t", str(b - a), "-i", arrow_png("%s_arrow%d.png" % (out, k), side)]
        graph.append("[%d:v]format=yuva444p10le,fade=t=in:st=0:d=0.3:alpha=1,fade=t=out:st=%s:d=0.3:alpha=1,"
                     "setpts=PTS-STARTPTS+%s/TB[b%d];" % (i, max(0, b - a - 0.3), a, i))
        graph.append("[%s][b%d]overlay=x='%s-%d':y='%s-%d':format=yuv444p10:eof_action=pass:repeatlast=0:"
                     "enable='between(t,%s,%s)'[v%d];" % (prev, i, lerp_expr(keys, 1), ARROW if side == "left" else 0,
                                                           lerp_expr(keys, 2), ARROW, a, b, i))
        prev = "v%d" % i
    tail = "[%s]" % prev + "".join(caption(folder, "b%d" % k, *c) for k, c in enumerate(captions))
    graph.append(tail + "setpts=PTS-STARTPTS,format=yuv420p10le[out]")
    script = out + "_filter.txt"
    with open(script, "w", encoding="utf-8") as f:
        f.write("\n".join(graph))
    audio = ["-map", "0:a:0", "-c:a", "copy"]
    if mute:
        inputs += [*cut, "-i", muted(clip, out + "_audio.wav", mute)]
        audio = ["-map", "%d:a:0" % (i + 1), "-c:a", "aac", "-b:a", "256k"]
    subprocess.run([vf.FFMPEG, "-v", "error", "-stats", "-y", "-init_hw_device", "vulkan", *inputs,
                    "-filter_complex_script", script, "-map", "[out]", *audio,
                    *vf.hevc_args(), *HLG_TAGS, out], check=True)


if __name__ == "__main__":
    spec = json.load(open(sys.argv[3], encoding="utf-8"))
    burn(sys.argv[1], sys.argv[2], spec.get("broll", []), spec.get("captions", []), mute=spec.get("mute", []),
         arrows=spec.get("arrows", []))
