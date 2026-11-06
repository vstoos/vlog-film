# Lessons from the Yaris film

Each of these cost a render or a round of user notes. They are why the pipeline looks the way it does.

## Cutting speech

- **First-pass transcripts misplace phrase ends.** WhisperX on a whole clip often compresses the
  last words (numbers above all) into too short a span or drops them, so a range ending "after the
  last word" cuts the phrase: "не 144, а 147" lost "а 147"; "від заправки 455 кілометрів" ended on
  "від"; "не їздила" ended early. Fix: transcribe a short window around the end again
  (`transcribe_window.py`; short windows are far more accurate), and if words are slow with long
  pauses, look at the voice-band energy (250-3500 Hz, 20 ms frames) to see where each word sits.
  Then end the range explicitly and mark it "keep" so it is not re-cut on the stale words.
- **Slips and false starts** ("він... вона") show up as a separate short burst of voice energy
  between words; cut around it with two ranges and check the splice by transcribing it.
- **Deliberate silence is content.** When the speaker stops talking to let the engine be heard,
  the whole range must be "keep"; automatic gap cutting would remove exactly the point.
- **Lost thoughts**: if the user says a phrase hangs ("де я вибрав собі зупинку?..."), the answer is
  usually a nearby range left out of the EDL; search the transcript after the cut point.
- **Cutting one word out of a phrase** ("я і дружина достали отримали тут", Mercedes film): find the
  word edges on the voice energy at 10-25 ms steps, then make 2-3 short mp3 samples of the joint with
  different cut points (ffmpeg atrim + concat from the source) and let the user choose by ear.
  WhisperX cannot judge a joint this short: it wrote "тримали" for every sample, while the user
  heard "дотримали" in one and a clean "отримали" in another. The winner started the cut just
  before the onset spike of the removed word and ended it in the dip before the next word.
  If the phrase is also in the teaser (HOOK), give the teaser the same cut.
- **filmkit moves cut edges to the neighbouring words.** islands() stretches a range end up to
  the next word's start (minus 0.05 s) and a range start back to the previous word's end, so a
  cut inside a phrase lands somewhere else than the EDL says. To pin it, insert the removed word
  into the transcript as a marker (`{"w": "достали", "s": ..., "e": ...}`) with its start 0.05 s
  after the wanted cut start and its end 0.05 s before the next range starts; add the range end
  to HARD_ENDS so the sentence is not completed. Check the .mlt entries with timeline.entries().
- After any change near a cut, verify on the finished film, not on the source.

## Audio

- Clips from different days or mic positions differ by 10+ dB. filmkit levels each clip per talk
  block to VOICE_TARGET by measuring only the pieces actually used (EBU R128 on the joined pieces;
  ffmpeg's aselect ignored its expression on these files, so the joining is done in numpy).
  Boost is capped at +14 dB so a very quiet clip does not turn into hiss.
- The final render is loudness-normalised to -14 LUFS (two-pass loudnorm, linear). After levelling,
  neighbouring sections should be within 1-2 dB; check the ones the user complained about.
- Music sits at -15 dB, rises under the last words before an insert and fades under the first
  words after it; voice and music never compete.

## HDR / colour

- iPhone clips are HLG 10-bit (often with Dolby Vision metadata); the film is HLG BT.2020 10-bit,
  Main 10, tagged hvc1. Shotcut's preview shows HLG flat and pale: that is the preview, not the file.
- SDR material (dash-cam, photos, map animations, text) is converted with libplacebo into HLG.
  Text and graphics go in as graphics white, not inverse-tonemapped, or white text blazes at peak;
  text drawn on HLG footage uses ~75% white (0xBFBFBF).
- **melt garbles rotated 10-bit clips (green frames).** Portrait clips are therefore rotated by
  ffmpeg first (`render_portrait`): pillarbox on a blurred copy, or a full-width 16:9 band
  (PORTRAIT_BAND) when the user wants them full screen. render_final.py counts green samples.
- When comparing colours of a processed clip with the original, compare raw YUV averages
  (signalstats), not tone-mapped previews: the original's Dolby Vision metadata changes the
  preview, but melt ignores it for every clip alike.

## Framing and inserts

- Dash-cam horizon: measure roll per car with roll_lr.py; filmkit rotates and zooms just enough.
- Portrait iPhone clips that are inserts can be cropped to the part that matters (CLIP_FRAME).
- Long walk-arounds can be sped up (CLIP_SPEED) instead of cut.
- Composite stills (make_stills): crop app badges like "1 / 5" off screenshots; keep important
  text above the caption band (bottom ~230 px of 1080) so the caption never covers it.
- For an OBD/Torque screen recording, sample the value every minute (crop the gauge, tile with
  time labels) to find the interesting moments, then every 5 s around them. Show the progression
  (several different values), not two identical endpoints; state facts in captions, not causes the
  data does not prove.

## Privacy

- Blur licence plates (blur_plates.py: YOLO detector, low threshold, held over 12 frames). Check
  its check frames, and blur plates on thumbnails too.
- Blur faces of people who did not agree to be filmed (rental staff, passers-by) and of children:
  `blur_plates.py --faces` (OpenCV YuNet). At a low score it took reflections in car paint for
  faces and put large blurs on the car; score 0.75 and a maximum face width of 12% of the frame
  fixed that. Check a dense contact sheet (every 0.2 s) of the moments with people.
- Route maps start at a public point (the first petrol station), never at the user's home.
- Do not put other people's children or faces on thumbnails without the user asking.

## Process

- Renders take ~30 min: run in the background, and do not rebuild while the user is still
  collecting notes.
- Keep a backup of the previous .mlt and description before a rebuild (film_check/), so changes can
  be compared.
- When the user's memory of what they said differs from the recording, tell them what the
  recording says (e.g. receipt says 13.28 l, not 19 l) before changing captions.
- **Check what the author says against the footage.** In the Mercedes film the author said twice
  that the car had no cruise control, while the stalk clip in the same film showed distance
  control; it had adaptive cruise and lacked only lane keeping. Before showing a cut, compare
  claims about equipment, numbers and places with the inserts, photos and screenshots; point out
  the conflict and let the author decide (cut the claim, or correct it in a caption).
