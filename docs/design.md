# herdr-blocked-hud — implementation design (brainstorm)

Status: design only, no code. Verified against Herdr 0.9.5 (installed) and the
Herdr source at `master` (741ccce1), on this machine (Lubuntu, LXQt + Openbox,
X11, Herdr client running in `wezterm-gui --class herdr`).

## 1. The real Herdr interface

### State source

- `herdr pane list` prints JSON by default. There is **no `--json` flag**:
  `herdr pane list --json` exits 2 with `unknown option: --json`.
- Shape: `{"id":…, "result": {"type": "pane_list", "panes": [PaneInfo…]}}`.
- `PaneInfo` fields relevant here: `pane_id` (e.g. `w20:p3`), `terminal_id`,
  `workspace_id`, `tab_id`, `focused`, `agent`, `display_agent`, `label`,
  `title` (only when metadata set it), `terminal_title_stripped`,
  `agent_status`, `state_labels`. Optional fields are omitted when empty.
- `agent_status` values: `idle`, `working`, `blocked`, `done`, `unknown`.
  Only `blocked` means "Herdr recognized an approval or question UI".
- Human labels are not on the pane: workspace `label` comes from
  `herdr workspace list`, tab label from `herdr tab list`. One call returns
  everything: `herdr api snapshot` (socket `session.snapshot`: workspaces, tabs,
  panes, agents, focused ids).
- Raw socket: newline-delimited JSON on `~/.config/herdr/herdr.sock`
  (named sessions: `~/.config/herdr/sessions/<name>/herdr.sock`;
  `HERDR_SOCKET_PATH` overrides). Request `{"id":"x","method":"pane.list","params":{}}`
  returns the same payload as the CLI without spawning a process.

### Done and seen

- `done` = detector state `idle` and the pane not yet seen
  (`src/app/api_helpers.rs::pane_agent_status`). It turns into `idle` when the
  server marks the pane seen: `agent focus` / `pane focus`, or when the active
  tab is shown in a Herdr window that has outer-terminal focus
  (`mark_active_tab_seen`). Reads do not mark seen.
- Caveat: each TUI client also tracks viewed completions itself; with several
  attached clients the server's `done` can lag behind what one window shows.
- There is no timestamp. `herdr agent list` (`agent.list`) carries
  `state_change_seq` and `completion_seq` (set for `idle`/`done`, absent while
  working); a new completion gets a new `completion_seq`. The HUD measures
  "done for how long" itself from the first poll that saw that
  `(terminal_id, completion_seq)` as `done`.
