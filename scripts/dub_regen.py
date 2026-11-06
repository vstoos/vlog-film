"""New takes for the sentences that need them; run dub_check.py after it, and repeat if flags remain.

usage: python dub_regen.py <out_dir> <ref.wav|-> --lang pl [--takes 3] [--engine higgs|chatterbox] [--dry]
("-" is the saved voice for the language, as in dub.py gen; --cfg / --exag are Chatterbox's)
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
    ap.add_argument("--engine", choices=["higgs", "chatterbox"], default=cfg.get("tts_engine") or "higgs")
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
    takes = os.path.join(a.out, "regen")
    os.makedirs(takes, exist_ok=True)
    jobs = []
    for i, m in enumerate(todo):
        say = dub.speakable(m["text"], a.lang)
        if say != m["say"]:
            m["say"], m["takes"] = say, []
        stem = "%07d" % (m["start"] * 100)
        first = sum(n.startswith(stem) for n in os.listdir(takes))
        for k in range(first, first + a.takes):
            f = os.path.join(takes, "%s_%d.wav" % (stem, k))
            # take number k picks the seed, so a later round never repeats an earlier take
            jobs.append((say, f, 5000 + 1000 * i + k if a.engine == "chatterbox" else 100 + k))
            m["takes"].append(f)
    dub.synth(jobs, a.lang, a.ref, a.engine, a.cfg, a.exag)
    json.dump(man, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(jobs), "new takes", flush=True)


if __name__ == "__main__":
    main()
