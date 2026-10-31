"""Camera roll with perspective cancelled: mean of left-half and right-half vertical leans.

Pitch (keystone) tilts verticals left and right of centre in opposite directions,
while roll tilts them all the same way, so (left + right) / 2 isolates roll.
usage: python roll_lr.py <video> [<video> ...]
"""
import math
import sys

import cv2
import numpy as np

side = {"L": [], "R": []}
for path in sys.argv[1:]:
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for i in np.linspace(n * 0.05, n * 0.95, 20).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame[: int(h * 0.6)], cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 60, 160)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 720, threshold=60, minLineLength=int(h * 0.08), maxLineGap=6)
        for x1, y1, x2, y2 in (lines.reshape(-1, 4) if lines is not None else []):
            xm = (x1 + x2) / 2
            if not (0.1 * w < xm < 0.9 * w):
                continue
            if y1 < y2:
                x1, y1, x2, y2 = x2, y2, x1, y1
            lean = math.degrees(math.atan2(x2 - x1, y1 - y2))
            if 0.3 < abs(lean) <= 12:
                side["L" if xm < w / 2 else "R"].append(lean)
for k, v in side.items():
    print("%s: %d lines, median %+.2f" % (k, len(v), np.median(v)))
print("roll estimate = %+.2f deg" % ((np.median(side["L"]) + np.median(side["R"])) / 2))
