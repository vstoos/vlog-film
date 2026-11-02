"""New takes for the sentences that need them; run dub_check.py after it, and repeat if flags remain.

usage: python dub_regen.py <out_dir> <ref.wav> --lang pl [--takes 3] [--cfg 0.3] [--exag 0.8] [--dry]
A sentence gets new takes when its text changed (speakable differs from "say"; its old takes are
dropped) or when every take has flags (new takes join the old ones). Takes are named by subtitle time
and number, so a later run overwrites nothing. Edit "text" in manifest.json along with the .srt.
"""
import argparse
import json
import os

import dub
import vfconfig as cfg


def flagged(m, checks):
    return all(checks.get(f, {}).get("flags") for f in m["takes"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("ref")
    ap.add_argument("--takes", type=int, default=3); ap.add_argument("--cfg", type=float, default=0.3)
    ap.add_argument("--exag", type=float, default=0.8); ap.add_argument("--lang", default="pl")
    ap.add_argument("--dry", action="store_true", help="only list what would be regenerated")
    a = ap.parse_args()
    path = os.path.join(a.out, "manifest.json")
    man = json.load(open(path, encoding="utf-8"))
    checks_file = os.path.join(a.out, "checks.json")
    checks = json.load(open(checks_file, encoding="utf-8")) if os.path.exists(checks_file) else {}
    dub.load_say(a.out, a.lang)
    todo = [m for m in man if dub.speakable(m["text"], a.lang) != m["say"] or flagged(m, checks)]
    print(len(todo), "sentences to regenerate", flush=True)
    if a.dry or not todo:
        for m in todo:
            print("  %.1f  %s" % (m["start"], m["text"][:70]))
        return
    import torch
    import torchaudio as ta
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda:%d" % cfg.cuda_index())
    takes = os.path.join(a.out, "regen")
    os.makedirs(takes, exist_ok=True)
    for i, m in enumerate(todo):
        say = dub.speakable(m["text"], a.lang)
        if say != m["say"]:
            m["say"], m["takes"] = say, []
        stem = "%07d" % (m["start"] * 100)
        first = sum(n.startswith(stem) for n in os.listdir(takes))
        for k in range(first, first + a.takes):
            torch.manual_seed(5000 + 1000 * i + k)
            wav = model.generate(say, language_id=a.lang, audio_prompt_path=a.ref, cfg_weight=a.cfg, exaggeration=a.exag)
            f = os.path.join(takes, "%s_%d.wav" % (stem, k))
            ta.save(f, wav.cpu(), model.sr)
            m["takes"].append(f)
        print(i + 1, say[:80], flush=True)
        json.dump(man, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
