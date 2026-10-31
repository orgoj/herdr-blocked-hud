import pathlib
import queue
import shutil
import subprocess
import tempfile
import unittest

from herdr_blocked_hud import dbus, tray
from herdr_blocked_hud.dbus import Message
from herdr_blocked_hud.tray import GREY, ORANGE, RED, TrayItem, TrayState, pixmap

ROOT = pathlib.Path(__file__).resolve().parent.parent


class FakeConnection:
    def __init__(self):
        self.sent = []

    def reply(self, call, signature="", body=()):
        self.sent.append(("reply", signature, body))

    def error(self, call, name, text):
        self.sent.append(("error", name))

    def signal(self, path, interface, member, signature="", body=()):
        self.sent.append(("signal", member))

    def call(self, destination, path, interface, member, signature="", body=(),
             expect_reply=True):
        self.sent.append(("call", member, body))


def call(member, interface=tray.ITEM_INTERFACE, signature="", body=(), path=tray.ITEM_PATH):
    return Message(dbus.METHOD_CALL, serial=5, path=path, interface=interface, member=member,
                   sender=":1.9", signature=signature, body=body)


class TrayItemTests(unittest.TestCase):
    def setUp(self):
        self.events = queue.Queue()
        self.item = TrayItem(self.events, "org.kde.StatusNotifierItem-1-1")
        self.connection = FakeConnection()

    def handle(self, message):
        self.connection.sent.clear()
        self.item.handle(self.connection, message)
        return self.connection.sent

    def test_state_colour_and_tooltip(self):
        self.assertEqual(TrayState().color, GREY)
        self.assertEqual(TrayState(done=1).color, ORANGE)
        self.assertEqual(TrayState(blocked=1, done=2).color, RED)
        self.assertEqual(TrayState(2, 1).tooltip, "2 blocked, 1 done")
        both = frozenset({"blocked", "done"})
        self.assertEqual(TrayState(0, 0, muted=both).tooltip, "0 blocked, 0 done · muted")
        self.assertEqual(TrayState(0, 0, muted=frozenset({"done"})).tooltip,
                         "0 blocked, 0 done · done muted")
        self.assertEqual(TrayState(0, 0, muted=frozenset({"blocked"})).tooltip,
                         "0 blocked, 0 done · blocked muted")

    def test_pixmap_is_argb32_big_endian(self):
        width, height, data = pixmap(22, RED)
        self.assertEqual((width, height, len(data)), (22, 22, 22 * 22 * 4))
        center = (11 * 22 + 11) * 4
        self.assertEqual(data[center:center + 4], bytes([0xFF, 0xF3, 0x8B, 0xA8]))
        self.assertEqual(data[0], 0)        # transparent corner

    def test_properties_and_methods(self):
        self.item.set_state(TrayState(blocked=1, done=0))
        [(kind, signature, (properties,))] = self.handle(
            call("GetAll", tray.PROPERTIES, "s", (tray.ITEM_INTERFACE,)))
        self.assertEqual((kind, signature), ("reply", "a{sv}"))
        self.assertEqual(properties["ToolTip"][1][3], "1 blocked, 0 done")
        self.assertEqual(properties["IconPixmap"][1][0][2][4:8], bytes([0, 0xF3, 0x8B, 0xA8]))
        self.assertNotIn("Menu", properties)
        self.assertEqual(
            self.handle(call("Get", tray.PROPERTIES, "ss", (tray.ITEM_INTERFACE, "Status"))),
            [("reply", "v", (("s", "Active"),))],
        )
        self.assertEqual(
            self.handle(call("Get", tray.PROPERTIES, "ss", (tray.ITEM_INTERFACE, "Menu"))),
            [("error", "org.freedesktop.DBus.Error.UnknownProperty")],
        )
        self.assertEqual(self.handle(call("Activate", body=(3, 4), signature="ii")),
                         [("reply", "", ())])
        self.handle(call("ContextMenu", body=(30, 40), signature="ii"))
        self.handle(call("SecondaryActivate", body=(1, 1), signature="ii"))
        self.assertEqual([self.events.get_nowait(), self.events.get_nowait()],
                         [("activate",), ("menu", 30, 40)])
        self.assertTrue(self.events.empty())
        self.assertEqual(self.handle(call("Nope")),
                         [("error", "org.freedesktop.DBus.Error.UnknownMethod")])
        self.assertEqual(self.handle(call("GetAll", tray.PROPERTIES, path="/other")),
                         [("error", "org.freedesktop.DBus.Error.UnknownObject")])
        [(_, signature, (xml,))] = self.handle(call("Introspect", tray.INTROSPECTABLE))
        self.assertIn('name="ContextMenu"', xml)

    def test_set_state_signals_only_changes(self):
        self.item.connection = self.connection
        self.item.set_state(TrayState(done=1))
        self.assertEqual(self.connection.sent, [("signal", "NewIcon"), ("signal", "NewToolTip")])
        self.connection.sent.clear()
        self.item.set_state(TrayState(done=1))
        self.item.set_state(TrayState(done=2))
        self.assertEqual(self.connection.sent, [("signal", "NewToolTip")])

    def test_new_watcher_gets_a_registration(self):
        def owner_changed(old, new, sender=dbus.BUS_NAME):
            return Message(dbus.SIGNAL, member="NameOwnerChanged", signature="sss",
                           sender=sender, body=(tray.WATCHER, old, new))

        self.assertEqual(self.handle(owner_changed("", ":1.77")),
                         [("call", "RegisterStatusNotifierItem", (self.item.service,))])
        self.assertEqual(self.handle(owner_changed(":1.77", "")), [])
        # Another client sending the signal straight to the HUD is ignored.
        self.assertEqual(self.handle(owner_changed("", ":1.78", sender=":1.9")), [])

    def test_wrong_argument_types_are_refused(self):
        for member, signature, body in (("ContextMenu", "ss", ("a", "b")),
                                        ("Activate", "", ()),
                                        ("ContextMenu", "iii", (1, 2, 3))):
            self.assertEqual(self.handle(call(member, signature=signature, body=body)),
                             [("error", "org.freedesktop.DBus.Error.InvalidArgs")])
        self.assertEqual(self.handle(call("Get", tray.PROPERTIES, "s", ("x",))),
                         [("error", "org.freedesktop.DBus.Error.InvalidArgs")])
        self.assertTrue(self.events.empty())

    def test_click_flood_is_bounded(self):
        item = TrayItem(queue.Queue(tray.MAX_EVENTS), "svc")
        for _ in range(1000):
            item.handle(self.connection, call("Activate", signature="ii", body=(0, 0)))
        self.assertEqual(item.events.qsize(), tray.MAX_EVENTS)


