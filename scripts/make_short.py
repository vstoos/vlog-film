"""Turn a landscape HLG render into a YouTube Short: 1080x1920 HLG, reframed around the speaker's face,
big burnt-in captions word by word, a hook line at the top, pictures in the upper part.

Build the Short as a small landscape film first (filmkit.py + render_final.py with its own project:
talk ranges, maybe one insert, no title card and no end card), then:

  python make_short.py <spec.json>

spec: {"src": "<landscape HLG mp4>", "out": "<short mp4>", "lang": "uk",
       "hook": "LG після 192 000 км", "hook_len": 4.0,            # top line for the first seconds (0 = whole Short)
       "pictures": [[t, length, "<png/jpg/HEIC or clip>"], ...],   # upper part of the frame, Short's own seconds
       "frame": [[from, to, "face" | "fit" | "center" | x], ...],   # overrides the automatic framing
       "music": ["<file in music_dir or a path>", offset_s], "music_lufs": -28}   # quiet bed under the voice
Framing: every shot (scene cut) is cropped 608x1080 around the median face centre and scaled up; a shot
with no face (road, screen, photo) is shown whole, 1080 wide, over a blurred fill ("fit"). x is the
crop's left edge in the 1920 frame.
Captions: the first run transcribes the Short with WhisperX and writes <spec>.words.json
([[start, end, word], ...]); fix the words there (names, numbers) and run again: the file is reused.
"""
import json
import os
import re
import subprocess
import sys

import numpy as np

import burn_in
import vfconfig as vf

W, H = 1080, 1920
CW = 608                    # crop width in the 1920x1080 source: 1080 * 9 / 16
WHITE = "0xBFBFBF"          # HLG reference white (~203 nits); full white glares on HDR phones
YELLOW = "0xBFA000"
CAP_Y = 1380                # caption centre line: above the Shorts UI (title, buttons) at the bottom
PIC_TOP, PIC_W, PIC_H = 420, 1000, 720   # pictures: a box under the hook line and over the captions
MUSIC_LUFS = -28.0          # music bed: 14 LU under the voice (-14); -34 was lost under the cabin noise


def duration(f):
    return float(subprocess.run([vf.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f],
                                capture_output=True, text=True).stdout)


def cuts(src, dur, thresh=0.3):
    """Shot boundaries [0, ..., dur]: scene changes (jump cuts inside one shot score low and stay in)."""
    out = subprocess.run([vf.FFMPEG, "-v", "info", "-i", src, "-an", "-vf",
                          "scale=320:180,select='gt(scene,%s)',showinfo" % thresh, "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    ts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", out)]
    b = [0.0]
    for t in ts:
        if t - b[-1] > 0.4:
            b.append(t)
    return b + [dur]


