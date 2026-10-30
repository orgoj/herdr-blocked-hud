import json
import pathlib
import shutil
import socket
import tempfile
import threading
import unittest

from herdr_blocked_hud import source
from herdr_blocked_hud.source import Model, Poller, Session, SessionState, SourceError

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SESSION = Session(name="default", socket_path="/unused", default=True)


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class FakeHerdr:
    """One-shot Unix socket server answering each connection with `reply`."""

    def __init__(self, reply: bytes | None):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=ROOT / "tmp")
        self.path = str(pathlib.Path(self.dir) / "herdr.sock")
        self.reply = reply
        self.requests = []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(1)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        conn, _ = self.server.accept()
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                data += conn.recv(4096)
            self.requests.append(json.loads(data))
            if self.reply is not None:
                # Split the reply to exercise reads across several recv calls.
                for start in range(0, len(self.reply), 1000):
                    conn.sendall(self.reply[start : start + 1000])

    def close(self):
        self.thread.join(timeout=2)
        self.server.close()
        shutil.rmtree(self.dir, ignore_errors=True)


class ParseTests(unittest.TestCase):
    def test_session_list_keeps_running_sessions(self):
        sessions = source.parse_session_list(fixture("session-list.json"))
        self.assertEqual([s.name for s in sessions], ["default", "work"])
        self.assertTrue(sessions[0].default)
        self.assertEqual(
            sessions[1].socket_path, "/home/user/.config/herdr/sessions/work/herdr.sock"
        )

    def test_snapshot_agents_with_labels(self):
        agents = source.parse_snapshot(SESSION, fixture("session-snapshot.json")["result"])
        by_pane = {a.pane_id: a for a in agents}
        self.assertEqual(len(agents), 4)

        blocked = by_pane["w1:p1"]
        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(
            (blocked.workspace_label, blocked.tab_label, blocked.agent_label),
            ("api", "main", "claude"),
        )
        self.assertEqual(blocked.terminal_id, "term_a")
        self.assertTrue(blocked.focused)
        self.assertIsNone(blocked.completion_seq)
        self.assertEqual(blocked.session, "default")

        self.assertEqual(by_pane["w1:p2"].agent_label, "Reviewer")
        self.assertEqual(by_pane["w1:p3"].agent_label, "builder")

        done = by_pane["w2:p1"]
        # Workspace and tab without a label fall back to their number.
        self.assertEqual((done.workspace_label, done.tab_label), ("2", "1"))
        self.assertEqual(done.completion_seq, 20)

    def test_model_filters_by_status_across_sessions(self):
        agents = source.parse_snapshot(SESSION, fixture("session-snapshot.json")["result"])
        other = Session("work", "/unused2", False)
        model = Model(
            sessions=(
                SessionState(SESSION, agents=agents),
                SessionState(other, error="work: refused"),
            )
        )
        self.assertEqual([a.pane_id for a in model.agents_with_status("blocked")], ["w1:p1"])
        self.assertEqual([a.pane_id for a in model.agents_with_status("done")], ["w2:p1"])
        self.assertEqual(model.errors, ["work: work: refused"])


class RequestTests(unittest.TestCase):
    def serve(self, reply):
        server = FakeHerdr(reply)
        self.addCleanup(server.close)
        return server

    def test_snapshot_over_socket(self):
        payload = (FIXTURES / "session-snapshot.json").read_bytes().replace(b"\n", b"")
        server = self.serve(payload + b"\n")
        state = source.read_session(Session("default", server.path, True))
        self.assertIsNone(state.error)
        self.assertEqual(len(state.agents), 4)
        self.assertEqual(
            server.requests, [{"id": "hud", "method": "session.snapshot", "params": {}}]
        )

    def test_error_response(self):
        reply = {"id": "hud", "error": {"code": "unknown_method", "message": "nope"}}
        server = self.serve(json.dumps(reply).encode() + b"\n")
        with self.assertRaisesRegex(SourceError, "unknown_method: nope"):
            source.request(server.path, "session.snapshot")

    def test_connection_closed_without_response(self):
        server = self.serve(None)
        state = source.read_session(Session("default", server.path, True))
        self.assertIn("connection closed", state.error)
        self.assertEqual(state.agents, ())

    def test_missing_socket_is_error_state(self):
        missing = str(ROOT / "tmp" / "no-such-herdr.sock")
        state = source.read_session(Session("default", missing, True))
        self.assertIsNotNone(state.error)
        self.assertEqual(state.agents, ())

    def test_bad_payload_is_error_state(self):
        server = self.serve(b'{"id":"hud","result":{"type":"x"}}\n')
        state = source.read_session(Session("default", server.path, True))
        self.assertIn("bad payload", state.error)


class PollerTests(unittest.TestCase):
    def make(self, list_sessions, read_session=None):
        self.now = 0.0
        return Poller(
            lambda model: None,
            list_sessions=list_sessions,
            read_session=read_session or (lambda s: SessionState(s)),
            clock=lambda: self.now,
        )

    def test_session_list_refreshed_every_ten_seconds(self):
        calls = []

        def list_sessions():
            calls.append(self.now)
            return [SESSION]

        poller = self.make(list_sessions)
        for t in (0.0, 1.0, 9.9, 10.0, 11.0, 20.5):
            self.now = t
            poller.poll_once()
        self.assertEqual(calls, [0.0, 10.0, 20.5])

    def test_session_list_failure_is_error_not_empty(self):
        def list_sessions():
            raise SourceError("herdr session list exited 1")

        model = self.make(list_sessions).poll_once()
        self.assertEqual(model.errors, ["herdr session list exited 1"])
        self.assertEqual(model.sessions, ())

    def test_session_list_retried_after_failure(self):
        results = [SourceError("down"), [SESSION]]

        def list_sessions():
            result = results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        poller = self.make(list_sessions)
        self.assertEqual(poller.poll_once().errors, ["down"])
        self.now = 1.0
        model = poller.poll_once()
        self.assertEqual(model.errors, [])
        self.assertEqual(len(model.sessions), 1)

    def test_no_running_session_is_error(self):
        model = self.make(lambda: []).poll_once()
        self.assertEqual(model.errors, ["no running Herdr session"])

    def test_poll_now_skips_the_interval(self):
        polls = threading.Semaphore(0)
        poller = Poller(
            lambda model: polls.release(),
            interval=60,
            list_sessions=lambda: [SESSION],
            read_session=lambda s: SessionState(s),
        )
        poller.start()
        self.addCleanup(poller.stop)
        self.assertTrue(polls.acquire(timeout=2))
        poller.poll_now()
        self.assertTrue(polls.acquire(timeout=2))

    def test_start_does_not_wait_for_a_slow_poll(self):
        release = threading.Event()
        delivered = threading.Event()

        def read_session(session):
            release.wait(5)
            return SessionState(session)

        poller = Poller(
            lambda model: delivered.set(),
            list_sessions=lambda: [SESSION],
            read_session=read_session,
        )
        poller.start()
        self.addCleanup(poller.stop)
        # The caller is free while the worker is stuck in a read.
        self.assertFalse(delivered.wait(0.2))
        release.set()
        self.assertTrue(delivered.wait(2))


if __name__ == "__main__":
    unittest.main()
