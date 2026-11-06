# Backlog

## blur_plates.py fails on iPhone Live Photo clips

- What: `python scripts/blur_plates.py <footage> <film> IMG_0097` (a 2 s Live Photo movie,
  1920x1440, hevc + pcm audio + 3 data streams) ends with hevc_nvenc "Could not open encoder before
  EOF"; the mask written for it is 1.73 s long while the clip is 1.97 s.
- Where: scripts/blur_plates.py, process(): frame size / rotation handling and the final overlay pass.
- How found: testing the published scripts on 2026-10-31; normal clips (IMG_0115, IMG_0096) work.
- How bad: low. Live Photo movies are rarely used as inserts, and photos can be used instead
  (the still HEIC of the same moment).

## render_final.py ignores the configured hardware encoder

- What: the melt render uses vcodec=libx265 (CPU), although config.json sets
  "hevc_encoder": "hevc_nvenc" and Shotcut's melt lists hevc_nvenc, hevc_qsv and hevc_amf.
- Where: scripts/render_final.py:28.
- How found: `melt -query vcodecs` and the source, 2026-11-01. Not tested yet: whether melt with
  hevc_nvenc keeps Main 10, the HLG tags and picture quality, and how much time it saves (melt's
  filters still run on the CPU).
- How bad: medium. Final renders take about 30 min, which slows every review round.

## filmkit.py cannot put b-roll or captions over speech

- What: the talking clip is shown only while it talks, so a picture over the voice has no EDL item.
- Where: scripts/filmkit.py. Workaround: C:/Data/mercedes-video/overlays.py burns them into the talk clip at
  source seconds, which keeps them in sync through every cut.
- How found: Mercedes GLC review, 2026-11-01.
- How bad: medium. Any film with one long static talk needs this.

## blur_plates.py floods a long selfie clip with false boxes

- What: CONF 0.15 gave boxes on 61759 of 80270 frames of IMG_8099, some 20% of the frame, on hands, shirt, ground,
  signs; on car interiors (IMG_8097) they are huge. Rotated clips also run detection twice (about 10 fps).
- Where: scripts/blur_plates.py detect() and the check frames, which sample every 243 s and miss all of this.
  Fix that worked: C:/Data/mercedes-video/clean_mask.py, keep boxes of plate size that live over 2 s.
- How found: mask statistics and a sheet of the frames with the largest mask.
- How bad: high. The check frames looked clean while the clip had big blurred patches.

## filmkit.py silently drops a word that sticks out of the range

- What: islands() keeps only words lying wholly inside [a, b]. When WhisperX stretches a word over a cough or merges
  a re-read into it ("електромобільність" 4.69-6.59 over a cough; "автобані" 1972.0-1974.6 swallowing the second
  "вимкнули на автобані"), a cut placed in the right silence drops the whole word with no warning.
- Where: scripts/filmkit.py islands(), line ~320. Workaround used: corrected the word times in the transcript
  (backup transcripts/IMG_8099_whisper.json). Better: clip a word that crosses the range edge to the edge and use
  the envelope, or print a warning naming the dropped word.
- How found: Mercedes build 2 came out 52 s short instead of 22 s; the diff of the .mlt entries showed it.
- How bad: high. The film loses words where the editor deliberately cut, and only an entry diff reveals it.

## filmkit.py clipped the start of a phrase that begins with a 20 ms word (fixed)

- What: islands() took prev_e from words with w[1] <= s + 0.02, which includes the first word itself when WhisperX
  gives it 20 ms ("В"[1252.93-1252.95]). lo_lim then landed after that word and cut "В мо(їй)".
- Where: scripts/filmkit.py islands(). Fixed 2026-11-03: neighbours must start before s / end after e.
- How found: Mercedes build 3, 4:54 heard back as "І те, що цього не було". The fix moved 3 more starts earlier
  in the same film (0:45 "В результаті", 10:27 "В порівнянні", 27:44 "в магнітолі"): they had been clipped too.
- How bad: medium, now fixed. Films built before the fix may have clipped one-letter words at phrase starts.

## filmkit.py trips on negative roll and upside-down clips

- What: zoom_for fails on a negative roll; rotated() treats rotation -180 as portrait.
- Where: scripts/filmkit.py. Workaround: positive roll, PORTRAIT_BAND 0.0 for those clips.
- How found: Mercedes GLC review, 2026-11-01.
- How bad: low.

## Second line of cards is hard to read

- What: FONT_LIGHT on the cards, title and end card is thin and fades on road footage; "чесно про плюси" and the
  referral line are barely readable at phone size.
- Where: scripts/filmkit.py, card and caption text.
- How found: frames of the finished Mercedes film, 2026-11-01. Bold on a darker band read well in overlays.py.
- How bad: medium.
- Status: fixed 2026-11-03 in filmkit.py (bold 50 px, stronger shadow on cards; captions bold on a black@0.6 band).
  Checked on frames of Mercedes build 2 (title, card, end card with referral line): readable. Can be closed.

## filmkit.py has no exact cut point inside a phrase

- What: islands() moves a range end to the next word's start - 0.05 s and a range start to the previous word's
  end + 0.05 s (plus the envelope), and project files complete sentences unless the end is in HARD_ENDS. A cut
  that removes one word from the middle of a phrase therefore does not land where the EDL says.
- Where: scripts/filmkit.py islands(); the sentence completion in the project file (_finish_sentences).
- How found: Mercedes GLC film, 32:42, removing "достали" took 6 listening samples (2026-11-05). Workaround in
  use: a marker word in the transcript plus a HARD_ENDS entry (references/lessons.md, "Cutting speech").
- Better: an EDL flag for an exact edge, e.g. r("44:14.44!", ...), that skips the word snapping and the
  sentence completion for that edge.
- How bad: medium. Every mid-phrase word cut needs transcript surgery today.
