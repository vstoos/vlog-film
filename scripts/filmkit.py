"""filmkit: build a talking-head + road-insert travel film as a Shotcut/MLT project, HLG 10-bit.

usage: python filmkit.py <project.py> [--no-media]
  --no-media  only rewrite the .mlt (skip re-rendering inserts, cards and stills)

Machine settings (ffmpeg, encoder, fonts, music folder) come from vfconfig / config.json.
The project file holds everything specific to one film: paths, the edit decision list (EDL),
the teaser (HOOK), music, per-clip framing and an optional make_stills(). See
references/project_template.py and references/example_yaris.py in the skill.
Talk blocks are cut on WhisperX word times: pauses longer than GAP_CUT become jump cuts.
"""
import importlib.util
import json
import math
import os
import subprocess
import sys
from xml.sax.saxutils import escape

import numpy as np

import vfconfig as vf

# --- defaults; the project file overrides any of these (UPPER_CASE names) ----------
SRC = OUT = TRANSCRIPTS = None
MUSIC_DIR = vf.MUSIC_DIR
ROAD_FILE = "{src}/Road/{clip}_fast.mp4"   # where road (dash-cam) footage lives
FILM_NAME = "film"                          # -> OUT/<FILM_NAME>.mlt
FILM_TITLE = "Film"
FPS = 30

GAP_CUT = 0.7          # s of silence inside a block that becomes a jump cut
PAD_IN, PAD_OUT = 0.15, 0.30   # minimum padding; the audio envelope can push cuts further out
MUSIC_GAIN_DB = -15.0
MUSIC_LEAD, MUSIC_TAIL = 1.2, 1.5   # music rises under the last words, fades under the first ones
VOICE_XFADE = 0.5      # voice fades out into / in from an insert over this much extra room tone
VOICE_TARGET = -20.0   # LUFS each clip's used voice is brought to, per talk block (day-2 clips are ~10 dB down)
VOICE_GAIN_MAX, VOICE_GAIN_MIN = 14.0, -6.0   # cap the boost, so the quietest clips do not pump up the hiss

CLIP_FRAME, CLIP_SPEED, PORTRAIT_BAND = {}, {}, {}
CLIP_SRC = {}   # clip -> picture file used as is (no plate blur), e.g. TeslaCam or another folder
HOOK, EDL, MUSIC = [], [], {}
MAKE_STILLS = None


FB = vf.ff_font(vf.FONT_BOLD)   # drawtext font; light faded on road footage


def roll_for(road):
    """Camera roll in degrees for a road clip; the project usually overrides this."""
    return 0.0


def configure(path):
    """Load the project file and take over its settings (UPPER_CASE), roll_for and make_stills."""
    spec = importlib.util.spec_from_file_location("project", path)
    proj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proj)
    g = globals()
    for k, v in vars(proj).items():
        if k.isupper():
            g[k] = v
    if hasattr(proj, "roll_for"):
        g["roll_for"] = proj.roll_for
    g["MAKE_STILLS"] = getattr(proj, "make_stills", None)
    return proj


# --- media -------------------------------------------------------------------
def zoom_for(deg):
    a = math.radians(deg)
    return math.cos(a) + 16 / 9 * math.sin(a) + 0.002


def fit_size(text, size, width=1920 - 2 * 100):
    """Font size for one line of `text` in the bold font: `size`, or smaller so it fits `width` px.
    "Де Mercedes заробляє на пакетах" at 120 ran off both edges of the card (Mercedes film, 16:22)."""
    from PIL import ImageFont
    w = ImageFont.truetype(vf.FONT_BOLD, size).getlength(text)
    return size if w <= width else int(size * width / w)


