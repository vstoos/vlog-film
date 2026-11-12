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
- Road and wind rumble (under ~150 Hz, a window open, a rough surface) makes a clip measure loud, so the levelling
  turned it down and buried the voice (Helm 2, 4:39: -5.7 dB on a clip whose voice was quiet). filmkit now cuts
  under VOICE_HIGHPASS (120 Hz, 24 dB/oct) on every talk entry and measures the voice above VOICE_MEASURE_HP
  (200 Hz); such clips now get about +7 dB relative to before. A spectrogram (`showspectrumpic`, fscale=log) shows it.
- Steady road noise under the voice (Helm 2, 12 clips with speech only 5-15 dB over the floor, measured as
  p90 vs p10 of 50 ms RMS per talk block): what the user approved by ear, after rejecting the rest:
  1. a noise profile from the clip's own pauses (gaps of 0.6 s+ between transcript words, the quietest 60 % of
     those frames), every STFT bin under profile mean + 1.5 std turned down 12 dB, the mask smoothed over ~3 bins
     x ~5 frames (Audacity / Ocean Audio "noise reduction" done in numpy+scipy);
  2. then DeepFilterNet (official deep-filter.exe v0.5.6, `-D -a 12`, 48 kHz wav; it drops the last ~30 ms,
     the start stays aligned, so pad the end).
  Only for clips under about 16 dB speech-over-floor: the clean ones (17-37 dB in Helm 2) were left alone, there
  is little to gain and every pass costs some voice. The whole clip is processed and remuxed under the video (`<clip>_dn.mov`), so every jump cut gets the same
  treatment. The gap went to 17-28 dB; the user: "відчутно кращі, не ріже вухо". Rejected: ffmpeg afftdn (the noise
  "warbles", not quieter), EQ cuts (the noise is not only low), DeepFilterNet alone at -20 dB (took the low end off
  the voice on some clips; fine on one), -8/-12 alone (too little). Make before/after samples per clip (12 s
  original, 12 s processed, level-matched) and let the user choose; the project's tools/denoise.py and
  tools/nr_profile.py in C:/Data/helm2-video are the working version.
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
- iPhone road clips on a windshield mount tilt differently in every clip (Helm 2: -2.5 to +2.4 deg), and the
  user saw it. roll_lr.py on the used part only (cut it out first), then check the sign on a grid frame:
  ffmpeg rotate = minus roll_lr (positive = clockwise). Render levelled copies (rotate + zoom_for, HLG) and
  point CLIP_SRC and any burn_in b-roll at them; cards rotate through roll_for. zoom_for must use abs(deg),
  or a negative angle zooms out and shows the black corners. roll_lr gives nan in tunnels and on handheld clips.
- Portrait iPhone clips that are inserts can be cropped to the part that matters (CLIP_FRAME).
- Long walk-arounds can be sped up (CLIP_SPEED) instead of cut.
- A phone screenshot over the voice padded to the full frame hides the speaker for 5-8 s each, and the
  user disliked it (Mercedes film, 25:25): burn_in.py puts portrait pictures at full height on the free
  side of the face. Screenshots in a row replace each other without fading, or they blink.
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

## GPUs and hardware encoders

- **Card numbers change: look them up every session, never reuse one from a note or config.** The
  user's laptop has an RTX 3060 Laptop (6 GB, internal) and an RTX 3090 (24 GB, eGPU over Thunderbolt).
  Which is 0 and which is 1 depends on boot order and when the eGPU was plugged in, and each tool
  counts its own way: on 07.11.2026 nvidia-smi said 0 = 3060, 1 = 3090, while NVENC (`gpu=` in melt or
  ffmpeg) said 0 = 3090, 1 = 3060, and CUDA by default puts the fastest card first. Before a heavy job:
  `nvidia-smi --query-gpu=index,name,memory.used,utilization.gpu --format=csv`, and for NVENC check
  `encoder.stats.sessionCount` during a short test. `CUDA_DEVICE_ORDER=PCI_BUS_ID` makes CUDA follow
  nvidia-smi. Config values that hold an index (`"gpu"`, `"higgs_gpu"`, `"nvenc_gpu"`) can go stale:
  check them against nvidia-smi first; `vfconfig.cuda_index()` picks the card with the most memory.
