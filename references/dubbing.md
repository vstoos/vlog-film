# Dubbing in the user's own voice

An extra audio track for YouTube: the film's subtitles spoken in the user's cloned voice over the
film's own road and music. Built on the Yaris film (Ukrainian to Polish and English, 24 min).
A cloned voice needs "AI use: yes" on upload. Only clone the user's own voice.

Polish and English work now (speakable() in dub.py writes out numbers for these two). Another
language needs its own speakable().

## Setup

The model and WhisperX do not fit one Python, so this uses two. Make a second venv and put it in
config.json as `"dub_python"` (torch 2.6 cu124 worked; `chatterbox-tts`, `demucs`, `num2words`,
`soundfile`). Everything `dub_check.py` needs is in the main Python.

## Steps

1. **Reference voice.** `python $K/dub_find_refs.py <footage> <project>/transcripts --cut ref 8` ranks
   stretches of the user's speech by voice over noise. Generate one sentence per reference, let the
   user choose by ear. Recording at a stop beats anything from the road, which adds artifacts. Look at
   the chosen reference's spectrum too: the model copies its hum into every line (see below).
2. **Pronunciation.** `<out>/say.json`: `{"pl": {"GPS": "dzi pi es"}, "en": {"Katowice": "Katoveetseh"}}`.
   Names, abbreviations, clock times. Fix them here, and only regenerate those sentences.
3. **Generate.** `$D $K/dub.py gen <subs.srt> ref/ref.wav <out> --lang pl --takes 3 --cfg 0.3 --exag 0.8`
   Long: run it in the background. On a 24 GB card two runs fit (give each a time
   range, then `$D $K/dub_merge.py <subs> <out> <part>...` with DUB_LANG set), and a 6 GB card fits one
   with 20-30% of the film. `CUDA_DEVICE_ORDER=PCI_BUS_ID` makes CUDA_VISIBLE_DEVICES match nvidia-smi.
4. **Check.** `python $K/dub_check.py <out> <lang>`: every take, in the background; finished takes are skipped.
5. **Fix.** `$D $K/dub_regen.py <out> ref/ref.wav --lang pl` makes new takes for sentences with no
   clean take and for changed text, then run the check again. Repeat while it finds sentences; `--dry` lists them.
6. **Mix.** `$D $K/dub.py mix <film.mp4> <out> --slow 0.92`. `--slow` is for a language shorter than
   the original (English from Ukrainian), so the voice stops less between lines. The log ends with
   lines off their subtitles and flags left on the chosen takes: **those are the list to listen to**.
7. Upload `dub.wav`. The user listens to `preview.mp4` first.

`$D` is the dub Python. A changed line: edit the .srt and "text" in manifest.json, then steps 5, 4, 6.

## What the model gets wrong, and what catches it

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
| Stalls, rushed or dragged takes | `gap`, `pace` |

Measured on the Yaris film: at every spot the listener reported a sound after a sentence, the take
ran 0.3-2.5 s past its last word. Of clicks and hums put into 60 clean takes, 46 and 60 were caught,
and the same 60 takes without them raised nothing. About 6% of takes were flagged, and 0 of 263 and
2 of 265 sentences had no clean take. Flags on a track the listener liked were 9 of 263 lines, so
they are a list to listen to, not proof: a name heard differently (Yaris, Jaris) raises `missing`.
None of this judges how natural the voice sounds, and quiet glitches inside a word can pass. The ear
stays last.

Traps from the way there:
- Align the wanted text, not the heard text: heard numbers come as digits, get no timing, and the cut
  falls before them.
- Word match alone picks takes with junk after the sentence, because recognition ignores junk.
- Among equal takes prefer the shortest. Preferring the length nearest the cue picked the junk-padded ones.
- HUM_FILTER assumes a mains frequency of 50 Hz and a man's voice; change it for 60 Hz or a higher cut
  would thin the voice. On the Yaris film the 49.8 Hz tone went from 15 dB over its neighbours to under 1 dB.
- Polish years after a preposition need the ordinal in say.json: "z 2013 roku" is "z dwa tysiące
  trzynastego roku"; num2words gives the cardinal, which sounds wrong to a native ear.
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
