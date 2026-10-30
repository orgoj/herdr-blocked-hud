# herdr-blocked-hud

Small always-on-top window for Linux/X11 that lists Herdr agents that need
you:

- **Blocked**: Herdr detected an approval or question prompt. A sound plays
  when a pane becomes blocked.
- **Done**: the agent finished and you have not looked at it for
  `done.after_seconds` (default 60 s). A separate, switchable sound plays.

Click a row to focus that pane in Herdr and raise its terminal window. The
window disappears when nothing is listed. Rows for the pane you are looking
at (focused in the active Herdr window) are hidden. If Herdr cannot be
reached for three polls, a grey error row appears.

All running local Herdr sessions are watched (`herdr session list --json`);
the session name is shown only when more than one session runs.

## Requirements

- Python 3.11+ with Tk (`python3-tk`), no other Python packages
- `herdr` on `PATH`, X11 with `wmctrl`, `xdotool`, `xrandr`, and `paplay`
- Tested on Lubuntu (LXQt + Openbox) with Herdr 0.9.5

## Install and run

```bash
ln -s /path/to/herdr-blocked-hud/bin/herdr-blocked-hud ~/.local/bin/
herdr-blocked-hud                 # run; a second instance exits with status 1
herdr-blocked-hud --demo          # show sample rows for 8 s (check placement)
herdr-blocked-hud --check-config  # validate the config file and exit
```

Start at LXQt login:

```bash
cp contrib/herdr-blocked-hud.desktop ~/.config/autostart/
```

The autostart entry runs `herdr-blocked-hud` from `PATH`; `~/.local/bin` must
be on the session `PATH` (Ubuntu's `~/.profile` adds it when it exists), as
must `herdr`.

## Configuration

`~/.config/herdr-blocked-hud/config.toml` (respects `XDG_CONFIG_HOME`). Every
key is optional; `contrib/config.toml` lists all keys with their defaults.
Unknown keys, wrong types and invalid regexes stop the HUD at startup.

| Key | Default | Meaning |
|---|---|---|
| `poll_interval` | `1.0` | Seconds between polls |
| `wm_class` | `"herdr.herdr"` | Exact `wmctrl -lx` class of the Herdr terminal window, used when the process tree finds none and no other session has a client; `""` disables |
| `blocked_sound` | `dialog-warning.oga` | Blocked sound file; `""` disables |
| `done_sound` | `complete.oga` | Done sound file; `""` disables |
| `corner` | `"top-right"` | `top-right`, `top-left`, `bottom-right`, `bottom-left` of the primary monitor |
| `margin_x`, `margin_y` | `24`, `36` | Pixels from that corner |
| `width` | `320` | Window width in pixels (positive; margins must not be negative) |
| `done.after_seconds` | `60` | How long an agent stays done before it is listed (positive) |
| `done.sound_enabled` | `true` | Done sound on/off, independent of the blocked sound |
| `done.status_line_regex` | `'^\s*STATUS:'` | Finds the agent's status line |
| `done.ignore_regexes` | `[]` | Hide an agent whose status line matches any of these |
| `done.read_lines` | `80` | Rows of pane output read per completion |

### Hiding agents by their status line

With `done.ignore_regexes` empty, every long-done agent is listed. When set,
the HUD reads the agent's last `done.read_lines` rows once per completion,
takes the bottom-most line matching `done.status_line_regex`, and hides the
agent when that line matches any ignore regex. No status line, or a failed
read, keeps the agent listed. Example: list only agents that did not finish
with `STATUS: DONE`:

```toml
[done]
ignore_regexes = ['STATUS:\s*DONE\s*$']
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
```