- **Check the cards are free first.** Other sessions run detection and transcription on them; Higgs
  takes about 85% of the 3090, WhisperX a few GB. An occupied card means OOM or a crawl for both jobs.
- **Hardware encoding.** NVENC is a separate block on the card and stays free while CUDA is busy.
  hevc_nvenc keeps Main 10 and the HLG tags (melt: `vcodec=hevc_nvenc pix_fmt=p010le vprofile=main10
  preset=p6 rc=vbr cq=16 b=0`; ffmpeg: `vfconfig.hevc_args()`). Measured on 20 s of the Mercedes film:
  11 s on either card (once warm; the first run up to 21 s) against 31 s for libx265, SSIM 0.995 to
  it. Thunderbolt did not slow the 3090's NVENC. melt's filters still run on the CPU, so a whole render
  gains about 2-3x, not more (the whole Mercedes render: 19 min against 30-40 with libx265, with another
  session loading the CPU). The user confirmed it: the 3060 encodes almost as fast as the 3090, and the
  hardware codec is clearly faster than the software one, so any free card will do for a render.
  render_final.py, burn_in.py and blur_plates use NVENC when config `"hevc_encoder"` is `"hevc_nvenc"`.
- **Every encode goes through the load check (user's rule).** Before parallel encodes, read each card's
  encoder load and the CPU load and give work only where there is room: `vfconfig.encode_slots()` returns
  one argument list per job that may run now (2 per card under 40% encoder load, 1 under 75%, none
  above; 2 libx264 slots when the CPU is under 30%, 1 under 60%). Use the CPU too when it is idle, for
  the most speed. Intermediates in SDR H.264 use `vfconfig.sdr_args(gpu)` (h264_nvenc). With
  `CUDA_DEVICE_ORDER=PCI_BUS_ID` NVENC's `-gpu N` is nvidia-smi's card N (tested 07.11.2026 by
  session counts); encode_slots() sets it. On the TeslaCam film both cards were 50-60% busy encoding for
  another session, so the check gave one slot, not four.
- **Sharing the CPU.** When another session is busy, start a long render at below-normal priority
  (`$p = Start-Process ... -PassThru; $p.PriorityClass = 'BelowNormal'`; child processes inherit it)
  instead of waiting for the CPU to be free.

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
- Numbers in the first-pass transcript have guessed word times (WhisperX cannot align digits):
  "191", "1240 чи 1250 кілометрів", "1074", "176,3", "4 700" all came 0.5-2 s early or squeezed
  into 0.1 s, so islands() cut them off at range ends and jump cuts (Helm film 1, five places).
  Before building, re-time every number near a range edge or a pause: cut test pieces ending at
  +0.3/+0.6/+1.0 s and run transcribe_window.py on each; the number is there only when WhisperX
  hears it whole. Fix the word times in the transcript JSON (keep a backup), not only the range.
- After a build, transcribe the whole film once and diff it against the EDL's expected words
  (difflib on normalised words): it lists clipped words in one pass instead of one review note each.
- Road inserts: the user does not want plates blurred (floating boxes spoil the shot); talk clips:
  blur_plates.py --green-only (own EV plate only), no faces; the VIN on the car screen always hidden.
- Horizon: "checked by eye, level" was wrong (user saw 2-3 deg). Judge roll on grid frames rendered
  at several angles (0, +-2, +-3 with filmkit's rotate+zoom) side by side; roll_lr.py only hints
  (Helm: Aug 2024 set roll_lr -3.0 -> filmkit +3; Dec 2024 roll_lr +0.9 -> +2 by eye).
