"""Tk window: always on top, no focus stealing, hidden when nothing is listed."""

from __future__ import annotations

import fcntl
import os
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
from .config import Config, ConfigError
from .focus import focus_agent
from .logic import DoneTracker, HudState, LongDone, Row, View
from .source import Agent, Model, Poller, Session, SessionState, read_agent_tail

DRAIN_MS = 100

BG = "#1e1e2e"
ROW_BG = "#313244"
ROW_ACTIVE_BG = "#f38ba8"
FG = "#cdd6f4"
HEADER_FG = "#fab387"
ERROR_FG = "#9399b2"


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


class Hud:
    def __init__(self, root: tk.Tk, on_click: Callable[[Agent], None], config: Config):
        self.root = root
        self.on_click = on_click
        self.config = config
        self.state = HudState()
        self.models: queue.Queue[tuple[Model, tuple[LongDone, ...]]] = queue.Queue()
        self.shown: View | None = None

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
        self.root.after(DRAIN_MS, self.start_draining)

    def show(self, view: View) -> None:
        sound = sound_for(view, self.config)
        if sound:
            play(sound)
        if not view.visible:
            if self.shown is None or self.shown.visible:
                self.root.withdraw()
            self.shown = view
            return
        if view != self.shown:
            self.render(view)
        if self.shown is None or not self.shown.visible:
            self.root.deiconify()
        self.root.lift()
        self.shown = view

    def render(self, view: View) -> None:
        for child in self.frame.winfo_children():
            child.destroy()
        if view.blocked:
            self.header("Blocked")
            for row in view.blocked:
                self.row(row)
        if view.done:
            self.header("Done")
            for row in view.done:
                self.row(row)
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
        self.root.geometry(f"{self.config.width}x{height}+{left}+{top}")

    def header(self, text: str) -> None:
        tk.Label(
            self.frame, text=text, bg=BG, fg=HEADER_FG, font=("Sans", 10, "bold"), anchor="w"
        ).pack(fill=tk.X, pady=(0, 2))

    def row(self, row: Row) -> None:
        label = tk.Label(
            self.frame,
            text=f"▶ {row.text}",
            bg=ROW_BG,
            fg=FG,
            padx=8,
            pady=4,
            anchor="w",
            cursor="hand2",
        )
        label.pack(fill=tk.X, pady=2)
        label.bind("<Enter>", lambda _e: label.configure(bg=ROW_ACTIVE_BG, fg=BG))
        label.bind("<Leave>", lambda _e: label.configure(bg=ROW_BG, fg=FG))
        label.bind("<Button-1>", lambda _e, agent=row.agent: self.on_click(agent))


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
    return Model(sessions=(SessionState(session, agents=agents),)), (LongDone(agents[2], 185),)


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
        hud = Hud(root, on_click=lambda agent: None, config=config)
        model, long_done = demo_model()
        hud.submit(model, long_done)
        hud.start_draining()
        # The first reading never beeps, so let the user hear both sounds here.
        for delay, view in ((300, View(beep_blocked=True)), (2500, View(beep_done=True))):
            sound = sound_for(view, config)
            if sound:
                root.after(delay, play, sound)
        root.after(8000, root.destroy)
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
                # Refresh at once: the row goes away, or the gone agent drops out.
                poller.poll_now()

            threading.Thread(target=work, name="herdr-focus", daemon=True).start()

        hud = Hud(root, on_click=on_click, config=config)
        poller.start()
        hud.start_draining()
    root.mainloop()
    return 130 if interrupted.is_set() else 0
