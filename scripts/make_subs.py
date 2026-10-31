"""Ukrainian subtitles for the finished film: WhisperX words on the final audio -> cues -> SRT.

usage: python make_subs.py <film.mp4> <out_dir> [language, default uk]
       python make_subs.py --from-words <out_dir> [language]   re-cut cues from words_<lang>.json
Writes <out_dir>/words_<lang>.json (every word with its time in the film) and <out_dir>/film.<lang>.srt.
The SRT is a first pass: names and numbers are fixed by hand afterwards, and the
Polish and English files keep exactly the same cue times.
"""
import json
import os
import subprocess
import sys

import torch

import vfconfig as vf

vf.torch_dlls()
import whisperx

MAX_CHARS = 84         # two lines of ~42
MAX_DUR, MIN_DUR = 6.0, 1.0
GAP_SPLIT = 0.8        # a pause this long always starts a new cue


def transcribe(film, out_dir, lang):
    wav = os.path.join(out_dir, "film_16k.wav")
    subprocess.run([vf.FFMPEG, "-v", "error", "-y", "-i", film, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
    gpu = vf.cuda_index()
    model = whisperx.load_model(vf.WHISPER_MODEL, "cuda", device_index=gpu, compute_type="float16", language=lang)
    audio = whisperx.load_audio(wav)
    segs = model.transcribe(audio, batch_size=8, language=lang)["segments"]
    am, meta = whisperx.load_align_model(language_code=lang, device="cuda:%d" % gpu)
    res = whisperx.align(segs, am, meta, audio, "cuda:%d" % gpu)
    words = []
    for s in res["segments"]:
        for w in s["words"]:
            if "start" in w:
                words.append({"w": w["word"], "s": round(w["start"], 2), "e": round(w["end"], 2)})
            elif words:                      # numbers often come back without times: glue to the previous word
                words[-1]["w"] += " " + w["word"]
    return words


def cues(words):
    """Group words into cues; break at a sentence end or comma when the cue would get too long."""
    out, cur = [], []

    def text(ws):
        return " ".join(x["w"] for x in ws)

    for w in words:
        if cur:
            too_long = len(text(cur + [w])) > MAX_CHARS or w["e"] - cur[0]["s"] > MAX_DUR
            pause = w["s"] - cur[-1]["e"] > GAP_SPLIT
            sentence_end = cur[-1]["w"].rstrip().endswith((".", "?", "!", "..."))
            if pause or (sentence_end and len(text(cur)) > 10):
                out.append(cur)
                cur = []
            elif too_long:
                # go back to the last comma or full stop that leaves a cue of a decent length
                cut = max((i for i in range(1, len(cur)) if cur[i - 1]["w"].rstrip().endswith((",", ".", "?", "!", ":", ";"))
                           and len(text(cur[:i])) >= 20), default=len(cur))
                out.append(cur[:cut])
                cur = cur[cut:]
        cur.append(w)
    if cur:
        out.append(cur)
    res = []
    for k, c in enumerate(out):
        s, e = c[0]["s"], c[-1]["e"] + 0.3
        if e - s < MIN_DUR:
            e = s + MIN_DUR
        if k + 1 < len(out):
            e = min(e, out[k + 1][0]["s"] - 0.05)
        res.append((s, e, text(c)))
    return res


def wrap(text, width=42):
    if len(text) <= width:
        return text
    mid = len(text) // 2
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    cut = min(spaces, key=lambda i: abs(i - mid))
    return text[:cut] + "\n" + text[cut + 1:]


def tc(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def write_srt(path, items):
    with open(path, "w", encoding="utf-8") as f:
        for k, (s, e, text) in enumerate(items, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (k, tc(s), tc(e), wrap(text)))


if __name__ == "__main__":
    if sys.argv[1] == "--from-words":
        out_dir, lang = sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else vf.LANGUAGE)
        words = json.load(open(os.path.join(out_dir, "words_%s.json" % lang), encoding="utf-8"))
    else:
        out_dir, lang = sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else vf.LANGUAGE)
        os.makedirs(out_dir, exist_ok=True)
        words = transcribe(sys.argv[1], out_dir, lang)
        json.dump(words, open(os.path.join(out_dir, "words_%s.json" % lang), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=0)
    items = cues(words)
    write_srt(os.path.join(out_dir, "film.%s.srt" % lang), items)
    print("%d words, %d cues" % (len(words), len(items)))
