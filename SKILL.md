---
name: vlog-film
description: Edit raw trip / car vlog footage (phone HLG talking-head clips recorded while driving, dash-cam road footage, photos, OBD/Torque screen recordings) into a finished HDR (HLG 10-bit) YouTube film with a teaser, jump cuts on speech, road inserts under music, captions, route map, licence-plate blurring, levelled voice, chapters, thumbnail and subtitles in several languages. Use this whenever the user wants to edit, cut, assemble or finish a video from footage they shot ("змонтуй відео з поїздки", "make a YouTube video from this folder", "add this clip/photo to the film", "fix the cut at 12:22", "the fragment at 9:15 is too quiet"), for review rounds on a film built this way, and for its YouTube description, chapters, thumbnail and subtitles, even when the user does not say "skill" or "montage".
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
   licence plates, the dash-cam files, screen recordings.
3. `python $K/transcribe_all.py <footage> transcripts`: word-timed WhisperX transcript of every
   talking clip (resumable, language from config). Read them all; they are the story's raw material.

### 2. Story and EDL

Propose the structure to the user in a few lines before building: the teaser, the parts, which
photos, maps or stills illustrate which talk. Typical shape:

- **Teaser (HOOK)**: 4-6 short, strong phrases from across the trip, each a complete thought.
- **Title card** on road footage, then talk blocks separated by 4-10 s road inserts under music.
- Inserts where the talk refers to something: the receipt when fuel is mentioned, the inspection
  stand when the inspection is, a route map at the start of each leg.
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
python $K/filmkit.py <project>/project.py                        # renders inserts, writes film/<name>.mlt
python $K/render_final.py <project>/film <name> <footage>/<Name>_HLG.mp4   # long: run in background
```

`filmkit.py --no-media` only rewrites the .mlt (seconds). The render prints loudness, duration,
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
subtitles (`make_subs.py` on the finished film, hand-corrected, then translated cue by cue), YouTube
auto-dubbing. The user can watch renders on a phone through `python $K/media_server.py --port 8765
<footage> <project>/film` (LAN / VPN only; read-only; also at github.com/vstoos/media-server).

## Privacy

Blur licence plates in clips and thumbnails, and the faces of staff, passers-by and children
(`blur_plates.py --faces`; check the frames, reflections in car paint can fool it); start route maps at a public place, never at the
user's home; do not put other people's faces (children above all) on thumbnails unless asked.

## Reference files

- `references/project_template.py`: annotated project file to copy; EDL syntax.
- `references/example_yaris.py`: the finished Yaris film, all features in use.
- `references/lessons.md`: HDR, audio, cutting and framing traps, with the fixes that worked.
- `references/youtube.md`: description, chapters, thumbnail, subtitles, dubbing, end screen.
- `references/example_make_route.py`: animated route map (Sentinel-2 tiles + OSRM roads) from the
  Yaris film; adapt its constants (bounds, cities, pins, legs) for a new trip.
