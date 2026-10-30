# herdr-blocked-hud

> **Personal pilot project.** I wrote this for my own computer and the
> tools I run on it (Lubuntu with LXQt and Openbox, X11, WezTerm, Herdr
> 0.9.5). It may not work anywhere else, and I do not plan to support other
> setups. It is not an official [Herdr](https://github.com/herdrdev/herdr)
> project and is not affiliated with it. Provided as is, without warranty of
> any kind; see [LICENSE](LICENSE).

Small always-on-top window for Linux/X11 that lists Herdr agents that need
you:

- **Blocked**: Herdr detected an approval or question prompt. A sound plays
  when a pane becomes blocked.
- **Done**: the agent finished and you have not looked at it for
  `done.after_seconds` (default 5 s), grouped by the value of its final
  `STATUS:` line. By default a row leaves once you view the pane; a status
  value set to `sticky` stays until the agent works again. A separate,
  switchable sound plays.

Click a row to focus that pane in Herdr and raise its terminal window; `×`
or a right click dismisses a done row. On the top line, `↻` restarts the
HUD with the same command (so a newly installed version starts) and `×`
quits it. The
window disappears when nothing is listed. A blocked pane stays listed until
it is no longer blocked, even while it is on screen in Herdr. If Herdr
cannot be reached for three polls, a grey error row appears.

All running local Herdr sessions are watched (`herdr session list --json`);
the session name is shown only when more than one session runs.

## Requirements

- Python 3.11+ with Tk (`python3-tk`), no other Python packages
- `herdr` on `PATH`, X11 with `wmctrl`, `xrandr`, and `paplay`
- Tested only on Lubuntu (LXQt + Openbox) with Herdr 0.9.5

## Install and run

Install a tagged release as a uv tool (a copy, so work in the checkout does
not affect the running HUD). The Python must include Tk; uv's managed
CPython does.

```bash
uv tool install --python 3.14 git+https://github.com/orgoj/herdr-blocked-hud@v0.1.6
herdr-blocked-hud                 # run; a second instance exits with status 1
herdr-blocked-hud --demo          # sample rows for 8 s and both sounds (check placement)
herdr-blocked-hud --check-config  # validate the config file and exit
```

Start at LXQt login:

```bash
cp contrib/herdr-blocked-hud.desktop ~/.config/autostart/
```

The autostart entry runs `herdr-blocked-hud` from `PATH`; `~/.local/bin` (where
uv puts tool commands) must be on the session `PATH` (Ubuntu's `~/.profile`
adds it when it exists), as must `herdr`.

To run from a checkout during development, without installing:
`bin/herdr-blocked-hud` (or `python3 -m herdr_blocked_hud`).

Releases: `bin/bump-version X.Y.Z` (sets `version` in `pyproject.toml` and the
install tag above), run the tests, commit, and tag `vX.Y.Z`.

## Configuration

`~/.config/herdr-blocked-hud/config.toml` (respects `XDG_CONFIG_HOME`). Every
key is optional; `contrib/config.toml` lists all keys with their defaults.
Unknown keys, wrong types and invalid regexes stop the HUD at startup.

| Key | Default | Meaning |
|---|---|---|
| `poll_interval` | `1.0` | Seconds between polls |
| `wm_class` | `"herdr.herdr"` | Exact `wmctrl -lx` class of the Herdr terminal window, used when the process tree finds none and no other session has a client; `""` disables |
| `blocked_sound` | `"builtin"` | `"builtin"` (the HUD's own urgent two-tone call), a sound file for `paplay`, or `""` to disable |
| `done_sound` | `"builtin"` | `"builtin"` (the HUD's own soft rising chime), a sound file, or `""` to disable |
| `corner` | `"top-right"` | `top-right`, `top-left`, `bottom-right`, `bottom-left` of the primary monitor |
| `margin_x`, `margin_y` | `24`, `36` | Pixels from that corner |
| `width` | `320` | Window width in pixels (positive; margins must not be negative) |
| `done.after_seconds` | `5` | How long an agent stays done before it is listed (positive) |
| `done.sound_enabled` | `true` | Done sound on/off, independent of the blocked sound |
| `done.status_regex` | `'^\s*STATUS:\s*(\S+)'` | Finds the agent's status line; group 1 is the status value |
| `done.modes` | `{}` | Mode per status value: `"transient"`, `"sticky"` or `"hide"` |
| `done.default_mode` | `"transient"` | Mode of status values not in `done.modes` |
| `done.no_status_mode` | `"transient"` | Mode of a reply without a status line, or a failed read |
| `done.read_lines` | `80` | Rows of pane output read per completion |

### Done sections by status value

When an agent finishes, the HUD reads its last `done.read_lines` rows once,
takes the bottom-most line matching `done.status_regex`, and lists the agent
under a `Done · <value>` section (plain `Done` without a status line). The
value's mode decides how long the row stays:

- `transient`: until you view the pane (Herdr marks it seen), as Herdr does.
- `sticky`: also after you viewed it, until the agent works again or
  finishes anew; a pane viewed before `done.after_seconds` is still listed.
- `hide`: never listed.

The `×` button or a right click dismisses a done row for that completion.
Example: forget `DONE` replies once seen, keep every other one listed:

```toml
[done]
default_mode = "sticky"

[done.modes]
DONE = "transient"
```

## How it works

Each poll sends one `session.snapshot` request to every running session's
Unix socket. Clicking runs `herdr --session <name> agent focus <pane>`, then
raises the window that owns that session's Herdr client (found through the
client's parent processes, else by `wm_class`; never by window title). Design
notes: `docs/design.md`.

## Development

```bash
python3 tests/run
xvfb-run -a env HUD_GUI_TESTS=1 python3 tests/run   # with the Tk tests, off-screen
```

## License

MIT, see [LICENSE](LICENSE). No warranty.
