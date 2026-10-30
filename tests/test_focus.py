import unittest
from unittest import mock

from herdr_blocked_hud import focus
from herdr_blocked_hud.source import Agent, Session

AGENT = Agent("work", "w2:p4", "term_x", "w2", "w2:t1", "api", "main", "claude",
              "blocked", False, None)
SESSIONS = [Session("work", "/c/work.sock", False)]


class FocusAgentTests(unittest.TestCase):
    def test_focus_then_raise_session_window(self):
        calls = []
        ok = focus.focus_agent(
            AGENT,
            SESSIONS,
            "herdr.herdr",
            agent_focus=lambda a: calls.append(("focus", a.pane_id)) or True,
            raise_window=lambda s, ss, c: calls.append(("raise", s, c)) or True,
        )
        self.assertTrue(ok)
        self.assertEqual(calls, [("focus", "w2:p4"), ("raise", "work", "herdr.herdr")])

    def test_failed_focus_raises_nothing(self):
        raised = []
        ok = focus.focus_agent(
            AGENT,
            SESSIONS,
            agent_focus=lambda a: False,
            raise_window=lambda *args: raised.append(args) or True,
        )
        self.assertFalse(ok)
        self.assertEqual(raised, [])

    def test_agent_focus_command(self):
        result = mock.Mock(returncode=0, stderr="")
        with mock.patch.object(focus.subprocess, "run", return_value=result) as run:
            self.assertTrue(focus.herdr_agent_focus(AGENT))
        self.assertEqual(
            run.call_args.args[0],
            ["herdr", "--session", "work", "agent", "focus", "w2:p4"],
        )

    def test_agent_focus_failure(self):
        result = mock.Mock(returncode=1, stderr="agent_not_found")
        with mock.patch.object(focus.subprocess, "run", return_value=result), \
                mock.patch.object(focus, "log"):
            self.assertFalse(focus.herdr_agent_focus(AGENT))


if __name__ == "__main__":
    unittest.main()
