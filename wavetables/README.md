# Wavetables

Copy this whole tree to the **root of the SD card**, so the board sees:

```
/wavetables/factory/     shipped tables (regenerate with tools/make_wavetable.py)
/wavetables/user/        your own tables
```

The synth scans both directories at boot and on `<RESCAN WT>` (PATCH page).
Factory tables appear in the UI prefixed `F:`; user tables appear bare.

## Format

Taken from AMY's `render_wavetable()` (`src/oscillators.c`):

* 16-bit mono PCM `.wav`
* **256 samples per cycle**
* **64 cycles = 16384 samples** total (the canonical size the UI assumes)
* minimum 2 cycles / 512 samples — AMY needs two cycles to crossfade between

`POSITION` crossfades linearly from the first cycle to the last, so order your
cycles as a timbral journey rather than a random pile.

Without an SD card the synth still runs: five wavetables are baked into the
firmware and appear as `INT 0`…`INT 4`.
