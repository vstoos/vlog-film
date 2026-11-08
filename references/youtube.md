# YouTube deliverables

All of these go into the footage folder next to the final mp4.

## Description (YouTube_description.txt)

- Two or three title options; a short story paragraph; the facts viewers ask about (fuel used,
  prices with the date, rental cost); preparation done to the car.
- **Chapters**: `python timeline.py film/<name>.mlt` lists where each block and insert starts;
  first chapter must be 0:00, at least 10 s apart. Shift them after every rebuild (a fix that adds
  a few seconds moves every later chapter).
- Credits: music titles from YouTube Audio Library; map attribution if a route map is used
  ("Sentinel-2 cloudless 2016 © EOX IT Services GmbH (contains modified Copernicus Sentinel data,
  CC BY 4.0), roads © OpenStreetMap contributors, routing OSRM").
- A film with a Higgs voice track or voice-over: "Voice: AI clone of the author's voice, Boson AI's
  Higgs Audio" near the top, not buried at the end (the licence's condition for monetised videos).
- Referral links the user gives (e.g. a Tesla referral link) go in the description
  and on the end card.

## End screen

The last 20 s (the "end" EDL item): road footage with music, thank-you text at the top, middle and
bottom free for the end-screen tiles the user adds in YouTube Studio.

## Thumbnail

- Pick candidate frames from the clips (the car in good light, the place that defines the story,
  the user's face); export full-size tone-mapped PNGs with libplacebo and show them as a sheet.
- `python make_thumb.py <frame.png> <out.jpg> "HEADLINE!" "second line" --plate x0,y0,x1,y1`:
  1280x720 JPEG, big yellow Segoe UI Black headline with black outline, white second line, top of
  the frame darkened so the text reads; plates blurred.
- The user prefers the untouched frame; offer AI enhancement (Gemini) only as an option. If used,
  the key is in the GEMINI_API_KEY user environment variable (never in files or chat).

## Subtitles (Ukrainian, Polish, English)

1. `python make_subs.py <final.mp4> <out_dir> [lang]` transcribes the finished film and writes a first-pass
   `film.<lang>.srt` (cue <= 2 lines of ~42 chars, <= 6 s, split at pauses and sentence ends).
2. Correct it by hand: names (Yaris, Orlen, Tesla, LTFT, Torque, place names), numbers and units,
   words WhisperX misheard; compare doubtful places with the audio.
3. Translate cue by cue into `.pl.srt` and `.en.srt` keeping the exact cue numbers and times;
   keep units and numbers, translate meaning not words, keep lines short.
4. **On-screen texts.** Cards, the title, the end card and captions stay in the film's language, and
   under a card there is no voice, so a dubbed or foreign viewer gets nothing (the user's note on the
   Mercedes film). After the speech subtitles and after every rebuild:
   `python onscreen_subs.py <project.py> list` prints each text with its film time and the ones with no
   translation; write them into `<project>/subs/onscreen.json` (`{"<text>": {"en": ..., "pl": ...}}`,
   one entry per line of text), then `python onscreen_subs.py <project.py> write <footage>/<Name> en pl`.
   Captions burnt into a clip (burn_in.py, voice-over clips) come from `onscreen()` in project.py,
   `[(clip, from_s, to_s, [lines])]` at the clip's own seconds; the script maps them through every cut.
   Over speech they are cues of their own in [brackets], overlapping the speech cue; the speech-only files
   are kept as `subs/<Name>.<lang>.speech.srt` and are what a rerun starts from. The dub is not affected:
   dub.py speaks its manifest, not these files. Check a few cue edges against frames of the film.
5. Upload in YouTube Studio > Subtitles. Also add the title and description in Polish and English
   there (Studio > Languages), so foreign viewers see them in their language.

## Auto-dubbing

YouTube dubs Ukrainian videos automatically only into English (as of 2026); dubs cannot be edited,
only previewed, unpublished or deleted. Set the video language to Ukrainian, turn on manual
publishing of dubs, listen before publishing. Polish needs subtitles or an own uploaded audio track (references/dubbing.md).
