"""Status-bar icon: a StatusNotifierItem exported over D-Bus.

Tk's own `tk systray` (XEmbed) gets no clicks in the LXQt panel, which proxies
XEmbed icons to StatusNotifierItems and injects clicks with XTest onto the
panel itself. So the HUD exports a StatusNotifierItem directly.

A worker thread owns the bus connection and answers the panel. Clicks reach
the Tk thread as events in a queue; the Tk thread calls `set_state`.
"""

from __future__ import annotations

import os
import queue
import struct
import sys
import threading
from dataclasses import dataclass

from . import dbus

ITEM_PATH = "/StatusNotifierItem"
ITEM_INTERFACE = "org.kde.StatusNotifierItem"
WATCHER = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
PROPERTIES = "org.freedesktop.DBus.Properties"
INTROSPECTABLE = "org.freedesktop.DBus.Introspectable"
PEER = "org.freedesktop.DBus.Peer"

GREY, ORANGE, RED = (0x9399B2, 0xFAB387, 0xF38BA8)
# Clicks waiting for the Tk thread; more are dropped (see TrayItem.post).
MAX_EVENTS = 4

# Argument signatures the item accepts; other calls get InvalidArgs.
METHOD_SIGNATURES = {
    (PROPERTIES, "GetAll"): "s",
    (PROPERTIES, "Get"): "ss",
    (ITEM_INTERFACE, "Activate"): "ii",
    (ITEM_INTERFACE, "SecondaryActivate"): "ii",
    (ITEM_INTERFACE, "ContextMenu"): "ii",
    (ITEM_INTERFACE, "Scroll"): "is",
}
ICON_SIZES = (16, 22, 32, 48)

INTROSPECTION = f"""<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
 <interface name="{ITEM_INTERFACE}">
  <property name="Category" type="s" access="read"/>
  <property name="Id" type="s" access="read"/>
  <property name="Title" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="WindowId" type="i" access="read"/>
  <property name="IconName" type="s" access="read"/>
  <property name="IconPixmap" type="a(iiay)" access="read"/>
  <property name="OverlayIconName" type="s" access="read"/>
  <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionIconName" type="s" access="read"/>
  <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionMovieName" type="s" access="read"/>
  <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
  <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
  <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
  <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
  <signal name="NewIcon"/>
  <signal name="NewToolTip"/>
  <signal name="NewStatus"><arg name="status" type="s"/></signal>
 </interface>
 <interface name="{PROPERTIES}">
  <method name="Get"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
  <method name="GetAll"><arg type="s" direction="in"/><arg type="a{{sv}}" direction="out"/></method>
 </interface>
 <interface name="{INTROSPECTABLE}">
  <method name="Introspect"><arg type="s" direction="out"/></method>
 </interface>
</node>
"""


@dataclass(frozen=True)
class TrayState:
    blocked: int = 0
    done: int = 0
    # Muted sound kinds: "blocked", "done".
    muted: frozenset[str] = frozenset()

    @property
    def color(self) -> int:
        return RED if self.blocked else ORANGE if self.done else GREY

    @property
    def tooltip(self) -> str:
        text = f"{self.blocked} blocked, {self.done} done"
        if {"blocked", "done"} <= self.muted:
            return text + " · muted"
        for kind in ("blocked", "done"):
            if kind in self.muted:
                return text + f" · {kind} muted"
        return text


def pixmap(size: int, color: int) -> tuple[int, int, bytes]:
    """A filled circle, ARGB32 in network byte order as the SNI spec wants."""
    pixels = bytearray()
    center = (size - 1) / 2
    radius = size * 0.42
    for y in range(size):
        for x in range(size):
            distance = ((x - center) ** 2 + (y - center) ** 2) ** 0.5
            alpha = max(0.0, min(1.0, radius + 0.5 - distance))
            pixels += struct.pack(">I", (round(alpha * 255) << 24) | color)
    return (size, size, bytes(pixels))


