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
import traceback
from typing import Callable

from . import config as config_module
from . import sounds, x11
from . import state as state_module
from . import tray as tray_module
from .config import Config, ConfigError
from .focus import focus_agent
from .logic import DoneTracker, HudState, LongDone, Row, View
from .source import Agent, Model, Poller, Session, SessionState, read_agent_tail

DRAIN_MS = 100
# Pointer travel (pixels) after which a left-button press becomes a drag.
DRAG_THRESHOLD = 4

BG = "#1e1e2e"
ROW_BG = "#313244"
ROW_ACTIVE_BG = "#f38ba8"
FG = "#cdd6f4"
HEADER_FG = "#fab387"
ERROR_FG = "#9399b2"
# Has ↻ and ×; the default Tk fonts lack ↻ and show a box instead.
CONTROL_FONT = ("DejaVu Sans", 11)


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
    view: View, config: Config, builtin: Callable[[str], str] = sounds.builtin_path
) -> str | None:
    """One sound per poll; blocked wins. The done switch leaves blocked alone."""
    if view.beep_blocked:
        kind, setting = "blocked", config.blocked_sound
    elif view.beep_done and config.done.sound_enabled:
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
    monitor: tuple[int, int, int, int], config: Config, height: int
) -> tuple[int, int]:
    """Top-left corner of the HUD in the configured monitor corner."""
    x, y, width, monitor_height = monitor
    vertical, horizontal = config.corner.split("-")
    left = x + config.margin_x if horizontal == "left" else x + width - config.width - config.margin_x
    top = y + config.margin_y if vertical == "top" else y + monitor_height - height - config.margin_y
    return left, top


