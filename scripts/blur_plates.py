"""Blur licence plates (and faces) in iPhone clips: detection per frame -> soft mask -> 10-bit HLG blur.

usage: python blur_plates.py <footage_dir> <film_dir> [--faces] <clip> [<clip> ...]   e.g. ... IMG_0089
  --faces   also blur every face found (OpenCV YuNet): strangers, staff, children
  --green-only  blur only green plates (the user's own EV plate), nothing else
Writes <film_dir>/<clip>_blur.mov (same length, audio copied, rotation baked in) plus
film/<clip>_mask.mkv and a few check frames in film/plates_check/.
filmkit.py picks up <film_dir>/<clip>_blur.mov automatically when it exists.
"""
import os
import subprocess
import sys

import cv2
import numpy as np
import vfconfig as vf

vf.torch_dlls()   # torch's bundled cuDNN DLLs, which the onnxruntime CUDA provider needs

import onnxruntime as ort

FACES = "--faces" in sys.argv
GREEN_ONLY = "--green-only" in sys.argv   # only green plates (Polish EV plates: the user's own car), no faces
_ARGS = [a for a in sys.argv[1:] if a not in ("--faces", "--green-only")]
SRC, OUT = (_ARGS[0].replace("\\", "/"), _ARGS[1].replace("\\", "/")) if len(_ARGS) > 2 else (None, None)
MODEL = vf.PLATE_MODEL   # YOLO licence-plate detector, downloaded by setup/setup.py
CONF = 0.15            # low on purpose: a missed plate is worse than a blurred bumper
HOLD = 12              # frames a detection is kept before and after, covers misses and motion
PAD_W, PAD_H = 0.20, 0.35
PLATE_ASPECT = 1.6     # min width/height of a plate box
FACE_CONF = 0.75       # YuNet score; lower ones fire on reflections in car paint
FACE_MAX = 0.12        # max face width as a share of frame width: bigger "faces" are car panels
FACE_PAD = 0.45        # faces get a bigger margin: hair, a turned head


def session():
    try:
        return ort.InferenceSession(MODEL, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    except Exception:
        return ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])


