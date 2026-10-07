#!/usr/bin/env python3

import sys
import os
import time
import math
import select
import signal
import termios
import tty
import shutil
import argparse
import subprocess
import atexit
import re
from typing import Optional, List, Tuple

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
INVERT = "\033[7m"

FG_CYAN = "\033[36m"
FG_GREEN = "\033[32m"
FG_YELLOW = "\033[33m"
FG_RED = "\033[31m"
FG_MAGENTA = "\033[35m"
FG_WHITE = "\033[97m"
FG_GRAY = "\033[90m"

CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW = "\033[?25h"
CLEAR_LINE = "\033[2K"
CLEAR_DOWN = "\033[J"
CLEAR_SCREEN = "\033[2J\033[H"

ANSI_REGEX = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

BIG_DIGITS = {
    '0': [" ▟███▙ ",
          " █   █ ",
          " █   █ ",
          " █   █ ",
          " ▜███▛ "],

    '1': ["  ▟█   ",
          "   █   ",
          "   █   ",
          "   █   ",
          " ▟███▙ "],

    '2': [" ▟███▙ ",
          "     █ ",
          " ▟███▛ ",
          " █     ",
          " ▟████ "],

    '3': [" ▟███▙ ",
          "     █ ",
          "  ███▙ ",
          "     █ ",
          " ▟███▛ "],

    '4': [" █   █ ",
          " █   █ ",
          " ▜████ ",
          "     █ ",
          "     █ "],

    '5': [" ▟████ ",
          " █     ",
          " ▜███▙ ",
          "     █ ",
          " ▟███▛ "],

    '6': [" ▟███▙ ",
          " █     ",
          " ▟███▙ ",
          " █   █ ",
          " ▜███▛ "],

    '7': [" ▟████ ",
          "     █ ",
          "    ▟▛ ",
          "   ▟▛  ",
          "  ▟▛   "],

    '8': [" ▟███▙ ",
          " █   █ ",
          " ▜███▛ ",
          " █   █ ",
          " ▜███▛ "],

    '9': [" ▟███▙ ",
          " █   █ ",
          " ▜████ ",
          "     █ ",
          " ▟███▛ "],

    ':': ["       ",
          "   █   ",
          "       ",
          "   █   ",
          "       "],

    '.': ["       ",
          "       ",
          "       ",
          "   █   ",
          "   ▀   "],

    ' ': ["   ",
          "   ",
          "   ",
          "   ",
          "   "],

    '-': ["       ",
          "       ",
          " ▟███▙ ",
          "       ",
          "       "],
}


def visible_len(text: str) -> int:
    return len(ANSI_REGEX.sub("", text))


