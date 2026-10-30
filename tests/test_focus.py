import unittest
from unittest import mock

from herdr_blocked_hud import focus
from herdr_blocked_hud.source import Agent, Session

AGENT = Agent("work", "w2:p4", "term_x", "w2", "w2:t1", "api", "main", "claude",
              "blocked", False, None)
SESSIONS = [Session("work", "/c/work.sock", False)]


CLASS_ONLY = [focus.x11.Window("0x0420", 5893, "herdr.herdr")]


class RaiseWindowTests(unittest.TestCase):
    """Clients under a mux server: only the WM_CLASS fallback could match."""

    def raise_with(self, clients):
        activated = []
        with mock.patch.object(focus.x11, "ui_clients", return_value=clients), \
                mock.patch.object(focus.x11, "list_windows", return_value=CLASS_ONLY), \
                mock.patch.object(focus.x11, "parent_pid", return_value=None), \
                mock.patch.object(focus.x11, "activate", side_effect=activated.append), \
                mock.patch.object(focus, "log"):
            focus.raise_session_window("work", SESSIONS, "herdr.herdr")
        return activated

    def test_class_fallback_when_only_this_session_has_clients(self):
        self.assertEqual(self.raise_with({"work": [8000]}), CLASS_ONLY)

    def test_no_class_fallback_when_another_session_has_clients(self):
        # Two sessions with the same terminal class: the match may be the
        # other session's window, so nothing is raised.
        self.assertEqual(self.raise_with({"work": [8000], "default": [9000]}), [])
        self.assertEqual(self.raise_with({"default": [9000]}), [])


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
