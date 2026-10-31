"""Minimal D-Bus client over the session bus socket, standard library only.

Covers what a StatusNotifierItem needs: SASL EXTERNAL authentication, method
calls, replies, errors and signals, and the marshalling of the basic types,
arrays, structs, dict entries and variants. No unix fd passing.

Values: `s`/`o`/`g` str, integer types int, `b` bool, `d` float, `ay` bytes,
other arrays list, `a{..}` dict, structs tuple, variants (signature, value).
"""

from __future__ import annotations

import os
import socket
import struct
import threading
from dataclasses import dataclass, field

METHOD_CALL, METHOD_RETURN, ERROR, SIGNAL = 1, 2, 3, 4
NO_REPLY_EXPECTED = 0x1

BUS_NAME = "org.freedesktop.DBus"
BUS_PATH = "/org/freedesktop/DBus"

# Header field codes and their types.
FIELDS = {
    1: ("path", "o"), 2: ("interface", "s"), 3: ("member", "s"), 4: ("error_name", "s"),
    5: ("reply_serial", "u"), 6: ("destination", "s"), 7: ("sender", "s"),
    8: ("signature", "g"),
}
FIELD_CODES = {name: (code, kind) for code, (name, kind) in FIELDS.items()}

FIXED = {"y": "B", "b": "I", "n": "h", "q": "H", "i": "i", "u": "I", "x": "q", "t": "Q",
         "d": "d", "h": "I"}
ALIGN = {"y": 1, "b": 4, "n": 2, "q": 2, "i": 4, "u": 4, "x": 8, "t": 8, "d": 8, "h": 4,
         "s": 4, "o": 4, "g": 1, "a": 4, "(": 8, "{": 8, "v": 1}
# The item exchanges small messages only; anything bigger is refused, which
# bounds what another session-bus client can make the HUD buffer.
MAX_MESSAGE = 1024 * 1024
MAX_PENDING = 64
MAX_AUTH_LINE = 1024
MAX_SIGNATURE = 255
MAX_DEPTH = 32          # nesting of arrays, structs and variants together
BASIC = set(FIXED) | set("sog")


class DBusError(Exception):
    pass


def split_signature(signature: str) -> list[str]:
    """Complete types of a valid signature: "a{sv}is" -> ["a{sv}", "i", "s"].

    Rejects what the D-Bus spec forbids: empty structs, dict entries outside
    an array or with a non-basic key, unbalanced brackets, too deep nesting.
    """
    if len(signature) > MAX_SIGNATURE:
        raise DBusError("signature too long")
    types, index = [], 0
    while index < len(signature):
        end = _type_end(signature, index, 0, in_array=False)
        types.append(signature[index:end])
        index = end
    return types


def _type_end(signature: str, index: int, depth: int, in_array: bool) -> int:
    if index >= len(signature):
        raise DBusError(f"incomplete signature {signature!r}")
    if depth > MAX_DEPTH:
        raise DBusError("signature nested too deep")
    char = signature[index]
    if char == "a":
        return _type_end(signature, index + 1, depth + 1, in_array=True)
    if char == "(":
        index += 1
        count = 0
        while index < len(signature) and signature[index] != ")":
            index = _type_end(signature, index, depth + 1, in_array=False)
            count += 1
        if index >= len(signature) or count == 0:
            raise DBusError(f"bad struct in signature {signature!r}")
        return index + 1
    if char == "{":
        if not in_array or index + 1 >= len(signature) or signature[index + 1] not in BASIC:
            raise DBusError(f"bad dict entry in signature {signature!r}")
        end = _type_end(signature, index + 2, depth + 1, in_array=False)
        if end >= len(signature) or signature[end] != "}":
            raise DBusError(f"bad dict entry in signature {signature!r}")
        return end + 1
    if char in BASIC or char == "v":
        return index + 1
    raise DBusError(f"bad signature {signature!r}")


class Writer:
    def __init__(self, endian: str = "<"):
        self.endian = endian
        self.data = bytearray()

    def align(self, n: int) -> None:
        self.data += b"\0" * (-len(self.data) % n)

    def write(self, signature: str, values: tuple | list) -> None:
        types = split_signature(signature)
        if len(types) != len(values):
            raise DBusError(f"{len(values)} values for signature {signature!r}")
        for kind, value in zip(types, values):
            self.value(kind, value)

    def value(self, kind: str, value: object) -> None:
        char = kind[0]
        self.align(ALIGN[char])
        if char in FIXED:
            self.data += struct.pack(self.endian + FIXED[char], value)
        elif char in "so":
            raw = value.encode()
            self.data += struct.pack(self.endian + "I", len(raw)) + raw + b"\0"
        elif char == "g":
            raw = value.encode()
            self.data += bytes([len(raw)]) + raw + b"\0"
        elif char == "v":
            signature, inner = value
            self.value("g", signature)
            self.value(signature, inner)
        elif char == "(":
            self.write(kind[1:-1], value)
        elif char == "{":
            key_type, value_type = split_signature(kind[1:-1])
            self.value(key_type, value[0])
            self.value(value_type, value[1])
        elif char == "a":
            self._array(kind[1:], value)

    def _array(self, element: str, value: object) -> None:
        length_at = len(self.data)
        self.data += b"\0\0\0\0"
        self.align(ALIGN[element[0]])
        start = len(self.data)
        if element == "y":
            self.data += bytes(value)
        else:
            items = value.items() if element[0] == "{" else value
            for item in items:
                self.value(element, item)
        struct.pack_into(self.endian + "I", self.data, length_at, len(self.data) - start)


