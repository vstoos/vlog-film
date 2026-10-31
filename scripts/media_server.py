"""Read-only video server for the LAN and the tailnet: a page per folder with an HTML5 player.

usage: python media_server.py [port]      (default 8765, listens on all interfaces)

Serves only video files from the folders in SECTIONS, with HTTP Range so players can seek
(Safari/iPhone will not play without it). Nothing outside those folders is reachable.
HLG/HEVC files play in HDR in Safari (iPhone, Mac) and in Edge/Chrome on Windows with HEVC
hardware decoding.
"""
import html
import os
import re
import sys
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# (key, title, folder, file filter); key becomes the URL prefix
# usage adds folders: python media_server.py [port] [footage_dir] [film_dir]
_ARGS = sys.argv[2:4] + [None, None]
SECTIONS = [s for s in [
    ("final", "Готові фільми", _ARGS[0], r"\.mp4$"),
    ("work", "Робочі рендери", _ARGS[1], r"^(?!.*_raw\.)(?!x_).*\.(mp4|mov)$"),
    ("clips", "Вихідні кліпи iPhone", _ARGS[0], r"\.mov$"),
] if s[2]]
TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime"}
CHUNK = 1 << 20

PAGE = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root {{ color-scheme: light dark; --bg:#f6f6f4; --fg:#1c1c1a; --mut:#6b6b66; --card:#fff; --line:#e2e2dc; --acc:#b4451f; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --fg:#ececea; --mut:#9a9a94; --card:#1f1f1d; --line:#2e2e2b; --acc:#e07a52; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.45 -apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:16px; }}
h1 {{ font-size:22px; margin:8px 0 16px; }} h2 {{ font-size:17px; margin:24px 0 8px; }}
a {{ color:var(--acc); text-decoration:none; }}
ul {{ list-style:none; padding:0; margin:0; }}
li {{ background:var(--card); border:1px solid var(--line); border-radius:10px; margin:8px 0; }}
li a {{ display:block; padding:12px 14px; }} .meta {{ color:var(--mut); font-size:13px; }}
video {{ width:100%; max-height:80vh; background:#000; border-radius:8px; }}
</style></head><body><main>{body}</main></body></html>"""


def section(key):
    for s in SECTIONS:
        if s[0] == key:
            return s
    return None


def listing(sec):
    _, _, folder, pattern = sec
    rx = re.compile(pattern, re.I)
    try:
        names = [n for n in os.listdir(folder) if rx.search(n) and os.path.isfile(os.path.join(folder, n))]
    except OSError:
        return []
    return sorted(names, key=lambda n: -os.path.getmtime(os.path.join(folder, n)))


def human(n):
    return "%.2f ГБ" % (n / 1e9) if n > 1e9 else "%.0f МБ" % (n / 1e6)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def send_page(self, title, body, code=200):
        data = PAGE.format(title=html.escape(title), body=body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        parts = [p for p in path.split("/") if p]
        if not parts:
            return self.index()
        sec = section(parts[0])
        if not sec:
            return self.send_page("Немає", "<p>Немає такої сторінки.</p>", 404)
        if len(parts) == 1:
            return self.folder(sec)
        name = parts[-1]
        if len(parts) != 3 or parts[1] not in ("play", "file") or name not in listing(sec):
            return self.send_page("Немає", "<p>Файл не знайдено.</p>", 404)
        if parts[1] == "play":
            return self.player(sec, name)
        return self.send_file(os.path.join(sec[2], name))

    do_HEAD = do_GET

    def index(self):
        items = "".join('<li><a href="/%s">%s</a><div class="meta" style="padding:0 14px 10px">%d файлів</div></li>'
                        % (k, html.escape(t), len(listing((k, t, f, p)))) for k, t, f, p in SECTIONS)
        self.send_page("Відео", "<h1>Відео</h1><ul>%s</ul>" % items)

    def folder(self, sec):
        key, title, folder, _ = sec
        rows = []
        for n in listing(sec):
            st = os.stat(os.path.join(folder, n))
            rows.append('<li><a href="/%s/play/%s">%s<div class="meta">%s · %s</div></a></li>'
                        % (key, urllib.parse.quote(n), html.escape(n), human(st.st_size),
                           datetime.fromtimestamp(st.st_mtime).strftime("%d.%m %H:%M")))
        body = '<p><a href="/">&larr; Усі розділи</a></p><h1>%s</h1><ul>%s</ul>' % (
            html.escape(title), "".join(rows) or "<p>Порожньо.</p>")
        self.send_page(title, body)

    def player(self, sec, name):
        src = "/%s/file/%s" % (sec[0], urllib.parse.quote(name))
        body = ('<p><a href="/%s">&larr; %s</a></p><h1>%s</h1>'
                '<video controls playsinline preload="metadata" src="%s"></video>'
                '<p class="meta"><a href="%s" download>Завантажити файл</a></p>'
                % (sec[0], html.escape(sec[1]), html.escape(name), src, src))
        self.send_page(name, body)

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
        self.send_header("Content-Type", TYPES.get(os.path.splitext(fpath)[1].lower(), "application/octet-stream"))
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


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    ThreadingHTTPServer.daemon_threads = True
    print("serving on port %d" % port)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
