# Dubbing in the user's own voice

An extra audio track for YouTube: the film's subtitles spoken in the user's cloned voice over the
film's own road and music. Built on the Yaris film (Ukrainian to Polish and English, 24 min).
A cloned voice needs "AI use: yes" on upload. Only clone the user's own voice.

Polish, English and Ukrainian work (speakable() in dub.py writes out numbers for these). Another
language needs its own speakable(). Ukrainian is for voice-over on silent footage (dash-cam clips):
the same .srt route, with the commentary written as subtitles.

## The voice model: Higgs TTS 3 (default)

Chosen by the user on 06.11.2026 over Chatterbox ("two heads above"), StyleTTS2 and HolosTTS:
Higgs TTS 3 (Boson AI, `bosonai/higgs-tts-3-4b`) through vLLM-Omni, offline, `scripts/higgs_tts.py`.
`--engine chatterbox` still works (the old route, with --cfg / --exag).

- **The reference must be in the language spoken.** From the Ukrainian reference, Polish came out
  accented with a glitch after every word; from a Polish recording of the user, clean. Chatterbox has
  no Ukrainian at all (through its Russian model: a heavy Russian accent).
- **The user's voices** are in `C:/Data/voices` (config `"voices_dir"`): `<lang>.wav`, its exact
  transcript in `<lang>.txt` and in `voices.json`. Pass `-` as the reference to use them. Private:
  never commit or upload them. A new one: 10-20 s in a parked car or a quiet room, the user's normal
  tone, cut on whole sentences, transcript checked with WhisperX, numbers written as spoken.
- **Licence.** Research/non-commercial, plus a Creator Use Grant: monetised videos on the user's own
  channel are allowed if the video's description visibly credits **"Boson AI's Higgs Audio"** (put it
  in every description of a film with a Higgs track). Higgs output must not train other speech models.
- Loading takes 1-2 min per run, so gen and regen send all lines in one run (batched per seed).

## Setup

Three Pythons: the main one (WhisperX, `dub_check.py`), `"dub_python"` for dub.py (num2words,
soundfile, demucs; chatterbox-tts for the old engine), and a Linux venv for Higgs. vLLM-Omni is
Linux-only; on Windows it lives in WSL (Docker is not needed):

```
# in WSL Ubuntu, no sudo needed
uv venv ~/higgs/.venv -p 3.12 && source ~/higgs/.venv/bin/activate
uv pip install vllm==0.32.0 --torch-backend=cu130 && uv pip install vllm-omni==0.32.0
vllm download-kernels        # FlashInfer cubins; without them it wants nvcc and dies at start
HF_HOME=~/higgs/hf uvx --from "huggingface_hub[cli]" hf download bosonai/higgs-tts-3-4b   # 9.3 GB, not gated
```

config.json: `"tts_engine": "higgs"`, `"voices_dir"`, `"higgs_distro": "Ubuntu"`, `"higgs_venv"`,
`"higgs_hf_home"`, `"higgs_gpu"` (the nvidia-smi index of the 24 GB card; it takes about 85% of it).
The index changes with boot order and when an eGPU is plugged in: check it against nvidia-smi before
every run, and that the card is free (references/lessons.md, "GPUs and hardware encoders").

## Steps

1. **Reference voice.** The saved one (`-`) unless the user wants another. From footage:
   `python $K/dub_find_refs.py <footage> <project>/transcripts --cut ref 8` ranks stretches of the
   user's speech by voice over noise; generate one sentence per reference, let the user choose by ear.
   Recording at a stop beats anything from the road, which adds artifacts. For another language ask
   the user to record one (above): it beats any reference in the film's language.
2. **Pronunciation.** `<out>/say.json`: `{"pl": {"GPS": "dzi pi es"}, "en": {"Katowice": "Katoveetseh"}}`.
   Names, abbreviations, clock times. Fix them here, and only regenerate those sentences.
3. **Generate.** `$D $K/dub.py gen <subs.srt> - <out> --lang pl --takes 3`. Long: run it in the
   background. Interrupted, run the same command again: finished takes are kept. With
   `--engine chatterbox`: `--cfg 0.3 --exag 0.8`, and two runs fit on 24 GB (give each a time range,
   then `$D $K/dub_merge.py <subs> <out> <part>...` with DUB_LANG set). `CUDA_DEVICE_ORDER=PCI_BUS_ID`
   makes CUDA_VISIBLE_DEVICES match nvidia-smi.
4. **Check.** `python $K/dub_check.py <out> <lang>`: every take, in the background; finished takes are skipped.
5. **Fix.** `$D $K/dub_regen.py <out> - --lang pl` makes new takes for sentences with no
   clean take and for changed text, then run the check again. Repeat while it finds sentences; `--dry` lists them.
6. **Mix.** `$D $K/dub.py mix <film.mp4> <out> --slow 0.92`. `--slow` is for a language shorter than
   the original (English from Ukrainian), so the voice stops less between lines. The log ends with
   lines off their subtitles and flags left on the chosen takes: **those are the list to listen to**.
7. Upload `dub.wav`. The user listens to `preview.mp4` first.

`$D` is the dub Python. A changed line: edit the .srt and "text" in manifest.json, then steps 5, 4, 6.

## What the model gets wrong, and what catches it

Higgs traps found while wiring it in:
- vLLM-Omni returns a batch in the order the lines finish, not the order sent: takes landed on the
  wrong sentences (every take flagged, score 0.1). higgs_tts.py sorts by the request id's index.
- The pipeline's sampling has a fixed seed (42), so repeated takes of a line were identical;
  higgs_tts.py sets the seed per batch (take k of every line: seed 7 + k; regen 100 + k).
