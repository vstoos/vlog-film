"""Map film time <-> source clip time from the built .mlt.

usage: python timeline.py <film.mlt>              block starts and inserts with film times (for chapters)
       python timeline.py <film.mlt> 12:22 9:30   which clip and source second plays at those film times

Use the second form whenever the viewer reports a problem "at 12:22": it names the clip and the
second in the original file, so the fix goes into the EDL and not into a guess.
"""
import re
import sys


def secs(t):
    parts = [float(p) for p in t.split(":")]
    v = 0.0
    for p in parts:
        v = v * 60 + p
    return v


def entries(path):
    x = open(path, encoding="utf-8").read()
    pl = x[x.index('<playlist id="playlist0"'):]
    pl = pl[:pl.index("</playlist>")]
    fps = 30.0
    m = re.search(r'frame_rate_num="(\d+)" frame_rate_den="(\d+)"', x)
    if m:
        fps = int(m.group(1)) / int(m.group(2))
    pos, out = 0.0, []
    for m in re.finditer(r"<(entry|blank)([^>]*)>", pl):
        a = m.group(2)
        if m.group(1) == "blank":
            pos += secs(re.search(r'length="([^"]+)"', a).group(1))
            continue
        prod = re.search(r'producer="([^"]+)"', a).group(1)
        i = secs(re.search(r'in="([^"]+)"', a).group(1))
        o = secs(re.search(r'out="([^"]+)"', a).group(1))
        out.append((pos, prod, i, o))
        pos += o - i + 1 / fps
    return out, pos


def fmt(t):
    return "%d:%05.2f" % (t // 60, t % 60)


if __name__ == "__main__":
    ents, total = entries(sys.argv[1])
    if len(sys.argv) > 2:
        for q in sys.argv[2:]:
            t = secs(q)
            for k, (pos, prod, i, o) in enumerate(ents):
                if pos <= t < pos + (o - i):
                    print("%s  %-28s source %.2f s   (entry %.2f-%.2f, starts at %s)"
                          % (q, prod, i + t - pos, i, o, fmt(pos)))
                    for p2, pr2, i2, o2 in ents[max(0, k - 1):k + 2]:
                        print("        %s %-28s %.2f-%.2f" % (fmt(p2), pr2, i2, o2))
                    break
    else:
        prev = None
        for pos, prod, i, o in ents:
            talk = not re.match(r"^(road|roads|card|photo|clip|anim|end)\d", prod)
            if not talk or prev != "talk":
                print("%s  %s %.1f" % (fmt(pos), prod, i))
            prev = "talk" if talk else "insert"
        print("end %s" % fmt(total))