def clamp(
    monitor: tuple[int, int, int, int], left: int, top: int, width: int, height: int
) -> tuple[int, int]:
    """Move a window of `width` x `height` at (left, top) fully onto the monitor."""
    x, y, monitor_width, monitor_height = monitor
    left = max(x, min(left, x + monitor_width - width))
    top = max(y, min(top, y + monitor_height - height))
    return left, top


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
        self.mute_button: tk.Label | None = None
        self.on_click = on_click
        self.on_dismiss = on_dismiss
        self.config = config
        self.state = HudState()
        self.models: queue.Queue[tuple[Model, tuple[LongDone, ...]]] = queue.Queue()
        self.shown: View | None = None
        # "quit" or "restart" once a control button ended the main loop.
        self.exit_action: str | None = None
        self.state_file = state_file
        saved = (
            state_module.load(state_file, config.corner)
            if state_file
            else state_module.HudSettings(config.corner)
        )
        # The ♪ button silences every HUD sound.
        self.muted = saved.muted

        # Override-redirect: Openbox neither manages nor focuses the window,
        # it shows on every desktop, and `lift()` keeps it on top.
        root.overrideredirect(True)
        root.configure(bg=BG)
        root.withdraw()
        self.frame = tk.Frame(root, bg=BG, padx=6, pady=6)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.monitor = x11.primary_monitor() or (
            0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
        )
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
        self.menu_mute = tk.BooleanVar(root, value=self.muted)
        self.menu.add_checkbutton(label="Mute", variable=self.menu_mute,
                                  command=self.toggle_mute)
        self.menu.add_command(label="Restart", command=lambda: self.exit("restart"))
        self.menu.add_command(label="Quit", command=lambda: self.exit("quit"))

    def drag_start(self, event: tk.Event) -> None:
        self.drag = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())
        self.dragged = False

    def drag_move(self, event: tk.Event) -> None:
        if self.drag is None:
            return
        x0, y0, left0, top0 = self.drag
        dx, dy = event.x_root - x0, event.y_root - y0
        if not self.dragged and max(abs(dx), abs(dy)) < DRAG_THRESHOLD:
            return
        self.dragged = True
        left, top = left0 + dx, top0 + dy
        placed_left, placed_top = place(self.monitor, self.config, self.root.winfo_height())
        self.offset = (left - placed_left, top - placed_top)
        self.root.geometry(f"+{left}+{top}")

    def drag_end(self, _event: tk.Event) -> None:
        # Runs after the widget's release binding, which checks `dragged`.
        if self.dragged:
            self.save_state()
        self.drag = None
        self.dragged = False

    def save_state(self) -> None:
        if self.state_file:
            state_module.save(
                self.state_file,
                state_module.HudSettings(self.config.corner, self.offset, self.muted),
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
        sound = sound_for(view, self.config)
        if sound:
            self.play(sound)
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
        self.root.lift()

    def tray_event(self, event: tuple) -> None:
        if event[0] == "activate":
            # Hide a shown HUD, show a hidden one (also with nothing listed).
            self.forced = not self.mapped
            self.apply(self.shown or View())
        elif event[0] == "menu":
            self.menu_mute.set(self.muted)
            self.menu.tk_popup(event[1], event[2])

    def update_tray(self) -> None:
        if self.tray is None:
            return
        view = self.shown or View()
        self.tray.set_state(tray_module.TrayState(
            blocked=len(view.blocked),
            done=sum(len(section.rows) for section in view.done),
            muted=self.muted,
        ))

    def render(self, view: View) -> None:
        for child in self.frame.winfo_children():
            child.destroy()
        # The first header shares its line with the mute, restart and quit buttons.
        self.top = tk.Frame(self.frame, bg=BG)
        self.top.pack(fill=tk.X)
        self.top_free = True
        for text, action in (("×", "quit"), ("↻", "restart")):
            button = tk.Label(
                self.top, text=text, bg=BG, fg=HEADER_FG, font=CONTROL_FONT, padx=4,
                cursor="hand2",
            )
            button.pack(side=tk.RIGHT)
            self.on_release(button, 1, lambda action=action: self.exit(action))
        self.mute_button = tk.Label(self.top, bg=BG, padx=4, cursor="hand2")
        self.mute_button.pack(side=tk.RIGHT)
        self.on_release(self.mute_button, 1, self.toggle_mute)
        self.show_mute()
        self.rendered = view
        if not view.visible:
            self.header("Nothing waiting")
        if view.blocked:
            self.header("Blocked")
            for row in view.blocked:
                self.row(row)
        for section in view.done:
            self.header(section.title)
            for row in section.rows:
                self.row(row, dismissible=True)
        if view.error:
            tk.Label(
                self.frame,
                text=f"herdr unreachable: {view.error}",
                bg=BG,
                fg=ERROR_FG,
                wraplength=self.config.width - 20,
                justify=tk.LEFT,
                anchor="w",
            ).pack(fill=tk.X, pady=2)
        self.root.update_idletasks()
        height = self.frame.winfo_reqheight()
        left, top = place(self.monitor, self.config, height)
        left, top = clamp(
            self.monitor, left + self.offset[0], top + self.offset[1], self.config.width, height
        )
        self.root.geometry(f"{self.config.width}x{height}+{left}+{top}")

    def header(self, text: str) -> None:
        label = tk.Label(
            self.top if self.top_free else self.frame,
            text=text, bg=BG, fg=HEADER_FG, font=("Sans", 10, "bold"), anchor="w",
        )
        if self.top_free:
            label.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=(0, 2))
            self.top_free = False
        else:
            label.pack(fill=tk.X, pady=(0, 2))

    def play(self, sound: str) -> None:
        """Every HUD sound goes through here, so the mute button covers it."""
        if not self.muted:
            play(sound)

    def toggle_mute(self) -> None:
        self.muted = not self.muted
        self.show_mute()
        self.save_state()
        self.update_tray()

    def show_mute(self) -> None:
        """Struck-through grey note while muted, plain note while sound plays."""
        if self.mute_button is None:
            return
        if self.muted:
            self.mute_button.configure(text="♪", fg=ERROR_FG, font=(*CONTROL_FONT, "overstrike"))
        else:
            self.mute_button.configure(text="♪", fg=HEADER_FG, font=CONTROL_FONT)

    def exit(self, action: str) -> None:
        """End the main loop; main() then quits or restarts."""
        self.exit_action = action
        self.root.quit()

    def row(self, row: Row, dismissible: bool = False) -> None:
        line = tk.Frame(self.frame, bg=ROW_BG)
        line.pack(fill=tk.X, pady=2)
        label = tk.Label(
            line,
            text=f"▶ {row.text}",
            bg=ROW_BG,
            fg=FG,
            padx=8,
            pady=4,
            anchor="w",
            cursor="hand2",
        )
        label.bind("<Enter>", lambda _e: label.configure(bg=ROW_ACTIVE_BG, fg=BG))
        label.bind("<Leave>", lambda _e: label.configure(bg=ROW_BG, fg=FG))
        self.on_release(label, 1, lambda agent=row.agent: self.on_click(agent))
        if dismissible:
            # Packed before the label so a long label cannot push it out.
            close = tk.Label(line, text="×", bg=ROW_BG, fg=FG, padx=6, pady=4, cursor="hand2")
            close.pack(side=tk.RIGHT)
            close.bind("<Enter>", lambda _e: close.configure(bg=ROW_ACTIVE_BG, fg=BG))
            close.bind("<Leave>", lambda _e: close.configure(bg=ROW_BG, fg=FG))
            self.on_release(close, 1, lambda agent=row.agent: self.on_dismiss(agent))
            on_release(label, 3, lambda agent=row.agent: self.on_dismiss(agent))
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)


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
        sound = sound_for(view, config)
        if sound:
            root.after(delay, hud.play, sound)
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
