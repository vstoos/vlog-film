"""Read-only home video server: browse folders of videos and play them in the browser, HDR included.

usage: python media_server.py [--port 8765] [--bind 0.0.0.0] [--lang uk|en] [folder ...]
  With no folders, serves the ones in config.json next to this file, or else ~/Videos.

Every subfolder becomes a page; video files get an HTML5 player and a download link. HTTP Range
is supported, so players can seek (Safari / iPhone will not play without it). Only files under the
configured folders are reachable (paths are resolved and checked), and nothing can be uploaded,
changed or deleted. HLG/HEVC files play in HDR in Safari (iPhone, iPad, Mac) and in Edge/Chrome on
Windows with HEVC hardware decoding.

Python standard library only. Meant for a home network or a private VPN such as Tailscale;
do not expose it to the internet: there is no login.
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
         ".mkv": "video/x-matroska"}
CHUNK = 1 << 20
TEXT = {
    "uk": {"home": "Відео", "all": "Усі папки", "empty": "Тут немає відео.", "files": "відео",
           "folders": "папок", "download": "Завантажити файл", "nf": "Не знайдено", "gb": "ГБ", "mb": "МБ",
           "back": "Назад"},
    "en": {"home": "Videos", "all": "All folders", "empty": "No videos here.", "files": "videos",
           "folders": "folders", "download": "Download", "nf": "Not found", "gb": "GB", "mb": "MB",
           "back": "Back"},
}

PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root {{ color-scheme: light dark; --bg:#f6f6f4; --fg:#1c1c1a; --mut:#6b6b66; --card:#fff; --line:#e2e2dc; --acc:#b4451f; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --fg:#ececea; --mut:#9a9a94; --card:#1f1f1d; --line:#2e2e2b; --acc:#e07a52; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.45 -apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:16px; }}
h1 {{ font-size:22px; margin:8px 0 16px; overflow-wrap:anywhere; }}
a {{ color:var(--acc); text-decoration:none; }}
ul {{ list-style:none; padding:0; margin:0; }}
li {{ background:var(--card); border:1px solid var(--line); border-radius:10px; margin:8px 0; }}
li a {{ display:block; padding:12px 14px; overflow-wrap:anywhere; }} .meta {{ color:var(--mut); font-size:13px; }}
li.dir a::before {{ content:"\\1F4C1  "; }}
video {{ width:100%; max-height:80vh; background:#000; border-radius:8px; }}
.crumbs {{ color:var(--mut); font-size:14px; overflow-wrap:anywhere; }}
</style></head><body><main>{body}</main></body></html>"""


def load_roots(args_folders):
    """[(key, title, absolute path)]: from the command line, else config.json, else ~/Videos."""
    roots = [{"path": f} for f in args_folders]
    if not roots:
        try:
            with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
                roots = json.load(f).get("folders", [])
        except (OSError, ValueError):
            roots = []
    if not roots:
        roots = [{"path": os.path.expanduser("~/Videos")}]
    out, seen = [], set()
    for r in roots:
        path = os.path.realpath(os.path.expanduser(r["path"]))
        title = r.get("title") or os.path.basename(path) or path
        # URL key from the folder name (titles may be in any script)
        key = re.sub(r"[^A-Za-z0-9_-]+", "-", r.get("key") or os.path.basename(path)).strip("-").lower() or "root"
        while key in seen:
            key += "-"
        seen.add(key)
        out.append((key, title, path))
    return out


