"""Herdr state source: local session discovery and snapshot polling.

One `session.snapshot` request per running session and poll returns agents,
workspaces and tabs together. Session discovery uses `herdr session list
--json` and is refreshed less often than the snapshots.
"""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

SOCKET_TIMEOUT_S = 1.0
SESSION_LIST_TIMEOUT_S = 2.0
POLL_INTERVAL_S = 1.0
SESSION_REFRESH_S = 10.0


class SourceError(Exception):
    """Herdr could not be reached or answered with an error."""


@dataclass(frozen=True)
class Session:
    name: str
    socket_path: str
    default: bool


@dataclass(frozen=True)
class Agent:
    session: str
    pane_id: str
    terminal_id: str
    workspace_id: str
    tab_id: str
    workspace_label: str
    tab_label: str
    agent_label: str
    status: str
    focused: bool
    completion_seq: int | None


@dataclass(frozen=True)
class SessionState:
    session: Session
    agents: tuple[Agent, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class Model:
    sessions: tuple[SessionState, ...] = ()
    # Set when the session list itself could not be read.
    error: str | None = None

    def agents_with_status(self, status: str) -> list[Agent]:
        return [
            agent
            for state in self.sessions
            for agent in state.agents
            if agent.status == status
        ]

    @property
    def errors(self) -> list[str]:
        errors = [self.error] if self.error else []
        errors.extend(
            f"{state.session.name}: {state.error}"
            for state in self.sessions
            if state.error
        )
        return errors


def parse_session_list(payload: dict) -> list[Session]:
    """Running sessions from `herdr session list --json` output."""
    sessions = []
    for entry in payload.get("sessions", []):
        if not entry.get("running"):
            continue
        sessions.append(
            Session(
                name=entry["name"],
                socket_path=entry["socket_path"],
                default=bool(entry.get("default")),
            )
        )
    return sessions


def list_sessions() -> list[Session]:
    try:
        result = subprocess.run(
            ["herdr", "session", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=SESSION_LIST_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        raise SourceError(f"herdr session list failed: {err}") from err
    if result.returncode != 0:
        raise SourceError(
            f"herdr session list exited {result.returncode}: {result.stderr.strip()}"
        )
    try:
        return parse_session_list(json.loads(result.stdout))
    except (ValueError, KeyError, TypeError) as err:
        raise SourceError(f"herdr session list: bad output: {err}") from err


def request(socket_path: str, method: str, params: dict | None = None) -> dict:
    """Send one request line to a Herdr socket and return its `result`."""
    line = json.dumps({"id": "hud", "method": method, "params": params or {}})
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(SOCKET_TIMEOUT_S)
            conn.connect(socket_path)
            conn.sendall(line.encode() + b"\n")
            response = _read_line(conn)
    except OSError as err:
        raise SourceError(f"{method}: {err}") from err
    try:
        message = json.loads(response)
    except ValueError as err:
        raise SourceError(f"{method}: bad response: {err}") from err
    if "error" in message:
        error = message["error"] or {}
        raise SourceError(
            f"{method}: {error.get('code', 'error')}: {error.get('message', '')}".rstrip(": ")
        )
    if "result" not in message:
        raise SourceError(f"{method}: response without result")
    return message["result"]


def _read_line(conn: socket.socket) -> bytes:
    chunks = []
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            raise OSError("connection closed before a full response")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            return b"".join(chunks)
        chunks.append(chunk)


def parse_snapshot(session: Session, result: dict) -> tuple[Agent, ...]:
    """Agents with human labels from a `session.snapshot` result."""
    snapshot = result["snapshot"]
    workspaces = {ws["workspace_id"]: ws for ws in snapshot.get("workspaces", [])}
    tabs = {tab["tab_id"]: tab for tab in snapshot.get("tabs", [])}
    agents = []
    for entry in snapshot.get("agents", []):
        workspace = workspaces.get(entry["workspace_id"], {})
        tab = tabs.get(entry["tab_id"], {})
        agents.append(
            Agent(
                session=session.name,
                pane_id=entry["pane_id"],
                terminal_id=entry["terminal_id"],
                workspace_id=entry["workspace_id"],
                tab_id=entry["tab_id"],
                workspace_label=_label(workspace, entry["workspace_id"]),
                tab_label=_label(tab, entry["tab_id"]),
                agent_label=entry.get("display_agent")
                or entry.get("name")
                or entry.get("agent")
                or "agent",
                status=entry["agent_status"],
                focused=bool(entry.get("focused")),
                completion_seq=entry.get("completion_seq"),
            )
        )
    return tuple(agents)


def _label(record: dict, fallback: str) -> str:
    if record.get("label"):
        return record["label"]
    if record.get("number") is not None:
        return str(record["number"])
    return fallback


def read_session(session: Session) -> SessionState:
    try:
        result = request(session.socket_path, "session.snapshot")
        return SessionState(session, agents=parse_snapshot(session, result))
    except SourceError as err:
        return SessionState(session, error=str(err))
    except (KeyError, TypeError) as err:
        return SessionState(session, error=f"session.snapshot: bad payload: {err}")


def read_agent_tail(agent: Agent, lines: int) -> str | None:
    """Last `lines` rendered rows of the agent's pane, or None on failure."""
    command = [
        "herdr", "--session", agent.session,
        "agent", "read", agent.pane_id, "--source", "recent", "--lines", str(lines),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=SESSION_LIST_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


class Poller:
    """Polls Herdr on a daemon thread and hands each Model to `on_model`.

    `on_model` runs on the worker thread; a Tk caller must hand the model to
    its main loop itself (e.g. through a queue drained with `after`).
    """

    def __init__(
        self,
        on_model: Callable[[Model], None],
        *,
        interval: float = POLL_INTERVAL_S,
        session_refresh: float = SESSION_REFRESH_S,
        list_sessions: Callable[[], list[Session]] = list_sessions,
        read_session: Callable[[Session], SessionState] = read_session,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._on_model = on_model
        self._interval = interval
        self._session_refresh = session_refresh
        self._list_sessions = list_sessions
        self._read_session = read_session
        self._clock = clock
        self._sessions: list[Session] = []
        self._sessions_error: str | None = None
        self._sessions_read_at: float | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._run, name="herdr-poller", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def poll_now(self) -> None:
        """Thread-safe: run the next poll without waiting for the interval."""
        self._wake.set()

    def poll_once(self) -> Model:
        now = self._clock()
        if (
            self._sessions_read_at is None
            or self._sessions_error is not None
            or now - self._sessions_read_at >= self._session_refresh
        ):
            self._sessions_read_at = now
            try:
                self._sessions = self._list_sessions()
                self._sessions_error = None
            except SourceError as err:
                self._sessions_error = str(err)
        if self._sessions_error is not None:
            return Model(error=self._sessions_error)
        if not self._sessions:
            return Model(error="no running Herdr session")
        return Model(sessions=tuple(self._read_session(s) for s in self._sessions))

    def _run(self) -> None:
        while not self._stop.is_set():
            self._on_model(self.poll_once())
            self._wake.wait(self._interval)
            self._wake.clear()
