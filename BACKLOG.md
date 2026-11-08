# Backlog

## blur_plates.py fails on iPhone Live Photo clips

- What: `python scripts/blur_plates.py <footage> <film> IMG_0097` (a 2 s Live Photo movie,
  1920x1440, hevc + pcm audio + 3 data streams) ends with hevc_nvenc "Could not open encoder before
  EOF"; the mask written for it is 1.73 s long while the clip is 1.97 s.
- Where: scripts/blur_plates.py, process(): frame size / rotation handling and the final overlay pass.
- How found: testing the published scripts on 2026-10-31; normal clips (IMG_0115, IMG_0096) work.
- How bad: low. Live Photo movies are rarely used as inserts, and photos can be used instead
  (the still HEIC of the same moment).

## render_final.py uses NVENC only, not hevc_qsv / hevc_amf / hevc_videotoolbox

- What: since 2026-11-07 the melt render follows config "hevc_encoder" for hevc_nvenc (tested: Main 10,
  HLG tags, SSIM 0.995 to libx265, about 3x faster); any other value still renders with libx265.
- Where: scripts/render_final.py main().
- How bad: low. Only matters on a machine without an NVIDIA card.

## filmkit.py cannot put b-roll or captions over speech

- What: the talking clip is shown only while it talks, so a picture over the voice has no EDL item.
- Where: scripts/filmkit.py. Workaround, now in the skill: scripts/burn_in.py burns them into the talk clip at
  source seconds before filmkit, which keeps them in sync through every cut (portrait pictures beside the
  face, 2026-11-07). Left: an EDL item kind in filmkit, so no extra file and no second encode of the clip.
- How found: Mercedes GLC review, 2026-11-01.
- How bad: low now. The second encode costs about 9 min on a 45-min clip.

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

## dub_check.py does not flag a word the model dropped when recognition misses it too

- What: "Sarny. Here is why I drive slowly in the forest." (Ukrainian): all 4 Higgs takes dropped the
  one-word sentence "Сарни.", WhisperX heard only the rest, and the takes scored 0.82-0.94 with no
  `missing` flag. Found only by transcribing the finished voice track.
- Where: scripts/dub_check.py, the word match / `missing` logic (a leading short word seems to be skipped).
- How found: TeslaCam compilation, 2026-11-07, C:/Data/teslacam-video (line s13b, takes dub/takes/026_*).
- Workaround: put one-word sentences inside a longer sentence (written in references/dubbing.md).
- How bad: medium. A missing word at a line's start ships unnoticed unless someone listens.

## The finished-track click check lives only in the TeslaCam project

- What: C:/Data/teslacam-video/tc_audio_check.py checks a finished voice track: level after every line
  end, jumps there, and clicks as 8 kHz steps. It caught the radio click (30 of 37 line ends on the old
  load()) where per-take checks did not. dub.py mix has no such step.
- Better: move it into scripts/ (reading the line positions mix already knows) and run it at the end of mix.
- How bad: low-medium.

## blur_plates.py: the mask video can drift off the plates on variable-rate footage

- What: the mask is written as a constant-rate video and laid over the clip by ffmpeg overlay, which
  pairs frames by timestamp. On Tesla dash-cam clips (variable rate, r_frame_rate like 272500000/7546337)
  the mask drifted: a BMW plate at the A1 toll plaza stayed half readable although every check frame
  (drawn from the detection pass) showed the box in place.
- Where: scripts/blur_plates.py, process(): the ffv1 mask + overlay graph.
- How found: TeslaCam compilation, 2026-11-07. Fixed there in C:/Data/teslacam-video/tc_blur.py by
  compositing in Python frame by frame (decode again, blur under the mask, pipe to the encoder).
- How bad: high for any variable-rate source (privacy); iPhone clips looked right so far.
- Note: the check frames come from the detection pass, so they cannot show this; check the output file.

## Tesla dash-cam telemetry (SEI) is not in the skill yet

- **What:** Tesla clips from 2025 on carry one protobuf per frame in an H.264 SEI (user data unregistered):
  4 speed m/s, 5 accelerator, 6 steering deg, 7/8 blinkers, 9 brake, 10 autopilot state, 11/12 lat/lon,
  14/15/16 acceleration. On the TeslaCam film it found hard braking minutes before the save that the
  30-second review around each honk missed (6 new candidate scenes).
- **Where:** prototypes in C:/Data/teslacam-video: tc_sei.py (decoder), tc_sei_scan.py (all front clips to
  json), tc_sei_find.py (deceleration over 3.5 m/s2 in 0.5 s, steering jumps; skips 1 s at clip edges,
  where smoothing fakes a speed drop), tc_triage.py, tc_look.py (sheets; -ss must go before -i or
  drawtext's frame count includes the skipped seconds).
- **How bad:** medium. Without it a TeslaCam review sees only the seconds around each save.
- **Cut-ins without braking, and pre-2025 clips (no telemetry):** a vehicle detector over the front camera
  finds them: torchvision fasterrcnn_mobilenet_v3_large_fpn (COCO, 74 MB from download.pytorch.org) at
  4 fps, about 2.5 s per one-minute clip with three workers on the 3090; then a car that is close (box
  bottom below 620 of 960) and moves from outside the lane ahead into it within 3 s
  (tc_veh_scan.py, tc_veh_find.py in C:/Data/teslacam-video). The plate detector as a stand-in finds
  daytime cut-ins but nothing at night (headlight glare hides plates). Drop boxes wider than 700 px:
  the bonnet and glare come out as frame-wide "cars".

## dub.py clean() mutes a quiet last word of a dubbed line

- What: the speech gate in clean() (floor -17 dB under the take's p95, hf -14 dB) treats a softly spoken
  last word as a pause and drops it 45 dB, then load() trims it off as silence. The word is in the take
  and dub_check heard it, so no flag warns. Yaris Polish dub, 1:38: "...w dalekich podróżach" came out
  as "...w dalekich" (take out_full/takes/013_2.wav, 6.0 s; after load() 4.50 s; with clean() off 5.88 s,
  with denoise() off 5.24 s, so denoise() makes it worse but clean() does the cutting).
- Where: scripts/dub.py clean() and load() (load passes nothing about the checked word end).
- Fix idea: pass CHECKS[f]["end"] (the aligned end of the last word) into clean() and keep the gate open
  up to it, e.g. the last 1 s before that end; then compare a whole film's voice.wav word count against
  the chosen takes' "heard" text to catch any other dropped word.
- How found: the user heard it in a 2:30 test mix on 2026-11-07; WhisperX on voice.wav and on the take.
- How bad: high. Words vanish from the dub silently, and only listening finds them.
- Fixed 2026-11-08: clean(word_end=...) holds the gate open from the last speech island to the checked
  end; 013_2 now loads at 5.82 s. All 1557 Higgs takes of the Yaris PL/EN dubs checked (loaded length
  vs checked end): none loses a word.
