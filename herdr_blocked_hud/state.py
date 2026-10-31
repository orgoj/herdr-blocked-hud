"""HUD state remembered across runs: dragged position and mute.

Kept apart from the hand-written config.toml, which the HUD never writes.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class HudSettings:
    # Corner the offset was dragged from; an offset from another corner is void.
    corner: str = ""
    offset: tuple[int, int] = (0, 0)
    muted: bool = False


def state_path() -> pathlib.Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return pathlib.Path(base) / "herdr-blocked-hud" / "state.json"


def load(path: pathlib.Path, corner: str) -> HudSettings:
    """Saved state; defaults for a missing or malformed file."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return HudSettings(corner=corner)
    except (OSError, ValueError) as err:
        print(f"herdr-blocked-hud: ignoring state file {path}: {err}", file=sys.stderr)
        return HudSettings(corner=corner)
    if not isinstance(data, dict):
        return HudSettings(corner=corner)
    muted = data.get("muted") is True
    offset = data.get("offset")
    if (
        data.get("corner") == corner
        and isinstance(offset, list)
        and len(offset) == 2
        and all(type(value) is int for value in offset)
    ):
        return HudSettings(corner, (offset[0], offset[1]), muted)
    return HudSettings(corner=corner, muted=muted)


def save(path: pathlib.Path, settings: HudSettings) -> None:
    """Write atomically; a failure is reported, never raised."""
    data = {"corner": settings.corner, "offset": list(settings.offset), "muted": settings.muted}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data) + "\n")
        os.replace(temporary, path)
    except OSError as err:
        print(f"herdr-blocked-hud: cannot save state to {path}: {err}", file=sys.stderr)
