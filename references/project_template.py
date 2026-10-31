"""Project file for filmkit.py: copy to C:/Data/<name>-video/project.py and fill in.

build: python <skill>/scripts/filmkit.py C:/Data/<name>-video/project.py [--no-media]

Every UPPER_CASE name here overrides filmkit's default; roll_for() and make_stills() are optional.
A finished, working example of all of this: example_yaris.py.
"""
import subprocess

# --- paths ----------------------------------------------------------------------
SRC = "C:/Users/<you>/Videos/<date>_<name>"          # footage folder (iPhone clips IMG_xxxx.MOV, photos .HEIC)
OUT = "C:/Data/<name>-video/film"                     # rendered inserts, blurred clips, the .mlt
TRANSCRIPTS = "C:/Data/<name>-video/transcripts"      # <clip>.json from transcribe_all.py
MUSIC_DIR = "C:/Users/<you>/Music"
ROAD_FILE = "{src}/Road/{clip}_fast.mp4"              # dash-cam footage; {clip} is e.g. MAH04457
FILM_NAME = "<name>"                                  # -> OUT/<name>.mlt, render_final.py <film> <name> ...
FILM_TITLE = "<Name>"

# --- tuning (defaults shown; delete what you do not change) ---------------------
# GAP_CUT = 0.7          s of silence inside a talk range that becomes a jump cut
# PAD_IN, PAD_OUT = 0.15, 0.30
# MUSIC_GAIN_DB = -15.0  music under nothing (inserts); voice is never under music
# VOICE_TARGET = -20.0   LUFS each clip's used speech is levelled to, per talk block
# VOICE_GAIN_MAX, VOICE_GAIN_MIN = 14.0, -6.0


def roll_for(road):
    """Degrees to level the dash-cam horizon for this road clip. Measure with scripts/roll_lr.py
    (mean of left and right halves cancels perspective); different cars need different values."""
    return 0.0


# --- teaser: complete phrases, (clip, from_s, to_s); always cut "keep" (no jump cuts inside)
HOOK = [
    # ("IMG_0083", 10.95, 20.45),
]

# --- edit decision list ------------------------------------------------------------
# ("talk", [(clip, from_s, to_s[, "keep"]) ...])
#       speech; pauses longer than GAP_CUT inside a range become jump cuts unless "keep".
#       Use "keep" for deliberate silences (engine sound) and for ranges whose end the first-pass
#       transcript gets wrong: then the range is taken as given, edges only nudged to silence.
# ("road", road_clip, at_s, len_s, music_key)                    dash-cam insert under music
# ("roads", [(road_clip, at_s, len_s) ...], music_key)           several road pieces, one insert
# ("card", road_clip, at_s, len_s, music_key, title, subtitle)   blurred road + big centred text
# ("end", road_clip, at_s, len_s, music_key, title, subtitle)    like card, text at the top; 20 s
#       for the YouTube end screen. "\n" in the subtitle gives several centred lines.
# ("photo", photo, len_s, music_key, title, subtitle)            photo (HEIC/PNG name in SRC, or an
#       absolute path, e.g. a still from make_stills) with slow zoom and a caption band; "" = no caption
# ("clip", iphone_clip, at_s, len_s, music_key, title, subtitle) silent iPhone footage under music
# ("anim", sdr_movie, len_s, music_key)                          ready-made SDR animation (route map)
EDL = [
    ("talk", [(c, a, b, "keep") for c, a, b in HOOK]),
    # ("card", "MAH04459", 60.0, 8.0, "p1", "Title", "subtitle"),
    # ("talk", [("IMG_0083", 1.4, 166.9)]),
    # ("road", "MAH04457", 138.0, 5.0, "p1"),
    # ...
    # ("end", "MAH04476", 60.0, 20.0, "p2", "Дякую за перегляд!", "line 1\nline 2"),
]

# music key -> (file in MUSIC_DIR, start offset in s); each key plays on from where it stopped
MUSIC = {
    # "p1": ("Highway Nocturne - National Sweetheart.mp3", 20.0),
}

# --- per-clip framing -----------------------------------------------------------------
CLIP_FRAME = {}      # clip -> ffmpeg crop/scale for "clip" inserts, e.g. "crop=1080:608:0:0,scale=1920:1080"
CLIP_SPEED = {}      # clip -> speed factor for "clip" inserts (2.0 = twice as fast)
PORTRAIT_BAND = {}   # portrait talk clip -> 0..1 position of a full-width 16:9 band (else pillarbox)


def make_stills():
    """Optional: build composite stills (OBD screens side by side, a fuel tally card, a cropped
    order screenshot) as 3840x2160 PNGs in OUT, for ("photo", OUT + "/still_x.png", ...) items.
    See example_yaris.py for working ones. Delete this function if there are none."""