@unittest.skipUnless(shutil.which("dbus-daemon") and shutil.which("gdbus"),
                     "needs dbus-daemon and gdbus")
class PrivateBusTests(unittest.TestCase):
    """Against a real, private dbus-daemon; gdbus decodes independently."""

    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        directory = tempfile.mkdtemp(dir=ROOT / "tmp")
        self.addCleanup(shutil.rmtree, directory)
        self.daemon = subprocess.Popen(
            ["dbus-daemon", "--session", "--nofork", "--nopidfile", "--print-address",
             f"--address=unix:path={directory}/bus"],
            stdout=subprocess.PIPE, text=True,
        )
        self.addCleanup(self.daemon.stdout.close)
        self.addCleanup(self.daemon.wait)
        self.addCleanup(self.daemon.terminate)
        self.address = self.daemon.stdout.readline().strip()

    def watcher(self):
        connection = dbus.Connection.open(self.address)
        self.addCleanup(connection.close)
        connection.call_wait(dbus.BUS_NAME, dbus.BUS_PATH, dbus.BUS_NAME, "RequestName", "su",
                             (tray.WATCHER, 4))
        connection.sock.settimeout(5)
        return connection

    def registration(self, watcher):
        while True:
            message = watcher.receive()
            if message.member == "RegisterStatusNotifierItem":
                return message.body[0]

    def gdbus(self, service, method, *args):
        return subprocess.run(
            ["gdbus", "call", "--address", self.address, "--dest", service,
             "--object-path", tray.ITEM_PATH, "--method", method, *args],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout

    def test_registers_answers_and_re_registers(self):
        watcher = self.watcher()
        item = tray.start(self.address)
        events = item.events
        service = self.registration(watcher)
        self.assertEqual(service, item.service)

        item.set_state(TrayState(blocked=2, done=1, muted=frozenset({"blocked", "done"})))
        output = self.gdbus(service, "org.freedesktop.DBus.Properties.GetAll",
                            tray.ITEM_INTERFACE)
        self.assertIn("'2 blocked, 1 done · muted'", output)
        self.assertIn("'Category': <'ApplicationStatus'>", output)
        self.gdbus(service, "org.kde.StatusNotifierItem.Activate", "1", "2")
        self.gdbus(service, "org.kde.StatusNotifierItem.ContextMenu", "100", "200")
        self.assertEqual(events.get(timeout=5), ("activate",))
        self.assertEqual(events.get(timeout=5), ("menu", 100, 200))

        # The panel restarts: a new watcher owner gets a fresh registration.
        watcher.close()
        self.assertEqual(self.registration(self.watcher()), service)


if __name__ == "__main__":
    unittest.main()
