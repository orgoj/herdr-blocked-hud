"""The HUD's own sounds, generated as WAV so they differ from the desktop theme.

Blocked: two quick high two-tone calls (urgent). Done: a soft rising chime.
"""

from __future__ import annotations

import io
import math
import os
import pathlib
import struct
import wave

BUILTIN = "builtin"
RATE = 44100
# Bump when a pattern changes, so a cached file from an older version is not reused.
VERSION = 1

# (frequency Hz or 0 for silence, duration s, decay per second)
PATTERNS: dict[str, list[tuple[float, float, float]]] = {
    "blocked": [
        (1319.0, 0.09, 0.0), (988.0, 0.09, 0.0), (0.0, 0.08, 0.0),
        (1319.0, 0.09, 0.0), (988.0, 0.09, 0.0),
    ],
    "done": [(523.0, 0.14, 6.0), (659.0, 0.14, 6.0), (784.0, 0.40, 5.0)],
}

AMPLITUDE = 0.45
FADE_S = 0.005


def render(kind: str) -> bytes:
    """Mono 16-bit WAV bytes for `kind` ("blocked" or "done")."""
    samples = bytearray()
    for frequency, duration, decay in PATTERNS[kind]:
        count = int(RATE * duration)
        fade = int(RATE * FADE_S)
        for i in range(count):
            t = i / RATE
            if frequency == 0.0:
                value = 0.0
            else:
                # Short fade in and out avoids clicks between tones.
                edge = min(1.0, i / fade, (count - 1 - i) / fade)
                value = AMPLITUDE * edge * math.exp(-decay * t) * math.sin(
                    2 * math.pi * frequency * t
                )
            samples += struct.pack("<h", int(value * 32767))
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(bytes(samples))
    return out.getvalue()


def cache_dir() -> pathlib.Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return pathlib.Path(base) / "herdr-blocked-hud"


def builtin_path(kind: str, directory: pathlib.Path | None = None) -> str:
    """Path of the generated sound for `kind`, written on first use."""
    directory = directory or cache_dir()
    path = directory / f"{kind}-v{VERSION}.wav"
    if not path.exists():
        directory.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        tmp.write_bytes(render(kind))
        tmp.replace(path)
    return str(path)
