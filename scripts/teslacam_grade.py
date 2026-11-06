"""Grade Tesla dash-cam / Sentry clips (Autopilot HW3) into natural-looking SDR bt709.

HW3 front and repeater cameras are RCCB sensors (red, clear, clear, blue): green is computed, so
hues are off unevenly, and the tone is very flat (sunny day: luma p1 ~45, p99 160-185 of 235).
The back camera is a normal RGGB sensor and serves as the colour reference. The chain:
  1. crop the 1280x960 frame to 16:9 (front: drops the bonnet and its green corner vignette)
  2. levels from this clip's own histogram: p0.5 -> black, p99.8 -> 0.92, white point never
     below 0.8 so that a clear blue sky is not stretched to white
  3. front only: a 3x3 colour matrix, half of a fit front -> back camera on matched patches
     (references/teslacam.md); the full fit copies the back camera's warm look
  4. a little saturation
The output is SDR; filmkit converts it to HLG like any other SDR insert.

usage: python teslacam_grade.py <clip.mp4> [front|repeater|back]
         -> prints the ffmpeg filter chain for that clip
       python teslacam_grade.py --render <out.mp4> <start_s> <len_s> <clip.mp4> [<next clip.mp4> ...]
         -> graded 1920x1080 SDR clip; the clips are joined in order (Tesla writes one file per
            minute), start is counted from the first one; the camera comes from the file name
"""
import os
import subprocess
import sys

import numpy as np

import vfconfig as vf

MATRIX = ("colorchannelmixer=rr=0.992:rg=0.119:rb=-0.085:gr=-0.273:gg=1.083:gb=0.187:"
          "br=-0.325:bg=0.413:bb=0.892")
CROP = {"front": "crop=1280:720:0:110", "repeater": "crop=1280:720:0:120", "back": "crop=1280:720:0:60"}


def camera(clip):
    name = os.path.basename(clip)
    return "repeater" if "repeater" in name or "pillar" in name else "back" if "back" in name else "front"


def luma_percentiles(clips):
    """p0.5 and p99.8 of luma over frames every 2 s, as 0..1 of the limited range."""
    ys = []
    for clip in clips:
        raw = subprocess.run([vf.FFMPEG, "-v", "error", "-i", clip, "-vf", "fps=0.5,scale=320:240",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        ys.append(np.frombuffer(raw, np.uint8))
    lo, hi = np.percentile(np.concatenate(ys).astype(float), [0.5, 99.8])
    return (lo - 16) / 219, (hi - 16) / 219


def chain(clips, cam=None):
    clips = [clips] if isinstance(clips, str) else clips
    cam = cam or camera(clips[0])
    lo, hi = luma_percentiles(clips)
    lo, hi = max(lo, 0.0), min(max(hi, 0.8), 1.0)
    curves = "curves=all='0/0 %.3f/0.0 %.3f/0.46 %.3f/0.92 1/1'" % (lo, (lo + hi) / 2, hi)
    parts = [CROP[cam], "format=gbrp", curves]
    parts += [MATRIX, "eq=saturation=1.1"] if cam == "front" else ["eq=saturation=1.05"]
    return ",".join(parts)


def render(out, start, length, clips):
    inputs = sum((["-i", c] for c in clips), [])
    join = "".join("[%d:v]" % i for i in range(len(clips))) + "concat=n=%d:v=1," % len(clips)
    vfc = (join + "trim=start=%s:duration=%s,setpts=PTS-STARTPTS," % (start, length) + chain(clips)
           + ",scale=1920:1080:flags=lanczos,format=yuv420p,"
           "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")
    subprocess.run([vf.FFMPEG, "-v", "error", "-y"] + inputs + ["-filter_complex", vfc, "-an",
                    "-c:v", "libx264", "-crf", "14", "-preset", "slow",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out],
                   check=True)
    print(out)


if __name__ == "__main__":
    if sys.argv[1] == "--render":
        render(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5:])
    else:
        print(chain(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
