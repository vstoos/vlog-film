"""WhisperX words for a short audio window, to check a cut by ear-level evidence.

usage: python transcribe_window.py <clip.wav> <offset_s> [language]
Prints every word with its time, shifted by offset_s (the window start in the film or clip).
"""
import os, sys
import torch
import vfconfig as vf

vf.torch_dlls()
import whisperx
off = float(sys.argv[2])
LANG = sys.argv[3] if len(sys.argv) > 3 else vf.LANGUAGE
gpu = vf.cuda_index()
model = whisperx.load_model(vf.WHISPER_MODEL, "cuda", device_index=gpu, compute_type="float16", language=LANG)
am, meta = whisperx.load_align_model(language_code=LANG, device="cuda:%d" % gpu)
audio = whisperx.load_audio(sys.argv[1])
res = whisperx.align(model.transcribe(audio, batch_size=8, language=LANG)["segments"], am, meta, audio, "cuda:%d" % gpu)
for s in res["segments"]:
    print(" ".join("%s[%.2f-%.2f]" % (w["word"], w.get("start", -1) + off, w.get("end", -1) + off) for w in s["words"]))
