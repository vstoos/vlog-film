"""Transcribe every talking clip with WhisperX large-v3 (Ukrainian) + word alignment.

usage: python transcribe_all.py <clips_dir> <out_dir> [language, default uk]
Writes <out_dir>/<clip>.json with segments and per-word start/end times.
Clips that already have a JSON are skipped, so the run can be resumed.
"""
import glob
import json
import os
import sys
import time

os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")

import torch

import vfconfig as vf

vf.torch_dlls()

import whisperx

clips_dir, out_dir = sys.argv[1], sys.argv[2]
LANG = sys.argv[3] if len(sys.argv) > 3 else vf.LANGUAGE
os.makedirs(out_dir, exist_ok=True)
gpu = vf.cuda_index()
dev = "cuda:%d" % gpu

model = whisperx.load_model(vf.WHISPER_MODEL, "cuda", device_index=gpu, compute_type="float16", language=LANG)
align_model, meta = whisperx.load_align_model(language_code=LANG, device=dev)

clips = sorted(glob.glob(os.path.join(clips_dir, "*.MOV")) + glob.glob(os.path.join(clips_dir, "*.mov")))
clips = sorted(set(clips))
for path in clips:
    name = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(out_dir, name + ".json")
    if os.path.exists(out):
        continue
    t = time.time()
    audio = whisperx.load_audio(path)
    res = model.transcribe(audio, batch_size=16, language=LANG)
    res = whisperx.align(res["segments"], align_model, meta, audio, dev)
    segments = [{
        "start": s.get("start"), "end": s.get("end"), "text": s["text"].strip(),
        "words": [{"w": w["word"], "s": w.get("start"), "e": w.get("end"), "p": w.get("score")}
                  for w in s.get("words", [])],
    } for s in res["segments"]]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"clip": os.path.basename(path), "duration": len(audio) / 16000, "segments": segments},
                  f, ensure_ascii=False, indent=1)
    print("%s: %.0fs audio in %.0fs, %d segments" % (name, len(audio) / 16000, time.time() - t, len(segments)),
          flush=True)
print("done")