class Reader:
    def __init__(self, data: bytes, endian: str = "<", offset: int = 0):
        self.data = data
        self.endian = endian
        self.offset = offset

    def align(self, n: int) -> None:
        self.offset += -self.offset % n

    def read(self, signature: str, depth: int = 0) -> tuple:
        return tuple(self.value(kind, depth) for kind in split_signature(signature))

    def value(self, kind: str, depth: int = 0) -> object:
        if depth > MAX_DEPTH:
            raise DBusError("value nested too deep")
        char = kind[0]
        self.align(ALIGN[char])
        if char in FIXED:
            fmt = self.endian + FIXED[char]
            (value,) = struct.unpack_from(fmt, self.data, self.offset)
            self.offset += struct.calcsize(fmt)
            return bool(value) if char == "b" else value
        if char in "so":
            (length,) = struct.unpack_from(self.endian + "I", self.data, self.offset)
            self.offset += 4
            return self._string(length)
        if char == "g":
            length = self.data[self.offset]
            self.offset += 1
            return self._string(length)
        if char == "v":
            signature = self.value("g")
            if len(split_signature(signature)) != 1:
                raise DBusError(f"variant signature {signature!r} is not one type")
            return (signature, self.value(signature, depth + 1))
        if char == "(":
            return self.read(kind[1:-1], depth + 1)
        if char == "{":
            key_type, value_type = split_signature(kind[1:-1])
            return (self.value(key_type, depth + 1), self.value(value_type, depth + 1))
        (length,) = struct.unpack_from(self.endian + "I", self.data, self.offset)
        self.offset += 4
        element = kind[1:]
        self.align(ALIGN[element[0]])
        end = self.offset + length
        if end > len(self.data):
            raise DBusError("array runs past the message")
        if element == "y":
            value = bytes(self.data[self.offset:end])
            self.offset = end
            return value
        items = []
        while self.offset < end:
            start = self.offset
            items.append(self.value(element, depth + 1))
            if self.offset <= start:
                raise DBusError("array element consumed no bytes")
        if self.offset != end:
            raise DBusError("array element runs past the array")
        return dict(items) if element[0] == "{" else items

    def _string(self, length: int) -> str:
        end = self.offset + length
        if end >= len(self.data) or self.data[end] != 0:
            raise DBusError("unterminated string")
        text = bytes(self.data[self.offset:end]).decode()
        self.offset = end + 1
        return text


@dataclass
class Message:
    type: int
    serial: int = 0
    flags: int = 0
    path: str | None = None
    interface: str | None = None
    member: str | None = None
    error_name: str | None = None
    reply_serial: int | None = None
    destination: str | None = None
    sender: str | None = None
    signature: str = ""
    body: tuple = field(default_factory=tuple)

    def encode(self) -> bytes:
        body = Writer()
        body.write(self.signature, self.body)
        fields = []
        for name, (code, kind) in FIELD_CODES.items():
            value = getattr(self, name)
            if name == "signature" and not value:
                continue
            if value is not None:
                fields.append((code, (kind, value)))
        header = Writer()
        header.write("yyyyuua(yv)", (ord("l"), self.type, self.flags, 1, len(body.data),
                                     self.serial, fields))
        header.align(8)
        return bytes(header.data + body.data)


def message_length(data: bytes) -> int | None:
    """Total length of the message at the start of `data`; None if unknown yet."""
    if len(data) < 16:
        return None
    if data[0:1] not in (b"l", b"B"):
        raise DBusError("bad endianness byte")
    endian = "<" if data[0:1] == b"l" else ">"
    body_length, _serial, fields_length = struct.unpack_from(endian + "III", data, 4)
    header = 16 + fields_length
    total = header + (-header % 8) + body_length
    if total > MAX_MESSAGE:
        raise DBusError("message too large")
    return total


def decode(data: bytes) -> Message:
    """Parse one message; any malformation raises DBusError."""
    try:
        return _decode(data)
    except DBusError:
        raise
    except (IndexError, struct.error, UnicodeDecodeError, ValueError, TypeError,
            KeyError, RecursionError) as err:
        raise DBusError(f"malformed message: {err!r}") from None


def _decode(data: bytes) -> Message:
    if data[0:1] not in (b"l", b"B"):
        raise DBusError("bad endianness byte")
    endian = "<" if data[0:1] == b"l" else ">"
    reader = Reader(data, endian)
    _endian, kind, flags, _version, body_length, serial, fields = reader.read("yyyyuua(yv)")
    message = Message(kind, serial, flags)
    for code, (signature, value) in fields:
        if code in FIELDS:
            name, expected = FIELDS[code]
            if signature != expected:
                raise DBusError(f"header field {name} has type {signature!r}")
            setattr(message, name, value)
    reader.align(8)
    if reader.offset + body_length > len(data):
        raise DBusError("body runs past the message")
    if message.signature:
        message.body = Reader(data[reader.offset:reader.offset + body_length], endian).read(
            message.signature
        )
    return message