def render_road(name, segs, title=None, sub=None, top=False):
    """Road footage levelled and SDR->HLG. Cards get blur, vignette and fading text."""
    rot = roll_for(segs[0][0])
    length = sum(n for _, _, n in segs)
    chain = "".join("[%d:v]" % i for i in range(len(segs)))
    if len(segs) > 1:
        chain += "concat=n=%d:v=1:a=0," % len(segs)
    chain += ("setparams=color_trc=bt709:color_primaries=bt709:colorspace=bt709:range=tv,format=yuv444p,"
             "rotate=%s*PI/180:bilinear=1,scale=iw*%.4f:ih*%.4f:flags=lanczos,crop=1920:1080,setsar=1,"
             % (rot, zoom_for(rot), zoom_for(rot)))
    if title:
        subs = sub.split("\n")       # each subtitle line centred on its own
        for fname, text in [("t", title)] + [("s%d" % i, s) for i, s in enumerate(subs)]:
            with open("%s/%s_%s.txt" % (OUT, name, fname), "w", encoding="utf-8") as f:
                f.write(text)
        alpha = "if(lt(t,{a}),0,if(lt(t,{b}),(t-{a}),if(lt(t,{c}),1,if(lt(t,{d}),({d}-t),0))))"
        esc = OUT.replace(":", "\\:")
        y_t, y_s = ("110", "270") if top else ("(h-text_h)/2-50", "(h/2)+70")   # top: end screen tiles below
        asub = alpha.format(a=1.6, b=2.6, c=length - 1.5, d=length - 0.5)
        chain += (
            "gblur=sigma=3,eq=brightness=-0.08:saturation=0.85,vignette=PI/4,"
            "drawtext=fontfile='{fb}':textfile='{e}/{n}_t.txt':fontsize={fs}:"
            "fontcolor=white:alpha='{am}':x=(w-text_w)/2:y={yt}:shadowcolor=black@0.6:shadowx=3:shadowy=3,"
        ).format(fb=FB, e=esc, n=name, yt=y_t, fs=fit_size(title, 120),
                 am=alpha.format(a=0.8, b=1.8, c=length - 1.5, d=length - 0.5))
        for i in range(len(subs)):
            chain += (
                "drawtext=fontfile='{fb}':textfile='{e}/{n}_s{i}.txt':fontsize=50:"     # bold: light faded on road footage
                "fontcolor=white:alpha='{a}':x=(w-text_w)/2:y={ys}+{dy}:shadowcolor=black@0.8:shadowx=3:shadowy=3,"
            ).format(fb=FB, e=esc, n=name, i=i, a=asub, ys=y_s, dy=i * 70)
        chain += "fade=t=in:st=0:d=0.5,fade=t=out:st=%s:d=0.5," % (length - 0.5)
        # SDR white -> HLG graphics white, so text does not blaze at peak
        chain += "libplacebo=colorspace=bt2020nc:color_primaries=bt2020:color_trc=arib-std-b67:range=tv:format=yuv420p10le"
    else:
        chain += ("libplacebo=colorspace=bt2020nc:color_primaries=bt2020:color_trc=arib-std-b67:range=tv:"
                  "inverse_tonemapping=1:format=yuv420p10le")
    script = "%s/%s_filter.txt" % (OUT, name)
    with open(script, "w", encoding="utf-8") as f:
        f.write(chain)
    inputs = []
    for road, at, n in segs:
        inputs += ["-ss", str(at), "-t", str(n), "-i", ROAD_FILE.format(src=SRC, clip=road)]
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-init_hw_device", "vulkan"] + inputs +
                   ["-an", "-filter_complex_script", script,
                    *vf.hevc_args(),
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    "%s/%s.mov" % (OUT, name)], check=True)


def caption_chain(name, length, title, sub, white="white"):
    """Dark band with title and subtitle fading in and out; empty title = no caption.

    white: SDR sources use white (graphics white after SDR->HLG); HLG sources need ~75%
    signal (0xBFBFBF) so the text sits at reference white instead of blazing at peak.
    """
    if not title:
        return ""
    for fname, text in (("t", title), ("s", sub)):
        with open("%s/%s_%s.txt" % (OUT, name, fname), "w", encoding="utf-8") as f:
            f.write(text)
    esc = OUT.replace(":", "\\:")
    alpha = "if(lt(t,{a}),0,if(lt(t,{b}),(t-{a})/0.6,if(lt(t,{c}),1,if(lt(t,{d}),({d}-t)/0.6,0))))"
    return (
        "drawbox=x=0:y=ih-230:w=iw:h=230:color=black@0.6:t=fill,"
        "drawtext=fontfile='{fb}':textfile='{e}/{nm}_t.txt':expansion=none:fontsize=64:"
        "fontcolor={w}:alpha='{a1}':x=(w-text_w)/2:y=h-200:shadowcolor=black@0.6:shadowx=2:shadowy=2,"
        "drawtext=fontfile='{fb}':textfile='{e}/{nm}_s.txt':expansion=none:fontsize=48:"
        "fontcolor={w}:alpha='{a2}':x=(w-text_w)/2:y=h-110:shadowcolor=black@0.6:shadowx=2:shadowy=2,"
    ).format(fb=FB, e=esc, nm=name, w=white,
             a1=alpha.format(a=0.4, b=1.0, c=length - 1.0, d=length - 0.4),
             a2=alpha.format(a=0.8, b=1.4, c=length - 1.0, d=length - 0.4))


