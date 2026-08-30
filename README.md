# AMYBoard Advanced Wavetable Synth

A 4-voice / 8-oscillator MicroPython wavetable synthesizer for the
[AMYboard](https://github.com/shorepine/amy), built on the AMY audio engine.
The whole synth is one file: **`sketch_wt.py`**.

Designed against the actual AMY source (`shorepine/amy`) and the lessons from
the earlier Megatron 8-oscillator virtual-analog sketch (`sketch_va8.py`) — the
oscillator-chain rules, the SILENT filter head, the freq-coefficient detune
trick and the OLED driver workaround all carry over verbatim.

```
per voice (5 AMY oscillators)          4 voices = 20 oscs, 8 sounding

  HEAD (SILENT) ── filter · filter drive · voice pan · MOD4 envelope
    │ chained_osc
  OSC A (WAVETABLE) ── position · pitch · level · drive/fold · amp EG · MOD3
    │ chained_osc
  OSC B (WAVETABLE) ── ditto

  MOD1 osc (silent) ─┐ mod_source of HEAD / A / B → mod0 coefficient
  MOD2 osc (silent) ─┘                            → mod1 coefficient
```

## Getting started

1. Copy `sketch_wt.py` to the board and run it. It boots, scans for wavetables
   and starts listening on MIDI channel 1.
2. Copy the `wavetables/` tree to the SD card root, so the board sees
   `/wavetables/factory/...` and `/wavetables/user/...`.
3. From the REPL: `status()`, `wt_list()`, `matrix_list()`, `wt_selftest()`.

Without an SD card it still works — five wavetables are baked into the
firmware and appear as `INT 0`…`INT 4`.

### Check your firmware first

`wave=WAVETABLE` is compiled in only with `-DAMY_WAVETABLE`. It is on in AMY's
own Makefile and `setup.py`, but the AMYboard MicroPython firmware is built
from the tulipcc tree, which could not be inspected here. Run:

```python
wt_selftest()
```

It plays a note, reads AMY's own rendered output back and reports the peak.
Near-silence means the flag is missing — set `WT_ENABLED = False` and re-run
`boot()`; the two oscillators fall back to a saw and everything else (filter,
envelopes, matrix, unison, FX) keeps working.

## Voice modes

Four **separate AMY synths**, one per voice — not one synth with four voices.
That is load-bearing: a command addressed to a synth is routed to the matching
oscillator in *every* one of its voices, so a single 4-voice synth cannot hold
four different detunes or pans. The three modes are then just allocation
policies over one fixed set of AMY objects, so switching mode allocates
nothing and cuts no notes.

| mode | behaviour |
|------|-----------|
| **MONO** | voice 0 only, last-note priority, legato (no retrigger while a key is held), portamento via `GLIDE` |
| **4× UNISON** | one note across all four voices, each with its own detune, pan, start phase and wavetable-position offset |
| **4-VOICE POLY** | four independent notes, oldest-voice stealing |

`DETUNE 15` gives exactly the brief's spread: **−15 / −5 / +5 / +15 cents**.

## Modulation

Four modulators, freely routable to eleven destinations, every routing with its
own amount and polarity. The matrix is evaluated in Python **once per parameter
change or note** and turned into AMY ControlCoefficients; AMY's DSP then applies
it at audio rate. There is no per-sample arithmetic anywhere in the file.

| slot | what it is | reaches |
|------|-----------|---------|
| **MOD1** | oscillator → `mod0` coefficient | everything |
| **MOD2** | oscillator → `mod1` coefficient | everything |
| **MOD3** | envelope (`eg1` on OSC A/B) | oscillator destinations |
| **MOD4** | envelope (`eg1` on the head) | filter destinations — this **is** the filter envelope |

MOD1/MOD2 each have a **RATE MODE**: as `LFO` they are ordinary low-frequency
modulators (6 shapes, free rate or tempo-synced, per-note phase retrigger); as
`AUDIO` they track the played note by ratio and become **FM/RM operators**.
Routed to pitch that is FM; routed to level it is ring modulation.

Destinations: `A.POS`, `B.POS`, `A.PIT`, `B.PIT`, `A.LVL`, `B.LVL`, `A.DRV`,
`B.DRV`, `CUT`, `F.DRV`, `PAN`. Adding another is one row in the `DESTS` table
plus one branch in the coefficient builder.

**Wavetable position is AMY's `duty` coefficient list.** That single fact is
what makes this design cheap: position scanning is modulated inside AMY's DSP
by envelopes and LFOs at zero MicroPython cost.

## Pages

`OSC A · OSC B · MIX · FILTER · ENV · MOD 1 · MOD 2 · MOD 3 · MOD 4 · MATRIX ·
UNISON · DRIVE · FX · REVERB · PATCH`

Turn to move, click to edit, **hold to pick a screen**. On an 8-encoder board
each encoder edits its own row directly. Every page carries a picture of what
its settings are doing — the output oscilloscope on MIX, the filter response
curve, ADSR shapes, LFO waveforms, the live matrix grid, the unison spread and
the distortion transfer curve.

## Patches

Named snapshots in `/user/wt_patches.json`, holding the parameters, the
modulation matrix, and **the two wavetables by filename** — never by index and
never as embedded waveform data. A patch keeps working when the card gains or
loses tables, and a missing table is reported rather than silently becoming
whatever now sits at the old index.

## Custom wavetables

AMY expects **16-bit mono PCM, 256 samples per cycle, 64 cycles = 16384
samples**. `tools/make_wavetable.py` builds them (a desktop-side utility — the
synth itself remains one file):

```bash
python3 tools/make_wavetable.py --all --out wavetables/factory
python3 tools/make_wavetable.py --from-wav yourfile.wav --out wavetables/user
```

Tables are loaded into AMY RAM presets on demand through a 4-slot LRU cache, so
a patch loads the two tables it names and nothing else. Loading is slow (a
16384-sample table is ~175 wire messages), so it only ever happens on an
explicit table selection or patch load, with the voices silenced first — never
from `loop()`.

## What AMY cannot do, and what is here instead

Every one of these was checked in the AMY source rather than assumed. The full
reasoning, with file and line references, is in the `AMY CAPABILITY NOTES`
block at the top of `sketch_wt.py`.

| requested | status | what is provided |
|-----------|--------|------------------|
| Oscillator sync | **not in AMY** — no hard sync anywhere in `src/` | `PH.SYNC`: both wavetables lock to a fixed start phase on every note-on, giving the phase-coherent attack sync is usually reached for |
| Audio-rate FM/RM between two wavetables | **not in AMY** — the `ALGO` FM engine takes only SINE operators; `mod_source` is control-rate (per audio block) | MOD1/MOD2 in `AUDIO` mode as shared FM/RM operators. Keeps both wavetables audible — routing OSC B into OSC A would work but `mod_source` *silences* the source |
| Filter resonance modulation | **not possible** — `resonance` is a plain float, not a coefficient list | static per patch; the matrix shows the pair as unreachable rather than pretending |
| Modulating an FX parameter or an FM amount | **not possible** — bus FX have no per-note modulation inputs, and AMY cannot modulate a coefficient. Mod-source oscs are also skipped by the note handlers, so they cannot carry an envelope | route MOD3/MOD4 to carrier pitch or level alongside the FM operator |
| Per-oscillator pan | **inert inside a chain** — AMY pans the summed chain once, through the head | pan is per *voice*, which is exactly what the unison stereo spread needs — and is only reachable because of the four-synth layout |
| Bipolar envelope / unipolar LFO | AMY EGs run 0..1, oscillators swing ±1 | both polarities delivered exactly, by compensating the destination's const term against the routing depth. Amplitude is the documented exception (amp coefficients combine in the log domain) |

## Performance

* No per-sample or per-block work in Python. `loop()` polls input, redraws on
  change, and services the optional analogue drift (≤8 messages, and only when
  `DRIFT` is turned up).
* All envelopes are AMY breakpoint sets; all effects are AMY's own bus FX. There
  is no custom C DSP slot at all, unlike the Megatron build.
* Parameter changes are **targeted**: turning `CUTOFF` sends 4 messages (one
  head per voice), not a rebuild of 20 oscillators, and never touches
  envelopes, phase or allocation — so a held note keeps sustaining.
* Full reallocation happens only at boot, on `PANIC`, on a patch load, and for
  the two controls that genuinely cannot take effect any other way (`PH.SYNC`
  and the per-oscillator start phases).
* `cpu_status()` reports AMY's own render load.

## Testing

The synth was exercised under a stub AMYboard environment in which every
`amy.send()` is validated by AMY's **real** `amy.message()` wire-protocol
builder — so unknown keywords, malformed coefficient lists and bad breakpoint
strings fail loudly rather than silently at runtime.

Covered: every page and row bumped to both rails; all three voice modes
including stealing and stuck-note checks; the polarity maths for all four
source/polarity combinations; scope enforcement; the filter's Nyquist ceiling;
patch save/load/rename/delete including a patch that predates a parameter;
MIDI including malformed and wrong-channel messages; SD scanning, the LRU
cache, a corrupt file, a vanished table and catalogue reordering; and drawing
all 15 screens. **3894 wire messages validated.**

Hardware verification — audio, the OLED panel and the encoders — has not been
done and is the remaining step.
