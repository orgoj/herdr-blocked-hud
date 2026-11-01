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
# Which HUD sound a done row plays when it is first listed.
SOUNDS = ("blocked", "done")


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
    # Sound kinds of the listed rows ("blocked", "done"): what a delayed
    # reminder would play now.
    pending: frozenset[str] = frozenset()

    @property
    def visible(self) -> bool:
        return bool(self.blocked or self.done or self.error)


@dataclass(frozen=True)
class LongDone:
    agent: Agent
    seconds: float
    # Value from the agent's status line; None without one.
    status: str | None = None
    # Sound played when the row is first listed: "blocked" or "done".
    sound: str = "done"


@dataclass(frozen=True)
class Item:
    """One line of the HUD. `key` names the widget that shows it: a line
    keeps its widget while its key stays, and only its text is updated.
    Keys: a row by its pane and dismissibility, a header by its place among
    the headers (("header",), ("header", 1), ...), the one error line by
    ("error",); a changed title or error message is a text change."""

    key: tuple
    text: str
    agent: Agent | None = None


def layout(view: View) -> tuple[Item, ...]:
    """The lines of `view`, top to bottom: headers, rows, the error line."""
    items: list[Item] = []
    seen: set[tuple] = set()

    def add(key: tuple, text: str, agent: Agent | None = None) -> None:
        # Keys stay unique, so two lines never share one widget.
        unique, n = key, 1
        while unique in seen:
            unique, n = (*key, n), n + 1
        seen.add(unique)
        items.append(Item(unique, text, agent))

    if not view.visible:
        add(("header",), "Nothing waiting")
    if view.blocked:
        add(("header",), "Blocked")
        for row in view.blocked:
            add(("row", agent_key(row.agent), False), f"▶ {row.text}", row.agent)
    for section in view.done:
        add(("header",), section.title)
        for row in section.rows:
            add(("row", agent_key(row.agent), True), f"▶ {row.text}", row.agent)
    if view.error:
        text = f"herdr unreachable: {view.error}"
        add(("error",), text)
    return tuple(items)


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

    # Status values whose Done sections come first, in this order (the keys of
    # [done.modes] as written); other values follow, plain Done last.
    section_order: tuple[str, ...] = ()
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
        # A new row plays its status's sound; "blocked" ones sound like a
        # blocked pane, so the blocked mute silences them.
        new = {
            d.sound for d in long_done
            if d.agent.status == "done" and done_key(d.agent) not in self._known_done
        }
        beep = beep or "blocked" in new
        beep_done = "done" in new
        self._known_done = {done_key(d.agent) for d in long_done}

        show_session = len({s.session.name for s in model.sessions}) > 1
        rows = tuple(Row(a, row_text(a, show_session)) for a in blocked)
        # One section per status value, oldest row first. Sections: the
        # section_order ones in that order, then the others in oldest-row
        # order, plain Done last.
        grouped: dict[str | None, list[Row]] = {}
        for d in sorted(long_done, key=lambda d: -d.seconds):
            text = f"{row_text(d.agent, show_session)} · {elapsed_text(d.seconds)}"
            grouped.setdefault(d.status, []).append(Row(d.agent, text))
        rank = {status: i for i, status in enumerate(self.section_order)}
        first_seen = list(grouped)
        ordered = sorted(grouped, key=lambda status: (
            status is None, rank.get(status, len(rank)), first_seen.index(status),
        ))
        sections = tuple(
            Section("Done" if status is None else f"Done · {status}", tuple(grouped[status]))
            for status in ordered
        )
        return View(
            blocked=rows,
            done=sections,
            error=error,
            beep_blocked=beep,
            beep_done=beep_done,
            pending=frozenset({"blocked"} if rows else ()) | {d.sound for d in long_done},
        )


class SoundReminder:
    """Delayed, repeating sound: `delay` seconds after something sounding is
    first listed, then every `repeat` seconds (0: once) while it stays
    listed; nothing listed resets it. New rows in between play nothing."""

    def __init__(self, delay: float, repeat: float):
        self.delay = delay
        self.repeat = repeat
        self._due: float | None = None

    def tick(self, pending: frozenset[str], now: float) -> frozenset[str]:
        """The kinds to play now (usually none)."""
        if not pending:
            self._due = None
            return frozenset()
        if self._due is None:
            self._due = now + self.delay
        if now < self._due:
            return frozenset()
        # Repeat counts from this sound; 0 never comes due again.
        self._due = now + self.repeat if self.repeat > 0 else float("inf")
        return pending


