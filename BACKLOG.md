# Backlog

## blur_plates.py fails on iPhone Live Photo clips

- What: `python scripts/blur_plates.py <footage> <film> IMG_0097` (a 2 s Live Photo movie,
  1920x1440, hevc + pcm audio + 3 data streams) ends with hevc_nvenc "Could not open encoder before
  EOF"; the mask written for it is 1.73 s long while the clip is 1.97 s.
- Where: scripts/blur_plates.py, process(): frame size / rotation handling and the final overlay pass.
- How found: testing the published scripts on 2026-10-31; normal clips (IMG_0115, IMG_0096) work.
- How bad: low. Live Photo movies are rarely used as inserts, and photos can be used instead
  (the still HEIC of the same moment).
