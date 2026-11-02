"""Check every generated take, so that the model's glitches are caught before anyone hears them.

usage: <whisperx python> dub_check.py <out_dir> <lang>
Writes out_dir/checks.json {take: {score, end, flags, heard, cps}}; takes already in it are skipped.
end   where the last word ends, from aligning the text we asked for. Aligning what was heard fails:
      heard numbers come as digits and get no timing, so the cut would fall before them. drop_tail()
      then removes a run-on after a pause, which the aligner counts as part of the last word.
score word match of the cut take with the text, numbers normalised (0..1).
flags what is still wrong after the cut and pause muting, the same audio the film gets:
      missing  words of the text not heard (swallowed)
      extra    words heard that are not in the text, repeats above all
      stray    a sound of 120+ ms outside every word (grunt, hum, squeak)
      pop      a click: energy jumps 22+ dB within 5 ms and dies within 40 ms
      gap      a silence over 1.2 s between words (the model stalled)
      pace     characters per second far from the median of all takes
"""
import difflib
import json
import os
import re
import statistics
import sys

import numpy as np

import dub
import vfconfig as cfg

cfg.torch_dlls()
import whisperx

SR = 16000
MIN_WORDS = 3     # shorter lines are too hard for speech recognition to judge


def words(t):
    return re.findall(r"\w+", t.lower())


def spoken_words(t):
    """Words with spelled letters joined, so "R P M" equals "rpm"."""
    return re.findall(r"\w+", re.sub(r"\b(\w) (?=\w\b)", r"\1", t.lower()))


def compare(want, heard_text, lang):
    """(score, missing, extra, heard words) of the heard text against the wanted words."""
    heard_text = re.sub(r"\b(1\d|2[0-3])\.?([0-5]\d)\b", r"\1:\2", heard_text)   # recognition writes 17:45 as 1745
    heard = spoken_words(dub.speakable(heard_text, lang))
    sm = difflib.SequenceMatcher(None, want, heard, autojunk=False)
    missing = extra = 0
    for tag, a, b, c, d in sm.get_opcodes():
        if tag != "equal":
            missing += b - a
            extra += d - c
    return round(sm.ratio(), 3), missing, extra, heard


def repeated(want, heard):
    """A run of 2+ words heard more times than the text has it (the model said it again)."""
    if len(heard) <= len(want) + 1:     # a repeat adds words; a name spelled differently does not
        return False
    for n in (2, 3, 4):
        grams = [tuple(heard[i:i + n]) for i in range(len(heard) - n + 1)]
        for g in set(grams):
            have = sum(tuple(want[i:i + n]) == g for i in range(len(want) - n + 1))
            if grams.count(g) > max(have, 1):
                return True
    return False


def drop_tail(a, end, want, lang, hear):
    """End of the take without a run-on that came after a pause and that the aligner took for the last word.

    It stretches the last word over any sound that follows, so the test is by ear: if the text is as
    complete without the last sound, that sound is not part of it."""
    for _ in range(3):
        cut = dub.clean(a[:int((end + 0.15) * SR)], SR)
        hop = SR // 100
        n = len(cut) // hop
        lv = 10 * np.log10((cut[:n * hop].reshape(-1, hop) ** 2).mean(1) + 1e-12)
        on = np.nonzero(lv > np.percentile(lv, 95) - 30)[0]
        gaps = np.nonzero(np.diff(on) >= 10)[0]       # 100 ms of silence
        if not len(gaps):
            return end
        last, first = on[gaps[-1]], on[gaps[-1] + 1]
        if on[-1] - first > 150 or last < 30:          # over 1.5 s is speech, or nothing would be left
            return end
        text = lambda x: " ".join(q["text"] for q in hear(x))
        before = cut[:(last + 3) * hop]
        if compare(want, text(before), lang)[0] < compare(want, text(cut), lang)[0] - 0.01:
            return end
        end = round((last + 1) * 0.01, 3)
    return end


