import re
import unittest

from herdr_blocked_hud.logic import DoneConfig, DoneTracker, HudState, LongDone, should_report
from herdr_blocked_hud.source import Agent, Model, Session, SessionState

DEFAULT = Session("default", "/s/default", True)
WORK = Session("work", "/s/work", False)

REPLY = """\
  STATUS: DONE
  Done: old turn
  ...
  STATUS: NEEDS_USER
  Done: half
────────────
❯
────────────
"""


def agent(terminal, status="done", seq=1, session="default"):
    return Agent(session, f"w1:{terminal}", terminal, "w1", "w1:t1", "api", "main", "claude",
                 status, False, seq)


def model(*agents, sessions=(DEFAULT,), failed=()):
    return Model(sessions=tuple(
        SessionState(s, error="refused") if s.name in failed
        else SessionState(s, agents=tuple(a for a in agents if a.session == s.name))
        for s in sessions
    ))


class ShouldReportTests(unittest.TestCase):
    def test_without_ignore_patterns_everything_is_reported(self):
        self.assertTrue(should_report("  STATUS: DONE", DoneConfig()))

    def test_only_bottom_most_status_line_decides(self):
        config = DoneConfig(ignore_regexes=[r"STATUS:\s*DONE\s*$"])
        self.assertTrue(should_report(REPLY, config))
        self.assertFalse(should_report(REPLY.replace("NEEDS_USER", "DONE"), config))

    def test_any_ignore_pattern_suppresses(self):
        config = DoneConfig(ignore_regexes=[r"DONE$", r"WAITING$"])
        self.assertFalse(should_report(REPLY.replace("NEEDS_USER", "WAITING"), config))

    def test_no_status_line_or_failed_read_is_reported(self):
        config = DoneConfig(ignore_regexes=[r"DONE"])
        self.assertTrue(should_report("all finished, DONE\n❯\n", config))
        self.assertTrue(should_report(None, config))

    def test_invalid_regex_fails_at_construction(self):
        with self.assertRaises(re.error):
            DoneConfig(ignore_regexes=["("])
        with self.assertRaises(re.error):
            DoneConfig(status_line_regex="[")


class DoneTrackerTests(unittest.TestCase):
    def make(self, config=None, reads=None):
        self.now = 0.0
        self.reads = []

        def read_tail(agent, lines):
            self.reads.append((agent.pane_id, lines))
            return (reads or {}).get(agent.terminal_id)

        return DoneTracker(config or DoneConfig(), read_tail, lambda: self.now)

    def at(self, tracker, t, m):
        self.now = t
        return [(d.agent.terminal_id, d.seconds) for d in tracker.update(m)]

    def test_reported_after_threshold(self):
        tracker = self.make()
        self.assertEqual(self.at(tracker, 0, model(agent("a"))), [])
        self.assertEqual(self.at(tracker, 59, model(agent("a"))), [])
        self.assertEqual(self.at(tracker, 60, model(agent("a"))), [("a", 60)])

    def test_new_completion_restarts_timer(self):
        tracker = self.make()
        self.at(tracker, 0, model(agent("a", seq=1)))
        self.assertEqual(self.at(tracker, 70, model(agent("a", seq=2))), [])
        self.assertEqual(self.at(tracker, 130, model(agent("a", seq=2))), [("a", 60)])

    def test_leaves_when_no_longer_done(self):
        tracker = self.make()
        self.at(tracker, 0, model(agent("a")))
        self.assertEqual(self.at(tracker, 61, model(agent("a", status="idle"))), [])
        # Same completion seen again later starts counting anew.
        self.assertEqual(self.at(tracker, 62, model(agent("a"))), [])

    def test_unreachable_session_keeps_timer(self):
        both = (DEFAULT, WORK)
        tracker = self.make()
        self.at(tracker, 0, model(agent("b", session="work"), sessions=both))
        self.at(tracker, 30, model(sessions=both, failed=("work",)))
        self.at(tracker, 31, Model(error="session list down"))
        got = self.at(tracker, 60, model(agent("b", session="work"), sessions=both))
        self.assertEqual(got, [("b", 60)])

    def test_custom_threshold(self):
        tracker = self.make(DoneConfig(after_seconds=5))
        self.at(tracker, 0, model(agent("a")))
        self.assertEqual(self.at(tracker, 5, model(agent("a"))), [("a", 5)])

    def test_no_reads_without_ignore_patterns(self):
        tracker = self.make()
        self.at(tracker, 0, model(agent("a")))
        self.at(tracker, 60, model(agent("a")))
        self.assertEqual(self.reads, [])

    def test_filter_reads_once_per_completion(self):
        config = DoneConfig(ignore_regexes=[r"STATUS:\s*DONE\s*$"], read_lines=40)
        tracker = self.make(config, reads={"a": "  STATUS: DONE\n", "b": REPLY})
        m = model(agent("a"), agent("b"))
        self.at(tracker, 0, m)
        self.assertEqual(self.at(tracker, 60, m), [("b", 60)])
        self.assertEqual(self.at(tracker, 61, m), [("b", 61)])
        self.assertEqual(sorted(self.reads), [("w1:a", 40), ("w1:b", 40)])


class DoneViewTests(unittest.TestCase):
    def test_done_rows_sound_and_visibility(self):
        hud = HudState()
        m = model(agent("a"), agent("b"))
        a, b = m.sessions[0].agents
        empty = hud.update(m, ())
        self.assertFalse(empty.visible)
        view = hud.update(m, (LongDone(a, 65), LongDone(b, 3700)))
        self.assertTrue(view.beep_done)
        self.assertFalse(view.beep_blocked)
        self.assertEqual(
            [r.text for r in view.done],
            ["api · main · claude · 1h01m", "api · main · claude · 1m"],
        )
        self.assertTrue(view.visible)
        again = hud.update(m, (LongDone(a, 66), LongDone(b, 3701)))
        self.assertFalse(again.beep_done)
        self.assertFalse(hud.update(m, ()).visible)


class SoundTests(unittest.TestCase):
    def test_done_switch_is_independent_of_blocked(self):
        from herdr_blocked_hud.app import sound_for
        from herdr_blocked_hud.config import Config
        from herdr_blocked_hud.logic import View

        on = Config(blocked_sound="b.oga", done_sound="d.oga")
        off = Config(blocked_sound="b.oga", done_sound="d.oga",
                     done=DoneConfig(sound_enabled=False))
        self.assertEqual(sound_for(View(beep_done=True), on), "d.oga")
        self.assertIsNone(sound_for(View(beep_done=True), off))
        self.assertEqual(sound_for(View(beep_blocked=True), off), "b.oga")
        self.assertEqual(sound_for(View(beep_blocked=True, beep_done=True), on), "b.oga")
        self.assertIsNone(sound_for(View(), on))
        self.assertIsNone(sound_for(View(beep_blocked=True), Config(blocked_sound="")))


if __name__ == "__main__":
    unittest.main()
