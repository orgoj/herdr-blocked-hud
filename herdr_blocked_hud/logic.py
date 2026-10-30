"""Pure HUD decisions: which rows to show, when to beep, when to hide."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Callable

from .source import Agent, Model

# Consecutive polls with errors before the error row appears.
ERROR_POLLS = 3

# What a status value does to its done row; see DoneTracker.
MODES = ("transient", "sticky", "hide")


@dataclass(frozen=True)
class Row:
    agent: Agent
    text: str


@dataclass(frozen=True)
class Section:
    title: str
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class View:
    blocked: tuple[Row, ...] = ()
    done: tuple[Section, ...] = ()
    error: str | None = None
    beep_blocked: bool = False
    beep_done: bool = False

    @property
    def visible(self) -> bool:
        return bool(self.blocked or self.done or self.error)


@dataclass(frozen=True)
class LongDone:
    agent: Agent
    seconds: float
    # Value from the agent's status line; None without one.
    status: str | None = None


def agent_key(agent: Agent) -> tuple[str, str]:
    return (agent.session, agent.terminal_id)


def row_text(agent: Agent, show_session: bool) -> str:
    parts = [agent.workspace_label, agent.tab_label, agent.agent_label]
    if show_session:
        parts.insert(0, agent.session)
    return " · ".join(parts)


def elapsed_text(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h{minutes % 60:02d}m"


@dataclass
class HudState:
    """Turns successive Models into Views.

    Every blocked pane is listed, also the one the user looks at: an active
    Herdr window does not mean the user sees its prompt.
    """

    _known_blocked: set[tuple[str, str]] | None = None
    _known_done: set[tuple[str, str, int | None]] = field(default_factory=set)
    _error_polls: int = 0

    def update(
        self,
        model: Model,
        long_done: tuple[LongDone, ...] = (),
    ) -> View:
        errors = model.errors
        self._error_polls = self._error_polls + 1 if errors else 0
        error = "; ".join(errors) if self._error_polls >= ERROR_POLLS else None

        blocked = model.agents_with_status("blocked")
        current = {agent_key(a) for a in blocked}
        failed = {s.session.name for s in model.sessions if s.error}
        if model.error:
            # Session list unreadable: nothing is known about any session.
            failed = None

        beep = False
        if self._known_blocked is None:
            # First reading: panes already blocked at start do not beep.
            if not errors:
                self._known_blocked = current
        else:
            beep = bool(current - self._known_blocked)
            if failed is None:
                kept = self._known_blocked
            else:
                # Keep panes of unreachable sessions so recovery does not re-beep.
                kept = {key for key in self._known_blocked if key[0] in failed}
            self._known_blocked = current | kept

        # A sticky row first listed after the user viewed the pane does not beep.
        entered = {done_key(d.agent) for d in long_done if d.agent.status == "done"}
        beep_done = bool(entered - self._known_done)
        self._known_done = {done_key(d.agent) for d in long_done}

        show_session = len({s.session.name for s in model.sessions}) > 1
        rows = tuple(Row(a, row_text(a, show_session)) for a in blocked)
        # One section per status value, oldest row first, sections in that order.
        grouped: dict[str | None, list[Row]] = {}
        for d in sorted(long_done, key=lambda d: -d.seconds):
            text = f"{row_text(d.agent, show_session)} · {elapsed_text(d.seconds)}"
            grouped.setdefault(d.status, []).append(Row(d.agent, text))
        sections = tuple(
            Section("Done" if status is None else f"Done · {status}", tuple(group))
            for status, group in grouped.items()
        )
        return View(
            blocked=rows,
            done=sections,
            error=error,
            beep_blocked=beep,
            beep_done=beep_done,
        )


def done_key(agent: Agent) -> tuple[str, str, int | None]:
    return (agent.session, agent.terminal_id, agent.completion_seq)


@dataclass
class DoneConfig:
    after_seconds: float = 5
    sound_enabled: bool = True
    # Bottom-most line matching this is the agent's status line; its first
    # group is the status value.
    status_regex: str = r"^\s*STATUS:\s*(\S+)"
    # Mode per status value; other values get default_mode, a reply without
    # a status line (or a failed read) gets no_status_mode.
    modes: dict[str, str] = field(default_factory=dict)
    default_mode: str = "transient"
    no_status_mode: str = "transient"
    read_lines: int = 80

    def __post_init__(self):
        # Invalid settings raise here, at startup: re.error or ValueError.
        self.status = re.compile(self.status_regex)
        if self.status.groups < 1:
            raise ValueError("status_regex needs a group for the status value")
        for mode in (*self.modes.values(), self.default_mode, self.no_status_mode):
            if mode not in MODES:
                raise ValueError(f"mode {mode!r} is not one of {', '.join(MODES)}")


def status_value(text: str | None, config: DoneConfig) -> str | None:
    """Status value from the bottom-most status line, or None."""
    value = None
    for line in (text or "").splitlines():
        match = config.status.search(line)
        if match:
            value = match.group(1)
    return value


def mode_for(status: str | None, config: DoneConfig) -> str:
    if status is None:
        return config.no_status_mode
    return config.modes.get(status, config.default_mode)


class DoneTracker:
    """Measures how long agents stay `done` and sorts them by status value.

    A completion is listed after `after_seconds` in `done`. Its mode decides
    what happens next: `transient` leaves when the pane leaves `done` (the
    user viewed it), `sticky` stays while the pane is `idle` with the same
    completion and leaves when the agent works again, `hide` is never listed.
    A dismissed completion is not listed again.

    Runs on the poll thread: `read_tail` does I/O, once per completion.
    `dismiss` is called from the Tk thread.
    """

    def __init__(
        self,
        config: DoneConfig,
        read_tail: Callable[[Agent, int], str | None],
        clock: Callable[[], float],
    ):
        self.config = config
        self.read_tail = read_tail
        self.clock = clock
        self.since: dict[tuple[str, str, int | None], float] = {}
        self.status: dict[tuple[str, str, int | None], str | None] = {}
        self.dismissed: set[tuple[str, str, int | None]] = set()
        self._lock = threading.Lock()
        self._to_dismiss: set[tuple[str, str, int | None]] = set()

    def dismiss(self, agent: Agent) -> None:
        """Thread-safe: stop listing this completion; applied on the next update."""
        with self._lock:
            self._to_dismiss.add(done_key(agent))

    def update(self, model: Model) -> tuple[LongDone, ...]:
        now = self.clock()
        with self._lock:
            self.dismissed |= self._to_dismiss
            self._to_dismiss.clear()
        reachable = {s.session.name for s in model.sessions if not s.error}
        panes = {(a.session, a.terminal_id): a for s in model.sessions for a in s.agents}
        for agent in model.agents_with_status("done"):
            self.since.setdefault(done_key(agent), now)
        result = []
        for key, since in list(self.since.items()):
            agent = panes.get(key[:2])
            if agent is None or agent.completion_seq != key[2]:
                # Pane gone or a new completion; unreachable sessions keep theirs.
                if key[0] in reachable:
                    self.forget(key)
                continue
            if agent.status == "done":
                if now - since < self.config.after_seconds:
                    continue
            elif agent.status != "idle" or self.mode(key, agent) != "sticky":
                # Viewed (idle) or working again: only a viewed sticky one stays.
                self.forget(key)
                continue
            if self.mode(key, agent) == "hide" or key in self.dismissed:
                continue
            result.append(LongDone(agent, now - since, self.status[key]))
        return tuple(result)

    def mode(self, key: tuple[str, str, int | None], agent: Agent) -> str:
        if key not in self.status:
            text = self.read_tail(agent, self.config.read_lines)
            self.status[key] = status_value(text, self.config)
        return mode_for(self.status[key], self.config)

    def forget(self, key: tuple[str, str, int | None]) -> None:
        self.since.pop(key, None)
        self.status.pop(key, None)
        self.dismissed.discard(key)
