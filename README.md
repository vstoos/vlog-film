# vlog-film

An agent skill that turns your own amateur footage (a talking-head vlog, a review, a trip, a family
event) into a finished **HDR (HLG 10-bit) YouTube film**: a teaser, jump cuts on speech, inserts under
music (dash-cam road, b-roll, photos and stills with captions), an animated route map, licence-plate
and face blurring, levelled voice, loudness-normalised final render, chapters, a thumbnail, subtitles
in several languages, dubbed audio tracks in your own cloned voice with automatic glitch checks,
vertical Shorts and the upload to YouTube. Then it runs review rounds: you watch, send notes with
times ("12:22 the end of the phrase is cut"), and the agent checks the source, fixes the edit and
rebuilds.

**Everything runs on your own computer.** No cloud video editor, no upload of your footage to a
service to cut it: transcription (WhisperX), plate and face blur, inserts, the edit, the HDR render
and even the dubbing in your own voice run locally, on your files, with free tools (ffmpeg,
Shotcut/melt, Python). Your raw clips never leave the machine until you publish the finished film.
What the agent's model does see: transcripts, small contact sheets of frames it looks at, and the
texts it writes (descriptions, subtitles), as with any chat with it. Optional exceptions, only when
you ask for them: an AI-improved thumbnail (Gemini) and the upload to YouTube.

The value is less in any one script than in the toolset and the experience written into it: what
went wrong on real films and how it was fixed (`references/lessons.md`). Car and trip footage is
where it was built, not a limit: with small changes it fits other amateur video. Ask your agent to
adapt it to your footage and your channel.

It works with any agent that reads the [Agent Skills](https://agentskills.io) `SKILL.md` format and
can run shell commands: Claude Code, OpenAI Codex, Hermes Agent and others.

Built on, and used every week for, the films and Shorts of the author's channel
[VS EV studies](https://www.youtube.com/@VSEVstudies) (Ukrainian, with Polish subtitles and dubs):
car reviews and pros-and-cons vlogs (a Mercedes GLC after a Tesla:
[gn_0TBRrO3s](https://youtu.be/gn_0TBRrO3s)), long trips ([z4BJ2E-rEJA](https://youtu.be/z4BJ2E-rEJA)),
farewell films. Sources: iPhone 10-bit HLG clips, Sony and Tesla dash-cams, photos, phone screen
recordings. `references/example_yaris.py` is one finished film's complete edit.

> Українською: це скіл для агентів (Claude Code, Codex, Hermes), який монтує любительське відео у
> готовий HDR-фільм для YouTube: тизер, склейки по мовленню, вставки під музику, фото з підписами,
> карта маршруту, розмиття номерів і облич, вирівняна гучність, розділи, обкладинка, субтитри й
> озвучка кількома мовами, шортси і завантаження на канал. Зроблено й перевірено на відео каналу
> [VS EV studies](https://www.youtube.com/@VSEVstudies): огляди авто, влоги, поїздки. Головне в ньому -
> інструменти й досвід реального монтажу; під своє відео його можна пристосувати невеликими правками.
> Уся обробка відео локальна, на вашому комп'ютері: жодного хмарного відеоредактора, сирі кліпи
> нікуди не завантажуються. Модель агента бачить лише розшифровки, невеликі аркуші кадрів і тексти.
> Встановлення нижче: агент може зробити його сам.

## Maintenance

This is a personal project shared as-is. **I may not have time to review pull requests or answer
issues.** Please fork or clone it and adapt it to your needs; ideas and wishes are welcome as issues,
with no promise of a reply.

## What you need

| | Tested with | Why |
|---|---|---|
| OS | Windows 11 | macOS / Linux should work with small changes (fonts, encoder), untested |
| GPU | NVIDIA RTX 3090 (24 GB) and RTX 3060 Laptop (6 GB) | WhisperX speech recognition (CUDA), hevc_nvenc encoding, libplacebo (Vulkan); a weaker card or none works too, see below |
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

### Weaker hardware

The RTX 3090 is what it was built on, not what it needs. Most of the work is the agent's own: looking
at contact sheets, reading transcripts, planning the story, writing the edit, captions, description
and subtitles. That runs on any laptop. What the hardware changes is how long the machine jobs take:

| Job | NVIDIA RTX 3060 / 4060 class (6-12 GB) | AMD Radeon or Intel Arc (8 GB+) | Apple Silicon (M1 and later, 16 GB+) | No usable GPU (CPU only) |
|---|---|---|---|---|
| Inserts, cards, HDR conversion (ffmpeg + libplacebo) | works (Vulkan) | works (Vulkan) | libplacebo through MoltenVK, untested | integrated graphics usually have Vulkan; slower |
| Encoding | hevc_nvenc, tested on a 3060 Laptop: almost as fast as the 3090 | libx265 today; ffmpeg's hevc_amf / hevc_qsv need a branch in `vfconfig.hevc_args()` | hevc_videotoolbox (already in `vfconfig`) | libx265: several times slower, fine overnight |
| Speech recognition | WhisperX large-v3 fits in 6 GB with `compute_type="int8_float16"` or batch 4-8 | WhisperX (faster-whisper) has no AMD / Intel GPU backend on Windows: CPU, or whisper.cpp with its Vulkan backend on the card (word times coarser, the scripts need adapting) | whisper.cpp (Metal) or mlx-whisper on the GPU; WhisperX on the CPU | WhisperX on the CPU, `compute_type="int8"`, model `medium`: hours for an hour of talk |
| Plate and face blur | works | CPU, slower | CPU, slower | CPU, slower |
| Final render (melt) | NVENC | libx265 | hevc_videotoolbox or libx265 | libx265 |
| Dubbing in your own voice (Higgs TTS 3, 4B, 9.3 GB of weights) | tested on 24 GB; 12 GB may fit in theory (a lower vLLM memory share), 6-8 GB no | vLLM runs on ROCm under Linux only: AMD 16 GB+ in theory | no vLLM on macOS; in theory PyTorch on Metal with enough unified memory | no |

**Tested only on NVIDIA RTX 3090 and RTX 3060 Laptop under Windows 11.** Everything else in the table
is what the tools support on paper; expect the agent to adapt scripts on the first run.

- Today `transcribe_all.py` and `transcribe_window.py` load WhisperX on CUDA; on a machine without an
  NVIDIA card ask the agent to switch them to `"cpu"` with `compute_type="int8"` (or to whisper.cpp),
  and set `"hevc_encoder"` in config.json (`libx265`, or `hevc_videotoolbox` on a Mac; setup.py picks
  libx265 when it finds no NVIDIA card).
- Laptop NPUs (Intel, AMD, Qualcomm) are not used by these tools. Apple Silicon is different: its GPU
  shares the system memory (unified memory), so a Mac with 16-32 GB can run models a 6-8 GB graphics
  card cannot.
- melt and Shotcut exist for Windows, macOS and Linux, and the MLT project is plain XML, but this skill
  has only rendered on Windows: fonts and paths may need fixing elsewhere.

The skill tells the agent to check the machine and adapt the scripts to it (SKILL.md, "Before you start").

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
