# TeslaCam / Sentry footage (Autopilot HW3)

Worked out on the Helm 2026 film (Model 3, built Nov 2020, HW3). Use `scripts/teslacam_grade.py`.

## Finding the moments

- Files: `TeslaCam/SavedClips/<event time>/` and `SentryClips/`, one file per minute per camera
  (`-front`, `-back`, `-left_repeater`, `-right_repeater`), 1280x960 h264 36 fps, no audio.
  `RecentClips` holds only the last hour, so old trips are only where the driver saved them.
- `event.json` gives time, place and reason (`user_interaction_honk`, `user_interaction_dashcam_icon`,
  `vehicle_auto_emergency_braking`, `sentry_aware_object_detection`, ...). It is the *save* time:
  a driver who honks to save often does it minutes after the incident, so look through the whole
  10 minutes, not only the last seconds.
- To find the incident fast, plot the median optical flow in the road area in front of the bonnet
  (4 samples/s, Farneback on 320x240): on a motorway the road texture gives almost nothing, so peaks
  are things close in front of the car. Check each peak with a tile of frames (fps=4) of the front
  and both repeaters; an automatic emergency braking event peaked exactly at its event.json second.
- Blur plates: other cars are close and their plates readable.

## Colour

- **Not a range problem.** Files are tagged tv (limited) range and really are limited range
  (signalstats YMIN/YMAX 0/255 are rare outliers; 99.9% of pixels sit inside 16-235).
- **Flat tone.** On a sunny day luma p1 is ~45 and p99 only 160-185: milky blacks, no whites.
  Levels must come from each clip's histogram; one fixed curve over- or under-stretches.
  Do not let the white point drop below ~0.8: on a clear-sky clip the sky is the brightest thing
  and gets stretched to white otherwise.
- **RCCB sensor.** HW3 front and repeater cameras are red-clear-clear-blue; green is computed by
  subtraction, so the error differs per hue (forum threads describe a sepia / yellow cast; this car's
  front camera gave a lavender sky). HW4 uses RGGB. The back camera of the same car is RGGB and looks
  natural, which makes it the reference.
- **Measured:** blue sky hue in YCbCr was -24 deg on the front camera, -43 deg on the back camera and
  -50 deg on a repeater (natural sky is about -45 to -55). The common forum fix "hue -30" rotates the
  sky right, but turns grass pink and an orange car magenta: rejected.
- **Matrix fit.** Take the moment a car passes: the same objects (that car, asphalt, blue sky,
  clouds, a coloured barrier stripe) are in the front frame and, a few seconds later, in the back
  frame. Pick pixels per class by colour (orange: R-B > 0.12; sky: B-R > 0.08; clouds: top 3% luma
  with low chroma), apply the levels to the front frame first, then least-squares a 3x3 matrix
  front -> back (weight the car and asphalt most), scaled so the asphalt luma is unchanged.
  The full matrix copied the back camera's own warm look (cyan sky, pink asphalt, brown grass);
  half matrix + half identity gave neutral asphalt, blue sky, orange car: that is what the script uses.
  Another car or HW revision may need a new fit; repeat it the same way if colours look off.
- Repeaters need only levels and a little saturation.
- Grade in SDR, then let filmkit convert SDR -> HLG like dash-cam footage.
- **Curve limits.** A night clip gives black point 0 and a sunny or snowy one white point 1.0 or more
  (p99.8 above 235). At 0 the curve repeats 0/0 and ffmpeg refuses it; near 1 the 0.92 point crowds 1/1
  and the spline overshoots into inverted, solarised colours (a sunlit Gdansk street, a car wash in
  snow). chain() now keeps the black point at 0.005 or more and the white point at 0.95 or less.
- **Variable frame rate.** Dash-cam files report r_frame_rate like 272500000/7546337; frame-exact work
  (masks, blurs) must count frames, not trust timestamps or r_frame_rate (BACKLOG: blur_plates drift).
- **Compilation of saved events** (TeslaCam film, 2026-11): event.json holds the save time; files are
  one minute per camera named by their start, so save + a .. save + b comes from joining the minute
  files. About 40 of 90 saves showed nothing (parking, the horn at home): look at a tile of the 30 s
  before every save first, and check every scene on frames yourself before writing commentary.
