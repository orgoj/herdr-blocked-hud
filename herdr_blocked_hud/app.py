"""Tk window: always on top, no focus stealing, hidden when nothing is listed."""

from __future__ import annotations

import fcntl
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Callable

from . import x11
from .focus import focus_agent
from .logic import DoneConfig, DoneTracker, HudState, LongDone, Row, View
from .source import Agent, Model, Poller, Session, SessionState, read_agent_tail

BLOCKED_SOUND = "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga"
DONE_SOUND = "/usr/share/sounds/freedesktop/stereo/complete.oga"
DRAIN_MS = 100
WIDTH = 320
MARGIN = 24

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


def sound_for(view: View, done_sound_enabled: bool) -> str | None:
    """One sound per poll; blocked wins. The done switch leaves blocked alone."""
    if view.beep_blocked:
        return BLOCKED_SOUND
    if view.beep_done and done_sound_enabled:
        return DONE_SOUND
    return None


def viewed_for(model: Model) -> set[str]:
    """Sessions the user is looking at; X11 is queried only when it matters."""
    if not any(a.focused for a in model.agents_with_status("blocked")):
        return set()
    sessions = [state.session for state in model.sessions]
    return x11.viewed_sessions(x11.active_window_pid(), x11.ui_clients(sessions))


class Hud:
    def __init__(
        self, root: tk.Tk, on_click: Callable[[Agent], None], done_sound_enabled: bool = True
    ):
        self.root = root
        self.on_click = on_click
        self.done_sound_enabled = done_sound_enabled
        self.state = HudState()
        self.models: queue.Queue[tuple[Model, set[str], tuple[LongDone, ...]]] = queue.Queue()
        self.shown: View | None = None

        # Override-redirect: Openbox neither manages nor focuses the window,
        # it shows on every desktop, and `lift()` keeps it on top.
        root.overrideredirect(True)
        root.configure(bg=BG)
        root.withdraw()
        self.frame = tk.Frame(root, bg=BG, padx=6, pady=6)
        self.frame.pack(fill=tk.BOTH, expand=True)
        monitor = x11.primary_monitor() or (0, 0, root.winfo_screenwidth(), 0)
        self.origin = (monitor[0] + monitor[2] - WIDTH - MARGIN, monitor[1] + MARGIN + 12)

    def submit(
        self, model: Model, viewed: set[str], long_done: tuple[LongDone, ...] = ()
    ) -> None:
        """Thread-safe: queue a model for the Tk main loop."""
        self.models.put((model, viewed, long_done))

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
        sound = sound_for(view, self.done_sound_enabled)
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
                wraplength=WIDTH - 20,
                justify=tk.LEFT,
                anchor="w",
            ).pack(fill=tk.X, pady=2)
        self.root.update_idletasks()
        height = self.frame.winfo_reqheight()
        self.root.geometry(f"{WIDTH}x{height}+{self.origin[0]}+{self.origin[1]}")

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


def main(argv: list[str]) -> int:
    demo = "--demo" in argv
    lock = acquire_single_instance()
    if lock is None:
        print("herdr-blocked-hud: already running", file=sys.stderr)
        return 1
    done_config = DoneConfig()
    root = tk.Tk(className="herdr-blocked-hud")
    if demo:
        hud = Hud(root, on_click=lambda agent: None)
        model, long_done = demo_model()
        hud.submit(model, set(), long_done)
        hud.start_draining()
        root.after(8000, root.destroy)
    else:
        sessions: list[Session] = []
        tracker = DoneTracker(done_config, read_agent_tail, time.monotonic)

        def on_model(model: Model) -> None:
            sessions[:] = [state.session for state in model.sessions]
            hud.submit(model, viewed_for(model), tracker.update(model))

        poller = Poller(on_model)

        def on_click(agent: Agent) -> None:
            def work() -> None:
                focus_agent(agent, list(sessions))
                # Refresh at once: the row goes away, or the gone agent drops out.
                poller.poll_now()

            threading.Thread(target=work, name="herdr-focus", daemon=True).start()

        hud = Hud(root, on_click=on_click, done_sound_enabled=done_config.sound_enabled)
        poller.start()
        hud.start_draining()
    root.mainloop()
    return 0