class Handler(BaseHTTPRequestHandler):
    roots, t, lang, hide = [], TEXT["uk"], "uk", None

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # --- helpers -------------------------------------------------------------------------
    def send_page(self, title, body, code=200):
        data = PAGE.format(lang=self.lang, title=html.escape(title), body=body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def not_found(self):
        self.send_page(self.t["nf"], "<p>%s. <a href=\"/\">%s</a></p>" % (self.t["nf"], self.t["all"]), 404)

    def resolve(self, key, rel):
        """Absolute path for root key + relative parts, or None if it leaves the root."""
        root = next((r for r in self.roots if r[0] == key), None)
        if not root:
            return None, None
        full = os.path.realpath(os.path.join(root[2], *rel))
        if full != root[2] and not full.startswith(root[2] + os.sep):
            return None, None
        return root, full

    def visible(self, name):
        return not name.startswith(".") and not (self.hide and self.hide.search(name))

    def human(self, n):
        return "%.2f %s" % (n / 1e9, self.t["gb"]) if n > 1e9 else "%.0f %s" % (n / 1e6, self.t["mb"])

    def href(self, key, rel, *extra):
        return "/" + "/".join(urllib.parse.quote(p) for p in [key] + list(extra) + list(rel))

    # --- routes: /  /<key>/<dir...>  /<key>/play/<file...>  /<key>/file/<file...> ----------------
    def do_GET(self):
        parts = [urllib.parse.unquote(p) for p in urllib.parse.urlsplit(self.path).path.split("/") if p]
        if not parts:
            return self.index()
        mode, rel = "dir", parts[1:]
        if rel and rel[0] in ("play", "file"):
            mode, rel = rel[0], rel[1:]
        if any(p in ("..", ".") for p in rel):
            return self.not_found()
        root, full = self.resolve(parts[0], rel)
        if not root:
            return self.not_found()
        if mode == "dir" and os.path.isdir(full):
            return self.folder(root, rel, full)
        if mode in ("play", "file") and os.path.isfile(full) and os.path.splitext(full)[1].lower() in VIDEO \
                and self.visible(os.path.basename(full)):
            return self.player(root, rel) if mode == "play" else self.send_file(full)
        return self.not_found()

    do_HEAD = do_GET

    def index(self):
        items = []
        for key, title, path in self.roots:
            items.append('<li class="dir"><a href="/%s">%s<div class="meta">%s</div></a></li>'
                         % (urllib.parse.quote(key), html.escape(title), html.escape(path)))
        self.send_page(self.t["home"], "<h1>%s</h1><ul>%s</ul>" % (self.t["home"], "".join(items)))

    def folder(self, root, rel, full):
        dirs, files = [], []
        try:
            entries = list(os.scandir(full))
        except OSError:
            entries = []
        for e in entries:
            if not self.visible(e.name):
                continue
            if e.is_dir():
                dirs.append(e)
            elif os.path.splitext(e.name)[1].lower() in VIDEO:
                files.append(e)
        dirs.sort(key=lambda e: e.name.lower(), reverse=True)        # dated names: newest first
        files.sort(key=lambda e: -e.stat().st_mtime)
        rows = ['<li class="dir"><a href="%s">%s</a></li>' % (self.href(root[0], rel + [d.name]), html.escape(d.name))
                for d in dirs]
        for f in files:
            st = f.stat()
            rows.append('<li><a href="%s">%s<div class="meta">%s · %s</div></a></li>'
                        % (self.href(root[0], rel + [f.name], "play"), html.escape(f.name), self.human(st.st_size),
                           datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M")))
        crumbs = ['<a href="/">%s</a>' % self.t["all"], '<a href="/%s">%s</a>' % (root[0], html.escape(root[1]))]
        for i, p in enumerate(rel):
            crumbs.append('<a href="%s">%s</a>' % (self.href(root[0], rel[:i + 1]), html.escape(p)))
        title = rel[-1] if rel else root[1]
        body = '<p class="crumbs">%s</p><h1>%s</h1><ul>%s</ul>' % (
            " / ".join(crumbs), html.escape(title), "".join(rows) or "<p>%s</p>" % self.t["empty"])
        self.send_page(title, body)

    def player(self, root, rel):
        src = self.href(root[0], rel, "file")
        body = ('<p class="crumbs"><a href="%s">&larr; %s</a></p><h1>%s</h1>'
                '<video controls playsinline preload="metadata" src="%s"></video>'
                '<p class="meta"><a href="%s" download>%s</a></p>'
                % (self.href(root[0], rel[:-1]), html.escape(rel[-2] if len(rel) > 1 else root[1]),
                   html.escape(rel[-1]), src, src, self.t["download"]))
        self.send_page(rel[-1], body)

    def send_file(self, fpath):
        size = os.path.getsize(fpath)
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        else:
            self.send_response(200)
        self.send_header("Content-Type", VIDEO.get(os.path.splitext(fpath)[1].lower(), "application/octet-stream"))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(fpath, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    buf = f.read(min(CHUNK, left))
                    if not buf:
                        break
                    self.wfile.write(buf)
                    left -= len(buf)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # players drop connections when seeking


def main():
    if sys.stdout is None or sys.stderr is None:      # pythonw (no console): log to a file instead
        log = open(os.path.join(HERE, "media_server.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    ap = argparse.ArgumentParser(description="Read-only home video server")
    ap.add_argument("folders", nargs="*", help="folders to serve (default: config.json, else ~/Videos)")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--bind", default=None, help="address to listen on (default 0.0.0.0: all interfaces)")
    ap.add_argument("--lang", choices=sorted(TEXT), default=None)
    a = ap.parse_args()
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    Handler.roots = load_roots(a.folders)
    Handler.lang = a.lang or cfg.get("lang", "uk")
    Handler.t = TEXT[Handler.lang]
    if cfg.get("hide"):
        Handler.hide = re.compile(cfg["hide"], re.I)     # e.g. "_raw\\.|^x_" to skip intermediate renders
    port, bind = a.port or cfg.get("port", 8765), a.bind or cfg.get("bind", "0.0.0.0")
    ThreadingHTTPServer.daemon_threads = True
    for key, title, path in Handler.roots:
        print("  /%-20s %s" % (key, path))
    print("serving on http://%s:%d" % (bind, port))
    ThreadingHTTPServer((bind, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
