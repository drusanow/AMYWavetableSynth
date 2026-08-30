#!/usr/bin/env python3
"""Build AMY-compatible wavetables for the AMYBoard wavetable synth.

DESKTOP-SIDE UTILITY.  It is not part of the synth -- sketch_wt.py is a single
self-contained file, as the brief requires.  This just makes the .wav files it
loads, because getting the format exactly right is the one real hurdle to using
custom tables.

THE FORMAT, taken from AMY's own render_wavetable() (src/oscillators.c):

  * 16-bit mono PCM .wav
  * 256 samples per cycle (WAVETABLE_SAMPLES_PER_CYCLE)
  * 64 cycles = 16384 samples total, the canonical size
  * AMY needs at least TWO cycles to have something to crossfade between, so
    512 samples is the hard minimum
  * `duty` crossfades linearly from cycle 0 to cycle N-1, which is what the
    synth's POSITION control and its modulation drive

Anything that is a whole number of 256-sample cycles works; 64 is what
wavetable editors emit and what the synth's UI assumes.

Usage:
    python3 tools/make_wavetable.py --all --out wavetables/factory
    python3 tools/make_wavetable.py --from-wav big.wav --out wavetables/user
    python3 tools/make_wavetable.py --list

Copy the results to the SD card as:
    /wavetables/factory/...   and   /wavetables/user/...
"""
import argparse
import math
import os
import struct
import wave

CYCLE = 256
CYCLES = 64
FULL = CYCLE * CYCLES


def _norm(cycle):
    """Scale one cycle to just under full scale, keeping its DC as-is.

    Per-cycle rather than whole-table normalisation: an even level across the
    scan is what makes POSITION read as a timbre change rather than a volume
    ramp."""
    peak = max(abs(min(cycle)), abs(max(cycle)), 1e-9)
    return [v / peak * 0.97 for v in cycle]


# ---- generators: each takes (phase 0..1, morph 0..1) and returns a sample ---

def g_saw_sine(ph, m):
    """Sine at the bottom of the table, saw at the top."""
    return math.sin(2 * math.pi * ph) * (1 - m) + (2 * ph - 1) * m


def g_harmonics(ph, m):
    """Additive: harmonics fade in one after another as the table is scanned."""
    n = 1 + int(m * 15)
    v = 0.0
    for h in range(1, n + 1):
        v += math.sin(2 * math.pi * h * ph) / h
    return v


def g_pwm(ph, m):
    """Pulse whose width sweeps from a narrow spike to a square."""
    duty = 0.5 - 0.45 * (1 - m)
    return 1.0 if ph < duty else -1.0


def g_formant(ph, m):
    """A vocal-ish pair of formants sliding up as the table is scanned."""
    f1 = 1 + m * 5
    f2 = 4 + m * 14
    return (math.sin(2 * math.pi * ph) * 0.6
            + math.sin(2 * math.pi * f1 * ph) * 0.3
            + math.sin(2 * math.pi * f2 * ph) * 0.25 * m)


def g_fold(ph, m):
    """A sine driven progressively into a wavefolder."""
    v = math.sin(2 * math.pi * ph) * (1 + m * 5)
    for _ in range(4):
        if v > 1.0:
            v = 2.0 - v
        elif v < -1.0:
            v = -2.0 - v
    return v


def g_bell(ph, m):
    """Inharmonic partials -- metallic, and very responsive to FM."""
    ratios = (1.0, 2.41, 3.83, 5.17, 7.61)
    v = 0.0
    for i, r in enumerate(ratios):
        amp = 1.0 / (i + 1) * (m if i else 1.0)
        v += math.sin(2 * math.pi * r * ph) * amp
    return v


GENERATORS = {
    "saw_sine": g_saw_sine,
    "harmonics": g_harmonics,
    "pwm": g_pwm,
    "formant": g_formant,
    "fold": g_fold,
    "bell": g_bell,
}


def write_wavetable(path, gen, cycles=CYCLES):
    frames = []
    for c in range(cycles):
        m = c / float(cycles - 1) if cycles > 1 else 0.0
        cycle = [gen(i / float(CYCLE), m) for i in range(CYCLE)]
        frames.extend(_norm(cycle))
    data = struct.pack("<%dh" % len(frames),
                       *[max(-32767, min(32767, int(v * 32767))) for v in frames])
    w = wave.open(path, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(44100)
    w.writeframes(data)
    w.close()
    return len(frames)


def from_wav(src, dst, cycles=CYCLES):
    """Slice an existing mono 16-bit wav into a 64-cycle table.

    The source is read at 256-sample cycle boundaries and resampled by nearest
    neighbour -- crude, but this is a shaping tool, not a converter, and a
    wavetable cycle is 256 samples whatever the source length."""
    r = wave.open(src, "rb")
    n = r.getnframes()
    ch = r.getnchannels()
    if r.getsampwidth() != 2:
        raise SystemExit("source must be 16-bit PCM")
    raw = r.readframes(n)
    r.close()
    all_s = struct.unpack("<%dh" % (len(raw) // 2), raw)
    if ch == 2:
        all_s = all_s[0::2]
        n = len(all_s)
    if n < CYCLE * 2:
        raise SystemExit("source too short: need at least %d frames" % (CYCLE * 2))
    frames = []
    for c in range(cycles):
        start = int(c * (n - CYCLE) / float(max(1, cycles - 1)))
        cycle = [all_s[min(n - 1, start + i)] / 32768.0 for i in range(CYCLE)]
        frames.extend(_norm(cycle))
    data = struct.pack("<%dh" % len(frames),
                       *[max(-32767, min(32767, int(v * 32767))) for v in frames])
    w = wave.open(dst, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(44100)
    w.writeframes(data)
    w.close()
    return len(frames)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="write every built-in shape")
    ap.add_argument("--name", help="write just this shape")
    ap.add_argument("--from-wav", help="slice an existing .wav into a table")
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--cycles", type=int, default=CYCLES)
    ap.add_argument("--list", action="store_true", help="list the built-in shapes")
    a = ap.parse_args()

    if a.list:
        for k in sorted(GENERATORS):
            print(" ", k)
        return
    os.makedirs(a.out, exist_ok=True)
    if a.from_wav:
        dst = os.path.join(a.out, os.path.basename(a.from_wav))
        print("%s -> %s (%d samples)" % (a.from_wav, dst,
                                         from_wav(a.from_wav, dst, a.cycles)))
        return
    names = sorted(GENERATORS) if a.all else ([a.name] if a.name else [])
    if not names:
        ap.error("give --all, --name NAME, --from-wav FILE or --list")
    for nm in names:
        if nm not in GENERATORS:
            raise SystemExit("unknown shape %r (try --list)" % nm)
        dst = os.path.join(a.out, nm + ".wav")
        print("%s (%d samples)" % (dst, write_wavetable(dst, GENERATORS[nm], a.cycles)))


if __name__ == "__main__":
    main()
