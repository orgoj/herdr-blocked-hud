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
import traceback
from dataclasses import dataclass
from typing import Callable

SOCKET_TIMEOUT_S = 1.0
REQUEST_DEADLINE_S = 3.0
# A snapshot of a dozen agents is ~20 KB; this leaves ample room.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
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


# Errors a schema-incompatible but valid JSON payload raises while parsed.
PAYLOAD_ERRORS = (KeyError, TypeError, AttributeError, ValueError)


def _str(record: dict, key: str) -> str:
    value = record[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} is not a string")
    return value


def parse_session_list(payload: dict) -> list[Session]:
    """Running sessions from `herdr session list --json` output."""
    sessions = []
    for entry in payload.get("sessions", []):
        if not entry.get("running"):
            continue
        sessions.append(
            Session(
                name=_str(entry, "name"),
                socket_path=_str(entry, "socket_path"),
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
    except PAYLOAD_ERRORS as err:
        raise SourceError(f"herdr session list: bad output: {err!r}") from err


def request(
    socket_path: str,
    method: str,
    params: dict | None = None,
    deadline_s: float = REQUEST_DEADLINE_S,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> dict:
    """Send one request line to a Herdr socket and return its `result`.

    The whole exchange must finish within `deadline_s` and the reply must fit
    in `max_bytes`, so a misbehaving peer cannot stall the poll thread.
    """
    line = json.dumps({"id": "hud", "method": method, "params": params or {}})
    deadline = time.monotonic() + deadline_s
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(min(SOCKET_TIMEOUT_S, deadline_s))
            conn.connect(socket_path)
            conn.sendall(line.encode() + b"\n")
            response = _read_line(conn, deadline, max_bytes)
    except OSError as err:
        raise SourceError(f"{method}: {err}") from err
    try:
        message = json.loads(response)
    except ValueError as err:
        raise SourceError(f"{method}: bad response: {err}") from err
    if not isinstance(message, dict):
        raise SourceError(f"{method}: response is not an object")
    if "error" in message:
        error = message["error"] if isinstance(message["error"], dict) else {}
        raise SourceError(
            f"{method}: {error.get('code', 'error')}: {error.get('message', '')}".rstrip(": ")
        )
    if "result" not in message:
        raise SourceError(f"{method}: response without result")
    return message["result"]


def _read_line(conn: socket.socket, deadline: float, max_bytes: int) -> bytes:
    chunks = []
    size = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OSError("response deadline exceeded")
        conn.settimeout(min(SOCKET_TIMEOUT_S, remaining))
        try:
            chunk = conn.recv(65536)
        except TimeoutError:
            if time.monotonic() >= deadline:
                raise OSError("response deadline exceeded") from None
            raise
        if not chunk:
            raise OSError("connection closed before a full response")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunk = chunk[:newline]
        size += len(chunk)
        if size > max_bytes:
            raise OSError(f"response larger than {max_bytes} bytes")
        chunks.append(chunk)
        if newline >= 0:
            return b"".join(chunks)


def parse_snapshot(session: Session, result: dict) -> tuple[Agent, ...]:
    """Agents with human labels from a `session.snapshot` result."""
    snapshot = result["snapshot"]
    workspaces = {_str(ws, "workspace_id"): ws for ws in snapshot.get("workspaces", [])}
    tabs = {_str(tab, "tab_id"): tab for tab in snapshot.get("tabs", [])}
    agents = []
    for entry in snapshot.get("agents", []):
        workspace_id = _str(entry, "workspace_id")
        tab_id = _str(entry, "tab_id")
        completion_seq = entry.get("completion_seq")
        if completion_seq is not None and not isinstance(completion_seq, int):
            raise TypeError("completion_seq is not an integer")
        agents.append(
            Agent(
                session=session.name,
                pane_id=_str(entry, "pane_id"),
                terminal_id=_str(entry, "terminal_id"),
                workspace_id=workspace_id,
                tab_id=tab_id,
                workspace_label=_label(workspaces.get(workspace_id, {}), workspace_id),
                tab_label=_label(tabs.get(tab_id, {}), tab_id),
                agent_label=_text(entry.get("display_agent"))
                or _text(entry.get("name"))
                or _text(entry.get("agent"))
                or "agent",
                status=_str(entry, "agent_status"),
                focused=bool(entry.get("focused")),
                completion_seq=completion_seq,
            )
        )
    return tuple(agents)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _label(record: dict, fallback: str) -> str:
    label = _text(record.get("label"))
    if label:
        return label
    if record.get("number") is not None:
        return str(record["number"])
    return fallback


def read_session(session: Session) -> SessionState:
    try:
        result = request(session.socket_path, "session.snapshot")
        return SessionState(session, agents=parse_snapshot(session, result))
    except SourceError as err:
        return SessionState(session, error=str(err))
    except PAYLOAD_ERRORS as err:
        return SessionState(session, error=f"session.snapshot: bad payload: {err!r}")


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
            # A bug or unexpected payload must not end polling and freeze the
            # HUD on stale rows: report it as an error state and keep going.
            try:
                model = self.poll_once()
            except Exception as err:
                traceback.print_exc()
                model = Model(error=f"internal error: {err!r}")
            try:
                self._on_model(model)
            except Exception:
                traceback.print_exc()
            self._wake.wait(self._interval)
            self._wake.clear()
