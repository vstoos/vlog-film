---
name: vlog-film
description: Edit raw trip / car vlog footage (phone HLG talking-head clips recorded while driving, dash-cam road footage, photos, OBD/Torque screen recordings) into a finished HDR (HLG 10-bit) YouTube film with a teaser, jump cuts on speech, road inserts under music, captions, route map, licence-plate blurring, levelled voice, chapters, thumbnail, subtitles in several languages, dubbed audio tracks in the user's cloned voice, vertical Shorts, and the upload to the YouTube channel (video, thumbnail, subtitles, translated titles; "завантаж на ютуб", "upload the subtitles"). Use this whenever the user wants to edit, cut, assemble or finish a video from footage they shot ("змонтуй відео з поїздки", "make a YouTube video from this folder", "add this clip/photo to the film", "fix the cut at 12:22", "the fragment at 9:15 is too quiet"), for review rounds on a film built this way, and for its YouTube description, chapters, thumbnail, subtitles and dubbing ("озвуч англійською моїм голосом", "dub this into Polish", "there is a pop at 4:25 in the dub"), even when the user does not say "skill" or "montage".
---

# Vlog film

Turn a folder of the user's footage into a finished YouTube film, then iterate on it with the
user's notes until they are happy. The pipeline was built on "Yaris farewell" (24 min, Ukrainian
speech, iPhone + Sony dash-cam); `references/example_yaris.py` is that film's complete project
file, the best guide to what a finished edit looks like.

## Before you start

- **Setup.** `<skill>/config.json` holds the machine's paths (ffmpeg, melt, Python with WhisperX,
  plate model, music folder, encoder, speech language). If it is missing, or a script fails for a
  missing tool, run `python <skill>/setup/setup.py` (check only) and show the user what is missing;
  with their OK run `python <skill>/setup/setup.py --install`. Run every script below with the
  Python from config.json (`"python"`), because that is where WhisperX and torch are installed.
- **The user.** If `<skill>/user.md` exists, read it: it says who the user is, which language to
  answer in, and their standing preferences. Without it: answer in the user's language, keep
  replies short, name film times as mm:ss for anything they should look at.
- In the commands below `$K` is `<skill>/scripts` and `python` is the configured Python.

## Project layout

Footage stays where the user put it; the final mp4, the YouTube description, thumbnail and
subtitles go there too, because that is where the user looks. Working files go in a project folder
(for example `C:/Data/<name>-video/`):

```
<name>-video/
  project.py        paths, EDL, HOOK, music, framing, make_stills()   (copy references/project_template.py)
  transcripts/      <clip>.json from transcribe_all.py
  film/             rendered inserts, <clip>_blur.mov, <name>.mlt, <name>.mp4
  film_check/       contact sheets, test wavs, check frames (scratch)
  edit_notes.md     the user's review notes and what was done about each
  subs/, thumbnail/, route/
```

## Workflow

### 1. Inventory

1. `python $K/scan_meta.py <footage> film_check/meta.json`: time, duration, GPS of every file.
   Sorted by time this is the story order.
2. Look before deciding: `python $K/contact_sheet.py <out.png> 6 <clips...>` for clips, a tiled sheet
   for photos; view the images yourself. Note portrait clips (rotation -90/90), clips that show
   licence plates, the dash-cam files, screen recordings. Tesla dash-cam / Sentry events from the
   trip dates: references/teslacam.md (finding the incident, colour via `teslacam_grade.py`).
3. `python $K/transcribe_all.py <footage> transcripts`: word-timed WhisperX transcript of every
   talking clip (resumable, language from config). Read them all; they are the story's raw material.

### 2. Story and EDL

Propose the structure to the user in a few lines before building: the teaser, the parts, which
photos, maps or stills illustrate which talk. Typical shape:

**What the channel's numbers say (YouTube Analytics, 2026-11-11).** Focused 6-14 min videos that answer
one owner's question (12 V error, which used Model 3, LFP on the motorway) keep 44-49 % of the video and
58-68 % of viewers at 1:00; the long trip films (24-45 min) keep 16-23 % and lose 40-57 % in the first
minute, which is where they lose most against similar videos. Search brings people with a question
("tesla model 3 lfp", "michelin pilot alpin 5"), so the films are not short of interest; they hide the
answer. The user films unscripted and will not shoot for viewers, so these are editing rules:

- **Name the question in the first 10 s**: the teaser opens with the challenge or question the film
  answers (with its number: "1650 km in one calendar day"), then 2-4 phrases of how it goes, and ends on
  the open question or a promise ("the numbers at the end"). Mood shots and greetings come after.
- **From the teaser straight to the point**: the title card is 5-7 s at most, and the first talk after it
  starts with the trip, not "привіт, довго не бачилися": keep one greeting phrase at most, drop the
  channel and name introduction (analytics review, 2026-11-12).
- **Order by the question, not the clock**: what answers the question stays, talk that only fills the
  drive goes, even when it was said in that order on the day.
