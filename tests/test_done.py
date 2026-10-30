import re
import unittest

from herdr_blocked_hud.logic import (
    DoneConfig, DoneTracker, HudState, LongDone, mode_for, status_value,
)
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

# User's way of working: DONE may vanish once viewed, the rest must stay.
STICKY = DoneConfig(modes={"DONE": "transient"}, default_mode="sticky")


def agent(terminal, status="done", seq=1, session="default"):
    return Agent(session, f"w1:{terminal}", terminal, "w1", "w1:t1", "api", "main", "claude",
                 status, False, seq)


def model(*agents, sessions=(DEFAULT,), failed=()):
    return Model(sessions=tuple(
        SessionState(s, error="refused") if s.name in failed
        else SessionState(s, agents=tuple(a for a in agents if a.session == s.name))
        for s in sessions
    ))


class StatusValueTests(unittest.TestCase):
    def test_bottom_most_status_line_gives_the_value(self):
        self.assertEqual(status_value(REPLY, DoneConfig()), "NEEDS_USER")
        self.assertEqual(status_value("STATUS: WAITING\n", DoneConfig()), "WAITING")

    def test_no_status_line_or_failed_read(self):
        self.assertIsNone(status_value("all finished, DONE\n❯\n", DoneConfig()))
        self.assertIsNone(status_value(None, DoneConfig()))

    def test_custom_regex_group(self):
        config = DoneConfig(status_regex=r"^Result: (\w+)")
        self.assertEqual(status_value("Result: ok\nResult: failed\n", config), "failed")

    def test_modes(self):
        config = DoneConfig(modes={"DONE": "hide"}, default_mode="sticky",
                            no_status_mode="transient")
        self.assertEqual(mode_for("DONE", config), "hide")
        self.assertEqual(mode_for("NEEDS_USER", config), "sticky")
        self.assertEqual(mode_for(None, config), "transient")
        self.assertEqual(mode_for("NEEDS_USER", DoneConfig()), "transient")

    def test_invalid_settings_fail_at_construction(self):
        with self.assertRaises(re.error):
            DoneConfig(status_regex="[")
        for bad in [{"status_regex": "STATUS:"}, {"default_mode": "keep"},
                    {"no_status_mode": ""}, {"modes": {"DONE": "gone"}}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                DoneConfig(**bad)


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
        return [(d.agent.terminal_id, d.seconds, d.status) for d in tracker.update(m)]

    def test_reported_after_default_threshold(self):
        tracker = self.make()
        self.assertEqual(self.at(tracker, 0, model(agent("a"))), [])
        self.assertEqual(self.at(tracker, 4, model(agent("a"))), [])
        self.assertEqual(self.at(tracker, 5, model(agent("a"))), [("a", 5, None)])

    def test_new_completion_restarts_timer(self):
        tracker = self.make(DoneConfig(after_seconds=60))
        self.at(tracker, 0, model(agent("a", seq=1)))
        self.assertEqual(self.at(tracker, 70, model(agent("a", seq=2))), [])
        self.assertEqual(self.at(tracker, 130, model(agent("a", seq=2))), [("a", 60, None)])

    def test_transient_leaves_when_viewed(self):
        tracker = self.make(reads={"a": "STATUS: DONE\n"})
        self.at(tracker, 0, model(agent("a")))
        self.assertEqual(self.at(tracker, 6, model(agent("a"))), [("a", 6, "DONE")])
        self.assertEqual(self.at(tracker, 7, model(agent("a", status="idle"))), [])
        # Same completion seen again later starts counting anew.
        self.assertEqual(self.at(tracker, 8, model(agent("a"))), [])

    def test_sticky_stays_while_idle_and_leaves_when_working(self):
        tracker = self.make(STICKY, reads={"a": REPLY})
        self.at(tracker, 0, model(agent("a")))
        self.assertEqual(self.at(tracker, 6, model(agent("a"))), [("a", 6, "NEEDS_USER")])
        idle = model(agent("a", status="idle"))
        self.assertEqual(self.at(tracker, 7, idle), [("a", 7, "NEEDS_USER")])
        self.assertEqual(self.at(tracker, 900, idle), [("a", 900, "NEEDS_USER")])
        self.assertEqual(self.at(tracker, 901, model(agent("a", status="working", seq=None))), [])
        self.assertEqual(self.at(tracker, 902, idle), [])

    def test_sticky_leaves_on_new_completion(self):
        tracker = self.make(STICKY, reads={"a": REPLY})
        self.at(tracker, 0, model(agent("a")))
        self.at(tracker, 6, model(agent("a", status="idle")))
        self.assertEqual(self.at(tracker, 7, model(agent("a", status="idle", seq=2))), [])

    def test_sticky_viewed_before_threshold_is_still_listed(self):
        tracker = self.make(STICKY, reads={"a": REPLY, "b": "STATUS: DONE\n"})
        self.at(tracker, 0, model(agent("a"), agent("b")))
        got = self.at(tracker, 1, model(agent("a", status="idle"), agent("b", status="idle")))
        self.assertEqual(got, [("a", 1, "NEEDS_USER")])

    def test_no_status_line_uses_no_status_mode(self):
        config = DoneConfig(default_mode="sticky", no_status_mode="hide")
        tracker = self.make(config, reads={"b": REPLY})
        m = model(agent("a"), agent("b"))
        self.at(tracker, 0, m)
        self.assertEqual(self.at(tracker, 5, m), [("b", 5, "NEEDS_USER")])

    def test_hide_is_never_listed(self):
        tracker = self.make(DoneConfig(modes={"DONE": "hide"}),
                            reads={"a": "STATUS: DONE\n", "b": REPLY})
        m = model(agent("a"), agent("b"))
        self.at(tracker, 0, m)
        self.assertEqual(self.at(tracker, 5, m), [("b", 5, "NEEDS_USER")])
        self.assertEqual(self.at(tracker, 6, m), [("b", 6, "NEEDS_USER")])

    def test_dismissed_completion_is_not_listed_again(self):
        tracker = self.make(STICKY, reads={"a": REPLY})
        self.at(tracker, 0, model(agent("a")))
        self.at(tracker, 5, model(agent("a")))
        tracker.dismiss(agent("a"))
        self.assertEqual(self.at(tracker, 6, model(agent("a"))), [])
        self.assertEqual(self.at(tracker, 7, model(agent("a", status="idle"))), [])
        # A new completion of the same pane is listed again.
        self.at(tracker, 8, model(agent("a", seq=2)))
        self.assertEqual(self.at(tracker, 13, model(agent("a", seq=2))),
                         [("a", 5, "NEEDS_USER")])

    def test_unreachable_session_keeps_timer(self):
        both = (DEFAULT, WORK)
        tracker = self.make(DoneConfig(after_seconds=60))
        self.at(tracker, 0, model(agent("b", session="work"), sessions=both))
        self.at(tracker, 30, model(sessions=both, failed=("work",)))
        self.at(tracker, 31, Model(error="session list down"))
        got = self.at(tracker, 60, model(agent("b", session="work"), sessions=both))
        self.assertEqual(got, [("b", 60, None)])

    def test_reads_once_per_completion(self):
        tracker = self.make(DoneConfig(read_lines=40), reads={"a": REPLY})
        m = model(agent("a"), agent("b"))
        self.at(tracker, 0, m)
        self.at(tracker, 5, m)
        self.at(tracker, 6, m)
        self.assertEqual(sorted(self.reads), [("w1:a", 40), ("w1:b", 40)])


class DoneViewTests(unittest.TestCase):
    def test_done_sections_sound_and_visibility(self):
        hud = HudState()
        m = model(agent("a"), agent("b"), agent("c"))
        a, b, c = m.sessions[0].agents
        empty = hud.update(m, ())
        self.assertFalse(empty.visible)
        view = hud.update(m, (LongDone(a, 65, "DONE"), LongDone(b, 3700, "NEEDS_USER"),
                              LongDone(c, 70)))
        self.assertTrue(view.beep_done)
        self.assertFalse(view.beep_blocked)
        self.assertEqual(
            [(s.title, [r.text for r in s.rows]) for s in view.done],
            [("Done · NEEDS_USER", ["api · main · claude · 1h01m"]),
             ("Done", ["api · main · claude · 1m"]),
             ("Done · DONE", ["api · main · claude · 1m"])],
        )
        self.assertTrue(view.visible)
        again = hud.update(m, (LongDone(a, 66, "DONE"),))
        self.assertFalse(again.beep_done)
        self.assertFalse(hud.update(m, ()).visible)

    def test_sticky_row_first_listed_while_idle_does_not_beep(self):
        hud = HudState()
        m = model(agent("a", status="idle"))
        hud.update(m, ())
        view = hud.update(m, (LongDone(m.sessions[0].agents[0], 1, "NEEDS_USER"),))
        self.assertTrue(view.visible)
        self.assertFalse(view.beep_done)


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

    def test_builtin_default_resolves_per_kind(self):
        from herdr_blocked_hud.app import sound_for
        from herdr_blocked_hud.config import Config
        from herdr_blocked_hud.logic import View

        def builtin(kind):
            return f"/cache/{kind}.wav"

        def unwritable(kind):
            raise OSError("read-only")

        default = Config()
        self.assertEqual(sound_for(View(beep_blocked=True), default, builtin), "/cache/blocked.wav")
        self.assertEqual(sound_for(View(beep_done=True), default, builtin), "/cache/done.wav")
        self.assertIsNone(sound_for(View(beep_blocked=True), default, unwritable))


if __name__ == "__main__":
    unittest.main()
