"""Bake a parameter sweep into JSON so the browser never has to run Python.

This is the "tier 1" applet workflow: the maths happens here, offline, and the
page ships a small table of precomputed curves. Sliders then just pick a frame,
which keeps interaction at display refresh rate with no runtime dependency.

Usage:
    python3 tools/precompute_applet.py

Stdlib only on purpose, so it runs without installing anything.
"""

import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "applets" / "second-order-sweep.json"

OMEGA_N = 1.0          # natural frequency [rad/s]
T_END = 14.0           # simulated horizon [s]
SAMPLES = 201          # points per curve
ZETA_MIN, ZETA_MAX = 0.05, 1.45
FRAMES = 29            # damping ratios in the sweep
DECIMALS = 4           # rounding trades a little accuracy for a lot of bytes


def step_response(t, zeta, wn=OMEGA_N):
    """Unit step response of 1 / (s^2 + 2*zeta*wn*s + wn^2)."""
    if abs(zeta - 1.0) < 1e-9:
        return 1.0 - (1.0 + wn * t) * math.exp(-wn * t)

    decay = math.exp(-zeta * wn * t)
    if zeta < 1.0:
        wd = wn * math.sqrt(1.0 - zeta * zeta)
        return 1.0 - decay * (math.cos(wd * t) + (zeta / math.sqrt(1.0 - zeta * zeta)) * math.sin(wd * t))

    wd = wn * math.sqrt(zeta * zeta - 1.0)
    return 1.0 - decay * (math.cosh(wd * t) + (zeta / math.sqrt(zeta * zeta - 1.0)) * math.sinh(wd * t))


def linspace(start, stop, n):
    if n == 1:
        return [start]
    step = (stop - start) / (n - 1)
    return [start + i * step for i in range(n)]


def main():
    t = linspace(0.0, T_END, SAMPLES)
    zetas = linspace(ZETA_MIN, ZETA_MAX, FRAMES)

    payload = {
        "title": "unit step response, wn = 1 rad/s",
        "x": [round(v, DECIMALS) for v in t],
        "xaxis": "time [s]",
        "yaxis": "output",
        "yrange": [0.0, 2.0],
        "trace": "y(t)",
        "control": {
            "name": "zeta",
            "label": "damping ratio",
            "format": "%.2f",
            "values": [round(z, DECIMALS) for z in zetas],
        },
        "frames": [[round(step_response(v, z), DECIMALS) for v in t] for z in zetas],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {OUT.relative_to(Path.cwd())} "
          f"({len(payload['frames'])} frames x {SAMPLES} samples, {OUT.stat().st_size / 1024:.1f} KiB)")


if __name__ == "__main__":
    main()
