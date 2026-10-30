"""Settings from `$XDG_CONFIG_HOME/herdr-blocked-hud/config.toml`.

A missing file means defaults. Unknown keys, wrong types and invalid regexes
are startup errors, so a typo never silently falls back to a default.
"""

from __future__ import annotations

import os
import pathlib
import re
import tomllib
from dataclasses import dataclass, field

from .logic import DoneConfig

CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left")


class ConfigError(Exception):
    pass


@dataclass
class Config:
    poll_interval: float = 1.0
    # Exact `wmctrl -lx` class used when the process tree finds no window;
    # empty disables the fallback.
    wm_class: str = "herdr.herdr"
    blocked_sound: str = "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga"
    done_sound: str = "/usr/share/sounds/freedesktop/stereo/complete.oga"
    corner: str = "top-right"
    margin_x: int = 24
    margin_y: int = 36
    width: int = 320
    done: DoneConfig = field(default_factory=DoneConfig)


def config_path() -> pathlib.Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return pathlib.Path(base) / "herdr-blocked-hud" / "config.toml"


def load(path: pathlib.Path | None = None) -> Config:
    path = path or config_path()
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return Config()
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise ConfigError(f"{path}: {err}") from err
    try:
        return parse(data)
    except ConfigError as err:
        raise ConfigError(f"{path}: {err}") from err


TOP_LEVEL = {
    "poll_interval": (int, float),
    "wm_class": str,
    "blocked_sound": str,
    "done_sound": str,
    "corner": str,
    "margin_x": int,
    "margin_y": int,
    "width": int,
}
DONE = {
    "after_seconds": (int, float),
    "sound_enabled": bool,
    "status_line_regex": str,
    "ignore_regexes": list,
    "read_lines": int,
}


def parse(data: dict) -> Config:
    done = data.get("done", {})
    if not isinstance(done, dict):
        raise ConfigError("[done] must be a table")
    top = {k: v for k, v in data.items() if k != "done"}
    _check(top, TOP_LEVEL, "")
    _check(done, DONE, "done.")
    if top.get("corner", "top-right") not in CORNERS:
        raise ConfigError(f"corner must be one of {', '.join(CORNERS)}")
    if top.get("poll_interval", 1.0) <= 0:
        raise ConfigError("poll_interval must be positive")
    if top.get("width", 320) <= 0:
        raise ConfigError("width must be positive")
    for key in ("margin_x", "margin_y"):
        if top.get(key, 0) < 0:
            raise ConfigError(f"{key} must not be negative")
    if done.get("after_seconds", 60) <= 0:
        raise ConfigError("done.after_seconds must be positive")
    if any(not isinstance(p, str) for p in done.get("ignore_regexes", [])):
        raise ConfigError("done.ignore_regexes must be a list of strings")
    if done.get("read_lines", 80) <= 0:
        raise ConfigError("done.read_lines must be positive")
    try:
        done_config = DoneConfig(**done)
    except re.error as err:
        raise ConfigError(f"done: invalid regex: {err}") from err
    return Config(**top, done=done_config)


def _check(values: dict, schema: dict, prefix: str) -> None:
    for key, value in values.items():
        if key not in schema:
            raise ConfigError(f"unknown key {prefix}{key}")
        expected = schema[key]
        # bool is an int subclass; reject it where a number is expected.
        if isinstance(value, bool) and expected is not bool:
            raise ConfigError(f"{prefix}{key} has the wrong type")
        if not isinstance(value, expected):
            raise ConfigError(f"{prefix}{key} has the wrong type")
