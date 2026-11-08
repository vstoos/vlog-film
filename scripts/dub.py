"""Dub a finished film into another language (Polish, English, Ukrainian) in the user's cloned voice.

  python dub.py gen <subs.srt> <ref.wav|-> <out_dir> [from_s] [to_s] --lang pl
  <whisperx python> dub_check.py <out_dir> <lang>      checks every take, writes out_dir/checks.json
  python dub_regen.py <out_dir> <ref.wav|-> --lang pl  new takes for changed or glitched sentences
  python dub.py mix <film.mp4> <out_dir> [from_s] [to_s]

gen: subtitle cues are joined into whole sentences (the models swallow words in fragments),
     numbers are written out, and every sentence is spoken N times in the voice of the reference.
     "-" takes the user's saved voice for the language (config "voices_dir", voices.json); a .wav
     given instead needs its transcript next to it as <ref>.txt for Higgs.
     --engine higgs (default, config "tts_engine"): Higgs TTS 3 in WSL, see higgs_tts.py;
     --engine chatterbox: Chatterbox Multilingual (MIT) in this Python, with --cfg / --exag.
     out_dir/say.json {lang: {"written": "spoken"}} holds the project's
     names and abbreviations, applied after ranges became words ("4,6 do 4,8").
mix: the best take of each sentence (fewest flags, then highest word match) goes at the sentence's
     first cue, cut after its last word, pauses muted. A line that does not fit is sped up (at most
     1.3x, pitch kept) and the following lines move later, so lines never overlap. Demucs removes the
     original voice; the new one goes over the rest, level matched to the original line.
     Writes dub.wav, voice.wav and preview.mp4 (the film's picture with the new sound).
references/dubbing.md has the whole method.
"""
import argparse
import json
import os
import platform
import re
import subprocess
import sys

import numpy as np
import soundfile as sf

import vfconfig as cfg

SR = 48000