# portrait clips whose subject sits in one part of the frame: cut that part out instead of pillarboxing


def render_clip(name, clip, at, length, title, sub):
    """A piece of iPhone HLG footage as a silent insert with a caption (stays in HLG)."""
    if clip in CLIP_FRAME:
        frame = CLIP_FRAME[clip] + ","
    elif rotated(clip):
        frame = ("split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                 "gblur=sigma=40,eq=brightness=-0.12[bg];[b]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,")
    else:
        frame = ""
    speed = CLIP_SPEED.get(clip, 1.0)
    if speed != 1.0:
        frame = "setpts=PTS/%s,fps=30," % speed + frame
    chain = ("[0:v]" + frame + "setsar=1,format=yuv444p10le," + caption_chain(name, length, title, sub, "0xBFBFBF") +
             "fade=t=in:st=0:d=0.4,fade=t=out:st=%s:d=0.4,format=yuv420p10le" % (length - 0.4))
    script = "%s/%s_filter.txt" % (OUT, name)
    with open(script, "w", encoding="utf-8") as f:
        f.write(chain)
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-ss", str(at), "-t", str(length * speed),
                    "-i", video_src(clip), "-an", "-filter_complex_script", script, "-t", str(length),
                    *vf.hevc_args(),
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    "%s/%s.mov" % (OUT, name)], check=True)



def render_anim(name, sdr_movie, length):
    """A ready-made SDR animation (route map) as graphics white in HLG; it fades in and out itself."""
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-init_hw_device", "vulkan", "-i", sdr_movie,
                    "-t", str(length), "-vf",
                    "setsar=1,setparams=color_trc=bt709:color_primaries=bt709:colorspace=bt709:range=tv,"
                    "libplacebo=colorspace=bt2020nc:color_primaries=bt2020:color_trc=arib-std-b67:range=tv:"
                    "format=yuv420p10le",
                    *vf.hevc_args(),
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    "%s/%s.mov" % (OUT, name)], check=True)


def render_photo(name, photo, length, title, sub):
    """iPhone photo on a blurred backdrop, slow zoom, caption on a dark band, SDR -> HLG."""
    from PIL import Image, ImageFilter, ImageOps
    import pillow_heif
    pillow_heif.register_heif_opener()
    path = photo if os.path.isabs(photo) else next(
        p for p in ("%s/%s.HEIC" % (SRC, photo), "%s/%s.PNG" % (SRC, photo)) if os.path.exists(p))
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    W, H = 3840, 2160
    bg = ImageOps.fit(im, (W, H)).filter(ImageFilter.GaussianBlur(60)).point(lambda v: int(v * 0.7))
    fg = im.copy()
    fg.thumbnail((W, H), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    still = "%s/%s_src.png" % (OUT, name)
    bg.save(still)
    n = frames(length)
    zoom = 0.08 if title else 0.03    # text-only stills barely move
    chain = (
        "[0:v]zoompan=z='1+%s*on/%d':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=30,"
        "setsar=1,format=yuv444p," % (zoom, n) + caption_chain(name, length, title, sub) +
        "fade=t=in:st=0:d=0.4,fade=t=out:st=%s:d=0.4,"
        "setparams=color_trc=bt709:color_primaries=bt709:colorspace=bt709:range=tv,"
        "libplacebo=colorspace=bt2020nc:color_primaries=bt2020:color_trc=arib-std-b67:range=tv:format=yuv420p10le"
        % (length - 0.4))
    script = "%s/%s_filter.txt" % (OUT, name)
    with open(script, "w", encoding="utf-8") as f:
        f.write(chain)
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-init_hw_device", "vulkan",
                    "-loop", "1", "-framerate", "30", "-t", str(length), "-i", still,
                    "-filter_complex_script", script, "-frames:v", str(n),
                    *vf.hevc_args(),
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    "%s/%s.mov" % (OUT, name)], check=True)


