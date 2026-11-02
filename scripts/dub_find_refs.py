"""Rank stretches of the user's speech that could serve as a voice reference.

usage: python find_refs.py <footage_dir> <transcripts_dir> [--cut out_dir N]
For every clip with a word-timed transcript: the noise floor is measured in the pauses between words
and the speech level on the words; windows of 9-15 s of continuous talk are ranked by that ratio
(clips recorded at stops, without road noise, come first). --cut writes the best N, one per clip.
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

SR = 16000


def audio(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def windows(words, lo=9.0, hi=15.0, gap=0.7):
    """Runs of words with no pause over `gap`, cut to lo..hi seconds."""
    out, i = [], 0
    while i < len(words):
        j = i
        while j + 1 < len(words) and words[j + 1]["s"] - words[j]["e"] < gap and words[j + 1]["e"] - words[i]["s"] < hi:
            j += 1
        if words[j]["e"] - words[i]["s"] >= lo:
            out.append((words[i]["s"], words[j]["e"], " ".join(w["w"] for w in words[i:j + 1])))
            i = j + 1
        else:
            i += 1
    return out


def main():
    footage, tdir = sys.argv[1], sys.argv[2]
    rows = []
    for tf in sorted(glob.glob(os.path.join(tdir, "*.json"))):
        t = json.load(open(tf, encoding="utf-8"))
        words = [w for s in t["segments"] for w in s.get("words", []) if "s" in w and "e" in w]
        clip = os.path.join(footage, t["clip"])
        if len(words) < 20 or not os.path.exists(clip):
            continue
        x = audio(clip)
        speech = np.zeros(len(x), bool)
        for w in words:
            speech[int(w["s"] * SR):int(w["e"] * SR)] = True
        if (~speech).sum() < SR:
            continue
        # quietest 30 % of the pause frames: road / fan noise under the voice
        pf = x[~speech][:len(x[~speech]) // 320 * 320].reshape(-1, 320)
        floor = np.percentile(20 * np.log10(np.sqrt((pf ** 2).mean(1)) + 1e-9), 30)
        for s, e, text in windows(words):
            seg = x[int(s * SR):int(e * SR)]
            rows.append((db(seg) - floor, t["clip"], s, e, text))
    rows.sort(reverse=True)
    seen = set()
    best = []
    for r in rows:
        if r[1] not in seen:
            seen.add(r[1])
            best.append(r)
    for r in best[:15]:
        print("%5.1f dB  %-14s %6.1f-%6.1f  %s" % (r[0], r[1], r[2], r[3], r[4][:70]))
    if "--cut" in sys.argv:
        out, n = sys.argv[sys.argv.index("--cut") + 1], int(sys.argv[sys.argv.index("--cut") + 2])
        os.makedirs(out, exist_ok=True)
        for r in best[:n]:
            f = os.path.join(out, "ref_%s_%d.wav" % (os.path.splitext(r[1])[0][4:], int(r[2])))
            sf.write(f, audio(os.path.join(footage, r[1]), 48000)[int(r[2] * 48000) - 4800:int(r[3] * 48000) + 4800], 48000)
            print("wrote", f)


if __name__ == "__main__":
    main()
