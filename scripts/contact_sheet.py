"""Contact sheet: N frames per clip, one row per clip, labelled with clip and time.

usage: python contact_sheet.py <out.png> <frames_per_clip> <video> [<video> ...]
"""
import os
import sys

import cv2
import numpy as np

out, per = sys.argv[1], int(sys.argv[2])
rows = []
for path in sys.argv[3:]:
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    tiles = []
    for p in np.linspace(0.05, 0.95, per):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * p))
        ok, frame = cap.read()
        frame = cv2.resize(frame, (320, 180)) if ok else np.zeros((180, 320, 3), np.uint8)
        label = "%s @%ds" % (os.path.basename(path)[3:8], n * p / fps)
        cv2.rectangle(frame, (0, 0), (150, 24), (0, 0, 0), -1)
        cv2.putText(frame, label, (4, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
        tiles.append(frame)
    rows.append(np.hstack(tiles))
cv2.imwrite(out, np.vstack(rows))
print(out)
