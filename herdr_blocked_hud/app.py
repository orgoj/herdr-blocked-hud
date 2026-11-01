"""Tk window: always on top, no focus stealing, hidden when nothing is listed."""

from __future__ import annotations

import fcntl
import os
import pathlib
import queue
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
from typing import Callable

from . import config as config_module
from . import sounds, x11
from . import state as state_module
from . import tray as tray_module
from .config import Config, ConfigError
from .focus import focus_agent
from .logic import DoneTracker, HudState, Item, LongDone, SoundReminder, View, layout
from .source import Agent, Model, Poller, Session, SessionState, read_agent_tail

DRAIN_MS = 100
# Pointer travel (pixels) after which a left-button press becomes a drag.
DRAG_THRESHOLD = 4
# Width of the grab zones on the left and right edge (the frame's padding)
# and the narrowest HUD an edge drag makes.
EDGE = 6
MIN_WIDTH = 200

BG = "#1e1e2e"
ROW_BG = "#313244"
ROW_ACTIVE_BG = "#f38ba8"
FG = "#cdd6f4"
HEADER_FG = "#fab387"
ERROR_FG = "#9399b2"
# Has ↻ and ×; the default Tk fonts lack ↻ and show a box instead.
CONTROL_FONT = ("DejaVu Sans", 11)
HEADER_FONT = ("Sans", 10, "bold")
# One mute button per sound, in the tray icon's colours (red, orange).
SOUND_KINDS = ("blocked", "done")
SOUND_FG = {"blocked": ROW_ACTIVE_BG, "done": HEADER_FG}


