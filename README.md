# Minimalist CLI timer and stopwatch

A terminal timer, stopwatch, and pomodoro tool written in Python with no third-party packages.

- Uses Python standard library modules only (`sys`, `time`, `termios`, `select`, `signal`).
- Displays 5-row ASCII digits centered horizontally and vertically by default in interactive mode.
- Offers a pipeline and script mode (`-t`) with no formatting, no fullscreen, and no ANSI escapes.
- Supports configurable Pomodoro intervals via arguments or flags.
- Reads keystrokes without waiting for Enter to pause, resume, reset, adjust time, and record laps.
- Counts overtime after a timer ends in interactive mode.
- Triggers the terminal bell and desktop notifications through `notify-send` or `osascript`.
- Disables colors when `NO_COLOR` is present in the environment.

---

## Quick start

Make `timer.py` executable:
```bash
chmod +x timer.py
```

Run a mode directly:
```bash
# Countdown timer for 5 minutes (interactive TUI, centered)
./timer.py 5m

# Pipeline / script mode (plain text time, exits with code 0 on completion)
./timer.py 5m -t

# Stopwatch
./timer.py -s

# Pomodoro with default 25m focus / 5m break
./timer.py pomo

# Pomodoro with custom durations: 50m focus, 10m break
./timer.py pomo 50m 10m

# Interactive selector
./timer.py
```

---

## Usage examples

### 1. Countdown timer
Pass durations with unit suffixes (`s`, `m`, `h`) or in clock format (`MM:SS`, `HH:MM:SS`):

```bash
./timer.py 25m                    # 25-minute timer
./timer.py 1h 30m "Deep Work"     # 1 hour 30 minute timer with label
./timer.py -c 45s                 # Compact single-line display
./timer.py 10:00 "Tea Steep"      # 10 minutes in MM:SS format
./timer.py 90                     # 90 seconds (bare numbers default to seconds)
```

Controls while running in interactive mode:
| Key | Action |
|---|---|
| `Space` or `p` | Pause or resume |
| `+` / `-` / `↑` / `↓` | Add or subtract 1 minute (or 10 seconds if under 1 minute) |
| `r` | Reset to initial duration |
| `b` | Toggle between big centered ASCII text and compact mode |
| `m` | Toggle terminal bell |
| `q` or `Esc` | Quit |

---

### 2. Pipeline and script mode (`-t`)
Designed for embedding inside bash scripts, subshells, CI jobs, or pipes.

- No fullscreen takeover or screen clearing.
- No ANSI styling or color codes.
- Updates in-place via carriage return when running in a terminal.
- Emits line-by-line output when piped (`not a tty`).
- Exits with return code `0` as soon as the timer reaches zero.

```bash
# Wait 10 seconds in a shell script
./timer.py 10s -t && echo "Next step"

# Pipe time updates to another command
./timer.py 5s -t | while read t; do echo "Time left: $t"; done

# Stopwatch in a script (stops with Ctrl+C)
./timer.py -s -t
```

---

### 3. Stopwatch
Counts up with hundredths-of-a-second precision and records lap splits.

```bash
./timer.py -s
./timer.py stopwatch -c           # Stopwatch in compact single-line mode
```

Controls while running:
| Key | Action |
|---|---|
| `Space` or `p` | Pause or resume |
| `l` | Record lap split |
| `r` | Reset stopwatch |
| `b` | Toggle between big centered ASCII text and compact mode |
| `q` or `Esc` | Stop and print total time, best lap, and average lap |

---

### 4. Pomodoro mode
Alternates between focus sessions and short breaks. Every fourth cycle uses a long break instead.

Default lengths are 25 minutes for focus, 5 minutes for short breaks, and 15 minutes for long breaks across 4 cycles.

Pass focus and break durations as arguments:
```bash
./timer.py pomo 50m 10m
./timer.py pomo 45m 15m 30m 3
```

Set them with flags:
```bash
./timer.py pomo --focus 50m --break 10m
./timer.py -p --focus 45m --break 15m --long-break 30m --cycles 3
```

Press `q` or `Esc` during focus, break, or overtime to exit.

---

## Optional installation

To run `timer` from any directory:

### Option A: Symlink to `~/.local/bin`
```bash
mkdir -p ~/.local/bin
ln -s "$(pwd)/timer.py" ~/.local/bin/timer
```

### Option B: Install with pip or pipx
```bash
pip install -e .
# or
pipx install .
```

---

## CLI options

```text
usage: timer.py [-h] [-s] [-p] [-t] [-c] [-b] [--focus FOCUS]
                [--break SHORT_BREAK] [--long-break LONG_BREAK]
                [--cycles CYCLES] [--no-bell]
                [args ...]

positional arguments:
  args                  Duration (e.g. 5m, 1h 30m) and optional label, or mode
                        ('stopwatch', 'pomo')

options:
  -h, --help            show this help message and exit
  -s, --stopwatch       Start stopwatch directly
  -p, --pomo            Start Pomodoro session
  -t, --time-only       Pipeline/script mode: plain text time only, no fullscreen or formatting
  -c, --compact         Use compact single-line display instead of big text
  -b, --big             Use Big ASCII digit display (default in interactive mode)
  --focus, --work FOCUS Pomodoro focus duration (default: 25m)
  --break SHORT_BREAK   Pomodoro short break duration (default: 5m)
  --long-break LONG_BREAK
                        Pomodoro long break duration (default: 15m)
  --cycles CYCLES       Pomodoro cycle count (default: 4)
  --no-bell             Disable audio bell / notification
```