def video_src(clip):
    """The clip's picture source: CLIP_SRC, else the plate-blurred copy from blur_plates.py, else SRC."""
    if clip in CLIP_SRC:
        return CLIP_SRC[clip]
    blurred = "%s/%s_blur.mov" % (OUT, clip)
    return blurred if os.path.exists(blurred) else "%s/%s.MOV" % (SRC, clip)


def rotated(clip):
    out = subprocess.run([vf.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream_side_data=rotation", "-of", "csv=p=0", "%s/%s.MOV" % (SRC, clip)],
                         capture_output=True, text=True).stdout.strip()
    return out not in ("", "0")


def render_portrait(clip):
    """melt garbles rotated 10-bit iPhone clips (green frames), so turn them landscape here:
    a full-width 16:9 band (PORTRAIT_BAND) or, by default, a pillarbox on a blurred backdrop."""
    if clip in PORTRAIT_BAND:
        graph = ("crop=iw:iw*9/16:0:(ih-iw*9/16)*%s,scale=1920:1080:flags=lanczos,setsar=1,format=yuv420p10le"
                 % PORTRAIT_BAND[clip])
    else:
        graph = ("split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                 "gblur=sigma=40,eq=brightness=-0.12[bg];[b]scale=-2:1080[fg];"
                 "[bg][fg]overlay=(W-w)/2:0,setsar=1,format=yuv420p10le")
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-i", video_src(clip),
                    "-map", "0:v:0", "-map", "0:a:0", "-vf", graph, "-c:a", "copy",
                    *vf.hevc_args(),
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    "%s/%s_land.mov" % (OUT, clip)], check=True)


# --- talk cutting --------------------------------------------------------------
_words, _env = {}, {}
ENV_HOP = 0.01         # s per envelope step


def words(clip):
    if clip not in _words:
        d = json.load(open("%s/%s.json" % (TRANSCRIPTS, clip), encoding="utf-8"))
        _words[clip] = [(w["s"], w["e"]) for s in d["segments"] for w in s["words"]
                        if w.get("s") is not None and w.get("e") is not None]
    return _words[clip]


