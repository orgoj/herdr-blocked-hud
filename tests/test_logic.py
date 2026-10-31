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
        view = self.hud.update(model(agent("a")))
        self.assertFalse(view.beep_blocked)
        self.assertEqual([r.text for r in view.blocked], ["api · main · claude"])

    def test_beeps_once_when_pane_becomes_blocked(self):
        self.hud.update(model(agent("a", "working")))
        self.assertTrue(self.hud.update(model(agent("a"), agent("b"))).beep_blocked)
        self.assertFalse(self.hud.update(model(agent("a"), agent("b"))).beep_blocked)

    def test_hidden_when_nothing_blocked(self):
        view = self.hud.update(model(agent("a", "working"), agent("b", "done")))
        self.assertEqual(view.blocked, ())
        self.assertFalse(view.visible)

    def test_focused_pane_is_listed_and_beeps(self):
        self.hud.update(model(agent("a", "working", focused=True)))
        view = self.hud.update(model(agent("a", focused=True)))
        self.assertTrue(view.beep_blocked)
        self.assertEqual(len(view.blocked), 1)
        self.assertTrue(view.visible)

    def test_session_name_shown_only_with_several_sessions(self):
        both = (DEFAULT, WORK)
        view = self.hud.update(model(agent("a"), agent("b", session="work"), sessions=both))
        self.assertEqual(
            [r.text for r in view.blocked],
            ["default · api · main · claude", "work · api · main · claude"],
        )

    def test_error_row_after_consecutive_failed_polls(self):
        down = Model(error="herdr session list exited 1")
        for _ in range(ERROR_POLLS - 1):
            self.assertIsNone(self.hud.update(down).error)
        view = self.hud.update(down)
        self.assertEqual(view.error, "herdr session list exited 1")
        self.assertTrue(view.visible)
        self.assertIsNone(self.hud.update(model()).error)

    def test_unreachable_session_recovery_does_not_rebeep(self):
        both = (DEFAULT, WORK)
        self.hud.update(model(agent("b", session="work"), sessions=both))
        self.hud.update(model(sessions=both, failed=("work",)))
        view = self.hud.update(model(agent("b", session="work"), sessions=both))
        self.assertFalse(view.beep_blocked)

    def test_session_list_failure_keeps_known_panes(self):
        self.hud.update(model(agent("a")))
        self.hud.update(Model(error="down"))
        self.assertFalse(self.hud.update(model(agent("a"))).beep_blocked)

    def test_baseline_waits_for_a_clean_poll(self):
        self.hud.update(Model(error="down"))
        self.assertFalse(self.hud.update(model(agent("a"))).beep_blocked)


class LayoutTests(unittest.TestCase):
    def test_lines_and_their_keys(self):
        from herdr_blocked_hud.logic import Row, Section, View, layout

        a, b = agent("a"), agent("b", status="done")
        items = layout(View(
            blocked=(Row(a, "row a"),),
            done=(Section("Done · DONE", (Row(b, "row b · 3m"),)),),
            error="refused",
        ))
        self.assertEqual([(i.key, i.text) for i in items], [
            (("header",), "Blocked"),
            (("row", ("default", "a"), False), "▶ row a"),
            (("header", 1), "Done · DONE"),
            (("row", ("default", "b"), True), "▶ row b · 3m"),
            (("error",), "herdr unreachable: refused"),
        ])
        self.assertEqual([i.agent for i in items], [None, a, None, b, None])
        # The key names the line, not what it shows: elapsed time, focus and
        # completion changes keep it.
        later = layout(View(done=(Section("Done", (Row(
            agent("b", status="done", focused=True), "row b · 4m"),)),)))
        self.assertEqual(later[1].key, items[3].key)
        self.assertEqual([i.key for i in layout(View())], [("header",)])

    def test_keys_stay_unique(self):
        from herdr_blocked_hud.logic import Row, Section, View, layout

        a = agent("a", status="done")
        items = layout(View(done=(Section("Done", (Row(a, "one"), Row(a, "two"))),)))
        keys = [i.key for i in items]
        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(keys[2], ("row", ("default", "a"), True, 1))


if __name__ == "__main__":
    unittest.main()