- **Aim for 10-15 min** for a new film (the user's own wish too); a long trip can become 2-3 films, one
  question each, rather than one 25-45 min film. Road inserts 3-5 s between talk, longer only where the
  road is the story.
- **Title and chapters in the viewer's search words** with the number ("Tesla Model 3 LFP: real winter
  range"), not the trip's name.
- After publishing, `yt_stats.py` (references/youtube.md, "After publishing") shows whether it worked.

- **Teaser (HOOK)**: 4-6 short, strong phrases from across the trip, each a complete thought; the first
  one names the challenge or question (see above).
- **Title card** on road footage, then talk blocks separated by 4-10 s road inserts under music.
- Inserts where the talk refers to something: the receipt when fuel is mentioned, the inspection
  stand when the inspection is, a route map at the start of each leg.
- **Trip numbers** (charge captions, battery % on route legs, summary card): collect and check them
  first, in the project's trip_stats.md, as `references/trip_stats.md` describes.
- **Pictures over the voice** (b-roll, phone screenshots, captions while the speaker goes on talking):
  burn them into the talking clip with `burn_in.py`, before filmkit (it shows a talking clip only while
  it talks). A portrait picture (screenshot, vertical clip, portrait photo) stands at full frame height
  on the free side of the speaker's face, found by face detection, so the face stays in view; the
  phone's clock and buttons fill the top and bottom anyway. A landscape picture covers the frame.
- Road inserts should show what the story needs at that point (the slip road into the petrol
  station before "we stopped", the airport car park before the scene at the airport), not just any
  motorway: look at a contact sheet of the road clip around the right moment.
- **End card**: 20 s on road footage, text at the top, the middle free for YouTube end-screen tiles;
  a referral link here if the user has one.

Write `project.py` from `references/project_template.py`; the EDL item kinds, captions, music keys
and per-clip options are documented there. Talk ranges come from the transcript times.

### 3. Build and render

```
python $K/blur_plates.py <footage> <project>/film [--faces] IMG_0089 ...   # plates; --faces: people too
python $K/burn_in.py film/IMG_0089_blur.mov film/IMG_0089_over.mov spec.json   # pictures over speech, if any
python $K/filmkit.py <project>/project.py                        # renders inserts, writes film/<name>.mlt
python $K/render_final.py <project>/film <name> <footage>/<Name>_HLG.mp4   # long: run in background
```

Before a heavy GPU job (render, WhisperX, dubbing) run `nvidia-smi`: card numbers change between
sessions and differ between tools, and other jobs may hold a card (references/lessons.md, "GPUs and
hardware encoders"). `filmkit.py --no-media` only rewrites the .mlt (seconds). The render prints loudness, duration,
codec/HDR tags and a green-frame count: expect about -14 LUFS, Main 10, arib-std-b67, bt2020, 0 green.

### 4. Verify before telling the user it is done

Listen with WhisperX instead of trusting the EDL: for every new or changed cut, cut the same seconds
out of the *finished* mp4 and transcribe them (`python $K/transcribe_window.py <wav> <offset>`).
First-pass transcripts are often wrong about where a phrase ends, especially with numbers, so cuts
made from them chop the end off ("не 144, а 147" lost "а 147"). Also measure loudness of
neighbouring sections (`ffmpeg -ss A -t N -i film.mp4 -af ebur128 -f null -`) and look at a frame of
every new insert. The other traps and their fixes: references/lessons.md.

### 5. Review rounds

The user watches and sends notes with film times. For each note:

1. `python $K/timeline.py film/<name>.mlt 12:22` names the clip and source second.
2. Check the source (transcribe a window, measure loudness, look at frames). Tell the user what is
   actually there, quoting the original words; their memory sometimes differs from the recording.
3. Change the EDL and log it in `edit_notes.md` (film time, clip and seconds, what was said, change).

While the user is still watching, collect notes and do not rebuild: one build at the end saves long
renders. When they say to build, rebuild once, verify every changed spot as in step 4, update chapters.

### 6. Deliverables

references/youtube.md: description with chapters (`timeline.py`), thumbnail (`make_thumb.py`),
subtitles (`make_subs.py` on the finished film, hand-corrected, then translated cue by cue, plus the on-screen texts translated as their own cues with `onscreen_subs.py`), YouTube
auto-dubbing, and the upload itself: `yt_upload.py` puts the video, thumbnail, subtitles and translated
titles on the channel (private, never deletes anything; `--dry-run` first). The user can watch renders on a phone through `python $K/media_server.py --port 8765
<footage> <project>/film` (LAN / VPN only; read-only; also at github.com/vstoos/media-server).

### 7. Dubbed audio tracks

For a language the user wants heard, not read: `references/dubbing.md`. The voice is Higgs TTS 3
(default since 06.11.2026) with the user's saved reference **in that language** (`C:/Data/voices`, pass
`-`); every film description with a Higgs track credits "Boson AI's Higgs Audio". The subtitles go through
`dub.py gen`, `dub_check.py` catches the model's glitches take by take, `dub_regen.py` replaces what
failed, and `dub.py mix` builds the track and prints what to listen to. Fix pronunciation in `say.json`.
Voice-over for silent footage (dash-cam clips) takes the same route in Ukrainian, written as subtitles.
Do not call a dub clean from the checks alone: the user's ear is the last step.

### 8. Shorts

A Short is a 9:16 cut of one strong passage (30-60 s), pointing to its long video. Build it as a small
landscape film first, then reframe it:

```
<project>/shorts/s1/project.py   talk ranges only (CLIP_SRC to the film's landscape/_over copies), no card, no end
python $K/filmkit.py <project>/shorts/s1/project.py
python $K/render_final.py <project>/shorts/s1/film s1 <project>/shorts/s1/s1_land.mp4
python $K/make_short.py <project>/shorts/s1/short.json     # -> <footage>/shorts/<name>.mp4, 1080x1920 HLG
```

`make_short.py` crops a 608-px window around the face of each shot (a new shot at a scene change or a
face jump), shows a shot without a face whole over a blurred fill, puts pictures (the screenshot the talk
mentions) over the whole frame, face included (the user: a small box half over the face looks worse; `"box"` as 4th item keeps the old box), and burns word-timed captions; `"music": [file, offset]` lays a quiet bed under the voice (14 LU down, fades in and out). The first run writes
`short.words.json` next to the spec: fix names and numbers there and run again. Look at frames of every
shot before sending it. Plan the batch in the project's shorts_plan.md: which long video each one points to.
Every Short gives the viewer a reason to open the long video: `"outro": "Вся поїздка:
посилання над назвою"`
puts that line at the top for the last seconds (`outro_len`, default 3 s; the Related-video link shows above
the title in the Shorts player), and the dub texts end with the same line in each language. Set Related
video, the first description line and a pinned comment with the film link as well.

Choosing and cutting (Helm batch, 2026-11-09):
- One complete thought, 30-60 s; ranges from word timings (`transcripts/<clip>.json`, words `w/s/e`),
  not segment ends. A hook (2 short lines, `hook_len: 0` keeps it on) says what the Short is about, so
  the talk can start mid-story. Skip false starts and repeats with several ranges of one clip.
- CLIP_SRC to the film's upright copies *without* burnt-in captions (`_land`): a 608-px crop cuts a
  landscape caption in half. Show a still the talk mentions as a `pictures` entry instead.
- Skip clips filmed on the car screen with the navigation map near home (privacy), even for one line.
- In `short.words.json` fix brand names (WhisperX: "Pizarro" = P Zero) and add units the viewer needs
  ("4 700" -> "4 700 PLN").
- Hook lines up to about 22 characters: longer ones run off the 1080 width.
- A different track per Short (`music`), so a batch does not sound the same; a melodic guitar track goes lower (`"music_lufs": -33`), it competes with the voice.
- A fact the talk leaves out ("the glass has since been replaced") goes in `"notes"`: small white lines under the hook.
- A word missing from the clip transcript is cut as a pause by filmkit ("саме сколи, дрібні"): when the user hears a word gone, transcribe the source window and add the word to `transcripts/<clip>.json`.
- Listen to the end: a range ending on a number can lose it ("4 700" became "4 тисячі"). End the range
  just before the next word, and cut a silent tail with `"until"`.
- Phone copy for the user: tone-map to SDR h264 (libplacebo bt.2390) and keep it under the messenger limit.

## Privacy

Plates: the user does not blur ordinary traffic (Poland; the floating box spoils road shots).
Blur a plate only where the clip shows that driver's possible violation or a near miss, so the film
cannot feed a complaint against a person; road inserts go in as is via CLIP_SRC in the project.
Blur the faces of staff, passers-by and children
(`blur_plates.py --faces`; check the frames, reflections in car paint can fool it); start route maps at a public place, never at the
user's home; do not put other people's faces (children above all) on thumbnails unless asked.

## Reference files

- `references/project_template.py`: annotated project file to copy; EDL syntax.
- `references/example_yaris.py`: the finished Yaris film, all features in use.
- `references/lessons.md`: HDR, audio, cutting and framing traps, with the fixes that worked.
- `references/teslacam.md`: Tesla dash-cam / Sentry clips (HW3): finding the incident in a saved
  event, and the colour correction (`scripts/teslacam_grade.py`).
- `references/youtube.md`: description, chapters, thumbnail, subtitles, dubbing, end screen.
- `references/dubbing.md`: own audio tracks in the user's cloned voice, and automatic glitch checks.
- `references/trip_stats.md`: trip numbers (car screen, logger, charger apps, tariff): which source
  wins, the project's trip_stats.md, charge captions with the whole stop time, route legs, summary
  card, conclusion, how to report them.
- `references/example_make_route.py`: animated route map (Sentinel-2 tiles + OSRM roads) from the
  Yaris film; adapt its constants (bounds, cities, pins, legs) for a new trip.