def face_x(src, t0, t1, step=0.5):
    """Median centre x (px of 1920) of the largest face in [t0, t1], or None if most frames have none."""
    import cv2
    det, xs, n = None, [], 0
    for t in np.arange(t0 + 0.1, max(t0 + 0.2, t1 - 0.1), step):
        raw = subprocess.run([vf.FFMPEG, "-v", "error", "-ss", "%.2f" % t, "-i", src, "-frames:v", "1",
                              "-vf", "libplacebo=tonemapping=bt.2390:colorspace=bt709:color_primaries=bt709:"
                              "color_trc=bt709:range=tv:format=yuv420p,scale=640:360",
                              "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
        if len(raw) < 640 * 360 * 3:
            continue
        n += 1
        det = det or cv2.FaceDetectorYN.create(vf.FACE_MODEL, "", (640, 360), 0.6, 0.3, 50)
        _, fs = det.detect(np.frombuffer(raw, np.uint8).reshape(360, 640, 3))
        if fs is not None:
            f = max(fs, key=lambda f: f[2] * f[3])
            if f[2] * 3 > 120:          # a face, not a face in the mirror or on a screen
                xs.append((f[0] + f[2] / 2) * 3)
    return float(np.median(xs)) if xs and len(xs) >= n / 2 else None


def face_track(src, dur, step=0.5):
    """[(t, face centre x or None)] every step seconds."""
    return [(t, face_x(src, t - 0.1, t + 0.1, step=1.0)) for t in np.arange(0.2, dur - 0.1, step)]


def framing(src, dur, manual, jump=120):
    """[(t0, t1, mode or crop x)] for the whole Short. A shot ends at a scene change or where the face moves
    more than `jump` px between samples (a jump cut to another clip of the same scene)."""
    b = cuts(src, dur)
    track = face_track(src, dur)
    for (t0, x0), (t1, x1) in zip(track, track[1:]):
        if x0 is not None and x1 is not None and abs(x1 - x0) > jump:
            b.append((t0 + t1) / 2)
    b = sorted(set(round(t, 2) for t in b))
    shots = []
    for t0, t1 in zip(b, b[1:]):
        xs = [x for t, x in track if t0 <= t < t1]
        fx = float(np.median([x for x in xs if x is not None])) if xs and sum(x is not None for x in xs) >= len(xs) / 2 else None
        if not xs:
            fx = face_x(src, t0, t1)
        shots.append([t0, t1, "fit" if fx is None else int(min(max(fx - CW / 2, 0), 1920 - CW))])
    for a, z, m in manual:                       # manual ranges win over the shots they overlap
        out = []
        for t0, t1, v in shots:
            if t1 <= a or t0 >= z:
                out.append([t0, t1, v])
                continue
            if t0 < a:
                out.append([t0, a, v])
            if t1 > z:
                out.append([z, t1, v])
        out.append([a, z, (1920 - CW) // 2 if m == "center" else m if m == "fit" else int(m) if m != "face" else
                    int(min(max((face_x(src, a, z) or 960) - CW / 2, 0), 1920 - CW))])
        shots = sorted(out)
    for s in shots:
        print("  %6.2f-%6.2f  %s" % tuple(s), flush=True)
    return shots


def words(src, lang, path):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    vf.torch_dlls()
    import whisperx
    gpu = vf.cuda_index()
    wav = path + ".wav"
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-i", src, "-ac", "1", "-ar", "16000", wav], check=True)
    model = whisperx.load_model(vf.WHISPER_MODEL, "cuda", device_index=gpu, compute_type="float16", language=lang)
    am, meta = whisperx.load_align_model(language_code=lang, device="cuda:%d" % gpu)
    audio = whisperx.load_audio(wav)
    res = whisperx.align(model.transcribe(audio, batch_size=8, language=lang)["segments"], am, meta, audio,
                         "cuda:%d" % gpu)
    os.remove(wav)
    ws = [[round(w["start"], 2), round(w["end"], 2), w["word"]] for s in res["segments"] for w in s["words"]
          if "start" in w]
    json.dump(ws, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("words ->", path, "(fix them there and run again)")
    return ws


def chunks(ws, max_chars=16, max_words=3, gap=0.45):
    """Words grouped into short caption pieces: a break at punctuation, a pause, or the size limits."""
    out, cur = [], []
    for w in ws:
        if cur and (len(" ".join(x[2] for x in cur + [w])) > max_chars or len(cur) >= max_words
                    or w[0] - cur[-1][1] > gap):
            out.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.,!?:;]$", w[2]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    res = []
    for i, c in enumerate(out):
        end = c[-1][1] + 0.25
        if i + 1 < len(out):
            end = min(max(end, out[i + 1][0][0] - 0.05), out[i + 1][0][0])   # no blink between close pieces
        res.append((c[0][0], end, " ".join(x[2] for x in c).strip(" ,;:.")))
    return res


def text_file(folder, name, text):
    p = os.path.join(folder, "%s.txt" % name)
    open(p, "w", encoding="utf-8").write(text)
    return vf.ff_font(p)


def main():
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    src, out = spec["src"], spec["out"]
    dur = duration(src)
    work = os.path.splitext(os.path.abspath(sys.argv[1]))[0]        # next to the spec: <spec>.words.json, <spec>_parts/
    tmp = work + "_parts"
    os.makedirs(tmp, exist_ok=True)
    shots = framing(src, dur, spec.get("frame", []))
    fits = [(a, z) for a, z, v in shots if v == "fit"]
    crop_x = "+".join("gte(t,%.3f)*lt(t,%.3f)*%d" % (a, z, v) for a, z, v in shots if v != "fit") or "656"
    pics = spec.get("pictures", [])
    inputs = ["-i", src]
    # face: a 608-wide window, scaled to the full height; fit: the whole frame 1080 wide over a blurred,
    # darkened fill of itself, laid over the face picture during the shots without a face
    g = ["[0:v]format=yuv444p10le%s" % (",split=3[s0][s1][s2]" if fits else "[s0]"),
         "[s0]crop=%d:1080:x='%s':y=0,scale=%d:%d:flags=lanczos,setsar=1[face]" % (CW, crop_x, W, H)]
    last = "face"
    if fits:
        g += ["[s1]scale=-2:%d,crop=%d:%d,gblur=sigma=40,colorlevels=romax=0.55:gomax=0.55:bomax=0.55[bg]" % (H, W, H),
              "[s2]scale=%d:-2:flags=lanczos[fg]" % W,
              "[bg][fg]overlay=x=0:y=(H-h)/2[fit]",
              "[face][fit]overlay=x=0:y=0:enable='%s'[v0]" % "+".join("between(t,%.3f,%.3f)" % f for f in fits)]
        last = "v0"
    fit_box = "scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos,setsar=1" % (PIC_W, PIC_H)
    for k, (t0, n, pic) in enumerate(pics, 1):
        if burn_in.is_image(pic):
            inputs += ["-loop", "1", "-framerate", "30", "-t", str(n), "-i", pic]
            pre = "%s,%s" % (fit_box, burn_in.SDR_TO_HLG)
        else:
            inputs += ["-t", str(n), "-i", pic]
            pre = fit_box + ","
        g.append("[%d:v]%sformat=yuva444p10le,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st=%s:d=0.25:alpha=1,"
                 "setpts=PTS-STARTPTS+%s/TB[p%d]" % (k, pre, n - 0.25, t0, k))
        g.append("[%s][p%d]overlay=x=(W-w)/2:y=%d+(%d-h)/2:format=yuv444p10:eof_action=pass:enable='between(t,%s,%s)'[v%d]"
                 % (last, k, PIC_TOP, PIC_H, t0, t0 + n, k))
        last = "v%d" % k
    fb = vf.ff_font(vf.FONT_BOLD)
    draw = []
    for i, (a, z, t) in enumerate(chunks(words(src, spec.get("lang", vf.LANGUAGE), work + ".words.json"))):
        draw.append("drawtext=fontfile='%s':textfile='%s':expansion=none:fontsize=86:fontcolor=%s:borderw=7:"
                    "bordercolor=black:x=(w-text_w)/2:y=%d-text_h/2:enable='between(t,%.2f,%.2f)'"
                    % (fb, text_file(tmp, "c%03d" % i, t), WHITE, CAP_Y, a, z))
    if spec.get("hook"):
        n = spec.get("hook_len", 4.0) or dur
        lines = spec["hook"].split("\n")
        for j, line in enumerate(lines):
            draw.append("drawtext=fontfile='%s':textfile='%s':expansion=none:fontsize=78:fontcolor=%s:borderw=7:"
                        "bordercolor=black:x=(w-text_w)/2:y=%d:enable='lt(t,%s)'"
                        % (fb, text_file(tmp, "hook%d" % j, line), YELLOW, 200 + 100 * j, n))
    g.append("[%s]%s,format=yuv420p10le[vout]" % (last, ",".join(draw) if draw else "null"))
    amap = "0:a"
    if spec.get("music"):
        fname, off = spec["music"]
        mp = fname if os.path.isabs(fname) else os.path.join(vf.MUSIC_DIR, fname)
        inputs += ["-ss", str(off), "-t", "%.2f" % (dur + 1), "-i", mp]
        g.append("[%d:a]loudnorm=I=%s:TP=-6:LRA=11,aresample=48000,afade=t=in:d=1,afade=t=out:st=%.2f:d=2.5,"
                 "atrim=0:%.3f[mus]" % (len(pics) + 1, spec.get("music_lufs", MUSIC_LUFS), dur - 2.5, dur))
        g.append("[0:a]aresample=48000[voc];[voc][mus]amix=inputs=2:duration=first:normalize=0[aout]")
        amap = "[aout]"
    script = os.path.join(tmp, "filter.txt")
    open(script, "w", encoding="utf-8").write(";\n".join(g))
    subprocess.run([vf.FFMPEG, "-v", "error", "-y"] + inputs + ["-filter_complex_script", script, "-map", "[vout]",
                    "-map", amap, "-c:a", "aac", "-b:a", "256k"] + vf.hevc_args() + burn_in.HLG_TAGS +
                   ["-tag:v", "hvc1", "-movflags", "+faststart", out], check=True)
    d = duration(out)
    print("done: %s  %.1f s%s" % (out, d, "  (over 60 s: fine for a Short up to 3 min, but 30-60 s work best)" if d > 60 else ""))


if __name__ == "__main__":
    main()
