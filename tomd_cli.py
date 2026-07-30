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

import converter_core
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
        print(f"{BOLD}ToMd — documents, emails & PDFs → Markdown{RESET}\n")
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
        tagline = "turn documents, emails & PDFs into clean Markdown"
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

def _build_type_menu() -> dict[str, tuple[str, str, tuple[str, ...]]]:
    """Build the menu from converter_core's format groups, plus an 'Any' entry.
    Returns {key: (label, pretty_extensions, extension_tuple)}."""
    menu: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for i, (label, exts) in enumerate(converter_core.FILE_GROUPS, start=1):
        pretty = ", ".join("." + e for e in exts)
        menu[str(i)] = (label, pretty, tuple(exts))
    any_key = str(len(converter_core.FILE_GROUPS) + 1)
    menu[any_key] = (
        "Any supported type", "everything below",
        tuple(converter_core.all_supported_extensions()),
    )
    return menu


def type_menu() -> tuple[str, ...] | None:
    """Ask what to convert. Returns the tuple of extensions to allow, or None
    if the user chose to quit."""
    menu = _build_type_menu()
    keys = ", ".join(menu.keys())
    print(f"{BOLD}What would you like to convert?{RESET}\n")
    for key, (label, pretty, _) in menu.items():
        print(f"  {PURPLE}{key}{RESET}) {label:<20}{GREY}{pretty}{RESET}")
    print(f"  {PURPLE}q{RESET}) {'Quit':<20}{GREY}exit ToMd{RESET}\n")

    while True:
        choice = _prompt(f"Choose {DIM}[{keys}, q]{RESET}: ").strip().lower()
        if choice in ("q", "quit", "exit"):
            return None
        if choice in menu:
            return menu[choice][2]
        print(f"  {YELLOW}Please enter {keys}, or q.{RESET}")


def _prompt(msg: str) -> str:
    try:
        return input(msg)
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


# ---------------------------------------------------------------------------
# Native file pickers (no Tk) — macOS via osascript, Linux via zenity/kdialog
# ---------------------------------------------------------------------------

def choose_files(extensions: tuple[str, ...]) -> list[Path]:
    """Open a native 'choose files' dialog restricted to the given extensions.
    Uses the OS's own dialog (no Tk). Returns selected paths, or [] on cancel.
    Falls back to a typed-path prompt if no graphical picker is available."""
    if sys.platform == "darwin":
        return _choose_files_macos(extensions)
    if sys.platform.startswith("linux"):
        picked = _choose_files_linux(extensions)
        if picked is not None:
            return picked
    # Last resort (headless, or no picker installed): ask for paths.
    raw = _prompt(f"{DIM}Enter file paths (space-separated): {RESET}")
    return [Path(os.path.expanduser(p)) for p in raw.split() if p.strip()]


def _choose_files_linux(extensions: tuple[str, ...]) -> list[Path] | None:
    """Try zenity, then kdialog. Returns a (possibly empty) list of paths if a
    dialog ran, or None if no graphical picker is installed."""
    pretty = " ".join(f"*.{e}" for e in extensions)

    if _which("zenity"):
        cmd = [
            "zenity", "--file-selection", "--multiple", "--separator=\n",
            "--title=Select file(s) to convert",
            f"--file-filter=Supported | {pretty}",
            "--file-filter=All files | *",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:  # user cancelled
            return []
        return [Path(ln) for ln in proc.stdout.splitlines() if ln.strip()]

    if _which("kdialog"):
        cmd = [
            "kdialog", "--getopenfilename", os.path.expanduser("~"),
            f"{pretty}|Supported files",
            "--multiple", "--separate-output",
            "--title", "Select file(s) to convert",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return []
        return [Path(ln) for ln in proc.stdout.splitlines() if ln.strip()]

    return None


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


def _choose_files_macos(extensions: tuple[str, ...]) -> list[Path]:
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
        detail = r.detail or r.kind
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


def _file_manager_label() -> str:
    return "Finder" if sys.platform == "darwin" else "file manager"


def reveal_output(results: list[ConversionResult]):
    """Open the folder containing the first output in the OS file manager."""
    if not results:
        return
    target = results[0].output
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(target)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(target.parent)], check=False)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# "What next" menu
# ---------------------------------------------------------------------------

def next_menu(has_output: bool) -> str:
    print(f"\n{BOLD}What next?{RESET}\n")
    print(f"  {PURPLE}1{RESET}) Convert more files")
    if has_output:
        print(f"  {PURPLE}2{RESET}) Reveal output in {_file_manager_label()}")
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
                    reveal_output(results)
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
    argv = sys.argv[1:]
    # --gui launches the full Tkinter app (bundled into the same executable).
    if "--gui" in argv:
        import app_gui
        app_gui.run_gui()
        return
    files = [a for a in argv if not a.startswith("-")]
    if files:
        raise SystemExit(batch(files))
    raise SystemExit(interactive())


if __name__ == "__main__":
    main()
