#!/usr/bin/env python3
"""
tomd_cli.py
-----------
The interactive terminal experience for ToMd — what the `ToMD` command runs.

A friendly, animated command-line front-end over converter_core:

    welcome animation  ->  pick a file type  ->  native Finder picker
        ->  animated per-file conversion  ->  report  ->  convert more / quit

Everything here is pure standard library (ANSI escape codes + osascript for the
native macOS file dialog), so there are no extra pip dependencies and no
Tkinter — which means none of the deprecated-system-Tk rendering trouble.

Run directly:   python3 tomd_cli.py            (interactive)
                python3 tomd_cli.py a.pdf b.msg (batch, non-interactive)
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from converter_core import convert_file, ConversionError, ConversionResult

# ---------------------------------------------------------------------------
# Terminal styling — degrades to plain text when output isn't a TTY (piped to
# a file, run under a dumb terminal, or NO_COLOR is set).
# ---------------------------------------------------------------------------
_ANSI = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and \
    os.environ.get("TERM") not in (None, "", "dumb")


def _c(code: str) -> str:
    return code if _ANSI else ""


RESET = _c("\033[0m")
BOLD = _c("\033[1m")
DIM = _c("\033[2m")
PURPLE = _c("\033[38;5;99m")
GREEN = _c("\033[38;5;42m")
RED = _c("\033[38;5;203m")
YELLOW = _c("\033[38;5;221m")
CYAN = _c("\033[38;5;80m")
GREY = _c("\033[38;5;245m")
PINK = _c("\033[38;5;211m")

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _hide_cursor():
    if _ANSI:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()


def _show_cursor():
    if _ANSI:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def _clear():
    if _ANSI:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Welcome animation
# ---------------------------------------------------------------------------

BANNER = [
    "  ████████╗ ██████╗ ███╗   ███╗██████╗ ",
    "  ╚══██╔══╝██╔═══██╗████╗ ████║██╔══██╗",
    "     ██║   ██║   ██║██╔████╔██║██║  ██║",
    "     ██║   ██║   ██║██║╚██╔╝██║██║  ██║",
    "     ██║   ╚██████╔╝██║ ╚═╝ ██║██████╔╝",
    "     ╚═╝    ╚═════╝ ╚═╝     ╚═╝╚═════╝ ",
]


def welcome_animation():
    """A short, tasteful intro. Skipped (reduced to a static header) when the
    terminal can't animate."""
    if not _ANSI:
        print(f"{BOLD}ToMd — .msg / .pdf → Markdown{RESET}\n")
        return

    _clear()
    _hide_cursor()
    try:
        # Reveal the banner line by line with a gentle colour sweep.
        for i, line in enumerate(BANNER):
            shade = [PURPLE, PURPLE, CYAN, CYAN, PINK, PINK][i % 6]
            print(f"  {shade}{line}{RESET}")
            time.sleep(0.06)

        # Animate the "paper → memo" motif walking across.
        tagline = "turn .msg emails & .pdf files into clean Markdown"
        for step in range(0, 9):
            arrow = "·" * step + "➜" + "·" * (8 - step)
            sys.stdout.write(
                f"\r  {GREY}📄 {CYAN}{arrow}{GREY} 📝   {DIM}{tagline}{RESET}"
            )
            sys.stdout.flush()
            time.sleep(0.05)
        print("\n")
        time.sleep(0.15)
    finally:
        _show_cursor()


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

TYPE_CHOICES = {
    "1": ("Outlook emails", "(.msg)", ("msg",)),
    "2": ("PDF documents", "(.pdf)", ("pdf",)),
    "3": ("Any mix", "(.msg + .pdf)", ("msg", "pdf")),
}


