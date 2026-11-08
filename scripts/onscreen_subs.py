"""Put the film's on-screen texts, translated, into the subtitles of other languages.

A dubbed or subtitled viewer hears or reads the speech, but cards, the title, the end card and captions
stay in the film's language; under a card there is no voice, so they saw nothing they could read.
Each on-screen text becomes its own cue at its film time. Over speech the cue overlaps the speech cue and
is put in [brackets], so the two can be told apart (YouTube shows overlapping cues together).

  python onscreen_subs.py <project.py> list
      every text with its film time, and which have no translation yet
  python onscreen_subs.py <project.py> write <subs_dir_or_name_prefix> en pl ...
      writes <prefix>.<lang>.srt from <project>/subs/<NAME>.<lang>.speech.srt (saved from the current
      <prefix>.<lang>.srt on the first run), so running it again after a rebuild does not add cues twice

Texts come from the EDL (card, clip, end: items 5 and 6; photo: 4 and 5) and from an optional
onscreen() in project.py returning [(clip, from_s, to_s, [lines])] for captions burnt into a clip at
its own seconds (burn_in.py captions, captions baked into voice-over clips); they are mapped through
every cut of that clip in film/<FILM_NAME>.mlt. Translations: <project>/subs/onscreen.json,
{"<text>": {"en": "...", "pl": "..."}}, one entry per line of text. dub.py reads its manifest, not
these files, so the cues are never spoken.
"""
import importlib.util
import json
import os
import re
import shutil
import sys

import timeline


def load(path):
    spec = importlib.util.spec_from_file_location("project", path)
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    spec.loader.exec_module(m)
    return m


TEXT_AT = {"card": 5, "clip": 5, "end": 5, "photo": 4}


def texts(pr):
    """(start, end, [lines], over_speech) in film seconds."""
    ents, _ = timeline.entries("%s/%s.mlt" % (pr.OUT, pr.FILM_NAME))
    out = []
    items = [x for x in pr.EDL if x[0] in TEXT_AT]
    named = [e for e in ents if re.match(r"(card|clip|end|photo)\d\d_", e[1])]
    if len(items) != len(named):
        sys.exit("EDL has %d text items, the .mlt %d: rebuild the .mlt first" % (len(items), len(named)))
    for x, (pos, prod, i, o) in zip(items, named):
        k = TEXT_AT[x[0]]
        lines = [s for s in [x[k]] + x[k + 1].split("\n") if s.strip()]
        if lines:
            out.append((pos + 0.2, pos + (o - i) - 0.1, lines, False))
    for clip, a, b, lines in (pr.onscreen() if hasattr(pr, "onscreen") else []):
        merged = []
        for pos, prod, i, o in ents:
            s, e = max(a, i), min(b, o)
            if prod != clip or e - s <= 0.4:
                continue
            if merged and pos + s - i - merged[-1][1] < 0.3:
                merged[-1][1] = pos + e - i
            else:
                merged.append([pos + s - i, pos + e - i])
        out += [(s, e, list(lines), True) for s, e in merged]
    return sorted(out)


def ts(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def parse(path):
    cues = []
    for b in open(path, encoding="utf-8-sig").read().strip().split("\n\n"):
        ln = b.strip().split("\n")
        a, z = ln[1].split(" --> ")
        cues.append((timeline.secs(a.replace(",", ".")), timeline.secs(z.replace(",", ".")), "\n".join(ln[2:])))
    return cues


def main():
    pr = load(sys.argv[1])
    root = os.path.dirname(os.path.abspath(sys.argv[1]))
    tr_path = root + "/subs/onscreen.json"
    tr = json.load(open(tr_path, encoding="utf-8")) if os.path.exists(tr_path) else {}
    items = texts(pr)
    if sys.argv[2] == "list":
        for s, e, lines, sp in items:
            print("%s-%s %s %s" % (timeline.fmt(s), timeline.fmt(e), "speech" if sp else "      ", " / ".join(lines)))
        missing = sorted({x for _, _, lines, _ in items for x in lines if x not in tr})
        print("%d without a translation in %s%s" % (len(missing), tr_path, "".join("\n  " + x for x in missing)))
        return
    prefix = sys.argv[3]
    for lang in sys.argv[4:]:
        path = "%s.%s.srt" % (prefix, lang)
        keep = "%s/subs/%s.%s.speech.srt" % (root, os.path.basename(prefix), lang)
        if not os.path.exists(keep):
            shutil.copy(path, keep)
        cues = parse(keep)
        for s, e, lines, sp in items:
            t = [tr[x][lang] for x in lines]
            cues.append((s, e, "[%s]" % " - ".join(t) if sp else "\n".join(t)))
        cues.sort(key=lambda c: c[0])
        with open(path, "w", encoding="utf-8") as f:
            for n, (s, e, txt) in enumerate(cues, 1):
                f.write("%d\n%s --> %s\n%s\n\n" % (n, ts(s), ts(e), txt))
        print(lang, len(cues), "cues ->", path)


if __name__ == "__main__":
    main()
