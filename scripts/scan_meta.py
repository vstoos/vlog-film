"""Collect time and GPS from every iPhone file (MOV via ffprobe tags, HEIC/PNG via EXIF).

usage: python scan_meta.py <footage_dir> <out.json>
Looks in the folder and one level of subfolders. Times are local with offset; lat/lon in degrees.
"""
import glob, json, os, re, subprocess, sys
from PIL import Image
import pillow_heif
pillow_heif.register_heif_opener()

SRC = sys.argv[1].replace("\\", "/")
rows = []
files = sorted(glob.glob(SRC + "/*.*") + glob.glob(SRC + "/*/*.*"))
for f in files:
    ext = os.path.splitext(f)[1].lower()
    r = {"file": os.path.relpath(f, SRC).replace("\\", "/")}
    if ext == ".mov":
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags", "-of", "json", f],
                           capture_output=True, text=True).stdout
        fm = json.loads(p).get("format", {})
        t = fm.get("tags", {})
        r["dur"] = round(float(fm.get("duration", 0)), 1)
        r["time"] = t.get("com.apple.quicktime.creationdate") or t.get("creation_time")
        loc = t.get("com.apple.quicktime.location.ISO6709")
        if loc:
            m = re.match(r"([+-][\d.]+)([+-][\d.]+)", loc)
            r["lat"], r["lon"] = float(m.group(1)), float(m.group(2))
    elif ext in (".heic", ".png", ".jpg"):
        try:
            im = Image.open(f)
            ex = im.getexif()
            r["size"] = im.size
            r["time"] = ex.get_ifd(0x8769).get(36867) or ex.get(306)
            g = ex.get_ifd(0x8825)
            if g and 2 in g:
                dms = lambda v: float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
                r["lat"] = dms(g[2]) * (-1 if g.get(1) == "S" else 1)
                r["lon"] = dms(g[4]) * (-1 if g.get(3) == "W" else 1)
        except Exception as e:
            r["err"] = str(e)
    else:
        continue
    rows.append(r)
    print(json.dumps(r, ensure_ascii=False))
json.dump(rows, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
