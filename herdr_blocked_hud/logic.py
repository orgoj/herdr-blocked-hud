"""Pure HUD decisions: which rows to show, when to beep, when to hide."""

from __future__ import annotations

from dataclasses import dataclass

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
    error: str | None = None
    beep_blocked: bool = False

    @property
    def visible(self) -> bool:
        return bool(self.blocked or self.error)


def agent_key(agent: Agent) -> tuple[str, str]:
    return (agent.session, agent.terminal_id)


def row_text(agent: Agent, show_session: bool) -> str:
    parts = [agent.workspace_label, agent.tab_label, agent.agent_label]
    if show_session:
        parts.insert(0, agent.session)
    return " · ".join(parts)


@dataclass
class HudState:
    """Turns successive Models into Views.

    A pane counts as viewed (hidden, silent) while it is focused in its
    session and that session's Herdr window is the active X11 window.
    """

    _known_blocked: set[tuple[str, str]] | None = None
    _error_polls: int = 0

    def update(self, model: Model, viewed_sessions: set[str]) -> View:
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
            new = current - self._known_blocked
            beep = any(
                agent_key(a) in new and not _viewed(a, viewed_sessions) for a in blocked
            )
            if failed is None:
                kept = self._known_blocked
            else:
                # Keep panes of unreachable sessions so recovery does not re-beep.
                kept = {key for key in self._known_blocked if key[0] in failed}
            self._known_blocked = current | kept

        show_session = len({s.session.name for s in model.sessions}) > 1
        rows = tuple(
            Row(a, row_text(a, show_session))
            for a in blocked
            if not _viewed(a, viewed_sessions)
        )
        return View(blocked=rows, error=error, beep_blocked=beep)


def _viewed(agent: Agent, viewed_sessions: set[str]) -> bool:
    return agent.focused and agent.session in viewed_sessions
