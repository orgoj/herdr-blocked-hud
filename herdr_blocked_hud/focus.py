"""Click action: focus the agent's pane in Herdr, then raise its window."""

from __future__ import annotations

import subprocess
import sys
from typing import Callable

from . import x11
from .source import Agent, Session

FOCUS_TIMEOUT_S = 2.0
DEFAULT_WM_CLASS = "herdr.herdr"


def herdr_agent_focus(agent: Agent) -> bool:
    command = ["herdr", "--session", agent.session, "agent", "focus", agent.pane_id]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=FOCUS_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as err:
        log(f"{' '.join(command)}: {err}")
        return False
    if result.returncode != 0:
        log(f"{' '.join(command)} exited {result.returncode}: {result.stderr.strip()}")
        return False
    return True


def raise_session_window(session: str, sessions: list[Session], wm_class: str | None) -> bool:
    all_clients = x11.ui_clients(sessions)
    clients = all_clients.get(session, [])
    # A class match proves the session only when no other session has a client.
    fallback = wm_class if set(all_clients) == {session} else None
    window = x11.host_window(clients, x11.list_windows(), fallback)
    if window is None:
        log(f"no Herdr window found for session {session}")
        return False
    if not x11.activate(window):
        log(f"wmctrl could not activate {window.wid}")
        return False
    return True


def focus_agent(
    agent: Agent,
    sessions: list[Session],
    wm_class: str | None = DEFAULT_WM_CLASS,
    agent_focus: Callable[[Agent], bool] = herdr_agent_focus,
    raise_window: Callable[[str, list[Session], str | None], bool] = raise_session_window,
) -> bool:
    """Focus the pane, then raise its window. A failed focus raises nothing."""
    if not agent_focus(agent):
        return False
    raise_window(agent.session, sessions, wm_class)
    return True


def log(message: str) -> None:
    print(f"herdr-blocked-hud: {message}", file=sys.stderr)
