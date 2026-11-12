"""How a published film is doing: retention by film time, biggest drops, traffic, search terms.

Read only (YouTube Analytics API, uses the login from yt_upload.py, ~/.youtube/token_<channel>.json).
Analytics data lags 2-3 days behind YouTube Studio; run it a week after publishing.

    python yt_stats.py VIDEO_ID [--channel main] [--since 2026-11-09]

Map each drop to the edit with  python timeline.py film/<name>.mlt <mm:ss>.
"""
import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def mmss(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument("--channel", default="main")
    p.add_argument("--since", default="2020-01-01", help="start date, default: all time")
    p.add_argument("--drops", type=int, default=5)
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    tok = Path.home() / ".youtube" / f"token_{a.channel}.json"
    if not tok.exists():
        sys.exit(f"ERROR: no login for channel '{a.channel}'; run yt_upload.py auth --channel {a.channel}")
    creds = Credentials.from_authorized_user_file(str(tok))
    if not creds.valid:
        creds.refresh(Request())
        tok.write_text(creds.to_json(), encoding="utf-8")
    ya = build("youtubeAnalytics", "v2", credentials=creds)
    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()

    def q(**k):
        k.setdefault("filters", f"video=={a.video_id}")
        for attempt in range(5):  # the Analytics API answers 500 now and then
            try:
                return ya.reports().query(ids="channel==MINE", startDate=a.since, endDate=end,
                                          **k).execute().get("rows") or []
            except HttpError as e:
                if e.resp.status < 500 or attempt == 4:
                    raise
                time.sleep(2 ** attempt)

    tot = q(metrics="views,averageViewDuration,averageViewPercentage,subscribersGained,likes,comments")
    if not tot or not tot[0][0]:
        sys.exit("No analytics yet (data lags 2-3 days behind Studio), or not a video of this channel.")
    views, avd, avp, subs, likes, comments = tot[0]
    length = avd * 100 / avp if avp else 0
    print(f"Views {views}, average view {mmss(avd)} of ~{mmss(length)} ({avp:.0f}%), "
          f"subscribers +{subs}, likes {likes}, comments {comments}")

    curve = q(dimensions="elapsedVideoTimeRatio",
              metrics="audienceWatchRatio,relativeRetentionPerformance")
    if curve and length > 60:
        at = lambda t: min(curve, key=lambda r: abs(r[0] - t / length))
        print("\nStill watching (vs similar videos, 0.5 = average):")
        for t in (30, 60, 120, 300, 600, 900, 1200):
            if t < length:
                r = at(t)
                print(f"  {mmss(t):>6}  {r[1] * 100:3.0f}%   rel {r[2]:.2f}")
        drops = []
        for prev, cur in zip(curve, curve[1:]):
            if cur[0] * length > 45:              # the first 45 s fall for every video
                drops.append((prev[1] - cur[1], cur[0] * length, prev[0] * length))
        drops.sort(reverse=True)
        print(f"\nBiggest drops after 0:45 (film time; check with timeline.py):")
        for d, t, t0 in drops[:a.drops]:
            print(f"  {mmss(t0)}-{mmss(t)}  -{d * 100:.1f} pts")
        rel = [(r[2], r[0] * length) for r in curve if r[0] * length > 45]
        if rel:
            lo = min(rel)
            print(f"  weakest vs similar videos: {mmss(lo[1])} (rel {lo[0]:.2f})")

    src = q(dimensions="insightTrafficSourceType", metrics="views", sort="-views")
    s = sum(r[1] for r in src) or 1
    print("\nWhere viewers came from: " + ", ".join(f"{r[0]} {r[1] * 100 // s}%" for r in src[:6]))
    terms = q(dimensions="insightTrafficSourceDetail", metrics="views", sort="-views", maxResults=10,
              filters=f"video=={a.video_id};insightTrafficSourceType==YT_SEARCH")
    if terms:
        print("Search terms: " + ", ".join(f"{r[0]} ({r[1]})" for r in terms))
    try:
        geo = q(dimensions="country", metrics="views,averageViewPercentage", sort="-views")
        print("Countries (views, avg %): " + ", ".join(f"{r[0]} {r[1]} ({r[2]:.0f}%)" for r in geo[:4]))
    except Exception as e:  # the API sometimes answers 500 for small videos
        print(f"Countries: not available ({str(e)[:60]})")


if __name__ == "__main__":
    main()
