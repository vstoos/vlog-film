"""Find second faces (a child in the back seat, a passenger behind the driver) in the talk ranges of a film.

usage: python kid_faces.py <project.py> [clip ...] > film_check/kid/faces.txt
Reads the project's EDL (and CLIP_SRC), looks at 5 frames per second of each used range (+-1 s) with a low
threshold, drops the speaker (the largest face) and prints every other face as  time (cx,cy) size score,
in px of the 1920x1080 picture filmkit shows. Then a per-clip summary: where the second face sits and how
far right it reaches, to place a kid_sticker.py smiley clear of the driver.

The detector misses a head turned away, half a face at the frame edge and a face under a cap or headphones:
look at a strip of the left/right edge of every used clip too (the Helm and Diesel films found peeks that way).
"""
import importlib.util
import subprocess
import sys

import cv2
import numpy as np

import vfconfig as vf

FPS, W2, H2 = 5, 960, 540


def load(path):
    spec = importlib.util.spec_from_file_location("project", path)
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    return p


def ranges(p):
    out = {}
    for item in p.EDL:
        if item[0] == "talk":
            for r in item[1]:
                out.setdefault(r[0], []).append((r[1], r[2]))
    return out


def source(p, clip):
    src = getattr(p, "CLIP_SRC", {}).get(clip)
    return src or "%s/%s.MOV" % (p.SRC, clip)      # ffmpeg turns a rotated phone clip upright itself


def survey(path, clip, used, det):
    proc = subprocess.Popen([vf.FFMPEG, "-v", "error", "-init_hw_device", "vulkan", "-i", path, "-vf",
                             "fps=%d,libplacebo=w=%d:h=%d:colorspace=bt709:color_primaries=bt709:color_trc=bt709:"
                             "format=bgr24" % (FPS, W2, H2), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                            stdout=subprocess.PIPE)
    i, out = 0, []
    while True:
        b = proc.stdout.read(W2 * H2 * 3)
        if len(b) < W2 * H2 * 3:
            break
        t = i / FPS
        i += 1
        if not any(a - 1 <= t <= e + 1 for a, e in used):
            continue
        _, fs = det.detect(np.frombuffer(b, np.uint8).reshape(H2, W2, 3).copy())
        if fs is None:
            continue
        fs = sorted(fs, key=lambda f: -f[2] * f[3])
        big = fs[0]
        bx, by = big[0] + big[2] / 2, big[1] + big[3] / 2
        for f in fs[1:]:
            cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
            if abs(cx - bx) < big[2] and abs(cy - by) < big[3]:
                continue                                  # the speaker found twice
            out.append((t, int(cx * 2), int(cy * 2), int(max(f[2], f[3]) * 2), round(float(f[14]), 2),
                        int(big[0] * 2)))
    return out


def main():
    p = load(sys.argv[1])
    used = ranges(p)
    det = cv2.FaceDetectorYN.create(vf.FACE_MODEL, "", (W2, H2), 0.45, 0.3, 5000)
    for clip in sys.argv[2:] or sorted(used):
        hits = survey(source(p, clip), clip, used[clip], det)
        print("== %s  %d second faces" % (clip, len(hits)))
        for t, x, y, s, sc, drv in hits:
            print("  %6.1f  (%d,%d) %d  %.2f   driver from x %d" % (t, x, y, s, sc, drv))
        if hits:
            xs, ys, ss = (np.array([h[k] for h in hits]) for k in (1, 2, 3))
            print("  -> centre %d,%d  x %d-%d  size %d  driver from x %d" % (
                np.median(xs), np.median(ys), xs.min(), xs.max(), np.median(ss), min(h[5] for h in hits)))


if __name__ == "__main__":
    main()