def srt(path):
    cues = []
    for b in open(path, encoding="utf-8").read().strip().split("\n\n"):
        lines = b.strip().split("\n")
        g = [int(v) for v in re.match(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", lines[1]).groups()]
        cues.append((g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000,
                     " ".join(lines[2:]).strip()))
    return cues


def sentences(cues, gap=0.8, longest=9.0):
    """Join cues into sentences: (start, end_of_last_cue, text).

    A long run-on sentence is also broken at a comma once it covers `longest` seconds, so that each
    piece starts at its own cue: Polish is spoken faster, and one 40 s line ended 15 s early.
    A cue with no punctuation at its end always goes on, however long the pause in the original:
    split there, the dub stops mid-phrase."""
    out, cur = [], None
    for s, e, t in cues:
        if cur and (s - cur[1] < gap or not re.search(r"[.,:;!?…]$", cur[2])) and not re.search(r"[.!?…]$", cur[2]) \
                and not (cur[1] - cur[0] >= longest and cur[2].endswith(",")):
            cur = (cur[0], e, cur[2] + " " + t)
        else:
            if cur:
                out.append(cur)
            cur = (s, e, t)
    if cur:
        out.append(cur)
    return out


SAY = {}    # written -> spoken for the project's names and abbreviations (out_dir/say.json); the model mangles them


def load_say(out, lang):
    f = os.path.join(out, "say.json")
    SAY.clear()
    if os.path.exists(f):
        SAY.update(json.load(open(f, encoding="utf-8")).get(lang, {}))


def replace_say(t):
    for a, b in SAY.items():
        t = t.replace(a, b)
    return t


def speakable_en(text):
    """English text for TTS: numbers, ranges, units and symbols written out."""
    from num2words import num2words

    def num(m):
        v = m.group(0).replace(",", "")
        try:
            return num2words(float(v) if "." in v else int(v), lang="en")
        except Exception:
            return m.group(0)
    t = re.sub(r"(\d)[-–](\d)", r"\1 to \2", text).replace("km/h", "kilometres per hour").replace("%", " percent")
    t = replace_say(t)
    t = re.sub(r"\bl/100 km\b", "litres per hundred kilometres", t)
    t = re.sub(r"\bkm\b", "kilometres", t)
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", r"\1 \2", t)
    t = re.sub(r"(\d)-(litre|something|plus|ish)", r"\1 \2", t)
    t = re.sub(r"\b20([12]\d)\b(?! kilomet)", lambda y: "twenty " + num2words(int(y.group(1)), lang="en"), t)   # years
    t = re.sub(r"\d{1,3}(?:,\d{3})+|\d+\.\d+|\d+", num, t)
    return re.sub(r"\s+", " ", t).strip()


def speakable_uk(text):
    """Ukrainian text for TTS: numbers, ranges, units and symbols written out."""
    from num2words import num2words

    def num(m):
        v = m.group(0).replace(" ", "")
        try:
            return num2words(float(v.replace(",", ".")) if "," in v else int(v), lang="uk")
        except Exception:
            return m.group(0)
    t = text.replace("–", " до ").replace("км/год", "кілометрів на годину").replace("%", " відсотків")
    t = replace_say(t)
    t = re.sub(r"\bл/100 км\b", "літрів на сто кілометрів", t)
    t = re.sub(r"\bкм\b", "кілометрів", t)
    t = re.sub(r"\d{1,3}(?: \d{3})+|\d+,\d+|\d+", num, t)
    return re.sub(r"\s+", " ", t).strip()


def speakable(text, lang="pl"):
    """Polish text for TTS: numbers, ranges, units and symbols written out."""
    if lang == "en":
        return speakable_en(text)
    if lang == "uk":
        return speakable_uk(text)
    from num2words import num2words

    def num(m):
        v = m.group(0).replace(" ", "")
        try:
            return num2words(float(v.replace(",", ".")) if "," in v else int(v), lang="pl")
        except Exception:
            return m.group(0)
    t = text.replace("–", " do ").replace("km/h", "kilometrów na godzinę").replace("%", " procent")
    t = replace_say(t)
    t = re.sub(r"\bkm\b", "kilometrów", t)
    t = re.sub(r"\bl/100 km\b", "litrów na sto kilometrów", t)
    t = re.sub(r"\d{1,3}(?: \d{3})+|\d+,\d+|\d+", num, t)
    return re.sub(r"\s+", " ", t).strip()


def voice(lang, ref="-"):
    """(reference wav, its transcript) for a language: the saved voice for "-", else ref and <ref>.txt."""
    if ref in (None, "", "-"):
        d = cfg.get("voices_dir") or "C:/Data/voices"
        v = json.load(open(os.path.join(d, "voices.json"), encoding="utf-8"))[lang]
        return os.path.join(d, v["wav"]), v["text"]
    txt = os.path.splitext(ref)[0] + ".txt"
    return ref, (open(txt, encoding="utf-8").read().strip() if os.path.exists(txt) else None)


def wsl_path(p):
    p = os.path.abspath(p).replace("\\", "/")
    return "/mnt/%s%s" % (p[0].lower(), p[2:]) if re.match(r"[A-Za-z]:/", p) else p


def synth(jobs, lang, ref, engine="higgs", cfg_weight=0.3, exag=0.8):
    """Speak jobs [(text, out_wav, seed)] in the reference voice; takes already on disk are kept (Higgs)."""
    ref_wav, ref_text = voice(lang, ref)
    if engine == "chatterbox":
        import torch
        import torchaudio as ta
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        model = ChatterboxMultilingualTTS.from_pretrained(device="cuda:%d" % cfg.cuda_index())
        for n, (text, f, seed) in enumerate(jobs):
            torch.manual_seed(seed)
            wav = model.generate(text, language_id=lang, audio_prompt_path=ref_wav, cfg_weight=cfg_weight, exaggeration=exag)
            ta.save(f, wav.cpu(), model.sr)
            print("%3d/%d  %s" % (n + 1, len(jobs), text[:70]), flush=True)
        return
    if not ref_text:
        raise SystemExit("Higgs needs the reference's transcript: put it in %s.txt" % os.path.splitext(ref_wav)[0])
    win = platform.system() == "Windows"
    p = wsl_path if win else os.path.abspath
    spec = {"ref": p(ref_wav), "ref_text": ref_text, "model": cfg.get("higgs_model") or "bosonai/higgs-tts-3-4b",
            "jobs": [{"text": t, "out": p(f), "seed": s} for t, f, s in jobs]}
    jf = os.path.join(os.path.dirname(os.path.abspath(jobs[0][1])), "_higgs_jobs.json")
    json.dump(spec, open(jf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # CUDA_DEVICE_ORDER=PCI_BUS_ID: higgs_gpu is the index nvidia-smi shows
    env = "HF_HOME=%s CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=%s" % (
        cfg.get("higgs_hf_home") or "~/higgs/hf", cfg.get("higgs_gpu") or "0")
    cmd = "%s %s/bin/python %s %s" % (env, cfg.get("higgs_venv") or "~/higgs/.venv",
                                      p(os.path.join(os.path.dirname(os.path.abspath(__file__)), "higgs_tts.py")), p(jf))
    run = ["wsl", "-d", cfg.get("higgs_distro") or "Ubuntu", "--", "bash", "-lc", cmd] if win else ["bash", "-lc", cmd]
    subprocess.run(run, check=True)
    missing = [f for _, f, _ in jobs if not os.path.exists(f)]
    if missing:
        raise SystemExit("Higgs wrote %d of %d takes; first missing: %s" % (len(jobs) - len(missing), len(jobs), missing[0]))


def gen(a):
    load_say(a.out, a.lang)
    sents = [s for s in sentences(srt(a.subs)) if a.start <= s[0] < a.end]
    os.makedirs(os.path.join(a.out, "takes"), exist_ok=True)
    manifest, jobs = [], []
    for i, (s, e, text) in enumerate(sents):
        say = speakable(text, a.lang)
        files = [os.path.join(a.out, "takes", "%03d_%d.wav" % (i, k)) for k in range(a.takes)]
        # Higgs takes one seed per batch, so take k of every line shares seed 7 + k
        jobs += [(say, f, 1000 * i + k if a.engine == "chatterbox" else 7 + k) for k, f in enumerate(files)]
        manifest.append({"start": s, "end": e, "text": text, "say": say, "takes": files})
    # the manifest first: an interrupted Higgs run is resumed by running gen again (finished takes are kept)
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%d sentences, %d takes, engine %s" % (len(sents), len(jobs), a.engine), flush=True)
    synth(jobs, a.lang, a.ref, a.engine, a.cfg, a.exag)


def clean(x, sr=SR, floor=-17.0, hf_floor=-14.0, depth=-45.0, word_end=None):
    """Mute what the model makes in pauses (low buzz, clicks, a squeak after the last word).

    A 10 ms frame is speech when it is loud (within `floor` dB of the take's loud frames) or, for
    quiet consonants like f and s, when its high-frequency part is (`hf_floor`). Pauses under 150 ms
    stay, speech gets 60 ms before and 150 ms after, and the rest drops by `depth` dB with short ramps.
    `word_end` (s, from dub_check) is where the recogniser heard the last word end: a quiet last word
    under the gate was muted and then trimmed as silence ("podrozach" at 1:38), so the gate stays open to it."""
    hop = sr // 100
    n = len(x) // hop
    if n < 10:
        return x
    def level(s):
        return 10 * np.log10((s[:n * hop].reshape(-1, hop) ** 2).mean(1) + 1e-12)
    lo, hi = level(x), level(np.diff(x, prepend=x[0]))
    on = (lo > np.percentile(lo, 95) + floor) | (hi > np.percentile(hi, 95) + hf_floor)
    idx = np.nonzero(on)[0]
    for a, b in zip(idx[:-1], idx[1:]):      # close short gaps
        if 1 < b - a <= 15:
            on[a:b] = True
    # islands under 60 ms with nothing around them are clicks, not speech
    edge = np.diff(np.concatenate([[0], on.astype(int), [0]]))
    for a, b in zip(np.nonzero(edge == 1)[0], np.nonzero(edge == -1)[0]):
        if b - a < 6:
            on[a:b] = False
    # a short sound after a clear silence at the very end is the model running on, not a word
    edge = np.diff(np.concatenate([[0], on.astype(int), [0]]))
    starts, ends = np.nonzero(edge == 1)[0], np.nonzero(edge == -1)[0]
    if word_end is not None and len(starts):
        w = min(n, int(word_end * 100))
        before = ends[ends <= w]
        on[before[-1] if len(before) else starts[0]:w] = True
    elif len(starts) > 1 and on.sum() > 150 and ends[-1] - starts[-1] < 35 and starts[-1] - ends[-2] >= 18:
        on[starts[-1]:ends[-1]] = False
    keep = np.convolve(on.astype(float), np.ones(15), "full")[:n] > 0   # 150 ms after ...
    keep = keep | np.concatenate([on[6:], np.zeros(6, bool)])               # ... and 60 ms before
    gain = np.repeat(np.where(keep, 1.0, 10 ** (depth / 20)), hop)
    ramp = np.ones(sr // 33) / (sr // 33)   # 30 ms: an 8 ms ramp opened the gate with a click, like a radio
    gain = np.convolve(gain, ramp, "same")
    gain = np.concatenate([gain, np.full(len(x) - len(gain), gain[-1])])
    return (x * gain).astype(np.float32)


# the model copies mains hum from the reference recording into every line; a man's voice has nothing under 70 Hz
HUM_FILTER = "highpass=f=70:poles=2,highpass=f=70:poles=2,bandreject=f=50:width_type=h:w=6,bandreject=f=100:width_type=h:w=3"
VOICE_LIFT = 2.0   # dB over the original voice's level: synthetic speech is harder to follow over road noise
CHECKS = {}   # take file -> dub_check.py result: end of its last word (the model may run on after it), score, flags


TAIL = 0.06   # s: Higgs decodes the last codec frames without look-ahead: +4 dB (p90 +14 dB) and a DC step, "like a radio"


def denoise(x, sr, floor=0.12):
    """Stationary noise out: the model adds a hiss/rumble floor about 20 dB under the voice (the reference
    has it at -44 dB), and gating that floor in pauses on and off is what sounds like a radio squelch.
    Noise profile = mean spectrum of the quietest fifth of the frames; Wiener-like gain, smoothed."""
    from scipy.ndimage import uniform_filter
    from scipy.signal import istft, stft
    if len(x) < sr // 2:
        return x
    _, _, X = stft(x, sr, nperseg=1024, noverlap=768)
    mag = np.abs(X)
    e = mag.sum(0)
    noise = mag[:, e <= np.percentile(e, 20)].mean(1, keepdims=True)
    gain = uniform_filter(np.clip(1 - 1.5 * noise / (mag + 1e-9), floor, 1), size=(3, 5))
    _, y = istft(X * gain, sr, nperseg=1024, noverlap=768)
    return y[:len(x)].astype(np.float32)


def load(f):
    x, sr = sf.read(f, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    stop = len(x) - int(TAIL * sr)
    if CHECKS.get(f, {}).get("end"):
        stop = min(stop, int((CHECKS[f]["end"] + 0.15) * sr))
    x = x[:max(stop, sr // 10)]
    from scipy.signal import butter, sosfiltfilt
    x = sosfiltfilt(butter(2, 60, "highpass", fs=sr, output="sos"), x).astype(np.float32)   # DC and rumble, before any fade
    x = denoise(x, sr)
    # float64 positions: on Windows numpy's default int is 32-bit and arange * sr overflows (audio loops)
    x = np.interp(np.arange(int(len(x) * SR / sr), dtype=np.float64) * (sr / SR), np.arange(len(x)), x).astype(np.float32)
    x = clean(x, word_end=CHECKS.get(f, {}).get("end"))
    fr = np.abs(x[:len(x) // 960 * 960]).reshape(-1, 960).max(1)   # trim silence: 20 ms frames
    on = np.nonzero(fr > fr.max() * 10 ** (-45 / 20))[0]
    if len(on):
        x = x[max(0, on[0] - 2) * 960:(on[-1] + 3) * 960]
    # fades: a take cut 0.15 s after its last word, or one that starts at full level, clicks at the edge
    # raised cosine, 15 ms in and 80 ms out: a straight 40 ms ramp off a word still left a thump
    fi, fo = min(len(x) // 4, SR * 15 // 1000), min(len(x) // 4, SR * 8 // 100)
    x[:fi] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fi))).astype(np.float32)
    x[len(x) - fo:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo))).astype(np.float32)
    return x


def ffmpeg(*args):
    subprocess.run([cfg.FFMPEG, "-v", "error", "-y", *args], check=True)


def loud(x, sr):
    """RMS (dB) of the louder half of 50 ms frames, so pauses do not count."""
    h = sr // 20
    n = len(x) // h
    if n < 2:
        return -90.0
    e = (x[:n * h].reshape(-1, h) ** 2).mean(1)
    return 10 * np.log10(np.sort(e)[n // 2:].mean() + 1e-12)


def level_gain(line, orig, sr, osr, most=8.0):
    """Gain that puts a dubbed line at the level the same words have in the original voice, so a line
    shouted over motorway noise stays loud. At most +-`most` dB; no change where the original has no voice."""
    o = loud(orig, osr)
    if o < -45:
        return 1.0
    g = 10 ** (np.clip(o - loud(line, sr) + VOICE_LIFT, -most, most) / 20)
    return min(g, 0.98 / max(np.abs(line).max(), 1e-6))


def take_rank(f, m):
    """Sort key for a sentence's takes: fewest flags, best word match, then the shortest: the longer
    one is more often padded with run-on, and picking the length nearest the cue chose exactly those."""
    c = CHECKS.get(f, {})
    return (-len(c.get("flags", [])), c.get("score", 0), -len(load(f)))


BED_DB = {"original": -28.0,   # voice-over: the whole original track, voice included, well under the dub (user: quieter than -22)
          "separated": -8.0}   # the film's sound without its voice (demucs): what it leaves there is noise


def talk_mask(orig, osr, gap=3.0):
    """100 ms frames where the original voice talks, pauses under `gap` s included: where bed() ducks."""
    hop = osr // 10
    n = len(orig) // hop
    lv = 10 * np.log10((orig[:n * hop].reshape(-1, hop) ** 2).mean(1) + 1e-12)
    talk = lv > np.percentile(lv, 95) - 30
    idx = np.nonzero(talk)[0]
    for p, q in zip(idx[:-1], idx[1:]):
        if q - p <= gap * 10:
            talk[p:q] = True
    return talk


def bed(rest, orig, osr, out, db, gap=3.0, ramp=1.0):
    """The bed under the dub (the original track, or its sound without the voice), steady and `db`
    quieter wherever the original voice talks (pauses under `gap` s count as talk), at full level in
    music and road inserts, `ramp` s fades between. Ducking under each dubbed line made the left-over
    noise swell in every pause between lines; the user preferred the original voice kept, quietly."""
    x, sr = sf.read(rest, dtype="float32")
    hop = osr // 10
    g = np.where(talk_mask(orig, osr, gap), 10 ** (db / 20), 1.0)
    k = int(ramp * 10)
    g = np.convolve(np.concatenate([np.full(k, g[0]), g, np.full(k, g[-1])]), np.ones(k) / k, "same")[k:-k]
    g = np.interp(np.arange(len(x)) * (osr / sr) / hop, np.arange(len(g)), g).astype(np.float32)
    sf.write(out, x * (g[:, None] if x.ndim > 1 else g), sr)


def place(man, lens, slow=1.0, lead=3.0, pause=0.35, gap=1.5, fastest=1.3, catch=0.08, brisk=1.15, until=None, since=None):
    """Start and tempo of every dubbed line. Lines of one stretch of talk (cues less than `gap` s apart)
    follow each other with a natural pause and may start up to `lead` s before their cue, so a short
    translation leaves no hole before each line. Tempo goes line by line: `slow` (or 1.0), plus `catch`
    per second the line starts behind its cue (to `brisk`), so a long translation catches up gradually;
    only a stretch that would run into the next one gets faster, to `fastest`. Cue by cue, short lines
    waited for their cue and long ones were sped up alone: 191 holes over 0.8 s and 28 lines up to 1.3x
    in the Polish Mercedes dub.
    `until(t)`: where the talk around time t ends and the bed comes up to full level (a music or road
    insert). A stretch must be over by then: its pauses shrink first, then it gets faster. Bounded only
    by the next stretch, the last lines ran up to 3 s into the music (Yaris: 4 places in Polish, 7 in English).
    `since(t)`: where the talk at a cue starting at t begins; no line starts before it, so a lead or a cue
    that covers the end of an insert does not put the line over full-level music."""
    groups, cur = [], [0]
    for i in range(1, len(man)):
        if man[i]["start"] - man[i - 1]["end"] < gap:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)
    out, free = [None] * len(man), -1e9
    for k, g in enumerate(groups):
        hard = man[groups[k + 1][0]]["start"] - 0.3 if k + 1 < len(groups) else 1e9
        if until:
            hard = min(hard, max(until(man[g[-1]]["end"]), man[g[-1]]["end"] + 0.2))

        def run(boost, squeeze=1.0):
            t, res = free, []
            for j, i in enumerate(g):
                if j == 0:
                    at = max(t + 0.15, man[i]["start"])
                else:
                    p = squeeze * min(0.8, pause + 0.5 * max(0.0, man[i]["start"] - man[g[j - 1]]["end"]))
                    at = max(t + p, man[i]["start"] - lead)
                if since:
                    at = max(at, min(since(man[i]["start"]), man[i]["start"] + 3.0))
                behind = max(0.0, at - man[i]["start"] - 0.3)
                f = min(fastest, min(brisk, max(slow, 1.0 if slow >= 1 else slow) + catch * behind) * boost)
                res.append((at, f))
                t = at + lens[i] / f
            return res, t

        boost, squeeze = 1.0, 1.0
        while run(boost, squeeze)[1] > hard and squeeze > 0.4:
            squeeze -= 0.05
        while run(boost, squeeze)[1] > hard and boost < fastest:
            boost += 0.01
        res, free = run(boost, squeeze)
        for i, r in zip(g, res):
            out[i] = r
    return out


def mix(a):
    man = json.load(open(os.path.join(a.out, "manifest.json"), encoding="utf-8"))
    CHECKS.update(json.load(open(os.path.join(a.out, "checks.json"), encoding="utf-8")))
    dur = min(a.end, float(subprocess.run([cfg.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of",
                                           "csv=p=0", a.film], capture_output=True, text=True).stdout)) - a.start
    voice = np.zeros(int(dur * SR) + SR * 30, np.float32)
    tmp = os.path.join(a.out, "_tmp")
    ffmpeg("-ss", str(a.start), "-t", str(dur), "-i", a.film, "-vn", "-ac", "2", "-ar", "44100", tmp + "_film.wav")
    subprocess.run([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-o", a.out,
                    tmp + "_film.wav"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stems = os.path.join(a.out, "htdemucs", os.path.basename(tmp) + "_film")
    orig, osr = sf.read(os.path.join(stems, "vocals.wav"), dtype="float32")
    orig = orig.mean(1)
    free = a.start
    timing = []   # (cue start, start lateness, end past the last cue's end)
    glitches = []
    bests = [max(m["takes"], key=lambda f: take_rank(f, m)) for m in man]
    takes = [load(f) for f in bests]
    talk = talk_mask(orig, osr)

    def until(t):   # end of the talk around film time t, less the bed's 0.5 s ramp up
        i = int((t - a.start) * 10)
        while 0 <= i < len(talk) and talk[i]:
            i += 1
        return a.start + i / 10 - 0.5

    def since(t):   # start of the talk at film time t (or the next talk if t is in an insert), plus the ramp down
        i = int((t - a.start) * 10)
        if 0 <= i < len(talk) and not talk[i]:
            while i < len(talk) and not talk[i]:
                i += 1
        else:
            while i > 0 and talk[i - 1]:
                i -= 1
        return a.start + i / 10 + 0.5

    plan = place(man, [len(x) / SR for x in takes], a.slow, until=until, since=since)
    for i, (m, best, x, (at, f)) in enumerate(zip(man, bests, takes, plan)):
        if not a.start <= at < a.start + dur:     # a window (start, end): only its lines
            continue
        if abs(f - 1) > 0.005:
            sf.write(tmp + "_in.wav", x, SR)
            ffmpeg("-i", tmp + "_in.wav", "-af", "atempo=%.3f" % f, tmp + "_out.wav")
            x, _ = sf.read(tmp + "_out.wav", dtype="float32")
        x = x * level_gain(x, orig[int((m["start"] - a.start) * osr):int((m["end"] - a.start) * osr)], SR, osr)
        free = at + len(x) / SR
        timing.append((m["start"], at - m["start"], free - m["end"], m["text"]))
        j = int((at - a.start) * SR)
        voice[j:j + len(x)] += x[:len(voice) - j]
        print("%3d %6.1f s late %4.1f  tempo %.2f  score %.2f  %s" % (i + 1, m["start"], at - m["start"], f,
                                                                    CHECKS.get(best, {}).get("score", 0), m["text"][:60]), flush=True)
        glitches += [(m["start"], fl, m["text"]) for fl in CHECKS.get(best, {}).get("flags", [])]
    late = [t for t in timing if t[1] > 1.5 or t[2] > 1.5]   # place() lets lines drift a little
    print("timing vs subtitles: %d lines, start late max %.1f s, end past cue max %.1f s, %d off by more than 0.5 / 1.5 s"
          % (len(timing), max(t[1] for t in timing), max(t[2] for t in timing), len(late)))
    for s, l, o, text in late:
        print("   %2d:%04.1f  late %.1f  over %.1f  %s" % (s // 60, s % 60, l, o, text[:60]))
    print("%d flags left on the chosen takes: listen to these" % len(glitches))
    for s, fl, text in glitches:
        print("   %2d:%04.1f  %s  %s" % (s // 60, s % 60, fl, text[:60]))
    sf.write(os.path.join(a.out, "voice.wav"), voice[:int(dur * SR)], SR)
    rest = tmp + "_film.wav" if a.bed == "original" else os.path.join(stems, "no_vocals.wav")
    bed(rest, orig, osr, tmp + "_bed.wav", a.bed_db if a.bed_db is not None else BED_DB[a.bed])
    graph = ("[0:a]aresample=48000[b];[1:a]aresample=48000," + HUM_FILTER + ",pan=stereo|c0=c0|c1=c0[v];"
             "[b][v]amix=inputs=2:normalize=0")
    mixed = [cfg.FFMPEG, "-hide_banner", "-i", tmp + "_bed.wav", "-i", os.path.join(a.out, "voice.wav"), "-filter_complex"]
    # linear loudness (one gain for the whole track): the dynamic loudnorm raised the noise in every pause
    err = subprocess.run(mixed + [graph + ",loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    ffmpeg(*mixed[2:], graph + (",loudnorm=I=-14:TP=-1:LRA=11:measured_I={input_i}:measured_TP={input_tp}:"
                                "measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}:"
                                "linear=true").format(**m),
           "-ar", "48000", os.path.join(a.out, "dub.wav"))
    ffmpeg("-ss", str(a.start), "-t", str(dur), "-i", a.film, "-i", os.path.join(a.out, "dub.wav"),
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-tag:v", "hvc1", "-c:a", "aac", "-b:a", "256k",
           "-movflags", "+faststart", os.path.join(a.out, "preview.mp4"))
    print("done:", os.path.join(a.out, "preview.mp4"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("subs"); g.add_argument("ref"); g.add_argument("out")
    g.add_argument("start", nargs="?", type=float, default=0.0); g.add_argument("end", nargs="?", type=float, default=1e9)
    g.add_argument("--takes", type=int, default=3); g.add_argument("--cfg", type=float, default=0.5)
    g.add_argument("--exag", type=float, default=0.5); g.add_argument("--lang", default="pl")
    g.add_argument("--engine", choices=["higgs", "chatterbox"], default=cfg.get("tts_engine") or "higgs")
    m = sub.add_parser("mix")
    m.add_argument("film"); m.add_argument("out")
    m.add_argument("start", nargs="?", type=float, default=0.0); m.add_argument("end", nargs="?", type=float, default=1e9)
    m.add_argument("--slow", type=float, default=1.0, help="slowest tempo, for a translation shorter than the original: 0.92 English, 0.94 Polish")
    m.add_argument("--bed", choices=["original", "separated"], default="original",
                   help="under the dub: the original track, voice kept (voice-over), or its sound without the voice")
    m.add_argument("--bed-db", type=float, help="how much quieter the bed is under the talk (default by --bed)")
    a = ap.parse_args()
    gen(a) if a.cmd == "gen" else mix(a)
