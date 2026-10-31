# vlog-film

An agent skill that edits raw trip and car vlog footage into a finished **HDR (HLG 10-bit) YouTube
film**: a teaser, jump cuts on speech, dash-cam road inserts under music, photo and still inserts
with captions, an animated route map, licence-plate blurring, levelled voice, loudness-normalised
final render, chapters, a thumbnail, face blurring for passers-by, and subtitles in several languages. Then it runs review
rounds: you watch, send notes with times ("12:22 the end of the phrase is cut"), and the agent
checks the source, fixes the edit and rebuilds.

It works with any agent that reads the [Agent Skills](https://agentskills.io) `SKILL.md` format and
can run shell commands: Claude Code, OpenAI Codex, Hermes Agent and others.

Built on, and tested with, one real film: a 24-minute Ukrainian-language farewell to a 2013 Toyota
Yaris (iPhone 10-bit HLG clips, Sony dash-cam timelapse, photos, an OBD Torque screen recording).
`references/example_yaris.py` is that film's complete edit.

> Українською: це скіл для агентів (Claude Code, Codex, Hermes), який монтує відео з поїздок у
> готовий HDR-фільм для YouTube: тизер, склейки по мовленню, вставки з відеореєстратора під музику,
> фото з підписами, анімована карта маршруту, розмиття номерів, вирівняна гучність, розділи,
> обкладинка і субтитри кількома мовами. Встановлення нижче: агент може зробити його сам.

## Maintenance

This is a personal project shared as-is. **I may not have time to review pull requests or answer
issues.** Please fork or clone it and adapt it to your needs; ideas and wishes are welcome as issues,
with no promise of a reply.

## What you need

| | Tested with | Why |
|---|---|---|
| OS | Windows 11 | macOS / Linux should work with small changes (fonts, encoder), untested |
| GPU | NVIDIA RTX 3090 (24 GB) | WhisperX speech recognition (CUDA), hevc_nvenc encoding, libplacebo (Vulkan) |
| Python | 3.11 | scripts; a venv with WhisperX, torch (CUDA 12.8), onnxruntime-gpu, OpenCV, pillow-heif |
| ffmpeg | 9.0 "full" build (gyan.dev) | needs libplacebo, Vulkan, hevc_nvenc or libx265 |
| Shotcut | 26.x (its `melt`) | the final render of the MLT project; you can also open the project in Shotcut |
| Disk | ~10 GB | venv with torch and models, plus renders |
| Music | YouTube Audio Library tracks | safe for monetised videos |

Speech recognition models (WhisperX large-v3, ~3 GB) download on first use. The licence-plate
detector is [morsetechlab/yolov11-license-plate-detection](https://huggingface.co/morsetechlab/yolov11-license-plate-detection)
(AGPL-3.0), and faces are found with OpenCV's [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
(MIT); both are downloaded by the setup script, not included here.

## Install

Easiest: open your agent and say *"install the vlog-film skill from https://github.com/vstoos/vlog-film"*.
It can follow the steps below; the setup script checks everything first and installs only after
you agree.

By hand:

```bash
git clone https://github.com/vstoos/vlog-film.git C:/Data/vlog-film
cd C:/Data/vlog-film
python setup/setup.py              # check: what is there, what is missing
python setup/setup.py --install    # install missing parts (winget on Windows), create .venv, download the plate model
python setup/install_skill.py      # make the skill visible to Claude Code, Codex, Hermes, ...
```

`setup.py --install` on Windows uses `winget` for ffmpeg (`Gyan.FFmpeg`) and Shotcut
(`Meltytech.Shotcut`), creates `.venv` with torch from the PyTorch CUDA index and the packages in
`setup/requirements.txt`, downloads the plate model and writes `config.json` with all paths. On
macOS / Linux it prints the commands for system programs instead of running them. Already have a
Python with these packages? `python setup/setup.py --python <path-to-python>`.

### Where each agent looks for skills

`install_skill.py` links the repository into every one of these that exists, so `git pull` updates
all of them:

| Agent | Skills folder |
|---|---|
| Claude Code (CLI, desktop, IDE) | `~/.claude/skills/vlog-film` |
| OpenAI Codex CLI | `~/.codex/skills/vlog-film` |
| Hermes Agent | `~/.hermes/skills/vlog-film` |
| others reading SKILL.md | `~/.agents/skills/vlog-film`, or point the agent at `SKILL.md` |

An agent without skill support can still use it: tell it "read C:/Data/vlog-film/SKILL.md and
follow it".

### Personal settings

- `config.json`: machine paths, written by `setup.py`; edit `music_dir`, `language` (speech
  language for WhisperX, default `uk`), `hevc_encoder` (`hevc_nvenc`, `libx265`,
  `hevc_videotoolbox`), `gpu` (CUDA index) as needed. Environment variables `VF_<KEY>` override it.
- `user.md` (optional, not committed): who you are and how you like to work, e.g. the language the
  agent should answer in, your referral links, your thumbnail style. The skill reads it at the start.

## Use

Put a trip's footage in a folder (phone clips, photos, a `Road/` folder with dash-cam files), then
ask the agent: *"зроби фільм з відео в C:/Users/me/Videos/250920_trip"* / *"make a YouTube film from
the footage in ..."*. It inventories and transcribes the clips, proposes a structure, builds,
renders and checks the film, then works through your notes. See `SKILL.md` for the full workflow.

## What is inside

```
SKILL.md                 the workflow the agent follows
scripts/filmkit.py       builds the film: talk cutting on word times, inserts, captions, music, MLT
scripts/render_final.py  melt render, two-pass loudness to -14 LUFS, HDR and green-frame checks
scripts/blur_plates.py   licence-plate (and optional face) detection and blur, 10-bit HLG
scripts/transcribe_*.py  WhisperX word-timed transcripts (whole clips, short windows)
scripts/make_subs.py     subtitles from the finished film
scripts/make_thumb.py    thumbnail with headline
scripts/timeline.py      film time <-> source clip time, chapters
scripts/media_server.py  read-only phone viewer for renders (also: github.com/vstoos/media-server)
scripts/scan_meta.py, contact_sheet.py, roll_lr.py, vfconfig.py
references/              project template, the Yaris example, lessons learned, YouTube notes, route map
setup/                   setup.py, install_skill.py, requirements.txt
```

## Licence

Code and documentation: MIT (see LICENSE). The licence-plate model has its own AGPL-3.0 licence;
music, fonts and map tiles keep theirs (the route map example uses EOX Sentinel-2 cloudless,
CC BY 4.0, and OpenStreetMap / OSRM data).