def stray(x, spans):
    """Longest run (s) of sound outside the words."""
    hop = SR // 100
    n = len(x) // hop
    lv = 10 * np.log10((x[:n * hop].reshape(-1, hop) ** 2).mean(1) + 1e-12)
    loud = lv > np.percentile(lv, 95) - 20
    for s, e in spans:
        loud[max(0, int((s - 0.1) * 100)):int((e + 0.17) * 100)] = False
    best = run = 0
    for v in loud:
        run = run + 1 if v else 0
        best = max(best, run)
    return best / 100


def pops(x):
    """Times of isolated clicks: a jump over the 5 ms before it that is gone 40 ms later."""
    hop = SR // 400   # 2.5 ms
    n = len(x) // hop
    if n < 40:
        return []
    lv = 10 * np.log10((x[:n * hop].reshape(-1, hop) ** 2).mean(1) + 1e-10)
    top = np.percentile(lv, 95)
    return [i * 0.0025 for i in range(4, n - 16)
            if lv[i] > top - 6 and lv[i] - lv[i - 2:i].max() > 22 and lv[i] - lv[i + 8:i + 16].mean() > 22]


def main():
    out, lang = sys.argv[1], sys.argv[2]
    man = json.load(open(os.path.join(out, "manifest.json"), encoding="utf-8"))
    path = os.path.join(out, "checks.json")
    checks = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    dub.load_say(out, lang)
    gpu = cfg.cuda_index()
    model = whisperx.load_model(cfg.WHISPER_MODEL, "cuda", device_index=gpu, compute_type="float16", language=lang)
    align, meta = whisperx.load_align_model(language_code=lang, device="cuda:%d" % gpu)

    def hear(a):
        return model.transcribe(a, batch_size=8, language=lang)["segments"]

    for n, m in enumerate(man):
        want = spoken_words(m["say"])
        for f in m["takes"]:
            if f in checks:
                continue
            a = whisperx.load_audio(f)
            seg, end, spans = hear(a), None, []
            if seg:
                r = whisperx.align([{"start": seg[0]["start"], "end": min(len(a) / SR, seg[-1]["end"] + 0.5),
                                     "text": m["say"]}], align, meta, a, "cuda:%d" % gpu, return_char_alignments=False)
                spans = [(w["start"], w["end"]) for w in r.get("word_segments") or [] if "end" in w]
                if spans:
                    end = drop_tail(a, round(float(spans[-1][1]), 3), want, lang, hear)
                    spans = [(s, min(e, end)) for s, e in spans if s < end]
            cut = dub.clean(a[:int((end + 0.15) * SR)] if end else a, SR)
            heard = " ".join(s["text"] for s in hear(cut)).strip()
            score, missing, extra, heard_words = compare(want, heard, lang)
            flags = []
            if len(want) >= MIN_WORDS:
                if missing >= max(2, len(want) * 0.3):
                    flags.append("missing")
                if extra >= max(3, len(want) * 0.3) or repeated(want, heard_words):
                    flags.append("extra")
            if spans and stray(cut, spans) >= 0.12:
                flags.append("stray")
            if pops(cut):
                flags.append("pop")
            if any(q[0] - p[1] > 1.2 for p, q in zip(spans, spans[1:])):
                flags.append("gap")
            checks[f] = {"score": score, "end": end, "flags": flags, "heard": heard,
                         "cps": round(len(m["say"]) / max(len(cut) / SR, 0.1), 1)}
        if n % 25 == 0:
            print(n, len(checks), flush=True)
            json.dump(checks, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    long_takes = [f for m in man if len(m["say"]) > 20 for f in m["takes"]]
    mid = statistics.median(checks[f]["cps"] for f in long_takes)
    for f in long_takes:
        c = checks[f]
        if not 0.55 * mid < c["cps"] < 1.7 * mid and "pace" not in c["flags"]:
            c["flags"].append("pace")
    json.dump(checks, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    takes = [f for m in man for f in m["takes"]]
    bad = sum(all(checks[f]["flags"] for f in m["takes"]) for m in man)
    print("done: %d takes, %d flagged; %d of %d sentences have no clean take; median %.1f chars/s"
          % (len(takes), sum(bool(checks[f]["flags"]) for f in takes), bad, len(man), mid))


if __name__ == "__main__":
    main()