def mute_button(parent: tk.Widget) -> tk.Canvas:
    """A ♪ of CONTROL_FONT with a hidden diagonal strike, fixed size."""
    font = tkfont.Font(root=parent, font=CONTROL_FONT)
    width, height = font.measure("♪") + 8, font.metrics("linespace")
    canvas = tk.Canvas(
        parent, width=width, height=height, bg=BG, highlightthickness=0, bd=0,
        cursor="hand2",
    )
    canvas.create_text(width // 2, height // 2, text="♪", font=CONTROL_FONT, tags="note")
    canvas.create_line(3, height - 3, width - 3, 3, width=2, fill=ERROR_FG,
                       state=tk.HIDDEN, tags="strike")
    return canvas


def play(path: str) -> None:
    try:
        subprocess.Popen(
            ["paplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as err:
        print(f"herdr-blocked-hud: paplay failed: {err}", file=sys.stderr)


def sound_for(
    view: View,
    config: Config,
    builtin: Callable[[str], str] = sounds.builtin_path,
    *,
    muted: frozenset[str] = frozenset(),
) -> str | None:
    """One sound per poll; blocked wins unless muted. The done switches
    (`done.sound_enabled`, the done mute) leave blocked alone."""
    if view.beep_blocked and "blocked" not in muted:
        kind, setting = "blocked", config.blocked_sound
    elif view.beep_done and config.done.sound_enabled and "done" not in muted:
        kind, setting = "done", config.done_sound
    else:
        return None
    if setting == sounds.BUILTIN:
        try:
            return builtin(kind)
        except OSError as err:
            print(f"herdr-blocked-hud: cannot write {kind} sound: {err}", file=sys.stderr)
            return None
    return setting or None


def place(
    monitor: tuple[int, int, int, int], config: Config, height: int, width: int | None = None
) -> tuple[int, int]:
    """Top-left corner of the HUD in the configured monitor corner; `width`
    defaults to config width."""
    x, y, monitor_width, monitor_height = monitor
    width = config.width if width is None else width
    vertical, horizontal = config.corner.split("-")
    left = x + config.margin_x if horizontal == "left" else x + monitor_width - width - config.margin_x
    top = y + config.margin_y if vertical == "top" else y + monitor_height - height - config.margin_y
    return left, top


def monitor_at(
    monitors: list[tuple[int, int, int, int]], cx: int, cy: int
) -> tuple[int, int, int, int]:
    """The monitor holding (cx, cy), else the one nearest to it."""

    def distance(monitor: tuple[int, int, int, int]) -> int:
        x, y, w, h = monitor
        dx = max(x - cx, 0, cx - (x + w - 1))
        dy = max(y - cy, 0, cy - (y + h - 1))
        return dx * dx + dy * dy

    # min() keeps the first of equals, so the primary wins ties.
    return min(monitors, key=distance)


def clamp(
    monitors: list[tuple[int, int, int, int]], left: int, top: int, width: int, height: int
) -> tuple[int, int]:
    """Move a window of `width` x `height` at (left, top) fully onto one monitor:
    the one holding the window's centre, else the one nearest to it (a saved
    position on a monitor that is gone lands on an existing one)."""
    x, y, monitor_width, monitor_height = monitor_at(
        monitors, left + width // 2, top + height // 2
    )
    left = max(x, min(left, x + monitor_width - width))
    top = max(y, min(top, y + monitor_height - height))
    return left, top


def resize(
    edge: str, left0: int, width0: int, dx: int, monitor: tuple[int, int, int, int]
) -> tuple[int, int]:
    """(left, width) after dragging the `edge` ("left" or "right") of a window
    at `left0`, `width0` by `dx` on `monitor`; the opposite edge stays in
    place, the moved one stops at the monitor's side, and the width is at
    least MIN_WIDTH."""
    x, _, monitor_width, _ = monitor
    if edge == "right":
        room = x + monitor_width - left0
        width = width0 + dx
    else:
        room = left0 + width0 - x
        width = width0 - dx
    width = max(MIN_WIDTH, min(width, room))
    return (left0 if edge == "right" else left0 + width0 - width), width


def bounded_width(width: int, monitor_width: int) -> int:
    """`width` within MIN_WIDTH..monitor_width (config or saved width alike)."""
    return min(max(width, MIN_WIDTH), monitor_width)


class Hud:
    def __init__(
        self,
        root: tk.Tk,
        on_click: Callable[[Agent], None],
        config: Config,
        on_dismiss: Callable[[Agent], None] = lambda agent: None,
        state_file: pathlib.Path | None = None,
        tray: tray_module.TrayItem | None = None,
    ):
        """`state_file` remembers position and mute across runs; None: no file.

        `tray` is the status-bar icon; its clicks arrive in `tray_events`.
        """
        self.root = root
        self.tray = tray
        self.tray_events: queue.Queue[tuple] = tray.events if tray else queue.Queue()
        # The window is mapped; `forced` overrides "shown when something is
        # listed" after a tray click, until the next sound event.
        self.mapped = False
        self.forced: bool | None = None
        self.rendered: View | None = None
        self.mute_buttons: dict[str, tk.Canvas] = {}
        self.on_click = on_click
        self.on_dismiss = on_dismiss
        self.config = config
        self.state = HudState(section_order=tuple(config.done.modes))
        self.reminder = SoundReminder(config.sound_delay, config.sound_repeat)
        self.clock: Callable[[], float] = time.monotonic
        self.models: queue.Queue[tuple[Model, tuple[LongDone, ...]]] = queue.Queue()
        self.shown: View | None = None
        # "quit" or "restart" once a control button ended the main loop.
        self.exit_action: str | None = None
        self.state_file = state_file
        saved = (
            state_module.load(state_file, config.corner, config.width)
            if state_file
            else state_module.HudSettings(config.corner)
        )
        # Muted sound kinds ("blocked", "done"), one ♪ button each.
        self.muted: set[str] = set(saved.muted)

        # Override-redirect: Openbox neither manages nor focuses the window,
        # it shows on every desktop, and `lift()` keeps it on top.
        root.overrideredirect(True)
        root.configure(bg=BG)
        root.withdraw()
        self.frame = tk.Frame(root, bg=BG, padx=EDGE, pady=6)
        self.frame.pack(fill=tk.BOTH, expand=True)
        # The corner position is on the primary monitor (listed first); a
        # dragged HUD may sit on any of them.
        self.monitors = x11.monitors() or [
            (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
        ]
        # Width: config width unless an edge drag set another one. The WM
        # cannot resize an override-redirect window, so the left and right
        # padding are grab zones over the frame; a drag there resizes.
        self.width = config.width if saved.width is None else saved.width
        self.edges = {}
        for edge in ("left", "right"):
            zone = tk.Frame(root, bg=BG, width=EDGE, cursor="sb_h_double_arrow")
            zone.place(relx=0 if edge == "left" else 1, x=0 if edge == "left" else -EDGE,
                       y=0, width=EDGE, relheight=1)
            self.edges[zone] = edge
        self.resizing: tuple[str, int, int, int] | None = None
        # The WM cannot move an override-redirect window, so a left-button
        # drag anywhere in the HUD moves it. `offset` is the dragged distance
        # from the configured corner position; it keeps that corner's edges
        # in place when the height changes.
        self.offset = saved.offset
        self.drag: tuple[int, int, int, int] | None = None
        self.dragged = False
        # Every widget carries its toplevel's binding tag, so these see
        # events on all children, after the widgets' own bindings.
        root.bind("<ButtonPress-1>", self.drag_start)
        root.bind("<B1-Motion>", self.drag_move)
        root.bind("<ButtonRelease-1>", self.drag_end)
        # Tray right-click menu: the same actions as the top-line buttons.
        self.menu = tk.Menu(root, tearoff=False)
        self.menu_mute = {
            kind: tk.BooleanVar(root, value=kind in self.muted) for kind in SOUND_KINDS
        }
        for kind in SOUND_KINDS:
            self.menu.add_checkbutton(
                label=f"Mute {kind} sound", variable=self.menu_mute[kind],
                command=lambda kind=kind: self.toggle_mute(kind),
            )
        self.menu.add_command(label="Restart", command=lambda: self.exit("restart"))
        self.menu.add_command(label="Quit", command=lambda: self.exit("quit"))
        self.menu_open = False
        self.menu.bind("<Map>", lambda _e: setattr(self, "menu_open", True))
        self.menu.bind("<Unmap>", lambda _e: setattr(self, "menu_open", False))
        # The top line is built once: the first header (`title`) shares it
        # with the mute, restart and quit buttons.
        self.top = tk.Frame(self.frame, bg=BG)
        self.top.pack(fill=tk.X)
        for text, action in (("×", "quit"), ("↻", "restart")):
            button = tk.Label(
                self.top, text=text, bg=BG, fg=HEADER_FG, font=CONTROL_FONT, padx=4,
                cursor="hand2",
            )
            button.pack(side=tk.RIGHT)
            self.on_release(button, 1, lambda action=action: self.exit(action))
        # Packed from the right: blocked ♪, done ♪, ↻, ×.
        for kind in reversed(SOUND_KINDS):
            button = mute_button(self.top)
            button.pack(side=tk.RIGHT)
            self.on_release(button, 1, lambda kind=kind: self.toggle_mute(kind))
            self.mute_buttons[kind] = button
        self.show_mute()
        self.title = tk.Label(
            self.top, text="", bg=BG, fg=HEADER_FG, font=HEADER_FONT, anchor="w",
        )
        self.title.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=(0, 2))
        # The lines below the top line by Item key, packed top to bottom
        # in `order`; the agent each row acts on.
        self.lines: dict[tuple, tuple[tk.Widget, tk.Label]] = {}
        self.order: list[tuple] = []
        self.agents: dict[tuple, Agent] = {}
        self.geometry: str | None = None

    def drag_start(self, event: tk.Event) -> None:
        self.drag = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())
        self.dragged = False
        edge = self.edges.get(event.widget)
        self.resizing = (edge, event.x_root, self.root.winfo_x(), self.width) if edge else None

    def drag_move(self, event: tk.Event) -> None:
        if self.resizing is not None:
            self.resize_move(event)
            return
        if self.drag is None:
            return
        x0, y0, left0, top0 = self.drag
        dx, dy = event.x_root - x0, event.y_root - y0
        if not self.dragged and max(abs(dx), abs(dy)) < DRAG_THRESHOLD:
            return
        self.dragged = True
        left, top = left0 + dx, top0 + dy
        placed_left, placed_top = place(
            self.monitors[0], self.config, self.root.winfo_height(), self.width
        )
        self.offset = (left - placed_left, top - placed_top)
        self.root.geometry(f"+{left}+{top}")
        self.geometry = None

    def resize_move(self, event: tk.Event) -> None:
        edge, x0, left0, width0 = self.resizing
        dx = event.x_root - x0
        if not self.dragged and abs(dx) < DRAG_THRESHOLD:
            return
        self.dragged = True
        height = self.root.winfo_height()
        monitor = monitor_at(self.monitors, left0 + width0 // 2, self.root.winfo_y() + height // 2)
        left, self.width = resize(edge, left0, width0, dx, monitor)
        placed_left, _ = place(self.monitors[0], self.config, height, self.width)
        self.offset = (left - placed_left, self.offset[1])
        # Re-render: the error text wraps to the new width.
        self.render(self.rendered or View())

    def drag_end(self, _event: tk.Event) -> None:
        # Runs after the widget's release binding, which checks `dragged`.
        if self.dragged:
            self.save_state()
        self.drag = None
        self.resizing = None
        self.dragged = False

    def save_state(self) -> None:
        if self.state_file:
            sized = self.width != self.config.width
            state_module.save(
                self.state_file,
                state_module.HudSettings(
                    self.config.corner, self.offset, frozenset(self.muted),
                    width=self.width if sized else None,
                    config_width=self.config.width if sized else None,
                ),
            )

    def on_release(self, widget: tk.Widget, button: int, action: Callable[[], None]) -> None:
        """`on_release`, except that a drag ending on `widget` is no click."""
        on_release(widget, button, lambda: None if self.dragged else action())

    def submit(self, model: Model, long_done: tuple[LongDone, ...] = ()) -> None:
        """Thread-safe: queue a model for the Tk main loop."""
        self.models.put((model, long_done))

    def start_draining(self) -> None:
        latest = None
        while True:
            try:
                latest = self.models.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            self.show(self.state.update(*latest))
        # A bounded number per tick, so a click flood cannot starve Tk.
        for _ in range(tray_module.MAX_EVENTS):
            try:
                event = self.tray_events.get_nowait()
            except queue.Empty:
                break
            self.tray_event(event)
        self.root.after(DRAIN_MS, self.start_draining)

    def show(self, view: View) -> None:
        if self.config.sound_mode == "immediate":
            self.beep(view)
        else:
            self.remind(view)
        if view.beep_blocked or view.beep_done:
            self.forced = None
        self.apply(view)

    def apply(self, view: View) -> None:
        """Map, render or hide for `view`; plays nothing."""
        self.shown = view
        self.update_tray()
        visible = view.visible if self.forced is None else self.forced
        if not visible:
            if self.mapped:
                self.root.withdraw()
                self.mapped = False
            return
        if view != self.rendered:
            self.render(view)
        if not self.mapped:
            self.root.deiconify()
            self.mapped = True
        # Raising the HUD while the tray menu is open would cover the menu.
        if not self.menu_open:
            self.root.lift()

    def tray_event(self, event: tuple) -> None:
        if event[0] == "activate":
            # Hide a shown HUD, show a hidden one (also with nothing listed).
            self.forced = not self.mapped
            self.apply(self.shown or View())
        elif event[0] == "menu":
            for kind, variable in self.menu_mute.items():
                variable.set(kind in self.muted)
            self.menu.tk_popup(event[1], event[2])

    def update_tray(self) -> None:
        if self.tray is None:
            return
        view = self.shown or View()
        self.tray.set_state(tray_module.TrayState(
            blocked=len(view.blocked),
            done=sum(len(section.rows) for section in view.done),
            muted=frozenset(self.muted),
        ))

    def render(self, view: View) -> None:
        """Show `view`, changing only what differs from the shown lines.

        Destroying and re-creating every widget on each change made the HUD
        flicker and lost a click whose press reached a widget that was gone
        by the release, so a line keeps its widget while its Item key stays.
        """
        # Config or saved width alike: at least MIN_WIDTH, at most the width
        # of the monitor the HUD lands on (picked with the last height).
        height = self.root.winfo_height()
        left, top = place(self.monitors[0], self.config, height, self.width)
        monitor = monitor_at(
            self.monitors, left + self.offset[0] + self.width // 2,
            top + self.offset[1] + height // 2,
        )
        self.width = bounded_width(self.width, monitor[2])
        items = layout(view)
        title = ""
        if items and items[0].key[0] == "header":
            title, items = items[0].text, items[1:]
        if self.title.cget("text") != title:
            self.title.configure(text=title)
        keys = [item.key for item in items]
        for key in set(self.lines) - set(keys):
            self.lines.pop(key)[0].destroy()
            self.agents.pop(key, None)
        for item in items:
            if item.key not in self.lines:
                self.lines[item.key] = self.line(item)
            label = self.lines[item.key][1]
            if label.cget("text") != item.text:
                label.configure(text=item.text)
            if item.agent is not None:
                self.agents[item.key] = item.agent
            if item.key[0] == "error":
                label.configure(wraplength=self.width - 20)
        if keys != self.order:
            for key in self.order:
                if key in self.lines:
                    self.lines[key][0].pack_forget()
            for key in keys:
                widget = self.lines[key][0]
                widget.pack(fill=tk.X, pady=(0, 2) if key[0] == "header" else 2)
            self.order = keys
        self.rendered = view
        self.root.update_idletasks()
        height = self.frame.winfo_reqheight()
        left, top = place(self.monitors[0], self.config, height, self.width)
        left, top = clamp(
            self.monitors, left + self.offset[0], top + self.offset[1], self.width, height
        )
        geometry = f"{self.width}x{height}+{left}+{top}"
        if geometry != self.geometry:
            self.root.geometry(geometry)
            self.geometry = geometry

    def line(self, item: Item) -> tuple[tk.Widget, tk.Label]:
        """New widgets for `item`: (the packed widget, the label with its text)."""
        kind = item.key[0]
        if kind == "header":
            label = tk.Label(self.frame, bg=BG, fg=HEADER_FG, font=HEADER_FONT, anchor="w")
            return label, label
        if kind == "error":
            label = tk.Label(self.frame, bg=BG, fg=ERROR_FG, justify=tk.LEFT, anchor="w")
            return label, label
        key, dismissible = item.key, item.key[2]
        line = tk.Frame(self.frame, bg=ROW_BG)
        label = tk.Label(
            line, bg=ROW_BG, fg=FG, padx=8, pady=4, anchor="w", cursor="hand2",
        )
        label.bind("<Enter>", lambda _e: label.configure(bg=ROW_ACTIVE_BG, fg=BG))
        label.bind("<Leave>", lambda _e: label.configure(bg=ROW_BG, fg=FG))
        # The agent of the latest poll: the row outlives the Agent it was made for.
        self.on_release(label, 1, lambda: self.on_click(self.agents[key]))
        if dismissible:
            # Packed before the label so a long label cannot push it out.
            close = tk.Label(line, text="×", bg=ROW_BG, fg=FG, padx=6, pady=4, cursor="hand2")
            close.pack(side=tk.RIGHT)
            close.bind("<Enter>", lambda _e: close.configure(bg=ROW_ACTIVE_BG, fg=BG))
            close.bind("<Leave>", lambda _e: close.configure(bg=ROW_BG, fg=FG))
            self.on_release(close, 1, lambda: self.on_dismiss(self.agents[key]))
            on_release(label, 3, lambda: self.on_dismiss(self.agents[key]))
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return line, label

    def beep(self, view: View) -> None:
        """Every HUD sound goes through here, so the mute buttons cover it."""
        sound = sound_for(view, self.config, muted=frozenset(self.muted))
        if sound:
            play(sound)

    def remind(self, view: View) -> None:
        """Delayed mode: a sound only when the reminder comes due. Kinds that
        would play nothing (muted, switched off) do not keep it running."""
        silent = set(self.muted)
        if not self.config.done.sound_enabled or not self.config.done_sound:
            silent.add("done")
        if not self.config.blocked_sound:
            silent.add("blocked")
        due = self.reminder.tick(view.pending - silent, self.clock())
        if due:
            self.beep(View(beep_blocked="blocked" in due, beep_done="done" in due))

    def toggle_mute(self, kind: str) -> None:
        self.muted ^= {kind}
        self.show_mute()
        self.save_state()
        self.update_tray()

    def show_mute(self) -> None:
        """Grey struck-through note while muted, coloured note while sound plays.

        The strike is a canvas line, not an overstrike font, so both states
        have the same size."""
        for kind, button in self.mute_buttons.items():
            muted = kind in self.muted
            button.itemconfigure("note", fill=ERROR_FG if muted else SOUND_FG[kind])
            button.itemconfigure("strike", state=tk.NORMAL if muted else tk.HIDDEN)

    def exit(self, action: str) -> None:
        """End the main loop; main() then quits or restarts."""
        self.exit_action = action
        self.root.quit()


def on_release(widget: tk.Widget, button: int, action: Callable[[], None]) -> None:
    """Run `action` on button release over `widget`, never on press.

    An action may hide the HUD. Acting on press would unmap the window before
    the release; X then ends the implicit pointer grab and delivers the
    release to the window below, which most applications treat as a click.
    """

    def released(event: tk.Event) -> None:
        if 0 <= event.x < widget.winfo_width() and 0 <= event.y < widget.winfo_height():
            action()

    widget.bind(f"<ButtonRelease-{button}>", released)


def start_demo(root: tk.Tk, config: Config) -> Hud:
    """Show the demo rows, play both sounds, end after 8 s."""
    hud = Hud(root, on_click=lambda agent: None, config=config)
    model, long_done = demo_model()
    hud.submit(model, long_done)
    hud.start_draining()
    # The first reading never beeps, so let the user hear both sounds here.
    for delay, view in ((300, View(beep_blocked=True)), (2500, View(beep_done=True))):
        root.after(delay, hud.beep, view)
    root.after(8000, root.destroy)
    return hud


def acquire_single_instance() -> object | None:
    """Hold an exclusive lock for the process lifetime; None if already held."""
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/herdr-blocked-hud-{os.getuid()}"
    os.makedirs(runtime, mode=0o700, exist_ok=True)
    handle = open(os.path.join(runtime, "herdr-blocked-hud.lock"), "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def quit_on_sigint(root: tk.Misc) -> threading.Event:
    """Ctrl+C leaves the main loop instead of raising KeyboardInterrupt in Tk.

    The handler runs between Python bytecodes, so it only asks Tk to stop. It
    schedules the quit as an idle callback: entering mainloop() resets Tk's
    quit flag, so a direct quit() during startup would be lost. The returned
    event tells main() it happened.
    """
    interrupted = threading.Event()

    def handler(_signum: int, _frame: object) -> None:
        interrupted.set()
        root.after_idle(root.quit)

    signal.signal(signal.SIGINT, handler)
    return interrupted


def demo_model() -> tuple[Model, tuple[LongDone, ...]]:
    session = Session("default", "", True)
    agents = tuple(
        Agent("default", f"w1:p{i}", f"term_{i}", "w1", "w1:t1", "demo", "main", name,
              status, False, i)
        for i, (name, status) in enumerate(
            [("claude", "blocked"), ("codex", "blocked"), ("pi", "done")], start=1
        )
    )
    return Model(sessions=(SessionState(session, agents=agents),)), (
        LongDone(agents[2], 185, "NEEDS_USER"),
    )


USAGE = "usage: herdr-blocked-hud [--demo] [--check-config]"


def main(argv: list[str] | None = None) -> int:
    """Entry point; the console script calls it without arguments."""
    if argv is None:
        argv = sys.argv[1:]
    if any(arg not in ("--demo", "--check-config") for arg in argv):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        config = config_module.load()
    except ConfigError as err:
        print(f"herdr-blocked-hud: config error: {err}", file=sys.stderr)
        return 2
    if "--check-config" in argv:
        print(f"herdr-blocked-hud: config ok ({config_module.config_path()})")
        return 0
    lock = acquire_single_instance()
    if lock is None:
        print("herdr-blocked-hud: already running", file=sys.stderr)
        return 1
    root = tk.Tk(className="herdr-blocked-hud")
    interrupted = quit_on_sigint(root)
    if "--demo" in argv:
        hud = start_demo(root, config)
    else:
        sessions: list[Session] = []
        tracker = DoneTracker(config.done, read_agent_tail, time.monotonic)

        def on_model(model: Model) -> None:
            sessions[:] = [state.session for state in model.sessions]
            # The done section fails soft: the blocked rows must still reach the window.
            try:
                long_done = tracker.update(model)
            except Exception:
                traceback.print_exc()
                long_done = ()
            hud.submit(model, long_done)

        poller = Poller(on_model, interval=config.poll_interval)

        def on_click(agent: Agent) -> None:
            def work() -> None:
                focus_agent(agent, list(sessions), config.wm_class or None)
                # Refresh at once: the row goes away (unless sticky), or the
                # gone agent drops out.
                poller.poll_now()

            threading.Thread(target=work, name="herdr-focus", daemon=True).start()

        def on_dismiss(agent: Agent) -> None:
            tracker.dismiss(agent)
            poller.poll_now()

        hud = Hud(
            root, on_click=on_click, config=config, on_dismiss=on_dismiss,
            state_file=state_module.state_path(), tray=tray_module.start(),
        )
        poller.start()
        hud.start_draining()
    root.mainloop()
    if hud.exit_action == "restart" and not interrupted.is_set():
        root.destroy()
        try:
            restart()
        except OSError as err:
            print(f"herdr-blocked-hud: restart failed: {err}", file=sys.stderr)
            return 1
    return 130 if interrupted.is_set() else 0


def restart_command() -> list[str]:
    """This process's command line: the console script (or `-m`) runs again,
    from whatever version is installed now."""
    return [sys.executable, *sys.orig_argv[1:]]


def restart() -> None:
    """Replace this process with a fresh HUD.

    Python opens the lock file non-inheritable, so the exec closes it and the
    new process can take the single-instance lock.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    command = restart_command()
    os.execv(command[0], command)