def session_address() -> str:
    address = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if not address:
        raise DBusError("DBUS_SESSION_BUS_ADDRESS is not set")
    return address


def _connect_socket(address: str) -> socket.socket:
    errors = []
    for entry in address.split(";"):
        transport, _, params = entry.partition(":")
        options = dict(item.split("=", 1) for item in params.split(",") if "=" in item)
        if transport != "unix":
            continue
        if "path" in options:
            target = options["path"]
        elif "abstract" in options:
            target = "\0" + options["abstract"]
        else:
            continue
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(target)
            return sock
        except OSError as err:
            sock.close()
            errors.append(str(err))
    raise DBusError(f"cannot connect to {address!r}: {'; '.join(errors) or 'no unix address'}")


class Connection:
    """One bus connection. `send` is thread-safe; one thread reads."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buffer = b""
        self.serial = 0
        self.lock = threading.Lock()
        self.pending: list[Message] = []
        self.unique_name = ""

    @classmethod
    def open(cls, address: str | None = None, timeout: float = 5.0) -> Connection:
        sock = _connect_socket(address or session_address())
        sock.settimeout(timeout)
        connection = cls(sock)
        try:
            connection._authenticate()
            (connection.unique_name,) = connection.call_wait(
                BUS_NAME, BUS_PATH, BUS_NAME, "Hello"
            ).body
        except (OSError, DBusError):
            sock.close()
            raise
        sock.settimeout(None)
        return connection

    def _authenticate(self) -> None:
        uid = str(os.getuid()).encode().hex()
        self.sock.sendall(b"\0AUTH EXTERNAL " + uid.encode() + b"\r\n")
        line = self._auth_line()
        if not line.startswith(b"OK "):
            raise DBusError(f"authentication rejected: {line!r}")
        self.sock.sendall(b"BEGIN\r\n")

    def _auth_line(self) -> bytes:
        while b"\r\n" not in self.buffer:
            if len(self.buffer) > MAX_AUTH_LINE:
                raise DBusError("authentication line too long")
            chunk = self.sock.recv(4096)
            if not chunk:
                raise DBusError("bus closed during authentication")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\r\n", 1)
        return line

    def close(self) -> None:
        self.sock.close()

    def send(self, message: Message) -> int:
        with self.lock:
            self.serial += 1
            message.serial = self.serial
            self.sock.sendall(message.encode())
            return message.serial

    def call(self, destination: str, path: str, interface: str, member: str,
             signature: str = "", body: tuple = (), expect_reply: bool = True) -> int:
        return self.send(Message(
            METHOD_CALL, path=path, interface=interface, member=member,
            destination=destination, signature=signature, body=body,
            flags=0 if expect_reply else NO_REPLY_EXPECTED,
        ))

    def call_wait(self, destination: str, path: str, interface: str, member: str,
                  signature: str = "", body: tuple = ()) -> Message:
        """Call and read until its reply; other messages wait for `receive`."""
        serial = self.call(destination, path, interface, member, signature, body)
        while True:
            message = self._read()
            if message.reply_serial == serial and message.type in (METHOD_RETURN, ERROR):
                if message.type == ERROR:
                    text = message.body[0] if message.body else ""
                    raise DBusError(f"{message.error_name}: {text}")
                return message
            if len(self.pending) >= MAX_PENDING:
                self.pending.pop(0)
            self.pending.append(message)

    def receive(self) -> Message:
        if self.pending:
            return self.pending.pop(0)
        return self._read()

    def _read(self) -> Message:
        """Next well-formed message. A frame whose content does not parse is
        skipped (its length is still known); a bad frame header or a frame
        over MAX_MESSAGE ends the connection with DBusError."""
        while True:
            length = message_length(self.buffer)
            if length is not None and len(self.buffer) >= length:
                data, self.buffer = self.buffer[:length], self.buffer[length:]
                try:
                    return decode(data)
                except DBusError:
                    continue
            chunk = self.sock.recv(65536)
            if not chunk:
                raise DBusError("bus connection closed")
            self.buffer += chunk

    def reply(self, call: Message, signature: str = "", body: tuple = ()) -> None:
        if call.flags & NO_REPLY_EXPECTED:
            return
        self.send(Message(METHOD_RETURN, reply_serial=call.serial, destination=call.sender,
                          signature=signature, body=body))

    def error(self, call: Message, name: str, text: str) -> None:
        if call.flags & NO_REPLY_EXPECTED:
            return
        self.send(Message(ERROR, reply_serial=call.serial, destination=call.sender,
                          error_name=name, signature="s", body=(text,)))

    def signal(self, path: str, interface: str, member: str,
               signature: str = "", body: tuple = ()) -> None:
        self.send(Message(SIGNAL, path=path, interface=interface, member=member,
                          signature=signature, body=body))
