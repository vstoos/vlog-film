"""Post the channel's own comment under each video once it is public; the user pins it by hand.

Pinning is not possible through the YouTube API, so the script writes a checklist for the phone.
It never deletes or edits a comment (yt_upload.service() refuses every delete method).

    python yt_comment.py [--plan <dir>/comments.json] [--dry-run]

comments.json: {"comments": [{"date": "2026-11-14", "label": "...", "video": "<id>" | "mp4": "<file>",
"text": "..."}]}; "mp4" takes the id from the <file>.youtube.json that yt_upload.py writes.
Next to it the script keeps posted.json (video id -> comment id; a video is never commented twice,
and a comment of the channel already under the video with the same first line counts as posted) and
writes checklist.md. Cost: 50 quota units per comment, 1 per check. Run daily after the 17:00 releases.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import yt_upload  # noqa: E402

DEFAULT_PLAN = Path.home() / "Videos" / "YouTube_comments" / "comments.json"


def video_id(entry):
    if entry.get("video"):
        return entry["video"]
    meta = Path(entry["mp4"]).with_suffix(".youtube.json")
    if meta.is_file():
        data = json.loads(meta.read_text(encoding="utf-8"))
        return data.get("id") or data.get("video_id") or data.get("videoId")
    return None


def first_line(text):
    return text.strip().splitlines()[0].strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", default=str(DEFAULT_PLAN))
    p.add_argument("--channel", default="main")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    yt_upload.CHANNEL = a.channel

    plan_path = Path(a.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    state_path = plan_path.with_name("posted.json")
    posted = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    entries = sorted(plan["comments"], key=lambda e: e["date"])
    for e in entries:
        e["id"] = video_id(e)
    ids = [e["id"] for e in entries if e["id"] and e["id"] not in posted]

    yt = yt_upload.service()
    status = {}
    stopped = None
    try:
        for i in range(0, len(ids), 50):
            r = yt.videos().list(part="status", id=",".join(ids[i:i + 50])).execute()
            for it in r.get("items", []):
                status[it["id"]] = it["status"]["privacyStatus"]
    except Exception as ex:  # quota used up by the morning uploads: just the checklist this time
        stopped = str(ex)[:200]
        print(f"STOPPED before posting: {stopped}")
    me = None

    for e in entries:
        vid = e["id"]
        if not vid or vid in posted or status.get(vid) != "public" or stopped:
            continue
        if me is None:
            me = yt.channels().list(part="id", mine=True).execute()["items"][0]["id"]
        # a comment of ours already there (state file lost, posted by hand) counts as posted
        r = yt.commentThreads().list(part="snippet", videoId=vid, maxResults=100,
                                     textFormat="plainText").execute()
        mine = [t for t in r.get("items", [])
                if t["snippet"]["topLevelComment"]["snippet"].get("authorChannelId", {}).get("value") == me
                and first_line(t["snippet"]["topLevelComment"]["snippet"]["textDisplay"]) == first_line(e["text"])]
        if mine:
            posted[vid] = {"comment": mine[0]["id"], "date": dt.date.today().isoformat(), "found": True}
            print(f"FOUND (already there): {e['label']}")
            continue
        if a.dry_run:
            print(f"DRY RUN would post under {vid} ({e['label']}):\n  " + e["text"].replace("\n", "\n  "))
            continue
        try:
            c = yt.commentThreads().insert(part="snippet", body={"snippet": {
                "videoId": vid, "topLevelComment": {"snippet": {"textOriginal": e["text"]}}}}).execute()
        except Exception as ex:  # quota or a closed comment section: try again next run
            stopped = str(ex)[:200]
            print(f"STOPPED at {e['label']}: {stopped}")
            continue
        posted[vid] = {"comment": c["id"], "date": dt.date.today().isoformat()}
        print(f"POSTED: {e['label']} https://youtu.be/{vid}")
        state_path.write_text(json.dumps(posted, ensure_ascii=False, indent=1), encoding="utf-8")

    if not a.dry_run:
        state_path.write_text(json.dumps(posted, ensure_ascii=False, indent=1), encoding="utf-8")

    # checklist for the phone
    today = dt.date.today().isoformat()
    lines = ["# Закріпити коментарі", "",
             f"Оновлено {dt.datetime.now():%d.%m %H:%M}. Скрипт сам публікує коментар, коли відео стає",
             "публічним (щодня о 17:20). Ваше: відкрити відео в YouTube (або Studio > Коментарі),",
             "біля свого коментаря меню (три крапки) > Закріпити. Після цього можна поставити [x].", ""]
    for e in entries:
        vid, d = e["id"], e["date"]
        if vid in posted:
            mark = f"[ ] **закріпити** (опубліковано {posted[vid]['date']})"
        elif d <= today and vid:
            mark = "чекає (відео ще не публічне або квота)"
        else:
            mark = "ще не вийшло"
        link = f"https://youtu.be/{vid}" if vid else "(ще не завантажено)"
        lines.append(f"- {d[8:10]}.{d[5:7]} {e['label']}: {mark}  \n  {link}")
    plan_path.with_name("checklist.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Checklist: {plan_path.with_name('checklist.md')}")


if __name__ == "__main__":
    main()