- The agent's last reply is readable with `herdr agent read <pane> --source
  recent --lines N` (socket `pane.read`, plain text, ANSI stripped).

### Events vs polling

- `events.subscribe` with `pane.agent_status_changed` **requires a `pane_id`**
  (schema: `PaneAgentStatusChanged { pane_id, agent_status? }`). There is no
  global "any pane changed status" subscription. A pane that does not exist
  rejects the whole request and closes the connection.
- Global, pane-less subscriptions exist for lifecycle events (`pane.created`,
  `pane.closed`, `pane.exited`, `pane.moved`, `pane.agent_detected`,
  `pane.updated`, …), but not for status.
- History is not durable; a slow subscriber gets `events_lost` and must
  resubscribe and reconcile with `session.snapshot`.
- Plugin event hooks (`[[events]] on = "pane.agent_status_changed"`) do fire
  for every pane: Herdr runs the hook command with `HERDR_PLUGIN_EVENT_JSON`.
  That is the only global push path today.

Conclusion: an event-driven HUD would need one subscription per pane plus
lifecycle tracking plus `events_lost` recovery. Polling `pane.list` once per
second over the socket is a few hundred bytes of JSON and no process spawn;
it is simpler and correct. Events can be added later as a latency optimization
(see option C).

### Focus

- `herdr agent focus <target>`: target is a live agent name or the pane id
  hosting the agent. On success the server focuses the pane and moves **all
  attached TUI clients** to it (`focus_all_shell_clients_on_default_target`),
  and marks `done` as seen. Fails when the pane no longer hosts an agent
  (race: agent exited between poll and click) — then the HUD does nothing and
  re-polls (decision 7).
- `herdr pane focus` only accepts `--direction`; there is no CLI pane focus by
  id.
- Herdr does not know or expose the outer terminal's X11 window.

### What the spec's sketch gets wrong

1. **`herdr pane list --json` is invalid** → exit 2 → `get_blocked_panes()`
   returns `[]` → the HUD never appears. Fatal.
2. Every error is swallowed into "nothing blocked": server down, socket
   missing or timeout hides the HUD silently. It must show a distinct error
   state (e.g. grey row "herdr unreachable") instead.
3. `wmctrl -a herdr` matches any window whose **title** contains "herdr"
   (a browser tab on github.com/…/herdr, an editor). Wrong window raised.
   Use the process tree or WM_CLASS (section 3).
4. Label uses `title` (absent unless metadata) and `pane_id`; the spec asks for
   `workspace · tab · agent`. Needs workspace/tab labels from the snapshot.
5. `print("\a")` goes to the HUD's own stdout (no terminal when autostarted) —
   no sound. `paplay` runs synchronously in the Tk loop with a timeout that
   raises and is swallowed, cutting the sound at 0.5 s.
6. All `subprocess.run` calls block the Tk main loop (up to 1.5 s per poll,
   plus the click handler). Use the socket with a short timeout, or a worker
   thread that posts results with `root.after`.
7. Beep identity keyed on `pane_id`: a moved pane gets a new public id and
   would beep again. Key on `terminal_id` (stable per terminal; to verify in
   the pilot), use `pane_id` only for the focus call.
8. `overrideredirect(True)` + `-topmost`: an unmanaged window is not
   restacked by Openbox; other "above" windows or fullscreen apps can cover
   it, and it is not on a WM layer. Conversely a managed window may **steal
   keyboard focus** on `deiconify()` while the user types in a terminal. This
   trade-off must be tested on Openbox (section 4).
9. Fixed geometry `x = screen_w - 284`: on multi-monitor, `winfo_screenwidth`
   is the whole X screen, so the HUD lands on the rightmost monitor.

## 2. Options

### A. Standalone Python/Tk HUD polling the socket (recommended)

- Python 3 stdlib only (`socket`, `json`, `tkinter`); Tk 9.0 is available.
- 1 s poll of `pane.list` (+ `workspace.list`/`tab.list`, or one
  `session.snapshot`) over the Unix socket, in a worker thread.
- Click: `agent focus` via socket, then raise the terminal window (section 3).
- Beep: `paplay` via `Popen`, non-blocking.
- Autostart via `~/.config/autostart/herdr-blocked-hud.desktop`.
- Pros: no Herdr changes, no Herdr build/restart (Herdr is the agents'
  terminal here), independent lifecycle, easy to iterate.
- Cons: up to 1 s latency; X11 logic lives outside Herdr; keeps the socket
  protocol as an external dependency (stable public JSON API, fine).

### B. Herdr-side feature

A desktop-overlay window is a TUI/OS presentation concern; Herdr is a terminal
program and has no GUI toolkit. Adding X11 windowing to Herdr conflicts with its
runtime/client boundary and platform isolation rules and would require
upstream acceptance. Two smaller upstream-friendly pieces could help any HUD:

- a global `pane.agent_status_changed` subscription (no `pane_id`), removing
  the polling argument entirely;
- exposing the attached client's outer-terminal identity (client pid or
  `WINDOWID` env) through the API, so window raising does not depend on
  process-tree guessing.

Both are upstream proposals, not prerequisites. Not recommended as the
delivery path.

### C. Plugin event hook as a wake-up trigger (optional add-on to A)

A local Herdr plugin with `[[events]] on = "pane.agent_status_changed"` runs a
tiny command (e.g. write one byte to a FIFO or a Unix datagram socket owned by
the HUD). The HUD re-polls immediately on wake, keeping the 1 s poll as the
safety net. Latency drops to ~0; correctness still comes from the poll.
Cost: a plugin install/link and one process spawn per status change across all
panes (agents change state often). Do only if 1 s latency bothers the user.

### Recommendation

A, implemented as one small Python file plus tests for the pure parts (state
diff, beep decision, label formatting, window-matching over a fixture of
`wmctrl -lp` output and a process table). No option C (decision 5). Upstream
proposals from B only on Michael's request.

## 3. Click-to-focus on X11

Order: `agent focus` first (switches Herdr's view), then raise the window.

Window resolution, most to least precise:

1. **Process tree → `_NET_WM_PID`.** Find Herdr TUI client processes of the
   row's session (argv `herdr` or `herdr -…`, not `herdr server` or CLI
   subcommands; session filter in decision 1), walk
   `PPid` from `/proc/<pid>/status` up to an ancestor whose pid owns a
   top-level window in `wmctrl -lp`, then `wmctrl -i -a <wid>` (Openbox
   switches desktop and raises). Verified here: client 5992 → parent
   `wezterm-gui` 5893 → window `0x04200003` with pid 5893, class
   `herdr.herdr`.
2. **WM_CLASS.** The user's launcher already starts
   `wezterm-gui --always-new-process --class herdr -- herdr`, so
   `wmctrl -x -a herdr.herdr` (or `xdotool search --classname herdr
   windowactivate`) is exact for this setup. Make the class configurable.
3. Fail visibly (row flashes, log line), never fall back to title matching.

Limits:

- Terminal-server or mux setups (`wezterm --domain unix`, gnome-terminal,
  tmux around herdr) break the pid chain: the client's ancestor is the mux
  server, not the GUI. Then only method 2 works.
- With several attached clients (several windows), `agent focus` moves all of
  them. Herdr does not expose the most recently active one; the HUD raises
  the first match (decision 4).
- Raising does not select an outer terminal tab if herdr runs in one tab of a
  multi-tab terminal.

## 4. HUD window behavior on Openbox

- Window: override-redirect Tk window, re-`lift()`ed on every refresh.
  Verified on this machine: it renders above other windows, the active window
  and keyboard focus stay on the terminal when it appears, and it is absent
  from `_NET_CLIENT_LIST` with no `_NET_WM_DESKTOP`, so desktop switches do
  not hide it. Chosen over a managed window because it needs no WM hints and
  cannot take focus.
- Position: top-right of the primary monitor (`xrandr --listmonitors`),
  configurable (TASK-5).
- Clicks reach the rows without focusing the HUD (rows are labels with
  button bindings).

## 5. Proposed behavior details

- Rows: `workspace label · tab label · agent` (`display_agent` or `agent`),
  sorted by workspace/tab order; tooltip with pane id and cwd.
- Beep: when a `terminal_id` enters `blocked` that was not blocked in the
  previous poll; at most one beep per poll; no beep on HUD start for already
  blocked panes (configurable).
- Hide when the blocked and done sections are both empty; show an error row
  (no beep) when Herdr is unreachable for more than N polls.

### Long-done agents (user requirement)

An agent that finished may still want something, so the HUD also lists agents
that stay `done` (finished, not yet seen) longer than a threshold.

- Second section below blocked: `workspace · tab · agent · 3m`, oldest first.
- Threshold `done.after_seconds`, default `60`. The timer starts at the first
  poll that sees the `(terminal_id, completion_seq)` as `done`; a new
  completion restarts it. After a HUD restart, panes already `done` start
  counting from the HUD start.
- The row disappears when the pane leaves `done`: user views it (server marks
  seen → `idle`), clicks it (`agent focus` marks seen), or the agent works
  again.
- Sound when a row enters the section: own switch `done.sound_enabled`
  (default `true`) and file `done.sound`, default a quieter sound than
  blocked. Turning it off leaves the blocked sound untouched.
- Click: same as blocked (focus pane, raise window).

Optional reply filter, **default off** (empty list = every long-done agent is
reported):

```toml
[done]
after_seconds = 60
sound_enabled = true           # independent of the blocked sound
# Bottom-most line matching this regex is the agent's final status line.
status_line_regex = '^\s*STATUS:'
# Do not report the agent when its status line matches any of these.
ignore_regexes = []            # e.g. ['^\s*STATUS:\s*DONE\s*$']
read_lines = 80                # recent rows read once per completion
```

- Read once per `(terminal_id, completion_seq)` when the threshold passes,
  never every poll; cache the decision.
- Only the bottom-most line matching `status_line_regex` is tested. Matching
  ignore regexes anywhere in the read window would be wrong: a short reply
  without a status block, or one ending `STATUS: NEEDS_USER`, still has the
  previous turn's `STATUS: DONE` higher up in the scrollback.
- No status line found, or the read fails → report (fail open; decided).
- Agent TUIs draw their prompt box below the reply; the status line is above
  it, inside the last 80 rows unless the reply's tail is very long.
- A regex that does not compile is a startup config error, not a silent skip.
- Single instance: lock file in `$XDG_RUNTIME_DIR`.
- Config: small TOML/INI in `~/.config/herdr-blocked-hud/` — socket/session,
  window class, sound file, position, poll interval.

## 6. Decisions (user)

Scope: a prototype for this Linux machine (LXQt/Openbox, X11). The user runs
one local session.

1. **Sessions: all local sessions, no remote machines.** The cost is small, so
   the prototype handles every local session:
   - Discover sessions with `herdr session list --json` (verified:
     `sessions[]` with `name`, `default`, `running`, `socket_path`); poll each
     `running` session's socket. Re-read the list every ~10 s.
   - Rows show the session name only when more than one session runs.
   - Focus with `herdr --session <name> agent focus <pane>` (or that
     session's socket).
   - Window raise per session: a UI client belongs to session `<name>` when
     its argv has `--session <name>` or its `/proc/<pid>/environ` has
     `HERDR_SESSION=<name>` / `HERDR_SOCKET_PATH=<socket>`; otherwise default.
     Only that session's clients are walked up to a window.
   - Comparison: `quinnjr/herdr-notifications` gets session scoping for free
     because it is a Herdr plugin (each server runs its event hook, and its
     `herdr` calls inherit that server's environment). Its window raise is not
     session-aware: it takes the first process whose argv looks like a Herdr UI
     client (`herdr` or `herdr -…`), walks parents and uses
     `xdotool search --pid`. The HUD reuses that pid-walk, adds the session
     filter above.
   - Remote machines (`--machine`) are out of scope.
2. **Sound: HUD-owned `paplay`.** Simplest: works without a foreground Herdr
   client and without Herdr config. If Herdr's own `[ui.sound]` request sound
   is also active, the user hears both; the HUD does not change Herdr config.
3. **Long-done section: yes** — 60 s default, regex filter off by default,
   agents without a status line are reported, done sound switchable on its
   own (section 5).
4. **Several Herdr windows: raise the first match.**
5. **Latency: 1 s polling is acceptable**; no plugin wake-up (option C).
6. **Hide the row the user is looking at.** A row is hidden (and does not
   beep) while its pane is `focused` in its session **and** the X11 active
   window (`_NET_ACTIVE_WINDOW`, `xdotool getactivewindow`) is that session's
   Herdr host window. When the user switches away it reappears without a
   beep. `done` panes need no extra rule: viewing them marks them seen and
   they leave `done`.
7. **Click on a row whose agent is gone: do nothing, refresh.** When
   `agent focus` fails, no tab focus and no window raise; the HUD re-polls
   immediately.