- The HTTP server (`vllm serve ... --omni`) started in WSL but refused every connection, even from
  WSL itself; the offline engine has no network and works.
- A root-owned `~/.cache/huggingface/hub/.locks` in WSL broke downloads: give each venv its own HF_HOME.
- The example script names output files from the Latin letters of the text: every Cyrillic line was
  "prompt.wav", each overwriting the last.

Chatterbox with low cfg and high exaggeration sounds most like the person, but about half the takes
run on after the sentence: a pop like a cork, a hum, or the sentence again. Fragments shorter than a
sentence lose words, which is why cues are joined into sentences first.

| Glitch | Caught by |
|---|---|
| Runs on after the last word | aligning the wanted text; the take is cut 0.15 s after its last word |
| Runs on after a pause | drop_tail(): the aligner counts it as the last word, so hear the take without it |
| Mains hum on every line | HUM_FILTER in mix: 70 Hz high-pass and 50/100 Hz notches |
| Buzz, clicks, squeaks in pauses | clean(): mutes everything that is not speech |
| Repeats, invented words | `extra`: heard words against the text, repeated word runs |
| Swallowed words | `missing` |
| Sound between words that survived | `stray`: 120+ ms of sound outside all aligned words |
| Click inside speech | `pop`: 22+ dB jump within 5 ms, gone in 40 ms |
| Click at a line's end ("like a radio") | load(): drops the last 60 ms (TAIL), 60 Hz high-pass, raised-cosine fades 15 ms in / 80 ms out. See below |
| Hiss floor 20 dB under the voice | load(): denoise(), stationary spectral subtraction; the gate then has nothing to switch on and off |
| Stalls, rushed or dragged takes | `gap`, `pace` |

Measured on the Yaris film: at every spot the listener reported a sound after a sentence, the take
ran 0.3-2.5 s past its last word. Of clicks and hums put into 60 clean takes, 46 and 60 were caught,
and the same 60 takes without them raised nothing. About 6% of takes were flagged, and 0 of 263 and
2 of 265 sentences had no clean take. Flags on a track the listener liked were 9 of 263 lines, so
they are a list to listen to, not proof: a name heard differently (Yaris, Jaris) raises `missing`.
None of this judges how natural the voice sounds, and quiet glitches inside a word can pass. The ear
stays last.

The radio click, measured on the TeslaCam film (Ukrainian, 148 Higgs takes, voice over silence):
- Higgs ends a take on the last word with no silence after it (133 of 148: file end = aligned word
  end), and the codec decodes its last frames without look-ahead: the last 60 ms rise 4 dB (p90 14 dB)
  with a DC step. That burst, cut off, is the radio click. Text endings ("...", an extra word, a blank
  line) did not give the model a quiet tail; dropping the 60 ms did.
- Every take also had a hiss/rumble floor about -20 dB under the voice (the reference: -44 dB); gating
  it in pauses sounded like a squelch. denoise() brings it to about -42 dB.
- HUM_FILTER's narrow notches ring for 0.5 s after each line (-50 down to -98 dBFS): masked under road
  noise, audible over silence. Over silent footage use only the high-pass.
- Check of the finished track: per line end, level 20-300 ms after it and any jump; clicks over the
  whole track as 8 kHz steps far above their surroundings. The same takes through the old load():
  30 of 37 line ends and 34 clicks; through the new one: 0 and 0.
- A one-word sentence at the start of a line ("Sarny. Here is why...") was dropped in all takes, and
  recognition missed it too, so no flag: put such words inside a sentence.

Traps from the way there:
- Align the wanted text, not the heard text: heard numbers come as digits, get no timing, and the cut
  falls before them.
- Word match alone picks takes with junk after the sentence, because recognition ignores junk.
- Among equal takes prefer the shortest. Preferring the length nearest the cue picked the junk-padded ones.
- HUM_FILTER assumes a mains frequency of 50 Hz and a man's voice; change it for 60 Hz or a higher cut
  would thin the voice. On the Yaris film the 49.8 Hz tone went from 15 dB over its neighbours to under 1 dB.
- Polish years after a preposition need the ordinal in say.json: "z 2013 roku" is "z dwa tysiące
  trzynastego roku"; num2words gives the cardinal, which sounds wrong to a native ear.
- Recognition does not catch mispronounced names: it wrote "Port" and "Katowice" where the user heard
  "Porter" and "Katowece". Those come from the user's ear. A say.json entry applies in its order, so a
  line-specific key ("Katowice has another") goes before the general one. Spell abbreviations as letters
  ("G P S"). For an extra syllable, generate 6 takes and keep the one whose aligned word is shortest.
- Read the manifest before generating: every line that starts in lower case or ends without a full stop.
  sentences() now carries a cue with no end punctuation over any pause, but a stop put in the wrong place
  ("1-2 kilometry." / "Na godzine."), a one-word orphan and a comma break before "ze" still split a
  phrase, and the dub then pauses in the middle of it. Fix the text in manifest.json; dub_regen.py picks
  up the change. Splitting differently is fine too, when the joined line would run far past its cue.
- clean() has two thresholds that took tuning: too weak leaves buzz at -20 dB, too strong clips words.
- Level each line to the same words in the original (Demucs vocals) plus about 2 dB, not to one
  target: a voice raised over the motorway has to stay raised.
- np.arange times a sample rate overflows 32-bit ints on Windows; the sign is words repeating.
- A long run-on sentence ends early: sentences() breaks them at a comma after 9 s.
- A longer subtitle pushes all following lines late. Shorten the lines after it, in subtitles too.
- Subtitle writing for dubbing: numbers read aloud are long; "4.6-4.8 litres per 100" takes 4 s.