def center_line(text: str, width: int) -> str:
    if not text:
        return ""
    vlen = visible_len(text)
    pad = max(0, (width - vlen) // 2)
    return (" " * pad) + text


def draw_screen(content_lines: List[str]):
    cols, rows = shutil.get_terminal_size((80, 24))
    top_pad = max(0, (rows - len(content_lines)) // 2)
    if top_pad + len(content_lines) > rows:
        top_pad = 0
        content_lines = content_lines[:rows]

    buf = ["\033[H"]
    for _ in range(top_pad):
        buf.append(f"{CLEAR_LINE}\n")

    for i, line in enumerate(content_lines):
        centered = center_line(line, cols)
        buf.append(f"{CLEAR_LINE}{centered}")
        if top_pad + i + 1 < rows:
            buf.append("\n")

    buf.append(CLEAR_DOWN)
    sys.stdout.write("".join(buf))
    sys.stdout.flush()


def render_big_text(text: str) -> List[str]:
    lines = ["", "", "", "", ""]
    for ch in text:
        glyph = BIG_DIGITS.get(ch, BIG_DIGITS[' '])
        for i in range(5):
            lines[i] += glyph[i]
    return lines


def format_duration(seconds: float, include_hundredths: bool = False) -> str:
    is_neg = seconds < 0
    sec = abs(seconds)
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    rem_seconds = int(sec % 60)
    hundredths = int((sec - int(sec)) * 100)

    prefix = "-" if is_neg else ""
    if hours > 0:
        base = f"{hours:02d}:{minutes:02d}:{rem_seconds:02d}"
    else:
        base = f"{minutes:02d}:{rem_seconds:02d}"

    if include_hundredths:
        return f"{prefix}{base}.{hundredths:02d}"
    return f"{prefix}{base}"


def parse_time_string(time_str: str) -> Optional[int]:
    s = time_str.strip().lower()
    if not s:
        return None

    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return None

    if s.isdigit():
        return int(s)

    total_seconds = 0
    current_num = ""
    found_any = False

    unit_multipliers = {
        'h': 3600,
        'm': 60,
        's': 1
    }

    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isdigit() or ch == '.':
            current_num += ch
        elif ch in unit_multipliers:
            if not current_num:
                return None
            try:
                val = float(current_num)
                total_seconds += int(val * unit_multipliers[ch])
                found_any = True
                current_num = ""
            except ValueError:
                return None
        elif ch.isspace():
            pass
        else:
            return None
        i += 1

    if current_num:
        try:
            total_seconds += int(float(current_num))
            found_any = True
        except ValueError:
            return None

    return total_seconds if found_any else None


def extract_duration_and_label(args: List[str]) -> Tuple[Optional[int], str]:
    for i in range(len(args), 0, -1):
        candidate = " ".join(args[:i])
        sec = parse_time_string(candidate)
        if sec is not None and sec > 0:
            label = " ".join(args[i:])
            return sec, label
    return None, " ".join(args)


def resolve_pomo_settings(
    tokens: List[str],
    focus_arg: Optional[str] = None,
    break_arg: Optional[str] = None,
    long_break_arg: Optional[str] = None,
    cycles_arg: Optional[int] = None
) -> Tuple[int, int, int, int]:
    work_sec = 25 * 60
    break_sec = 5 * 60
    long_break_sec = 15 * 60
    cycles = cycles_arg if (cycles_arg is not None and cycles_arg > 0) else 4

    pomo_tokens = tokens[1:] if (tokens and tokens[0].lower() in ("pomo", "pomodoro")) else tokens

    if len(pomo_tokens) >= 1:
        w = parse_time_string(pomo_tokens[0])
        if w:
            work_sec = w
    if len(pomo_tokens) >= 2:
        b = parse_time_string(pomo_tokens[1])
        if b:
            break_sec = b
    if len(pomo_tokens) >= 3:
        lb = parse_time_string(pomo_tokens[2])
        if lb:
            long_break_sec = lb
    if len(pomo_tokens) >= 4 and pomo_tokens[3].isdigit():
        cycles = int(pomo_tokens[3])

    if focus_arg:
        w = parse_time_string(focus_arg)
        if w:
            work_sec = w
    if break_arg:
        b = parse_time_string(break_arg)
        if b:
            break_sec = b
    if long_break_arg:
        lb = parse_time_string(long_break_arg)
        if lb:
            long_break_sec = lb

    return work_sec, break_sec, long_break_sec, cycles


def notify_user(title: str, message: str, sound: bool = True):
    if sound:
        sys.stdout.write("\a")
        sys.stdout.flush()

    if shutil.which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", "-a", "CLI Timer", title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
    elif sys.platform == "darwin" and shutil.which("osascript"):
        try:
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass


def run_pipeline_timer(duration_seconds: int, sound: bool = False, exit_on_complete: bool = True) -> bool:
    total_sec = float(duration_seconds)
    start = time.time()
    is_tty = sys.stdout.isatty()
    last_sec = None

    try:
        while True:
            elapsed = time.time() - start
            rem = max(0.0, total_sec - elapsed)
            sec_int = int(math.ceil(rem))

            if sec_int != last_sec:
                last_sec = sec_int
                time_str = format_duration(sec_int)
                if is_tty:
                    sys.stdout.write(f"\r{time_str}  ")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(f"{time_str}\n")
                    sys.stdout.flush()

            if rem <= 0:
                break
            time.sleep(0.04)

        if is_tty:
            sys.stdout.write(f"\r{format_duration(0)}  \n")
            if sound:
                sys.stdout.write("\a")
            sys.stdout.flush()

        if exit_on_complete:
            sys.exit(0)
        return True

    except KeyboardInterrupt:
        if is_tty:
            sys.stdout.write("\n")
        sys.exit(130)


def run_pipeline_stopwatch():
    start = time.time()
    is_tty = sys.stdout.isatty()
    last_sec = None

    try:
        while True:
            elapsed = time.time() - start
            if is_tty:
                time_str = format_duration(elapsed, include_hundredths=True)
                sys.stdout.write(f"\r{time_str}  ")
                sys.stdout.flush()
                time.sleep(0.04)
            else:
                sec_int = int(elapsed)
                if sec_int != last_sec:
                    last_sec = sec_int
                    time_str = format_duration(sec_int)
                    sys.stdout.write(f"{time_str}\n")
                    sys.stdout.flush()
                time.sleep(0.1)

    except KeyboardInterrupt:
        if is_tty:
            sys.stdout.write("\n")
        sys.exit(0)


def run_pipeline_pomo(work_sec: int, break_sec: int, long_break_sec: int, cycles: int, sound: bool = False):
    try:
        for cycle in range(1, cycles + 1):
            run_pipeline_timer(work_sec, sound=sound, exit_on_complete=False)
            if cycle == cycles:
                break
            is_long = (cycle % 4 == 0)
            b_sec = long_break_sec if is_long else break_sec
            run_pipeline_timer(b_sec, sound=sound, exit_on_complete=False)
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)


class RawTerminal:
    _active_instance = None

    def __init__(self):
        self.old_settings = None
        self.fd = sys.stdin.fileno() if sys.stdin.isatty() else None

    def __enter__(self):
        RawTerminal._active_instance = self
        if self.fd is not None:
            try:
                self.old_settings = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
            except Exception:
                self.old_settings = None
            sys.stdout.write(CURSOR_HIDE)
            sys.stdout.flush()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        RawTerminal._active_instance = None

    def cleanup(self):
        if self.fd is not None and self.old_settings is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
            except Exception:
                pass
            self.old_settings = None
        _, rows = shutil.get_terminal_size((80, 24))
        sys.stdout.write(f"\033[{rows};1H{CURSOR_SHOW}\n")
        sys.stdout.flush()

    def get_key(self) -> Optional[str]:
        if self.fd is None:
            return None
        r, _, _ = select.select([self.fd], [], [], 0.05)
        if not r:
            return None
        try:
            data = os.read(self.fd, 32)
            if not data:
                return None
            seq = data.decode("utf-8", errors="ignore")
        except Exception:
            return None

        if seq == "\033":
            r2, _, _ = select.select([self.fd], [], [], 0.03)
            if r2:
                try:
                    more = os.read(self.fd, 32).decode("utf-8", errors="ignore")
                    seq += more
                except Exception:
                    pass

        if seq in ("\033[A", "\033OA"):
            return "UP"
        elif seq in ("\033[B", "\033OB"):
            return "DOWN"
        elif seq in ("\033[C", "\033OC"):
            return "RIGHT"
        elif seq in ("\033[D", "\033OD"):
            return "LEFT"
        elif seq.startswith("\033[") or seq.startswith("\033O"):
            return "OTHER_SEQ"
        elif seq == "\033":
            return "ESC"

        return seq


def _global_cleanup(*args):
    if RawTerminal._active_instance is not None:
        RawTerminal._active_instance.cleanup()
    sys.exit(130)

signal.signal(signal.SIGINT, _global_cleanup)
signal.signal(signal.SIGTERM, _global_cleanup)

def _safe_atexit():
    if RawTerminal._active_instance is not None:
        RawTerminal._active_instance.cleanup()

atexit.register(_safe_atexit)


def draw_progress_bar(progress: float, width: int = 28) -> str:
    progress = max(0.0, min(1.0, progress))
    filled_len = int(width * progress)
    empty_len = width - filled_len

    bar = f"{FG_CYAN}{'█' * filled_len}{FG_GRAY}{'░' * empty_len}{RESET}"
    percent = f"{int(progress * 100):3d}%"
    return f"[{bar}] {FG_WHITE}{percent}{RESET}"


class StopwatchApp:
    def __init__(self, big_mode: bool = True):
        self.big_mode = big_mode
        self.elapsed_before_pause = 0.0
        self.start_time: Optional[float] = None
        self.is_paused = False
        self.user_quit = False
        self.laps: List[Tuple[int, float, float]] = []
        self.last_lap_split = 0.0
        self.last_term_size = None

    def get_elapsed(self) -> float:
        if self.is_paused or self.start_time is None:
            return self.elapsed_before_pause
        return self.elapsed_before_pause + (time.time() - self.start_time)

    def toggle_pause(self):
        if self.is_paused:
            self.start_time = time.time()
            self.is_paused = False
        else:
            self.elapsed_before_pause = self.get_elapsed()
            self.start_time = None
            self.is_paused = True

    def record_lap(self):
        elapsed = self.get_elapsed()
        lap_duration = elapsed - self.last_lap_split
        self.last_lap_split = elapsed
        lap_num = len(self.laps) + 1
        self.laps.append((lap_num, elapsed, lap_duration))

    def reset(self):
        self.elapsed_before_pause = 0.0
        self.start_time = time.time() if not self.is_paused else None
        self.laps.clear()
        self.last_lap_split = 0.0

    def run(self) -> bool:
        self.start_time = time.time()
        sys.stdout.write(CLEAR_SCREEN)
        sys.stdout.flush()
        self.last_term_size = shutil.get_terminal_size()
        with RawTerminal() as term:
            try:
                while True:
                    key = term.get_key()
                    if key in ('q', 'Q', 'ESC', '\x03'):
                        self.user_quit = True
                        break
                    elif key in (' ', 'p', 'P'):
                        self.toggle_pause()
                    elif key in ('l', 'L'):
                        self.record_lap()
                    elif key in ('r', 'R'):
                        self.reset()
                    elif key in ('b', 'B'):
                        self.big_mode = not self.big_mode
                        sys.stdout.write(CLEAR_SCREEN)
                        sys.stdout.flush()

                    curr_size = shutil.get_terminal_size()
                    if curr_size != self.last_term_size:
                        sys.stdout.write(CLEAR_SCREEN)
                        sys.stdout.flush()
                        self.last_term_size = curr_size

                    self.render()
                    time.sleep(0.04)
            except KeyboardInterrupt:
                self.user_quit = True

        self.print_summary()
        return not self.user_quit

    def render(self):
        cols, _ = shutil.get_terminal_size((80, 24))
        elapsed = self.get_elapsed()
        status_text = f"{FG_YELLOW}PAUSED{RESET}" if self.is_paused else f"{FG_GREEN}RUNNING{RESET}"

        buf = []
        time_str_base = format_duration(elapsed, include_hundredths=False)
        hundredths = f".{int((elapsed - int(elapsed)) * 100):02d}"

        use_big = self.big_mode
        if use_big:
            big_lines = render_big_text(time_str_base)
            if any(visible_len(l) + len(hundredths) > cols for l in big_lines):
                use_big = False

        buf.append(f"{BOLD}{FG_CYAN}⏱  STOPWATCH{RESET}  {status_text}")
        buf.append("")

        if use_big:
            big_lines = render_big_text(time_str_base)
            for i, line in enumerate(big_lines):
                if i == 4:
                    buf.append(f"{FG_WHITE}{BOLD}{line}{FG_CYAN}{hundredths}{RESET}")
                else:
                    buf.append(f"{FG_WHITE}{BOLD}{line}   {RESET}")
        else:
            time_str = format_duration(elapsed, include_hundredths=True)
            buf.append(f"{BOLD}{FG_WHITE}{time_str}{RESET}")

        buf.append("")

        if self.laps:
            buf.append(f"{DIM}Laps ({len(self.laps)} total):{RESET}")
            recent_laps = self.laps[-5:]
            min_lap = min(l[2] for l in self.laps) if len(self.laps) > 1 else -1
            max_lap = max(l[2] for l in self.laps) if len(self.laps) > 1 else -1

            for num, split, duration in recent_laps:
                tag = ""
                dur_color = FG_WHITE
                if len(self.laps) > 1:
                    if duration == min_lap:
                        tag = f" {FG_GREEN}(best){RESET}"
                        dur_color = FG_GREEN
                    elif duration == max_lap:
                        tag = f" {FG_RED}(slowest){RESET}"
                        dur_color = FG_RED

                buf.append(
                    f"{FG_GRAY}#{num:02d}{RESET}  "
                    f"{dur_color}{format_duration(duration, True)}{RESET}  "
                    f"{FG_GRAY}split: {format_duration(split, True)}{RESET}{tag}"
                )
            buf.append("")

        controls = (
            f"{FG_GRAY}[Space/p] Pause  "
            f"[l] Lap  "
            f"[r] Reset  "
            f"[b] {'Compact' if self.big_mode else 'Big'}  "
            f"[q] Quit{RESET}"
        )
        buf.append(controls)
        draw_screen(buf)

    def print_summary(self):
        elapsed = self.get_elapsed()
        print("\n" + f"{BOLD}Stopwatch Stopped.{RESET}")
        print(f"Total Time: {BOLD}{FG_CYAN}{format_duration(elapsed, True)}{RESET}")
        if self.laps:
            print(f"Total Laps: {len(self.laps)}")
            best_lap = min(self.laps, key=lambda x: x[2])
            avg_lap = sum(l[2] for l in self.laps) / len(self.laps)
            print(f"Best Lap:   #{best_lap[0]} in {FG_GREEN}{format_duration(best_lap[2], True)}{RESET}")
            print(f"Avg Lap:    {format_duration(avg_lap, True)}")


class TimerApp:
    def __init__(self, duration_seconds: int, label: str = "", big_mode: bool = True, sound: bool = True):
        self.total_duration = float(duration_seconds)
        self.remaining = float(duration_seconds)
        self.label = label
        self.big_mode = big_mode
        self.sound = sound
        self.start_time: Optional[float] = None
        self.is_paused = False
        self.is_done = False
        self.user_quit = False
        self.notified = False
        self.last_beep_time = 0.0
        self.last_term_size = None

    def toggle_pause(self):
        if self.is_paused:
            self.start_time = time.time()
            self.is_paused = False
        else:
            if self.start_time is not None:
                elapsed = time.time() - self.start_time
                self.remaining -= elapsed
            self.start_time = None
            self.is_paused = True

    def adjust_time(self, delta_seconds: float):
        if not self.is_paused and self.start_time is not None:
            elapsed = time.time() - self.start_time
            self.remaining -= elapsed
            self.start_time = time.time()
        self.remaining += delta_seconds
        self.total_duration = max(self.total_duration, self.remaining)

    def reset(self):
        self.remaining = self.total_duration
        self.start_time = time.time() if not self.is_paused else None
        self.is_done = False
        self.notified = False

    def get_remaining(self) -> float:
        if self.is_paused or self.start_time is None:
            return self.remaining
        return self.remaining - (time.time() - self.start_time)

    def run(self) -> bool:
        self.start_time = time.time()
        sys.stdout.write(CLEAR_SCREEN)
        sys.stdout.flush()
        self.last_term_size = shutil.get_terminal_size()
        with RawTerminal() as term:
            try:
                while True:
                    key = term.get_key()
                    if key in ('q', 'Q', 'ESC', '\x03'):
                        self.user_quit = True
                        break
                    elif self.is_done and key in (' ', '\n', '\r', 'c', 'C'):
                        break
                    elif key in (' ', 'p', 'P'):
                        self.toggle_pause()
                    elif key in ('+', '=', 'UP', 'RIGHT'):
                        step = 10 if self.total_duration < 60 else 60
                        self.adjust_time(step)
                    elif key in ('-', '_', 'DOWN', 'LEFT'):
                        step = 10 if self.total_duration < 60 else 60
                        self.adjust_time(-step)
                    elif key in ('r', 'R'):
                        self.reset()
                    elif key in ('b', 'B'):
                        self.big_mode = not self.big_mode
                        sys.stdout.write(CLEAR_SCREEN)
                        sys.stdout.flush()
                    elif key in ('m', 'M'):
                        self.sound = not self.sound

                    curr_size = shutil.get_terminal_size()
                    if curr_size != self.last_term_size:
                        sys.stdout.write(CLEAR_SCREEN)
                        sys.stdout.flush()
                        self.last_term_size = curr_size

                    rem = self.get_remaining()
                    if rem <= 0 and not self.is_done:
                        self.is_done = True
                        if not self.notified:
                            title = f"Timer Finished: {self.label}" if self.label else "Timer Finished!"
                            msg = f"{format_duration(self.total_duration)} elapsed."
                            notify_user(title, msg, sound=self.sound)
                            self.notified = True

                    if self.is_done and self.sound:
                        now = time.time()
                        if now - self.last_beep_time >= 10.0:
                            sys.stdout.write("\a")
                            sys.stdout.flush()
                            self.last_beep_time = now

                    self.render()
                    time.sleep(0.05)
            except KeyboardInterrupt:
                self.user_quit = True

        if self.user_quit:
            print(f"\n{BOLD}Timer stopped.{RESET}")
        else:
            print(f"\n{BOLD}Timer completed.{RESET}")

        return not self.user_quit

    def render(self):
        cols, _ = shutil.get_terminal_size((80, 24))
        rem = self.get_remaining()

        display_rem = max(0.0, rem) if not self.is_done else rem
        time_str = format_duration(display_rem)
        color = FG_RED if self.is_done else (FG_YELLOW if self.is_paused else FG_WHITE)

        use_big = self.big_mode
        if use_big:
            big_lines = render_big_text(time_str)
            if any(visible_len(l) > cols for l in big_lines):
                use_big = False

        buf = []

        if self.is_done:
            status_text = f"{FG_RED}{BOLD}TIME'S UP!{RESET} (+{format_duration(abs(rem))} overdue)"
        elif self.is_paused:
            status_text = f"{FG_YELLOW}PAUSED{RESET}"
        else:
            status_text = f"{FG_GREEN}COUNTING{RESET}"

        header = f"{BOLD}{FG_CYAN}⏳ TIMER{RESET}"
        if self.label:
            header += f" {FG_WHITE}({self.label}){RESET}"
        header += f"  {status_text}"
        buf.append(header)
        buf.append("")

        if use_big:
            big_lines = render_big_text(time_str)
            for line in big_lines:
                buf.append(f"{color}{BOLD}{line}{RESET}")
        else:
            buf.append(f"{BOLD}{color}{time_str}{RESET} / {format_duration(self.total_duration)}")

        buf.append("")

        if self.total_duration > 0:
            progress = max(0.0, min(1.0, 1.0 - (rem / self.total_duration)))
            bar_width = min(40, max(15, cols - 24))
            buf.append(draw_progress_bar(progress, bar_width))
            buf.append("")

        sound_status = f"{FG_GREEN}on{RESET}" if self.sound else f"{FG_GRAY}off{RESET}"
        if self.is_done:
            controls = (
                f"{FG_GREEN}[Space/Enter] Next/Done  "
                f"{FG_GRAY}[r] Reset  "
                f"[q] Quit{RESET}"
            )
        else:
            controls = (
                f"{FG_GRAY}[Space/p] Pause  "
                f"[+/- or ↑/↓] ±1m  "
                f"[r] Reset  "
                f"[b] {'Compact' if self.big_mode else 'Big'}  "
                f"[m] Bell:{sound_status}  "
                f"[q] Quit{RESET}"
            )
        buf.append(controls)

        draw_screen(buf)


class PomodoroApp:
    def __init__(
        self,
        work_sec: int = 25 * 60,
        break_sec: int = 5 * 60,
        long_break_sec: int = 15 * 60,
        cycles: int = 4,
        big_mode: bool = True
    ):
        self.work_sec = work_sec
        self.break_sec = break_sec
        self.long_break_sec = long_break_sec
        self.target_cycles = cycles
        self.current_cycle = 1
        self.big_mode = big_mode

    def run(self):
        print(
            f"\n{BOLD}{FG_CYAN}🍅 Pomodoro Session Started{RESET} "
            f"({self.target_cycles} cycles: {format_duration(self.work_sec)} focus, {format_duration(self.break_sec)} break)"
        )
        time.sleep(1)

        while self.current_cycle <= self.target_cycles:
            label = f"🍅 Focus #{self.current_cycle}/{self.target_cycles}"
            app = TimerApp(self.work_sec, label=label, big_mode=self.big_mode)
            completed_focus = app.run()

            if not completed_focus:
                return

            if self.current_cycle == self.target_cycles:
                notify_user("Pomodoro Finished!", f"Completed all {self.target_cycles} focus cycles! Great job!")
                print(f"\n{BOLD}{FG_GREEN}🎉 All {self.target_cycles} Pomodoro cycles completed!{RESET}\n")
                break

            is_long = (self.current_cycle % 4 == 0)
            break_time = self.long_break_sec if is_long else self.break_sec
            break_label = f"☕ {'Long ' if is_long else ''}Break"

            print(f"\n{BOLD}{FG_YELLOW}Starting {break_label} ({format_duration(break_time)})...{RESET}")
            time.sleep(1)

            b_app = TimerApp(break_time, label=break_label, big_mode=self.big_mode)
            completed_break = b_app.run()

            if not completed_break:
                return

            self.current_cycle += 1


def interactive_menu():
    print(f"\n{BOLD}{FG_CYAN}⏱  Minimalist Timer & Stopwatch{RESET}\n")
    print(f"  {BOLD}1{RESET}) Stopwatch")
    print(f"  {BOLD}2{RESET}) Countdown Timer")
    print(f"  {BOLD}3{RESET}) Pomodoro")
    print(f"  {BOLD}q{RESET}) Exit\n")

    try:
        choice = input(f"{BOLD}Select [1/2/3/q]: {RESET}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)

    if choice == '1':
        StopwatchApp(big_mode=True).run()
    elif choice == '2':
        try:
            val = input(f"{BOLD}Enter duration (e.g. 5m, 1h30m, 90s, 10:00): {RESET}").strip()
            sec = parse_time_string(val)
            if not sec or sec <= 0:
                print(f"{FG_RED}Invalid time format.{RESET}")
                return
            label = input(f"{BOLD}Optional label: {RESET}").strip()
            TimerApp(sec, label=label, big_mode=True).run()
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(0)
    elif choice == '3':
        try:
            val = input(f"{BOLD}Focus / Break duration [press enter for 25m 5m, or type e.g. 50m 10m]: {RESET}").strip()
            if val:
                w, b, lb, cyc = resolve_pomo_settings(val.split())
                PomodoroApp(work_sec=w, break_sec=b, long_break_sec=lb, cycles=cyc, big_mode=True).run()
            else:
                PomodoroApp(big_mode=True).run()
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(0)
    else:
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Minimalist CLI Timer, Stopwatch & Pomodoro app.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s 5m                  # 5-minute countdown timer (interactive TUI)
  %(prog)s 5m -t               # Pipeline/script mode (plain text time, no fullscreen)
  %(prog)s 1h 30m "Study"      # 1 hour 30 min timer with label
  %(prog)s -s                  # Stopwatch mode (interactive TUI)
  %(prog)s -s -t               # Stopwatch in pipeline/script mode
  %(prog)s -c 45s              # 45-second timer with compact single-line display
  %(prog)s pomo                # Pomodoro session (25m focus / 5m break)
  %(prog)s pomo 50m 10m        # Custom Pomodoro: 50m focus / 10m break
  %(prog)s pomo --focus 45m --break 15m --cycles 3
  %(prog)s                     # Interactive menu
"""
    )
    parser.add_argument("args", nargs="*", help="Duration (e.g. 5m, 1h 30m) and optional label, or mode ('stopwatch', 'pomo')")
    parser.add_argument("-s", "--stopwatch", action="store_true", help="Start stopwatch directly")
    parser.add_argument("-p", "--pomo", action="store_true", help="Start Pomodoro session")
    parser.add_argument("-t", "--time-only", action="store_true", help="Pipeline/script mode: plain text time only, no fullscreen or formatting")
    parser.add_argument("-c", "--compact", action="store_true", help="Use compact single-line display instead of big text")
    parser.add_argument("-b", "--big", action="store_true", help="Use Big ASCII digit display (default in interactive mode)")
    parser.add_argument("--focus", "--work", dest="focus", default=None, help="Pomodoro focus duration (default: 25m)")
    parser.add_argument("--break", dest="short_break", default=None, help="Pomodoro short break duration (default: 5m)")
    parser.add_argument("--long-break", dest="long_break", default=None, help="Pomodoro long break duration (default: 15m)")
    parser.add_argument("--cycles", dest="cycles", type=int, default=4, help="Pomodoro cycle count (default: 4)")
    parser.add_argument("--no-bell", action="store_true", help="Disable audio bell / notification")

    parsed = parser.parse_args()

    if "NO_COLOR" in os.environ:
        global RESET, BOLD, DIM, ITALIC, INVERT
        global FG_CYAN, FG_GREEN, FG_YELLOW, FG_RED, FG_MAGENTA, FG_WHITE, FG_GRAY
        RESET = BOLD = DIM = ITALIC = INVERT = ""
        FG_CYAN = FG_GREEN = FG_YELLOW = FG_RED = FG_MAGENTA = FG_WHITE = FG_GRAY = ""

    big_mode = not parsed.compact
    time_only = parsed.time_only
    tokens = parsed.args

    if time_only:
        if parsed.stopwatch or (tokens and tokens[0].lower() in ("stopwatch", "sw")):
            run_pipeline_stopwatch()
        elif parsed.pomo or parsed.focus or parsed.short_break or (tokens and tokens[0].lower() in ("pomo", "pomodoro")):
            work_sec, break_sec, long_break_sec, cycles = resolve_pomo_settings(
                tokens,
                focus_arg=parsed.focus,
                break_arg=parsed.short_break,
                long_break_arg=parsed.long_break,
                cycles_arg=parsed.cycles
            )
            run_pipeline_pomo(work_sec, break_sec, long_break_sec, cycles, sound=not parsed.no_bell)
        elif tokens:
            sec, _ = extract_duration_and_label(tokens)
            if sec is None or sec <= 0:
                sys.stderr.write(f"Error: Could not parse duration from '{' '.join(tokens)}'.\n")
                sys.exit(1)
            run_pipeline_timer(sec, sound=not parsed.no_bell)
        else:
            sys.stderr.write("Error: -t requires a duration or mode (e.g. 'timer 5s -t' or 'timer -s -t').\n")
            sys.exit(1)
        return

    if parsed.stopwatch or (tokens and tokens[0].lower() in ("stopwatch", "sw")):
        StopwatchApp(big_mode=big_mode).run()
    elif parsed.pomo or parsed.focus or parsed.short_break or (tokens and tokens[0].lower() in ("pomo", "pomodoro")):
        work_sec, break_sec, long_break_sec, cycles = resolve_pomo_settings(
            tokens,
            focus_arg=parsed.focus,
            break_arg=parsed.short_break,
            long_break_arg=parsed.long_break,
            cycles_arg=parsed.cycles
        )
        PomodoroApp(
            work_sec=work_sec,
            break_sec=break_sec,
            long_break_sec=long_break_sec,
            cycles=cycles,
            big_mode=big_mode
        ).run()
    elif tokens:
        sec, label = extract_duration_and_label(tokens)
        if sec is None or sec <= 0:
            print(f"{FG_RED}Error: Could not parse duration from '{' '.join(tokens)}'.{RESET}")
            print("Use formats like: 5m, 1h30m, 1h 30m, 45s, 10:00, or 300")
            sys.exit(1)
        TimerApp(sec, label=label, big_mode=big_mode, sound=not parsed.no_bell).run()
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