def detect(sess, frame):
    h, w = frame.shape[:2]
    long_side = 1280
    s = long_side / max(h, w)
    nh, nw = int(round(h * s / 32)) * 32, int(round(w * s / 32)) * 32
    img = cv2.resize(frame, (nw, nh))[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255
    out = sess.run(None, {"images": np.ascontiguousarray(img)})[0][0]      # (5, N): cx cy w h conf
    keep = out[4] > CONF
    if not keep.any():
        return []
    cx, cy, bw, bh, conf = out[:, keep]
    boxes = np.stack([cx - bw / 2, cy - bh / 2, bw, bh], 1)
    idx = cv2.dnn.NMSBoxes(boxes.tolist(), conf.tolist(), CONF, 0.45)
    sx, sy = w / nw, h / nh
    return [(boxes[i][0] * sx, boxes[i][1] * sy, boxes[i][2] * sx, boxes[i][3] * sy, float(conf[i]))
            for i in np.array(idx).flatten()]


def is_green(frame, box):
    """A green plate (Polish EV plate): green clearly over red and blue in the box."""
    x, y, bw, bh = (int(v) for v in box[:4])
    crop = frame[max(0, y):y + bh, max(0, x):x + bw]
    if crop.size == 0:
        return False
    b, g, r = crop.reshape(-1, 3).mean(axis=0)
    return g > 1.15 * r and g > 1.05 * b


def process(clip):
    src = "%s/%s.MOV" % (SRC, clip)
    # decode with ffmpeg, not OpenCV: OpenCV turns rotated iPhone clips the other way round,
    # which put the mask on the wrong side of the frame
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,r_frame_rate:stream_side_data=rotation", "-of", "json", src],
                           capture_output=True, text=True).stdout
    import json
    st = json.loads(probe)["streams"][0]
    w, h = st["width"], st["height"]
    rot = int(next((d["rotation"] for d in st.get("side_data_list", []) if "rotation" in d), 0))
    if rot in (90, -90, 270, -270):
        w, h = h, w
    num, den = st["r_frame_rate"].split("/")
    fps = int(num) / int(den)
    size = (w, h)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                           stdout=subprocess.PIPE)
    sess, sess_turned = session(), session()    # one per input shape: no re-tuning per frame
    faces = None
    if FACES:
        faces = cv2.FaceDetectorYN.create(vf.FACE_MODEL, "", (w, h), FACE_CONF, 0.3, 5000)
    dets = []
    while True:
        buf = dec.stdout.read(w * h * 3)
        if len(buf) < w * h * 3:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        # plates are wide: drop tall or square boxes, which are the false hits
        found = [d for d in detect(sess, frame) if d[2] >= 1.1 * d[3] or d[4] >= 0.5]   # sure hits may be edge-on
        if rot:
            # portrait clips hold plates sideways: look at a rotated copy too (stricter, it misfires more)
            turned = np.ascontiguousarray(np.rot90(frame))        # 90 deg counter-clockwise
            for x, y, bw, bh, c in detect(sess_turned, turned):
                if bw >= PLATE_ASPECT * bh and c >= 0.35:
                    # point (u, v) in the turned image is (w-1-v, u) in the frame
                    found.append((w - (y + bh), x, bh, bw, c))
        if GREEN_ONLY:
            found = [d for d in found if is_green(frame, d)]
        if faces is not None and not GREEN_ONLY:
            _, fs = faces.detect(frame)
            for f in (fs if fs is not None else []):
                if f[2] > FACE_MAX * w:
                    continue
                found.append((float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[14]), "face"))
        dets.append(found)
        if len(dets) % 100 == 0:
            print("  %s: %d frames" % (clip, len(dets)), flush=True)
    dec.stdout.close()
    dec.wait()
    n = len(dets)
    hits = sum(1 for d in dets if d)
    faces_n = sum(1 for d in dets if any(len(b) > 5 for b in d))
    print("%s: %d frames %dx%d, plates or faces found on %d%s" % (clip, n, size[0], size[1], hits,
          (" (faces on %d)" % faces_n) if FACES else ""), flush=True)

    mask_path = "%s/%s_mask.mkv" % (OUT, clip)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
                            "-s", "%dx%d" % size, "-r", "%.5f" % fps, "-i", "-", "-c:v", "ffv1", mask_path],
                           stdin=subprocess.PIPE)
    for i in range(n):
        m = np.zeros((size[1], size[0]), np.uint8)
        for j in range(max(0, i - HOLD), min(n, i + HOLD + 1)):
            for box in dets[j]:
                x, y, bw, bh = box[:4]
                pw, ph = (FACE_PAD, FACE_PAD) if len(box) > 5 else (PAD_W, PAD_H)
                x0, y0 = int(x - bw * pw), int(y - bh * ph)
                x1, y1 = int(x + bw * (1 + pw)), int(y + bh * (1 + ph))
                cv2.rectangle(m, (x0, y0), (x1, y1), 255, -1)
        enc.stdin.write(m.tobytes())
    enc.stdin.close()
    enc.wait()

    out = "%s/%s_blur.mov" % (OUT, clip)
    graph = ("[0:v]format=yuv444p10le,split[a][b];[b]gblur=sigma=80:steps=2[bl];"
             "[1:v]format=gray,gblur=sigma=5,format=gray10le[m];"
             "[bl][m]alphamerge[blm];[a][blm]overlay=format=yuv444p10,format=yuv420p10le")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", mask_path,
                    "-filter_complex", graph, "-map", "0:a:0?", "-c:a", "copy",
                    *vf.hevc_args(),
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    out], check=True)

    chk = "%s/plates_check" % OUT
    os.makedirs(chk, exist_ok=True)
    for t in np.linspace(0.5, n / fps - 0.5, 12):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-init_hw_device", "vulkan", "-ss", "%.2f" % t, "-i", out,
                        "-frames:v", "1", "-vf",
                        "libplacebo=colorspace=bt709:color_primaries=bt709:color_trc=bt709:format=yuv420p,"
                        "scale=-2:360", "%s/%s_%05.1f.png" % (chk, clip, t)], check=True)


if __name__ == "__main__":
    for c in _ARGS[2:]:
        process(c)
