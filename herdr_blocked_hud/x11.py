"""Herdr UI clients, their sessions and their X11 host windows."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable

from .source import Session

TOOL_TIMEOUT_S = 1.0
# Parent-walk depth cap, so a corrupt parent loop cannot hang.
MAX_DEPTH = 64


@dataclass(frozen=True)
class Process:
    pid: int
    argv: tuple[str, ...]
    environ: dict[str, str]


# Herdr global options that take a value (`herdr --help`).
VALUE_OPTIONS = ("--session", "--machine", "--remote", "--remote-keybindings")


@dataclass(frozen=True)
class ClientArgs:
    session: str | None
    remote: bool


def parse_client_args(argv: tuple[str, ...]) -> ClientArgs | None:
    """Arguments of a local Herdr UI client, or None for anything else.

    UI clients are `herdr [options]` and `herdr session attach <name>`;
    `herdr server`, `herdr --session x agent focus …` and other CLI commands
    are not.
    """
    if not argv or os.path.basename(argv[0]) != "herdr":
        return None
    options: dict[str, str] = {}
    positional: list[str] = []
    args = list(argv[1:])
    while args:
        arg = args.pop(0)
        name, has_value, value = arg.partition("=")
        if name in VALUE_OPTIONS:
            if not has_value:
                if not args:
                    return None
                value = args.pop(0)
            options[name] = value
        elif arg.startswith("-"):
            continue
        else:
            positional.append(arg)
    if positional[:2] == ["session", "attach"] and len(positional) == 3:
        return ClientArgs(session=positional[2], remote=False)
    if positional or "--machine" in options:
        return None
    return ClientArgs(session=options.get("--session"), remote="--remote" in options)


def is_ui_client(argv: tuple[str, ...]) -> bool:
    return parse_client_args(argv) is not None


def client_session(process: Process, sessions: Iterable[Session]) -> str | None:
    """Name of the local session a UI client is attached to, if it is known."""
    args = parse_client_args(process.argv)
    if args is None or args.remote:
        return None
    sessions = list(sessions)
    names = {s.name for s in sessions}
    if args.session is not None:
        return args.session if args.session in names else None
    socket_path = process.environ.get("HERDR_SOCKET_PATH")
    if socket_path:
        for s in sessions:
            if s.socket_path == socket_path:
                return s.name
        return None
    name = process.environ.get("HERDR_SESSION")
    if name:
        return name if name in names else None
    for s in sessions:
        if s.default:
            return s.name
    return None


def read_process(pid: int) -> Process | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv = tuple(a.decode(errors="replace") for a in f.read().split(b"\0") if a)
        if not is_ui_client(argv):
            return Process(pid, argv, {})
        with open(f"/proc/{pid}/environ", "rb") as f:
            environ = dict(
                item.decode(errors="replace").split("=", 1)
                for item in f.read().split(b"\0")
                if b"=" in item
            )
        return Process(pid, argv, environ)
    except OSError:
        return None


def ui_clients(sessions: Iterable[Session]) -> dict[str, list[int]]:
    """UI client pids per session name, from /proc."""
    sessions = list(sessions)
    clients: dict[str, list[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        process = read_process(int(entry))
        if process is None or not is_ui_client(process.argv):
            continue
        name = client_session(process, sessions)
        if name is not None:
            clients.setdefault(name, []).append(process.pid)
    for pids in clients.values():
        pids.sort()
    return clients


def parent_pid(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat") as f:
            stat = f.read()
    except OSError:
        return None
    # `pid (comm) state ppid ...`; comm may contain spaces and parentheses.
    fields = stat.rsplit(")", 1)[-1].split()
    try:
        return int(fields[1])
    except (IndexError, ValueError):
        return None


def ancestors(pid: int, parent_of: Callable[[int], int | None] = parent_pid) -> list[int]:
    """`pid` followed by its parents, nearest first."""
    chain = [pid]
    for _ in range(MAX_DEPTH):
        parent = parent_of(chain[-1])
        if parent is None or parent <= 1 or parent in chain:
            break
        chain.append(parent)
    return chain


def active_window_pid() -> int | None:
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowpid"],
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except ValueError:
        return None


@dataclass(frozen=True)
class Window:
    wid: str
    pid: int
    wm_class: str


def parse_window_list(listing: str) -> list[Window]:
    """Windows from `wmctrl -lpx`: `wid desktop pid instance.Class host title`."""
    windows = []
    for line in listing.splitlines():
        fields = line.split(None, 4)
        if len(fields) < 4:
            continue
        try:
            windows.append(Window(fields[0], int(fields[2]), fields[3]))
        except ValueError:
            continue
    return windows


def list_windows() -> list[Window]:
    try:
        result = subprocess.run(
            ["wmctrl", "-lpx"], capture_output=True, text=True, timeout=TOOL_TIMEOUT_S
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_window_list(result.stdout) if result.returncode == 0 else []


def host_window(
    client_pids: list[int],
    windows: list[Window],
    wm_class: str | None,
    parent_of: Callable[[int], int | None] = parent_pid,
) -> Window | None:
    """First window owning a client's nearest ancestor; else exact WM_CLASS.

    The WM_CLASS fallback cannot tell sessions apart, so callers pass it only
    when every local UI client belongs to the requested session. Window
    titles are never matched: a browser tab titled "herdr" is not the
    terminal.
    """
    by_pid: dict[int, Window] = {}
    for window in windows:
        by_pid.setdefault(window.pid, window)
    for pid in client_pids:
        for ancestor in ancestors(pid, parent_of):
            if ancestor in by_pid:
                return by_pid[ancestor]
    if wm_class:
        for window in windows:
            if window.wm_class == wm_class:
                return window
    return None


def activate(window: Window) -> bool:
    """Switch to the window's desktop and raise it."""
    try:
        result = subprocess.run(
            ["wmctrl", "-i", "-a", window.wid],
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def primary_monitor() -> tuple[int, int, int, int] | None:
    """(x, y, width, height) of the primary monitor from `xrandr --listmonitors`."""
    try:
        result = subprocess.run(
            ["xrandr", "--listmonitors"],
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_primary_monitor(result.stdout) if result.returncode == 0 else None


def parse_primary_monitor(listing: str) -> tuple[int, int, int, int] | None:
    # ` 0: +*DP-0 2560/698x1440/393+0+0  DP-0`; `*` marks the primary.
    first = None
    for line in listing.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 3:
            continue
        try:
            size, x, y = fields[2].split("+")
            width, height = (int(part.split("/")[0]) for part in size.split("x"))
            geometry = (int(x), int(y), width, height)
        except ValueError:
            continue
        if fields[1].startswith("+*") or fields[1].startswith("*"):
            return geometry
        first = first or geometry
    return first


def viewed_sessions(
    window_pid: int | None,
    clients: dict[str, list[int]],
    parent_of: Callable[[int], int | None] = parent_pid,
) -> set[str]:
    """Sessions whose Herdr UI client lives in the window owned by `window_pid`."""
    if window_pid is None:
        return set()
    return {
        name
        for name, pids in clients.items()
        if any(window_pid in ancestors(pid, parent_of) for pid in pids)
    }