def envelope(clip):
    """Loudness in dB every 10 ms, and the 'quiet' threshold (room/engine floor + 10 dB)."""
    if clip not in _env:
        raw = subprocess.run([vf.FFMPEG, "-v", "error", "-i", "%s/%s.MOV" % (SRC, clip), "-vn", "-ac", "1",
                              "-ar", "8000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        hop, win = 80, 160
        n = max(1, (len(x) - win) // hop)
        frames_ = np.lib.stride_tricks.as_strided(x, (n, win), (x.strides[0] * hop, x.strides[0]))
        db = 10 * np.log10((frames_ ** 2).mean(1) + 1e-10)
        _env[clip] = (db, np.percentile(db, 10) + 10)
    return _env[clip]


def voice_lufs(clip, ranges):
    """Integrated loudness (EBU R128) of just these pieces of the clip's sound, joined."""
    # aselect ignores its expression on these files, so cut the pieces out in numpy instead
    sr = 48000
    raw = subprocess.run([vf.FFMPEG, "-v", "error", "-i", "%s/%s.MOV" % (SRC, clip), "-vn", "-ac", "2",
                          "-ar", str(sr), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).reshape(-1, 2)
    joined = np.concatenate([x[int(lo * sr):int(hi * sr)] for lo, hi in ranges])
    err = subprocess.run([vf.FFMPEG, "-nostats", "-f", "s16le", "-ar", str(sr), "-ac", "2", "-i", "-",
                          "-af", "ebur128", "-f", "null", "-"], input=joined.tobytes(),
                         capture_output=True).stderr.decode("utf-8", "replace")
    found = [l for l in err.splitlines() if l.strip().startswith("I:")]
    return float(found[-1].split()[1]) if found else None


def quiet_after(clip, t, limit):
    """First moment at or after t where 150 ms of quiet starts; limit if speech runs on."""
    db, thr = envelope(clip)
    for i in range(int(t / ENV_HOP), min(int(limit / ENV_HOP), len(db) - 15)):
        if (db[i:i + 15] < thr).all():
            return i * ENV_HOP
    return limit


def quiet_before(clip, t, limit):
    db, thr = envelope(clip)
    for i in range(int(t / ENV_HOP), max(int(limit / ENV_HOP), 15), -1):
        if (db[i - 15:i] < thr).all():
            return i * ENV_HOP
    return limit


def islands(clip, a, b, keep):
    """Speech spans inside [a, b] as (lo, hi, lo_limit, hi_limit); pauses > GAP_CUT split them.

    Edges are pushed out to where the audio actually goes quiet (WhisperX word ends are often
    early), but never into the neighbouring word. The limits say how far a fade may extend.
    """
    allw = words(clip)
    if keep:
        spans = [[a, b]]
    else:
        ws = [(s, e) for s, e in allw if s >= a - 0.05 and e <= b + 0.05]
        if not ws:
            spans = [[a, b]]
        else:
            spans = [[ws[0][0], ws[0][1]]]
            for s, e in ws[1:]:
                if s - spans[-1][1] > GAP_CUT:
                    spans.append([s, e])
                else:
                    spans[-1][1] = e
    out = []
    for s, e in spans:
        # w[0] < s, w[1] > e: a 20 ms word ("В") must not count as its own neighbour
        prev_e = max([w[1] for w in allw if w[1] <= s + 0.02 and w[0] < s - 0.005] + [0.0])
        next_s = min([w[0] for w in allw if w[0] >= e - 0.02 and w[1] > e + 0.005] + [envelope(clip)[0].size * ENV_HOP])
        lo_lim, hi_lim = max(prev_e + 0.05, s - 0.8, 0.0), min(next_s - 0.05, e + 1.0)
        if keep:
            lo = max(lo_lim, min(s, quiet_before(clip, s, lo_lim)))
            hi = min(hi_lim, max(e, quiet_after(clip, e, hi_lim)))
        else:
            lo = max(lo_lim, min(s - PAD_IN, quiet_before(clip, s, lo_lim) - 0.05))
            hi = min(hi_lim, max(e + PAD_OUT, quiet_after(clip, e, hi_lim) + 0.08))
        if out and lo <= out[-1][1]:
            out[-1][1], out[-1][3] = hi, hi_lim
        else:
            out.append([lo, hi, lo_lim, hi_lim])
    return out


# --- MLT -----------------------------------------------------------------------
def frames(sec):
    return int(round(sec * FPS))


def tc(f):
    return "%02d:%02d:%06.3f" % (f // (FPS * 3600), f // (FPS * 60) % 60, (f % (FPS * 60)) / FPS)


def chain_xml(cid, path, audio=True, video=True):
    return ('  <chain id="%s">\n    <property name="resource">%s</property>\n'
            '    <property name="mlt_service">avformat-novalidate</property>\n'
            '    <property name="seekable">1</property>\n'
            '    <property name="video_index">%d</property>\n    <property name="audio_index">%d</property>\n'
            '    <property name="shotcut:caption">%s</property>\n  </chain>\n'
            % (cid, escape(path), 0 if video else -1, (1 if video else 0) if audio else -1,
               escape(os.path.basename(path))))


def volume_filter(i, o, level):
    return ('      <filter in="%s" out="%s"><property name="mlt_service">volume</property>'
            '<property name="level">%s</property><property name="shotcut:filter">%s</property></filter>\n'
            % (i, o, level, "fadeInVolume" if "=" in str(level) else "audioGain"))


def music_entry(key, src_in_f, length_f, fin_f, fout_f):
    i, o = tc(src_in_f), tc(src_in_f + length_f - 1)
    return ('    <entry producer="music_%s" in="%s" out="%s">\n' % (key, i, o) +
            volume_filter(i, o, "%s=-30;%s=0;%s=0;%s=-36" % (tc(0), tc(fin_f), tc(length_f - 1 - fout_f),
                                                            tc(length_f - 1))) +
            volume_filter(i, o, "%.1f" % MUSIC_GAIN_DB) + '    </entry>')


def talk_entry(clip, fi, fo, fade_in_f, fade_out_f, gain_db=0.0):
    """Voice entry with a one-frame de-click ramp, or a longer fade next to an insert."""
    i, o, n = tc(fi), tc(fo - 1), fo - fi
    fin, fout = max(1, fade_in_f), max(1, fade_out_f)
    floor_in = -24
    floor_out = -30 if fade_out_f > 1 else -24
    level = "%s=%d;%s=0;%s=0;%s=%d" % (tc(0), floor_in, tc(fin), tc(n - 1 - fout), tc(n - 1), floor_out)
    return ('    <entry producer="%s" in="%s" out="%s">\n' % (clip, i, o) + volume_filter(i, o, level) +
            (volume_filter(i, o, "%.1f" % gain_db) if abs(gain_db) >= 0.1 else "") + '    </entry>')


def build(render_media=True):
    os.makedirs(OUT, exist_ok=True)
    clips, video, music = set(), [], []
    t_f, music_used, music_end_f = 0, {k: frames(v[1]) for k, v in MUSIC.items()}, 0
    n_road = 0
    report, spans, used = [], [], {}
    if render_media and MAKE_STILLS:
        MAKE_STILLS()
    for k, item in enumerate(EDL):
        if item[0] == "talk":
            after_insert = k > 0
            before_insert = k + 1 < len(EDL)
            pieces = []
            for rng in item[1]:
                clip, a, b = rng[:3]
                clips.add(clip)
                for lo, hi, lo_lim, hi_lim in islands(clip, a, b, len(rng) > 3):
                    pieces.append([clip, lo, hi, lo_lim, hi_lim, 1, 1])
            # room tone around the block, so the voice can fade against the music
            if after_insert:
                p = pieces[0]
                lo = max(p[3], p[1] - VOICE_XFADE)
                p[1], p[5] = lo, max(frames(p[1] - lo), frames(0.25))
            if before_insert:
                p = pieces[-1]
                hi = min(p[4], p[2] + VOICE_XFADE)
                p[2], p[6] = hi, max(frames(hi - p[2]), frames(0.25))
            for p in pieces:
                # an edge pushed into room tone must not replay a range another block already used
                for ulo, uhi in used.get(p[0], []):
                    if ulo < p[1] < uhi and uhi - p[1] < 0.6:
                        p[1] = uhi
                    if ulo < p[2] < uhi and p[2] - ulo < 0.6:
                        p[2] = ulo
            # one steady gain per clip within the block, from the loudness of what is actually used
            gains = {}
            for clip in dict.fromkeys(p[0] for p in pieces):
                lufs = voice_lufs(clip, [(p[1], p[2]) for p in pieces if p[0] == clip])
                gains[clip] = 0.0 if lufs is None else min(VOICE_GAIN_MAX, max(VOICE_GAIN_MIN, VOICE_TARGET - lufs))
                report.append("voice   %-8s block %2d  %6s LUFS  gain %+5.1f dB"
                              % (clip, k, "-" if lufs is None else "%.1f" % lufs, gains[clip]))
            for clip, lo, hi, _, _, fin, fout in pieces:
                used.setdefault(clip, []).append((lo, hi))
                fi, fo = frames(lo), frames(hi)
                if fo - fi < 6:
                    continue
                video.append(talk_entry(clip, fi, fo, min(fin, (fo - fi) // 3), min(fout, (fo - fi) // 3),
                                        gains[clip]))
                t_f += fo - fi
            continue
        kind = item[0]
        if kind == "roads":
            segs, key, extra = item[1], item[2], ()
        elif kind == "photo":
            segs, key, extra = [(item[1], 0, item[2])], item[3], item[4:6]
        elif kind == "anim":
            segs, key, extra = [(item[1], 0, item[2])], item[3], ()
        else:
            segs, key, extra = [item[1:4]], item[4], item[5:7]
        n_road += 1
        src_tag = os.path.splitext(os.path.basename(segs[0][0]))[0]
        name = "%s%02d_%s" % ("road" if kind == "roads" else kind, n_road, src_tag)
        if render_media:
            if kind == "photo":
                render_photo(name, segs[0][0], segs[0][2], *extra)
            elif kind == "anim":
                render_anim(name, segs[0][0], segs[0][2])
            elif kind == "clip":
                render_clip(name, *segs[0], *extra)
            else:
                render_road(name, segs, *extra, top=(kind == "end"))
        len_f = sum(frames(n) for _, _, n in segs)
        video.append('    <entry producer="%s" in="%s" out="%s"/>' % (name, tc(0), tc(len_f - 1)))
        clips.add(("media", name))
        # back-to-back inserts share one stretch of music
        if spans and spans[-1][0] == key and spans[-1][2] == t_f:
            spans[-1][2], spans[-1][3] = t_f + len_f, k
        else:
            spans.append([key, t_f, t_f + len_f, k])
        report.append("%-7s %-22s at %s" % (kind, name, tc(t_f)))
        t_f += len_f

    # music rises under the last words before an insert and fades under the first words after
    for key, start, stop, last_k in spans:
        lead = min(frames(MUSIC_LEAD), start - music_end_f)
        tail = frames(MUSIC_TAIL) if last_k + 1 < len(EDL) else 0
        m_len = lead + (stop - start) + tail
        if start - lead > music_end_f:
            music.append('    <blank length="%s"/>' % tc(start - lead - music_end_f))
        music.append(music_entry(key, music_used[key], m_len, max(lead, frames(0.5)), max(tail, frames(0.5))))
        music_used[key] += m_len
        music_end_f = start - lead + m_len

    body = ""
    for c in sorted(x for x in clips if isinstance(x, str)):
        if rotated(c):
            if render_media:
                render_portrait(c)
            body += chain_xml(c, "%s/%s_land.mov" % (OUT, c))
        else:
            body += chain_xml(c, video_src(c))
    for _, name in sorted(x for x in clips if isinstance(x, tuple)):
        body += chain_xml(name, "%s/%s.mov" % (OUT, name), audio=False)
    for key, (fname, _) in MUSIC.items():
        body += chain_xml("music_" + key, "%s/%s" % (MUSIC_DIR, fname), video=False)

    end = tc(max(t_f, music_end_f) - 1)
    xml = """<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" version="7.36.0" title="{title}" producer="main_bin">
  <profile description="HD 1080p 30 fps HLG" width="1920" height="1080" progressive="1"
           sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="16" display_aspect_den="9"
           frame_rate_num="30" frame_rate_den="1" colorspace="2020"/>
  <playlist id="main_bin">
    <property name="xml_retain">1</property>
    <property name="shotcut:processingMode">Native10Cpu</property>
  </playlist>
  <producer id="black" in="00:00:00.000" out="{end}">
    <property name="length">{end}</property>
    <property name="eof">pause</property>
    <property name="resource">0</property>
    <property name="mlt_service">color</property>
    <property name="mlt_image_format">rgba</property>
    <property name="set.test_audio">0</property>
  </producer>
  <playlist id="background">
    <entry producer="black" in="00:00:00.000" out="{end}"/>
  </playlist>
{body}  <playlist id="playlist0">
    <property name="shotcut:video">1</property>
    <property name="shotcut:name">V1</property>
{video}
  </playlist>
  <playlist id="playlist1">
    <property name="shotcut:audio">1</property>
    <property name="shotcut:name">A1 music</property>
{music}
  </playlist>
  <tractor id="tractor0" title="{title}" in="00:00:00.000" out="{end}">
    <property name="shotcut">1</property>
    <property name="shotcut:processingMode">Native10Cpu</property>
    <track producer="background"/>
    <track producer="playlist0"/>
    <track producer="playlist1" hide="video"/>
    <transition><property name="a_track">0</property><property name="b_track">1</property>
      <property name="mlt_service">mix</property><property name="always_active">1</property><property name="sum">1</property></transition>
    <transition><property name="a_track">0</property><property name="b_track">2</property>
      <property name="mlt_service">mix</property><property name="always_active">1</property><property name="sum">1</property></transition>
  </tractor>
</mlt>
""".format(title=escape(FILM_TITLE), end=end, body=body, video="\n".join(video), music="\n".join(music))
    with open("%s/%s.mlt" % (OUT, FILM_NAME), "w", encoding="utf-8") as f:
        f.write(xml)
    print("\n".join(report))
    print("film length %s, %d video entries" % (tc(t_f), len(video)))



if __name__ == "__main__":
    configure(sys.argv[1])
    build(render_media="--no-media" not in sys.argv)
