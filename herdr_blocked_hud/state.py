"""HUD state remembered across runs: dragged position, width and mute.

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
    # Muted sound kinds, a subset of KINDS.
    muted: frozenset[str] = frozenset()
    # Width dragged by an edge, None: config width. Like the offset for the
    # corner, it is void when config width changed from `config_width`.
    width: int | None = None
    config_width: int | None = None


KINDS = ("blocked", "done")


def parse_muted(value: object) -> frozenset[str] | None:
    """A list of kinds; the old single-button bool mutes both or none."""
    if isinstance(value, bool):
        return frozenset(KINDS) if value else frozenset()
    if isinstance(value, list) and all(kind in KINDS for kind in value):
        return frozenset(value)
    return None


def state_path() -> pathlib.Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return pathlib.Path(base) / "herdr-blocked-hud" / "state.json"


def load(path: pathlib.Path, corner: str, config_width: int | None = None) -> HudSettings:
    """Saved state; defaults for a missing or malformed file.

    A saved width applies only when it was saved under `config_width`."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return HudSettings(corner=corner)
    except (OSError, ValueError) as err:
        print(f"herdr-blocked-hud: ignoring state file {path}: {err}", file=sys.stderr)
        return HudSettings(corner=corner)
    # Any malformed field voids the whole file; a valid offset saved for
    # another corner is only not applied.
    if not isinstance(data, dict):
        return HudSettings(corner=corner)
    offset = data.get("offset")
    muted = parse_muted(data.get("muted"))
    # Files from before the width was saved have neither key.
    width, saved_config_width = data.get("width"), data.get("config_width")
    if not (
        muted is not None
        and isinstance(data.get("corner"), str)
        and isinstance(offset, list)
        and len(offset) == 2
        and all(type(value) is int for value in offset)
        and (
            width is saved_config_width is None
            or all(type(v) is int and v > 0 for v in (width, saved_config_width))
        )
    ):
        return HudSettings(corner=corner)
    if width is None or saved_config_width != config_width:
        width = None
    sized = {"width": width, "config_width": config_width if width else None}
    if data["corner"] != corner:
        return HudSettings(corner=corner, muted=muted, **sized)
    return HudSettings(corner, (offset[0], offset[1]), muted, **sized)


def save(path: pathlib.Path, settings: HudSettings) -> None:
    """Write atomically; a failure is reported, never raised."""
    data = {
        "corner": settings.corner,
        "offset": list(settings.offset),
        "muted": [kind for kind in KINDS if kind in settings.muted],
    }
    if settings.width is not None and settings.config_width is not None:
        data["width"] = settings.width
        data["config_width"] = settings.config_width
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data) + "\n")
        os.replace(temporary, path)
    except OSError as err:
        print(f"herdr-blocked-hud: cannot save state to {path}: {err}", file=sys.stderr)
