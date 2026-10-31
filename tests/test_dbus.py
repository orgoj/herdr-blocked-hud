import unittest

from herdr_blocked_hud import dbus
from herdr_blocked_hud.dbus import Message, Reader, Writer, decode, message_length, split_signature


class CodecTests(unittest.TestCase):
    def round_trip(self, signature, values):
        writer = Writer()
        writer.write(signature, values)
        return Reader(bytes(writer.data)).read(signature)

    def test_split_signature(self):
        self.assertEqual(split_signature("a{sv}is(sa(iiay)ss)ay"),
                         ["a{sv}", "i", "s", "(sa(iiay)ss)", "ay"])
        with self.assertRaises(dbus.DBusError):
            split_signature("z")

    def test_round_trip_of_the_tray_types(self):
        values = (
            {"Id": ("s", "hud"), "WindowId": ("i", -1), "ItemIsMenu": ("b", True),
             "IconPixmap": ("a(iiay)", [(2, 1, b"\x01\x02\x03\x04\x05\x06\x07\x08")]),
             "ToolTip": ("(sa(iiay)ss)", ("", [], "title", "2 blocked, 0 done · muted"))},
            7, "ž", True, b"", [], 2 ** 40,
        )
        decoded = self.round_trip("a{sv}usbayasx", values)
        self.assertEqual(decoded[0]["IconPixmap"], ("a(iiay)", [(2, 1, values[0]["IconPixmap"][1][0][2])]))
        self.assertEqual(decoded[0]["ToolTip"], ("(sa(iiay)ss)", ("", [], "title", "2 blocked, 0 done · muted")))
        self.assertEqual(decoded[1:], values[1:])

    def test_alignment_and_padding(self):
        writer = Writer()
        writer.write("yx", (1, 2))
        # The int64 starts on an 8-byte boundary.
        self.assertEqual(bytes(writer.data), b"\x01" + b"\0" * 7 + (2).to_bytes(8, "little"))
        writer = Writer()
        writer.write("a(i)", ([],))
        # Empty array: length 0, then padding to the struct alignment.
        self.assertEqual(bytes(writer.data), b"\0" * 8)

    def test_hello_message_bytes(self):
        message = Message(dbus.METHOD_CALL, serial=1, path=dbus.BUS_PATH, interface=dbus.BUS_NAME,
                          member="Hello", destination=dbus.BUS_NAME)
        data = message.encode()
        self.assertEqual(data[:4], b"l\x01\x00\x01")
        self.assertEqual(len(data) % 8, 0)
        self.assertEqual(message_length(data), len(data))
        decoded = decode(data)
        self.assertEqual((decoded.member, decoded.path, decoded.destination, decoded.body),
                         ("Hello", dbus.BUS_PATH, dbus.BUS_NAME, ()))

    def test_message_round_trip_with_body(self):
        message = Message(dbus.ERROR, serial=9, reply_serial=4, destination=":1.5",
                          error_name="org.example.Error", signature="s", body=("text",))
        decoded = decode(message.encode())
        self.assertEqual(
            (decoded.type, decoded.serial, decoded.reply_serial, decoded.error_name, decoded.body),
            (dbus.ERROR, 9, 4, "org.example.Error", ("text",)),
        )

    def test_big_endian_message_decodes(self):
        writer = Writer(">")
        writer.write("yyyyuua(yv)", (ord("B"), dbus.SIGNAL, 0, 1, 0, 3,
                                     [(1, ("o", "/a")), (3, ("s", "Sig"))]))
        writer.align(8)
        decoded = decode(bytes(writer.data))
        self.assertEqual((decoded.type, decoded.serial, decoded.path, decoded.member),
                         (dbus.SIGNAL, 3, "/a", "Sig"))

    def test_invalid_signatures_are_rejected(self):
        for signature in ("()", "a()", "{sv}", "a{vs}", "a{s}", "a{sss}", "a", "(i", "i)",
                          "a" * 40 + "i", "(" * 40 + "i" + ")" * 40, "s" * 256):
            with self.assertRaises(dbus.DBusError, msg=signature):
                split_signature(signature)

    def header(self, fields, body=b"", body_length=None):
        writer = Writer()
        writer.write("yyyyuua(yv)", (ord("l"), dbus.METHOD_CALL, 0, 1,
                                     len(body) if body_length is None else body_length, 1,
                                     fields))
        writer.align(8)
        return bytes(writer.data) + body

    def test_hostile_messages_raise_dbus_error(self):
        member = [(1, ("o", "/a")), (3, ("s", "M"))]
        cases = {
            # An array of empty structs would make no progress.
            "empty struct": self.header(member + [(8, ("g", "a()"))], b"\x08\0\0\0" + b"\0" * 8),
            "variant of two types": self.header(member + [(8, ("g", "v"))], b"\x02ii\0"),
            "field of the wrong type": self.header([(1, ("s", "/a")), (5, ("s", "x"))]),
            "body past the end": self.header(member + [(8, ("g", "s"))], b"", body_length=64),
            "bad utf-8": self.header(member + [(8, ("g", "s"))], b"\x02\0\0\0\xff\xfe\0"),
            "array past the array": self.header(
                member + [(8, ("g", "ai"))], b"\x02\0\0\0\x01\0\0\0"),
        }
        for name, data in cases.items():
            with self.assertRaises(dbus.DBusError, msg=name):
                decode(data)
        nested = "v"
        data = b""
        for _ in range(40):
            data += b"\x01v\0"
        with self.assertRaises(dbus.DBusError):
            Reader(data + b"\x01y\0\x07").read(nested)

    def test_oversized_frame_is_refused_before_buffering(self):
        frame = self.header([], body_length=dbus.MAX_MESSAGE)
        with self.assertRaises(dbus.DBusError):
            message_length(frame)

    def test_connection_skips_a_bad_frame_and_caps_buffers(self):
        import socket

        ours, theirs = socket.socketpair()
        self.addCleanup(ours.close)
        self.addCleanup(theirs.close)
        connection = dbus.Connection(ours)
        good = Message(dbus.SIGNAL, serial=2, path="/a", interface="x.y", member="Ok").encode()
        bad = self.header([(1, ("o", "/a")), (8, ("g", "a()"))], b"\x08\0\0\0" + b"\0" * 8)
        theirs.sendall(bad + good)
        self.assertEqual(connection.receive().member, "Ok")
        # Unrelated messages queued while waiting for a reply are capped.
        for serial in range(dbus.MAX_PENDING + 10):
            theirs.sendall(Message(dbus.SIGNAL, serial=serial + 3, path="/a", interface="x.y",
                                   member=f"S{serial}").encode())
        theirs.sendall(Message(dbus.METHOD_RETURN, serial=999, reply_serial=1).encode())
        connection.call_wait("x", "/", "x.y", "Z")
        self.assertEqual(len(connection.pending), dbus.MAX_PENDING)
        self.assertEqual(connection.pending[-1].member, f"S{dbus.MAX_PENDING + 9}")
        # A server that never ends its auth line is cut off.
        connection.buffer = b""
        theirs.sendall(b"x" * (dbus.MAX_AUTH_LINE + 10))
        with self.assertRaises(dbus.DBusError):
            connection._auth_line()

    def test_malformed_input_raises_dbus_error(self):
        with self.assertRaises(dbus.DBusError):
            Reader(b"\x05\0\0\0abc").read("s")
        with self.assertRaises(dbus.DBusError):
            Reader(b"\x10\0\0\0").read("ay")
        with self.assertRaises(dbus.DBusError):
            decode(b"x" + b"\0" * 15)
        with self.assertRaises(dbus.DBusError):
            dbus._connect_socket("tcp:host=localhost,port=1")


if __name__ == "__main__":
    unittest.main()