def done_key(agent: Agent) -> tuple[str, str, int | None]:
    return (agent.session, agent.terminal_id, agent.completion_seq)


@dataclass
class DoneConfig:
    after_seconds: float = 5
    sound_enabled: bool = True
    # Bottom-most line matching this is the agent's status line; its first
    # group is the status value.
    status_regex: str = r"^\s*STATUS:\s*(\S+)"
    # Mode per status value, a mode string or a table
    # `{ mode = "...", sound = "blocked" | "done" }` (sound default "done");
    # other values get default_mode, a reply without a status line (or a
    # failed read) gets no_status_mode, both with the done sound.
    modes: dict[str, str | dict] = field(default_factory=dict)
    default_mode: str = "transient"
    no_status_mode: str = "transient"
    read_lines: int = 80

    def __post_init__(self):
        # Invalid settings raise here, at startup: re.error or ValueError.
        self.status = re.compile(self.status_regex)
        if self.status.groups < 1:
            raise ValueError("status_regex needs a group for the status value")
        self.mode_of: dict[str, str] = {}
        self.sound_of: dict[str, str] = {}
        for status, value in self.modes.items():
            if isinstance(value, dict):
                unknown = set(value) - {"mode", "sound"}
                if unknown:
                    raise ValueError(f"modes.{status}: unknown key {sorted(unknown)[0]}")
                if "mode" not in value:
                    raise ValueError(f"modes.{status}: missing mode")
                mode, sound = value["mode"], value.get("sound", "done")
            else:
                mode, sound = value, "done"
            if sound not in SOUNDS:
                raise ValueError(f"sound {sound!r} is not one of {', '.join(SOUNDS)}")
            self.mode_of[status], self.sound_of[status] = mode, sound
        for mode in (*self.mode_of.values(), self.default_mode, self.no_status_mode):
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
    return config.mode_of.get(status, config.default_mode)


def done_sound_for(status: str | None, config: DoneConfig) -> str:
    """Which sound, "blocked" or "done", a completion with `status` plays."""
    return config.sound_of.get(status, "done") if status is not None else "done"


class DoneTracker:
    """Measures how long agents stay `done` and sorts them by status value.

    A completion is listed after `after_seconds` in `done`. Its mode decides
    what happens next: `transient` leaves when the pane leaves `done` (the
    user viewed it), `sticky` stays while the pane is `idle` with the same
    completion and leaves when the agent works again, `hide` is never listed.
    A dismissed completion is not listed again. At HUD start, idle panes that
    still carry a completion are read once and listed if sticky.

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
        # Sessions whose idle panes were read once (see _read_idle_at_start).
        self._started_sessions: set[str] = set()

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
        self._read_idle_at_start(model, now)
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
            status = self.status[key]
            result.append(LongDone(
                agent, now - since, status, done_sound_for(status, self.config)
            ))
        return tuple(result)

    def _read_idle_at_start(self, model: Model, now: float) -> None:
        """First time a session is readable: list its viewed sticky completions.

        Herdr keeps an idle pane's completion_seq until the agent works again,
        so a sticky row listed before a HUD restart comes back; nothing is
        stored on disk, so a dismissal before the restart is not remembered.
        """
        for state in model.sessions:
            if state.error or state.session.name in self._started_sessions:
                continue
            self._started_sessions.add(state.session.name)
            for agent in state.agents:
                key = done_key(agent)
                if agent.status != "idle" or agent.completion_seq is None or key in self.since:
                    continue
                if self.mode(key, agent) == "sticky":
                    self.since[key] = now
                else:
                    self.status.pop(key, None)

    def mode(self, key: tuple[str, str, int | None], agent: Agent) -> str:
        if key not in self.status:
            text = self.read_tail(agent, self.config.read_lines)
            self.status[key] = status_value(text, self.config)
        return mode_for(self.status[key], self.config)

    def forget(self, key: tuple[str, str, int | None]) -> None:
        self.since.pop(key, None)
        self.status.pop(key, None)
        self.dismissed.discard(key)
