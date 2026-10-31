"""Final render: melt the .mlt -> two-pass loudnorm to -14 LUFS -> checks -> copy next to the footage.

usage: python render_final.py <film_dir> <name> <dest.mp4>
  reads <film_dir>/<name>.mlt, writes <film_dir>/<name>_raw.mp4 and <name>.mp4, copies to <dest.mp4>
Takes about as long as the film itself (or longer): run it in the background.
Prints loudness (want about -14 LUFS), duration, codec/HDR tags (want Main 10, arib-std-b67,
bt2020) and a green-frame count (want 0; melt turns rotated 10-bit clips green).
"""
import json
import os
import re
import shutil
import subprocess
import sys

import vfconfig as vf


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def main(film_dir, name, dest):
    os.chdir(film_dir)
    raw, final = name + "_raw.mp4", name + ".mp4"
    x265 = "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:range=limited:log-level=error"
    r = run([vf.MELT, "-quiet", name + ".mlt", "-consumer", "avformat:" + raw,
             "mlt_image_format=yuv420p10", "color_trc=arib-std-b67", "vcodec=libx265", "pix_fmt=yuv420p10le",
             "crf=18", "preset=medium", "x265-params=" + x265, "acodec=pcm_s16le", "ar=48000", "channels=2",
             "real_time=0"])
    if not os.path.exists(raw):
        sys.exit("melt failed:\n" + r.stderr[-2000:])

    # two-pass loudness normalisation, linear (no pumping)
    err = run([vf.FFMPEG, "-hide_banner", "-i", raw, "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
               "-f", "null", "-"]).stderr
    m = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    af = ("loudnorm=I=-14:TP=-1:LRA=11:measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:"
          "measured_thresh={input_thresh}:offset={target_offset}:linear=true,aresample=48000").format(**m)
    r = run([vf.FFMPEG, "-v", "error", "-y", "-i", raw, "-c:v", "copy", "-tag:v", "hvc1", "-af", af,
             "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", final])
    if r.returncode:
        sys.exit("audio pass failed:\n" + r.stderr[-2000:])

    err = run([vf.FFMPEG, "-hide_banner", "-i", final, "-af", "ebur128", "-f", "null", "-"]).stderr
    print("loudness:", " ".join(re.findall(r"^\s+(?:I|LRA):\s+(.+)$", err, re.M)[-2:]))
    print("duration,size:", run([vf.FFPROBE, "-v", "error", "-show_entries", "format=duration,size",
                                 "-of", "csv=p=0", final]).stdout.strip())
    print("video:", run([vf.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=profile,codec_tag_string,pix_fmt,color_transfer,color_primaries",
                         "-of", "csv=p=0", final]).stdout.strip())
    # green frames: average chroma of a tiny frame collapses towards U+V < 1000 (10-bit) when melt garbles it
    out = run([vf.FFMPEG, "-v", "error", "-i", final, "-vf",
               "fps=2,scale=64:36,signalstats,metadata=print:file=-", "-f", "null", "-"]).stdout
    u = [float(v) for v in re.findall(r"signalstats\.UAVG=([\d.]+)", out)]
    v = [float(v) for v in re.findall(r"signalstats\.VAVG=([\d.]+)", out)]
    print("green samples: %d of %d" % (sum(1 for a, b in zip(u, v) if a + b < 1000), len(u)))
    shutil.copyfile(final, dest)
    print("copied to", dest)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
