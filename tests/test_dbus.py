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
