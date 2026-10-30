"""Pure HUD decisions: which rows to show, when to beep, when to hide."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .source import Agent, Model

# Consecutive polls with errors before the error row appears.
ERROR_POLLS = 3


@dataclass(frozen=True)
class Row:
    agent: Agent
    text: str


@dataclass(frozen=True)
class View:
    blocked: tuple[Row, ...] = ()
    done: tuple[Row, ...] = ()
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

        done_keys = {done_key(d.agent) for d in long_done}
        beep_done = bool(done_keys - self._known_done)
        self._known_done = done_keys

        show_session = len({s.session.name for s in model.sessions}) > 1
        rows = tuple(Row(a, row_text(a, show_session)) for a in blocked)
        done_rows = tuple(
            Row(d.agent, f"{row_text(d.agent, show_session)} · {elapsed_text(d.seconds)}")
            for d in sorted(long_done, key=lambda d: -d.seconds)
        )
        return View(
            blocked=rows,
            done=done_rows,
            error=error,
            beep_blocked=beep,
            beep_done=beep_done,
        )


def done_key(agent: Agent) -> tuple[str, str, int | None]:
    return (agent.session, agent.terminal_id, agent.completion_seq)


@dataclass
class DoneConfig:
    after_seconds: float = 60
    sound_enabled: bool = True
    # Bottom-most line matching this is the agent's final status line.
    status_line_regex: str = r"^\s*STATUS:"
    # Do not report an agent whose status line matches any of these.
    ignore_regexes: list[str] = field(default_factory=list)
    read_lines: int = 80

    def __post_init__(self):
        # Invalid patterns raise re.error here, at startup.
        self.status_line = re.compile(self.status_line_regex)
        self.ignore = [re.compile(pattern) for pattern in self.ignore_regexes]


def should_report(text: str | None, config: DoneConfig) -> bool:
    """Whether a finished agent's output still deserves a row."""
    if not config.ignore or text is None:
        return True
    status = None
    for line in text.splitlines():
        if config.status_line.search(line):
            status = line
    if status is None:
        return True
    return not any(pattern.search(status) for pattern in config.ignore)


class DoneTracker:
    """Measures how long agents stay `done` and applies the reply filter.

    Runs on the poll thread: `read_tail` does I/O, once per completion and
    only when ignore patterns are configured.
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
        self.report: dict[tuple[str, str, int | None], bool] = {}

    def update(self, model: Model) -> tuple[LongDone, ...]:
        now = self.clock()
        reachable = {s.session.name for s in model.sessions if not s.error}
        done = model.agents_with_status("done")
        current = {done_key(a) for a in done}
        # Forget completions that ended; keep those of unreachable sessions.
        for table in (self.since, self.report):
            for key in list(table):
                if key not in current and key[0] in reachable:
                    del table[key]
        result = []
        for agent in done:
            key = done_key(agent)
            since = self.since.setdefault(key, now)
            seconds = now - since
            if seconds < self.config.after_seconds:
                continue
            if key not in self.report:
                text = (
                    self.read_tail(agent, self.config.read_lines)
                    if self.config.ignore
                    else None
                )
                self.report[key] = should_report(text, self.config)
            if self.report[key]:
                result.append(LongDone(agent, seconds))
        return tuple(result)