def type_menu() -> tuple[str, ...] | None:
    """Ask what to convert. Returns the tuple of extensions to allow, or None
    if the user chose to quit."""
    print(f"{BOLD}What would you like to convert?{RESET}\n")
    for key, (label, ext, _) in TYPE_CHOICES.items():
        print(f"  {PURPLE}{key}{RESET}) {label:<16}{GREY}{ext}{RESET}")
    print(f"  {PURPLE}q{RESET}) {'Quit':<16}{GREY}(exit ToMd){RESET}\n")

    while True:
        choice = _prompt(f"Choose {DIM}[1-3, q]{RESET}: ").strip().lower()
        if choice in ("q", "quit", "exit"):
            return None
        if choice in TYPE_CHOICES:
            return TYPE_CHOICES[choice][2]
        print(f"  {YELLOW}Please enter 1, 2, 3, or q.{RESET}")


def _prompt(msg: str) -> str:
    try:
        return input(msg)
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


# ---------------------------------------------------------------------------
# Native macOS file picker (no Tk)
# ---------------------------------------------------------------------------

def choose_files(extensions: tuple[str, ...]) -> list[Path]:
    """Open the native macOS 'choose files' dialog restricted to the given
    extensions. Returns selected paths ([] on cancel or non-macOS)."""
    if sys.platform != "darwin":
        # Fallback: let the user type/paste space-separated paths.
        raw = _prompt(f"{DIM}Enter file paths (space-separated): {RESET}")
        return [Path(os.path.expanduser(p)) for p in raw.split() if p.strip()]

    type_list = "{" + ", ".join(f'"{e}"' for e in extensions) + "}"
    pretty = " / ".join(f".{e}" for e in extensions)

    def _run(with_filter: bool):
        type_clause = f"of type {type_list} " if with_filter else ""
        script = (
            "set chosen to choose file "
            f'with prompt "Select {pretty} file(s) to convert" '
            + type_clause
            + "with multiple selections allowed\n"
            'set out to ""\n'
            "repeat with f in chosen\n"
            "    set out to out & POSIX path of f & linefeed\n"
            "end repeat\n"
            "return out"
        )
        try:
            return subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True
            )
        except FileNotFoundError:
            return None

    proc = _run(with_filter=True)
    if proc is None:
        return []
    if proc.returncode != 0:
        # Tell a user cancel (respect it) apart from the type filter being
        # rejected by this macOS version (retry unfiltered so it still opens).
        if "cancel" in (proc.stderr or "").lower():
            return []
        proc = _run(with_filter=False)
        if proc is None or proc.returncode != 0:
            return []
    return [Path(ln) for ln in proc.stdout.splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# Animated conversion
# ---------------------------------------------------------------------------

def _spinner(stop: threading.Event, state: dict):
    i = 0
    while not stop.is_set():
        note = state.get("note", "")
        sys.stdout.write(
            f"\r{CYAN}{SPINNER[i % len(SPINNER)]}{RESET} {state['label']}"
            f"{DIM}{('  ' + note) if note else ''}{RESET}\033[K"
        )
        sys.stdout.flush()
        i += 1
        time.sleep(0.08)


def convert_one(path: Path) -> tuple[ConversionResult | None, str | None]:
    """Convert a single file, animating a spinner while it runs. Returns
    (result, error_message)."""
    label = f"Converting {BOLD}{path.name}{RESET} …"

    if not _ANSI:
        print(f"Converting {path.name} …")
        try:
            return convert_file(path), None
        except ConversionError as e:
            return None, str(e)
        except Exception as e:  # noqa: BLE001
            return None, f"unexpected error — {e}"

    state = {"label": label, "note": ""}
    stop = threading.Event()
    spin = threading.Thread(target=_spinner, args=(stop, state), daemon=True)
    _hide_cursor()
    spin.start()
    try:
        result = convert_file(path, log=lambda m: state.__setitem__("note", m.strip()))
        error = None
    except ConversionError as e:
        result, error = None, str(e)
    except Exception as e:  # noqa: BLE001 - surface anything unexpected
        result, error = None, f"unexpected error — {e}"
    finally:
        stop.set()
        spin.join()
        _show_cursor()

    # Clear the spinner line and print the final one-liner.
    sys.stdout.write("\r\033[K")
    if error:
        print(f"{RED}⚠️  {path.name}{RESET}  {DIM}{error.splitlines()[0]}{RESET}")
    else:
        print(f"{GREEN}✅ {path.name}{RESET} {DIM}→{RESET} {result.output.name}")
    return result, error


def convert_all(paths: list[Path]) -> tuple[list[ConversionResult], list[tuple[Path, str]]]:
    results: list[ConversionResult] = []
    errors: list[tuple[Path, str]] = []
    print(f"\n{BOLD}Converting {len(paths)} file(s)…{RESET}\n")
    for path in paths:
        result, error = convert_one(path)
        if result is not None:
            results.append(result)
        else:
            errors.append((path, error or "unknown error"))
    return results, errors


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _rule(label: str = "") -> str:
    bar = "─" * 46
    if not label:
        return f"{GREY}{bar}{RESET}"
    return f"{GREY}──── {RESET}{BOLD}{label}{RESET} {GREY}{'─' * (40 - len(label))}{RESET}"


def show_report(results: list[ConversionResult], errors: list[tuple[Path, str]]):
    ok, bad = len(results), len(errors)
    print()
    print(_rule("Report"))
    for r in results:
        detail = (
            f"{r.pages_or_attachments} page(s)" if r.kind == "pdf"
            else f"{r.pages_or_attachments} attachment(s)"
        )
        print(f"  {GREEN}✅{RESET} {r.output.name:<28} {GREY}{detail}{RESET}")
    for path, err in errors:
        print(f"  {RED}⚠️{RESET}  {path.name:<28} {DIM}{err.splitlines()[0]}{RESET}")
    print(_rule())

    if bad == 0:
        icon, color, msg = "🎉", GREEN, f"All {ok} file(s) converted!"
    elif ok == 0:
        icon, color, msg = "😕", RED, f"None converted · {bad} failed."
    else:
        icon, color, msg = "✅", YELLOW, f"{ok} converted · {bad} failed."
    print(f"\n{icon}  {color}{BOLD}{msg}{RESET}")
    if results:
        print(f"{DIM}   Output saved next to each source file.{RESET}")


def reveal_in_finder(results: list[ConversionResult]):
    if not results or sys.platform != "darwin":
        return
    try:
        subprocess.run(["open", "-R", str(results[0].output)], check=False)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# "What next" menu
# ---------------------------------------------------------------------------

def next_menu(has_output: bool) -> str:
    print(f"\n{BOLD}What next?{RESET}\n")
    print(f"  {PURPLE}1{RESET}) Convert more files")
    if has_output:
        print(f"  {PURPLE}2{RESET}) Reveal output in Finder")
    print(f"  {PURPLE}q{RESET}) Quit\n")
    while True:
        choice = _prompt(f"Choose {DIM}[1{', 2' if has_output else ''}, q]{RESET}: ").strip().lower()
        if choice in ("q", "quit", "exit", ""):
            return "quit"
        if choice == "1":
            return "more"
        if choice == "2" and has_output:
            return "reveal"
        print(f"  {YELLOW}Not an option — try again.{RESET}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def interactive() -> int:
    welcome_animation()
    try:
        while True:
            extensions = type_menu()
            if extensions is None:
                break

            paths = choose_files(extensions)
            if not paths:
                print(f"{DIM}No files selected.{RESET}\n")
                continue

            results, errors = convert_all(paths)
            show_report(results, errors)

            while True:
                action = next_menu(bool(results))
                if action == "reveal":
                    reveal_in_finder(results)
                    continue
                break
            if action == "quit":
                break
            print()
    except KeyboardInterrupt:
        print()
    finally:
        _show_cursor()

    print(f"\n{PURPLE}Thanks for using ToMd. 👋{RESET}")
    return 0


def batch(paths: list[str]) -> int:
    """Non-interactive path for `ToMD file1 file2 …` (and pipelines)."""
    results, errors = convert_all([Path(p) for p in paths])
    show_report(results, errors)
    return 1 if errors else 0


def main():
    files = [a for a in sys.argv[1:] if not a.startswith("-")]
    if files:
        raise SystemExit(batch(files))
    raise SystemExit(interactive())


if __name__ == "__main__":
    main()
