"""YouTube uploader: video, thumbnail, subtitles, translated titles/descriptions.

Secrets live in %USERPROFILE%\\.youtube\\ (never in the Videos folder):
    client_secret.json  - OAuth "Desktop app" client downloaded from Google Cloud
    token_<channel>.json - one per YouTube channel, created on first login
                           (--channel main | pl | ua ...; default "main")

Usage examples (PowerShell or git-bash):
    python yt_upload.py auth --channel pl
        One-time login in the browser for that channel; prints its real name.
        Every other command takes the same --channel (default: main).

    python yt_upload.py upload "film.mp4" --title "My trip" --desc desc.txt \
        --thumb thumb.jpg --sub uk=film.uk.srt --sub en=film.en.srt \
        --loc en="Title EN|desc.en.txt" --lang uk --tags "Tesla,EV,trip"
        Uploads as PRIVATE by default (use --privacy public|unlisted or
        --publish-at 2026-11-20T18:00:00Z to schedule).

    python yt_upload.py captions VIDEO_ID --sub pl=film.pl.srt
    python yt_upload.py thumb VIDEO_ID thumb.jpg
    python yt_upload.py loc VIDEO_ID --loc en="Title EN|desc.en.txt"

Add --dry-run to any command to only check files, without touching YouTube.

Dubbed audio tracks cannot be uploaded through the YouTube API; add them in
YouTube Studio -> Languages.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

SECRETS_DIR = Path.home() / ".youtube"
CLIENT_SECRET = SECRETS_DIR / "client_secret.json"
CHANNEL = "main"  # set from --channel in main()
SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",       # upload, captions, thumbnails
    "https://www.googleapis.com/auth/yt-analytics.readonly",   # read channel statistics
]

CATEGORY_AUTOS = "2"  # Autos & Vehicles
RETRY_STATUS = {500, 502, 503, 504}


def log(msg):
    print(msg, flush=True)


def win_path(s):
    """git-bash style /c/Data/x -> C:/Data/x (Windows Python does not understand the former)."""
    m = re.match(r"^/([a-zA-Z])/(.*)$", s)
    return f"{m.group(1).upper()}:/{m.group(2)}" if m else s


def read_text(path_or_text):
    """A value may be a path to a .txt/.md file or the text itself.

    A value that ends in .txt/.md is always taken as a path: if the file is missing the script stops,
    so a path never goes up to YouTube as the description (it did on 12.11.2026: a /c/... path from
    git-bash was not found and became the EN description of the Mercedes film).
    """
    if path_or_text is None:
        return None
    s = path_or_text.strip()
    p = Path(win_path(s))
    if p.suffix.lower() in (".txt", ".md"):
        if not p.is_file():
            sys.exit(f"ERROR: description file not found: {s}")
        return p.read_text(encoding="utf-8").strip()
    return path_or_text


def parse_pairs(items, what):
    out = {}
    for item in items or []:
        if "=" not in item:
            sys.exit(f"ERROR: {what} must look like lang=value, got: {item}")
        lang, val = item.split("=", 1)
        val = val.strip()
        # drop only a pair of wrapping quotes: a title like '"Tesla is noisy"? Listen' keeps its own
        if len(val) >= 2 and val[0] == val[-1] == '"' and val.count('"') == 2:
            val = val[1:-1]
        out[lang.strip()] = win_path(val) if what == "--sub" else val
    return out


def parse_locs(items):
    """--loc en="Title|desc.txt" -> {"en": {"title": ..., "description": ...}}"""
    out = {}
    for lang, val in parse_pairs(items, "--loc").items():
        title, _, desc = val.partition("|")
        out[lang] = {"title": title.strip(), "description": read_text(desc.strip()) or ""}
    return out


def check_files(paths):
    missing = [str(p) for p in paths if p and not Path(p).is_file()]
    if missing:
        sys.exit("ERROR: file(s) not found:\n  " + "\n  ".join(missing))


class NoDelete:
    """Safety guard around the YouTube client: any delete call is refused.

    The OAuth permission Google gives for subtitles is the broad "manage your
    channel" one, which would technically allow deleting videos. This wrapper
    makes sure this script can never do that, even by mistake.
    """

    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        if "delete" in name.lower():
            raise PermissionError(f"BLOCKED: '{name}' is not allowed - this tool never deletes anything")
        attr = getattr(self._obj, name)
        if not callable(attr):
            return attr

        def call(*a, **k):
            from googleapiclient.discovery import Resource
            res = attr(*a, **k)
            return NoDelete(res) if isinstance(res, Resource) else res
        return call


def token_path():
    return SECRETS_DIR / f"token_{CHANNEL}.json"


def service():
    return NoDelete(_raw_service())


def channel_name(yt):
    me = yt.channels().list(part="snippet", mine=True).execute()
    items = me.get("items", [])
    return (items[0]["snippet"]["title"], items[0]["id"]) if items else (None, None)


def _raw_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    TOKEN = token_path()
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    else:
        log(f"No login yet for channel '{CHANNEL}' - opening the browser. "
            "Pick the right channel there.")
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:  # refresh token expired/revoked
                log(f"Token refresh failed ({e}); logging in again.")
                creds = None
        if not creds or not creds.valid:
            if not CLIENT_SECRET.exists():
                sys.exit(f"ERROR: put the OAuth JSON file at {CLIENT_SECRET}")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        SECRETS_DIR.mkdir(exist_ok=True)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def resumable(request, label):
    from googleapiclient.errors import HttpError

    response, tries = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                log(f"  {label}: {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in RETRY_STATUS and tries < 8:
                tries += 1
                wait = 2 ** tries
                log(f"  server error {e.resp.status}, retry in {wait}s")
                time.sleep(wait)
            else:
                raise
        except (ConnectionError, TimeoutError, OSError) as e:
            if tries < 8:
                tries += 1
                wait = 2 ** tries
                log(f"  network error ({e}), retry in {wait}s")
                time.sleep(wait)
            else:
                raise
    return response


def do_thumb(yt, video_id, thumb):
    from googleapiclient.http import MediaFileUpload

    yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumb)).execute()
    log(f"  thumbnail set: {thumb}")


def do_captions(yt, video_id, subs):
    from googleapiclient.http import MediaFileUpload

    for lang, path in subs.items():
        body = {"snippet": {"videoId": video_id, "language": lang, "name": ""}}
        media = MediaFileUpload(path, mimetype="application/octet-stream", resumable=False)
        yt.captions().insert(part="snippet", body=body, media_body=media).execute()
        log(f"  subtitles {lang}: {path}")


def do_locs(yt, video_id, locs, default_lang=None):
    vid = yt.videos().list(part="snippet,localizations", id=video_id).execute()
    if not vid.get("items"):
        sys.exit(f"ERROR: video {video_id} not found on your channel")
    item = vid["items"][0]
    snippet = item["snippet"]
    if default_lang:
        snippet["defaultLanguage"] = default_lang
    if not snippet.get("defaultLanguage"):
        sys.exit("ERROR: translations need the video's own language; pass --lang uk")
    merged = item.get("localizations", {})
    merged.update(locs)
    body = {
        "id": video_id,
        "snippet": {k: snippet[k] for k in
                    ("title", "description", "categoryId", "defaultLanguage",
                     "defaultAudioLanguage", "tags")
                    if k in snippet},
        "localizations": merged,
    }
    yt.videos().update(part="snippet,localizations", body=body).execute()
    log(f"  translated title/description: {', '.join(locs)}")


def cmd_auth(args):
    if args.dry_run:
        state = "saved" if token_path().exists() else "NOT logged in yet"
        log(f"DRY RUN: channel '{CHANNEL}' login is {state}")
        return
    yt = service()
    title, cid = channel_name(yt)
    if title:
        log(f"OK, '{CHANNEL}' is logged in as channel: {title}  (id {cid})")
    else:
        log("Logged in, but this Google account has no YouTube channel.")


def cmd_upload(args):
    from googleapiclient.http import MediaFileUpload

    subs = parse_pairs(args.sub, "--sub")
    locs = parse_locs(args.loc)
    check_files([args.video, args.thumb, *subs.values()])
    description = read_text(args.desc) or ""
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    status = {
        "privacyStatus": "private" if args.publish_at else args.privacy,
        "selfDeclaredMadeForKids": False,
    }
    if args.publish_at:
        status["publishAt"] = args.publish_at
    snippet = {"title": args.title, "description": description, "tags": tags,
               "categoryId": args.category}
    if args.lang:
        snippet["defaultLanguage"] = args.lang
        snippet["defaultAudioLanguage"] = args.lang
    body = {"snippet": snippet, "status": status}
    if locs:
        if not args.lang:
            sys.exit("ERROR: --loc needs --lang (the film's own language)")
        body["localizations"] = locs

    size_mb = Path(args.video).stat().st_size / 1e6
    log(f"Video: {args.video} ({size_mb:.0f} MB)")
    log(f"Title: {args.title}")
    log(f"Privacy: {status['privacyStatus']}" + (f", publish at {args.publish_at}" if args.publish_at else ""))
    log(f"Subtitles: {', '.join(subs) or '-'}   Translations: {', '.join(locs) or '-'}")
    if args.dry_run:
        log("DRY RUN: all files found, nothing uploaded.")
        return

    yt = service()
    title, _ = channel_name(yt)
    log(f"Channel: {title}  (--channel {CHANNEL})")
    parts = "snippet,status" + (",localizations" if locs else "")
    media = MediaFileUpload(args.video, chunksize=64 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part=parts, body=body, media_body=media)
    resp = resumable(req, "upload")
    vid = resp["id"]
    log(f"Uploaded: https://youtu.be/{vid}")
    log(f"Studio:   https://studio.youtube.com/video/{vid}/edit")
    if args.thumb:
        do_thumb(yt, vid, args.thumb)
    if subs:
        do_captions(yt, vid, subs)
    Path(args.video).with_suffix(".youtube.json").write_text(
        json.dumps({"id": vid, "url": f"https://youtu.be/{vid}"}, indent=2), encoding="utf-8")
    log("Done. Reminder: dubbed audio tracks are added in YouTube Studio -> Languages.")


def cmd_captions(args):
    subs = parse_pairs(args.sub, "--sub")
    check_files(subs.values())
    if args.dry_run:
        log(f"DRY RUN: would add subtitles {', '.join(subs)} to {args.video_id}")
        return
    do_captions(service(), args.video_id, subs)


def cmd_thumb(args):
    check_files([args.image])
    if args.dry_run:
        log(f"DRY RUN: would set thumbnail {args.image} on {args.video_id}")
        return
    do_thumb(service(), args.video_id, args.image)


def cmd_loc(args):
    locs = parse_locs(args.loc)
    if args.dry_run:
        log(f"DRY RUN: would set translations {', '.join(locs)} on {args.video_id}")
        return
    do_locs(service(), args.video_id, locs, args.lang)


def main():
    p = argparse.ArgumentParser(description="Upload videos, thumbnails and subtitles to YouTube.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("auth", help="log in once and show the channel")
    a.set_defaults(fn=cmd_auth)

    u = sub.add_parser("upload", help="upload a video")
    u.add_argument("video")
    u.add_argument("--title", required=True)
    u.add_argument("--desc", help="description text or a .txt file (chapters go here)")
    u.add_argument("--tags", help="comma separated")
    u.add_argument("--thumb", help="thumbnail image (jpg/png, under 2 MB)")
    u.add_argument("--sub", action="append", help="lang=file.srt, repeatable")
    u.add_argument("--loc", action="append", help='lang="Title|desc.txt", repeatable')
    u.add_argument("--lang", help="film language code, e.g. uk")
    u.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    u.add_argument("--publish-at", help="schedule, ISO time e.g. 2026-11-20T18:00:00Z")
    u.add_argument("--category", default=CATEGORY_AUTOS)
    u.set_defaults(fn=cmd_upload)

    c = sub.add_parser("captions", help="add subtitles to an uploaded video")
    c.add_argument("video_id")
    c.add_argument("--sub", action="append", required=True)
    c.set_defaults(fn=cmd_captions)

    t = sub.add_parser("thumb", help="set thumbnail")
    t.add_argument("video_id")
    t.add_argument("image")
    t.set_defaults(fn=cmd_thumb)

    l = sub.add_parser("loc", help="add translated titles/descriptions")
    l.add_argument("video_id")
    l.add_argument("--loc", action="append", required=True)
    l.add_argument("--lang", help="film language, if not set on the video yet")
    l.set_defaults(fn=cmd_loc)

    for sp in (a, u, c, t, l):
        sp.add_argument("--dry-run", action="store_true")
        sp.add_argument("--channel", default="main",
                        help="which saved channel login to use (main, pl, ua ...)")

    args = p.parse_args()
    global CHANNEL
    CHANNEL = args.channel
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args.fn(args)


if __name__ == "__main__":
    main()
