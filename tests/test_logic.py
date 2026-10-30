import unittest

from herdr_blocked_hud.logic import ERROR_POLLS, HudState
from herdr_blocked_hud.source import Agent, Model, Session, SessionState

DEFAULT = Session("default", "/s/default", True)
WORK = Session("work", "/s/work", False)


def agent(terminal, status="blocked", session="default", focused=False, ws="api"):
    return Agent(session, f"w1:{terminal}", terminal, "w1", "w1:t1", ws, "main", "claude",
                 status, focused, None)


def model(*agents, sessions=(DEFAULT,), failed=()):
    states = []
    for s in sessions:
        if s.name in failed:
            states.append(SessionState(s, error="refused"))
        else:
            states.append(SessionState(s, agents=tuple(a for a in agents if a.session == s.name)))
    return Model(sessions=tuple(states))


class HudStateTests(unittest.TestCase):
    def setUp(self):
        self.hud = HudState()

    def test_no_beep_for_panes_blocked_at_start(self):
        view = self.hud.update(model(agent("a")), set())
        self.assertFalse(view.beep_blocked)
        self.assertEqual([r.text for r in view.blocked], ["api · main · claude"])

    def test_beeps_once_when_pane_becomes_blocked(self):
        self.hud.update(model(agent("a", "working")), set())
        self.assertTrue(self.hud.update(model(agent("a"), agent("b")), set()).beep_blocked)
        self.assertFalse(self.hud.update(model(agent("a"), agent("b")), set()).beep_blocked)

    def test_hidden_when_nothing_blocked(self):
        view = self.hud.update(model(agent("a", "working"), agent("b", "done")), set())
        self.assertEqual(view.blocked, ())
        self.assertFalse(view.visible)

    def test_viewed_pane_is_hidden_and_silent_then_returns_without_beep(self):
        self.hud.update(model(agent("a", "working", focused=True)), set())
        viewed = self.hud.update(model(agent("a", focused=True)), {"default"})
        self.assertFalse(viewed.beep_blocked)
        self.assertFalse(viewed.visible)
        back = self.hud.update(model(agent("a", focused=True)), set())
        self.assertFalse(back.beep_blocked)
        self.assertEqual(len(back.blocked), 1)

    def test_focused_pane_in_unviewed_session_stays_visible(self):
        self.hud.update(model(agent("a", "working", focused=True)), set())
        view = self.hud.update(model(agent("a", focused=True)), {"work"})
        self.assertTrue(view.beep_blocked)
        self.assertEqual(len(view.blocked), 1)

    def test_session_name_shown_only_with_several_sessions(self):
        both = (DEFAULT, WORK)
        view = self.hud.update(model(agent("a"), agent("b", session="work"), sessions=both), set())
        self.assertEqual(
            [r.text for r in view.blocked],
            ["default · api · main · claude", "work · api · main · claude"],
        )

    def test_error_row_after_consecutive_failed_polls(self):
        down = Model(error="herdr session list exited 1")
        for _ in range(ERROR_POLLS - 1):
            self.assertIsNone(self.hud.update(down, set()).error)
        view = self.hud.update(down, set())
        self.assertEqual(view.error, "herdr session list exited 1")
        self.assertTrue(view.visible)
        self.assertIsNone(self.hud.update(model(), set()).error)

    def test_unreachable_session_recovery_does_not_rebeep(self):
        both = (DEFAULT, WORK)
        self.hud.update(model(agent("b", session="work"), sessions=both), set())
        self.hud.update(model(sessions=both, failed=("work",)), set())
        view = self.hud.update(model(agent("b", session="work"), sessions=both), set())
        self.assertFalse(view.beep_blocked)

    def test_session_list_failure_keeps_known_panes(self):
        self.hud.update(model(agent("a")), set())
        self.hud.update(Model(error="down"), set())
        self.assertFalse(self.hud.update(model(agent("a")), set()).beep_blocked)

    def test_baseline_waits_for_a_clean_poll(self):
        self.hud.update(Model(error="down"), set())
        self.assertFalse(self.hud.update(model(agent("a")), set()).beep_blocked)


if __name__ == "__main__":
    unittest.main()