class TrayItem:
    """Answers the panel's calls; pure apart from the connection it is given."""

    def __init__(self, events: queue.Queue, service: str):
        self.events = events
        self.service = service
        self.connection: dbus.Connection | None = None
        self.lock = threading.Lock()
        self.state = TrayState()
        self.icons: dict[int, list] = {}

    def icon(self, color: int) -> list:
        if color not in self.icons:
            self.icons[color] = [pixmap(size, color) for size in ICON_SIZES]
        return self.icons[color]

    def properties(self) -> dict[str, tuple[str, object]]:
        with self.lock:
            state = self.state
        icon = self.icon(state.color)
        return {
            "Category": ("s", "ApplicationStatus"),
            "Id": ("s", "herdr-blocked-hud"),
            "Title": ("s", "herdr-blocked-hud"),
            "Status": ("s", "Active"),
            "WindowId": ("i", 0),
            "IconName": ("s", ""),
            "IconPixmap": ("a(iiay)", icon),
            "OverlayIconName": ("s", ""),
            "OverlayIconPixmap": ("a(iiay)", []),
            "AttentionIconName": ("s", ""),
            "AttentionIconPixmap": ("a(iiay)", []),
            "AttentionMovieName": ("s", ""),
            "ToolTip": ("(sa(iiay)ss)", ("", icon, "herdr-blocked-hud", state.tooltip)),
            # No Menu property: the panel then sends ContextMenu(x, y) and the
            # HUD shows its own Tk menu there.
            "ItemIsMenu": ("b", False),
        }

    def set_state(self, state: TrayState) -> None:
        """Tk thread: new counts or mute; tells the panel to re-read them."""
        with self.lock:
            if state == self.state:
                return
            old, self.state = self.state, state
        connection = self.connection
        if connection is None:
            return
        try:
            if old.color != state.color:
                connection.signal(ITEM_PATH, ITEM_INTERFACE, "NewIcon")
            connection.signal(ITEM_PATH, ITEM_INTERFACE, "NewToolTip")
        except OSError as err:
            print(f"herdr-blocked-hud: tray update failed: {err}", file=sys.stderr)

    def handle(self, connection: dbus.Connection, message: dbus.Message) -> None:
        if message.type == dbus.SIGNAL:
            # Only the bus itself can send as org.freedesktop.DBus.
            if (message.sender == dbus.BUS_NAME and message.member == "NameOwnerChanged"
                    and message.signature == "sss"
                    and message.body[0] == WATCHER and message.body[2]):
                self.register(connection)
            return
        if message.type != dbus.METHOD_CALL:
            return
        member, interface = message.member, message.interface
        if interface == PEER and member == "Ping":
            connection.reply(message)
        elif interface == INTROSPECTABLE and member == "Introspect":
            connection.reply(message, "s", (INTROSPECTION,))
        elif message.path != ITEM_PATH:
            connection.error(message, "org.freedesktop.DBus.Error.UnknownObject",
                             f"no object {message.path}")
        elif (interface, member) in METHOD_SIGNATURES and \
                message.signature != METHOD_SIGNATURES[interface, member]:
            connection.error(message, "org.freedesktop.DBus.Error.InvalidArgs",
                             f"{member} takes ({METHOD_SIGNATURES[interface, member]})")
        elif interface == PROPERTIES and member == "GetAll":
            connection.reply(message, "a{sv}", (self.properties(),))
        elif interface == PROPERTIES and member == "Get":
            name = message.body[1]
            properties = self.properties()
            if name in properties:
                connection.reply(message, "v", (properties[name],))
            else:
                connection.error(message, "org.freedesktop.DBus.Error.UnknownProperty",
                                 "no such property")
        elif interface == ITEM_INTERFACE and member in (
            "Activate", "SecondaryActivate", "ContextMenu", "Scroll"
        ):
            connection.reply(message)
            if member == "Activate":
                self.post(("activate",))
            elif member == "ContextMenu":
                self.post(("menu", *message.body))
        else:
            connection.error(message, "org.freedesktop.DBus.Error.UnknownMethod",
                             f"no method {interface}.{member}")

    def post(self, event: tuple) -> None:
        """Hand a click to the Tk thread; extra clicks are dropped while
        the bounded queue is full, so a flood cannot grow memory."""
        try:
            self.events.put_nowait(event)
        except queue.Full:
            pass

    def register(self, connection: dbus.Connection) -> None:
        # No reply needed: a missing watcher is reported by the caller, and a
        # later watcher announces itself with NameOwnerChanged.
        connection.call(WATCHER, WATCHER_PATH, WATCHER, "RegisterStatusNotifierItem",
                        "s", (self.service,), expect_reply=False)

    def serve(self, connection: dbus.Connection) -> None:
        """Worker thread: claim the name, register, answer until the bus ends."""
        connection.call_wait(dbus.BUS_NAME, dbus.BUS_PATH, dbus.BUS_NAME, "RequestName",
                             "su", (self.service, 4))
        connection.call_wait(
            dbus.BUS_NAME, dbus.BUS_PATH, dbus.BUS_NAME, "AddMatch", "s",
            (f"type='signal',sender='{dbus.BUS_NAME}',member='NameOwnerChanged',"
             f"arg0='{WATCHER}'",),
        )
        (has_watcher,) = connection.call_wait(
            dbus.BUS_NAME, dbus.BUS_PATH, dbus.BUS_NAME, "NameHasOwner", "s", (WATCHER,)
        ).body
        self.connection = connection
        if has_watcher:
            self.register(connection)
        else:
            print("herdr-blocked-hud: no status-bar tray yet (no StatusNotifierWatcher)",
                  file=sys.stderr)
        while True:
            message = connection.receive()
            try:
                self.handle(connection, message)
            except (dbus.DBusError, struct.error, ValueError, TypeError, IndexError):
                # A call the item cannot answer must not end the icon.
                continue


def start(address: str | None = None) -> TrayItem:
    """Connect and serve on a daemon thread, so Tk never waits on the bus.

    Clicks arrive in the item's bounded `events` queue. Without a session bus
    the thread reports it and ends; the HUD runs on without an icon.
    """
    item = TrayItem(queue.Queue(MAX_EVENTS), f"org.kde.StatusNotifierItem-{os.getpid()}-1")

    def run() -> None:
        try:
            connection = dbus.Connection.open(address)
        except (OSError, dbus.DBusError) as err:
            print(f"herdr-blocked-hud: no status-bar icon: {err}", file=sys.stderr)
            return
        try:
            item.serve(connection)
        except (OSError, dbus.DBusError) as err:
            print(f"herdr-blocked-hud: status-bar icon stopped: {err}", file=sys.stderr)
        item.connection = None
        connection.close()

    threading.Thread(target=run, name="tray", daemon=True).start()
    return item
