#!/usr/bin/env python3
"""
ToMd — turn .msg and .pdf files into Markdown, with a friendly GUI.

Run directly:      python3 app_gui.py
Or launch as an app via the "ToMd.app" built by build_app.sh
(so it shows up in Spotlight and you can just type its name).
"""

from __future__ import annotations

import queue
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

from converter_core import convert_file, ConversionError

# Tkinter is imported lazily (see _load_tk) so the headless CLI path works
# even where Tk is missing or broken. With `from __future__ import annotations`
# the `root: Tk` hints below are just strings and never need Tk at import time.


def _load_tk():
    """Import the Tkinter symbols this module uses into globals, on demand."""
    global Tk, Canvas, filedialog, messagebox, ttk, StringVar
    from tkinter import Tk, Canvas, filedialog, messagebox
    from tkinter import ttk, StringVar

# ---------------------------------------------------------------------------
# Palette — soft dark theme with an accent color, feels a bit more "app-like"
# than default Tk grey.
# ---------------------------------------------------------------------------
BG = "#1e1f29"
BG_PANEL = "#262838"
FG = "#f2f2f7"
FG_DIM = "#9a9cb0"
ACCENT = "#7c5cff"
ACCENT2 = "#33d17a"
DANGER = "#ff5c5c"

FONT_TITLE = ("SF Pro Display", 22, "bold")
FONT_SUB = ("SF Pro Text", 12)
FONT_MONO = ("Menlo", 11)
FONT_BTN = ("SF Pro Text", 13, "bold")


class ToMdApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("ToMd")
        self.root.configure(bg=BG)
        self.root.geometry("560x420")
        self.root.minsize(480, 380)

        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.files: list[Path] = []
        self.results = []
        self.errors = []

        self._build_welcome()
        self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # Screen 1 — welcome / picker
    # ------------------------------------------------------------------
    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _build_welcome(self):
        self._clear()
        wrap = Canvas(self.root, bg=BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True)

        wrap.create_text(
            280, 90, text="📄 ➜ 📝", font=("SF Pro Display", 40), fill=FG
        )
        wrap.create_text(
            280, 150, text="ToMd", font=FONT_TITLE, fill=FG
        )
        wrap.create_text(
            280, 180,
            text="Turn .msg emails and .pdf files into clean Markdown.",
            font=FONT_SUB, fill=FG_DIM,
        )

        btn = self._make_button(
            wrap, "Choose Files…", ACCENT, self._pick_files, width=220
        )
        wrap.create_window(280, 250, window=btn)

        wrap.create_text(
            280, 300,
            text="Select any mix of .msg and .pdf files.\nOutput lands right next to each source file.",
            font=("SF Pro Text", 10), fill=FG_DIM, justify="center",
        )

        quit_btn = self._make_button(
            wrap, "Quit", BG_PANEL, self.root.destroy, width=100, fg=FG_DIM
        )
        wrap.create_window(280, 380, window=quit_btn)

    def _make_button(self, parent, text, color, command, width=160, fg=FG):
        b = ttk.Button(parent, text=text, command=command)
        style_name = f"Btn{id(b)}.TButton"
        style = ttk.Style()
        style.configure(
            style_name,
            font=FONT_BTN,
            foreground=fg,
            background=color,
            padding=10,
        )
        style.map(style_name, background=[("active", color)])
        b.configure(style=style_name)
        return b

    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Choose .msg or .pdf files",
            filetypes=[
                ("Emails & PDFs", "*.msg *.pdf"),
                ("Outlook messages", "*.msg"),
                ("PDF documents", "*.pdf"),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        self.files = [Path(p) for p in paths]
        self._build_progress()
        threading.Thread(target=self._convert_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Screen 2 — progress
    # ------------------------------------------------------------------
    def _build_progress(self):
        self._clear()
        self.results, self.errors = [], []

        header = ttk.Label(
            self.root, text="Converting…", font=FONT_TITLE,
            background=BG, foreground=FG,
        )
        header.pack(pady=(24, 4))

        self.status_var = StringVar(value="Getting started…")
        status = ttk.Label(
            self.root, textvariable=self.status_var, font=FONT_SUB,
            background=BG, foreground=FG_DIM,
        )
        status.pack(pady=(0, 12))

        style = ttk.Style()
        style.theme_use(style.theme_use())
        style.configure(
            "Fun.Horizontal.TProgressbar",
            troughcolor=BG_PANEL, background=ACCENT, thickness=18,
        )
        self.progress = ttk.Progressbar(
            self.root, orient="horizontal", mode="determinate",
            maximum=max(len(self.files), 1), length=460,
            style="Fun.Horizontal.TProgressbar",
        )
        self.progress.pack(pady=(0, 16))

        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        from tkinter import Text
        self.log = Text(
            log_frame, bg=BG_PANEL, fg=FG_DIM, font=FONT_MONO,
            relief="flat", wrap="word", height=10, borderwidth=0,
        )
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

    def _append_log(self, text: str, color=FG_DIM):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _convert_worker(self):
        for i, path in enumerate(self.files, start=1):
            self.queue.put(("status", f"({i}/{len(self.files)}) {path.name}"))
            try:
                result = convert_file(
                    path, log=lambda m: self.queue.put(("log", m))
                )
                self.queue.put(("log", f"✅ {path.name} → {result.output.name}"))
                self.queue.put(("done_one", result))
            except ConversionError as e:
                self.queue.put(("log", f"⚠️  {path.name}: {e}"))
                self.queue.put(("error_one", (path, str(e))))
            except Exception as e:  # noqa: BLE001 - surface anything unexpected
                self.queue.put(("log", f"❌ {path.name}: unexpected error — {e}"))
                self.queue.put(("error_one", (path, str(e))))
            self.queue.put(("progress", i))
        self.queue.put(("finished", None))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "log":
                    self._append_log(payload)
                elif kind == "progress":
                    self.progress["value"] = payload
                elif kind == "done_one":
                    self.results.append(payload)
                elif kind == "error_one":
                    self.errors.append(payload)
                elif kind == "finished":
                    self._build_summary()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # Screen 3 — summary / celebration
    # ------------------------------------------------------------------
    def _build_summary(self):
        self._clear()
        ok = len(self.results)
        bad = len(self.errors)

        canvas = Canvas(self.root, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        icon = "🎉" if bad == 0 else "✅"
        canvas.create_text(280, 60, text=icon, font=("SF Pro Display", 40), fill=FG)
        canvas.create_text(
            280, 110, text="All done!", font=FONT_TITLE, fill=FG
        )
        summary = f"{ok} file(s) converted"
        if bad:
            summary += f" · {bad} failed"
        canvas.create_text(280, 140, text=summary, font=FONT_SUB, fill=FG_DIM)

        y = 190
        for r in self.results[:6]:
            canvas.create_text(
                280, y, text=f"📝 {r.output.name}", font=FONT_MONO, fill=ACCENT2
            )
            y += 20
        for path, err in self.errors[:3]:
            canvas.create_text(
                280, y, text=f"⚠️ {path.name}", font=FONT_MONO, fill=DANGER
            )
            y += 20

        if bad == 0 and ok:
            self._confetti(canvas)

        open_btn = self._make_button(
            canvas, "Reveal in Finder", ACCENT, self._reveal_output, width=180
        )
        canvas.create_window(280, 340, window=open_btn)

        again_btn = self._make_button(
            canvas, "Convert More", BG_PANEL, self._build_welcome, width=180, fg=FG_DIM
        )
        canvas.create_window(280, 380, window=again_btn)

        self._play_sound("Glass" if bad == 0 else "Basso")

    def _reveal_output(self):
        target = self.results[0].output if self.results else None
        if target and sys.platform == "darwin":
            subprocess.run(["open", "-R", str(target)])
        elif target:
            messagebox.showinfo("Output location", str(target.parent))

    def _play_sound(self, name: str):
        if sys.platform != "darwin":
            return
        sound = f"/System/Library/Sounds/{name}.aiff"
        try:
            subprocess.Popen(
                ["afplay", sound],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _confetti(self, canvas: Canvas):
        colors = [ACCENT, ACCENT2, "#ffd166", "#ff5c8a", "#5cd1ff"]
        bits = []
        for _ in range(40):
            x = random.randint(0, 560)
            size = random.randint(4, 8)
            item = canvas.create_oval(
                x, -10, x + size, -10 + size,
                fill=random.choice(colors), outline="",
            )
            bits.append([item, random.uniform(2, 5), random.uniform(-1, 1)])

        def step(n=0):
            if n > 60:
                return
            for item, vy, vx in bits:
                canvas.move(item, vx, vy)
            canvas.after(30, lambda: step(n + 1))

        step()


def run_cli(paths: list[str]) -> int:
    """Headless conversion — used when file paths are passed as arguments.

    Needs no Tk, so it works anywhere the two conversion packages are
    installed, even where the GUI's Tk is broken/deprecated.
    """
    ok = bad = 0
    for raw in paths:
        path = Path(raw)
        try:
            result = convert_file(path, log=lambda m: print(f"   {m}"))
            print(f"✅ {path.name} → {result.output.name}")
            ok += 1
        except ConversionError as e:
            print(f"⚠️  {path.name}: {e}")
            bad += 1
        except Exception as e:  # noqa: BLE001 - surface anything unexpected
            print(f"❌ {path.name}: unexpected error — {e}")
            bad += 1
    print(f"\nDone: {ok} converted" + (f", {bad} failed" if bad else ""))
    return 1 if bad else 0


def run_gui():
    _load_tk()
    root = Tk()
    if sys.platform == "darwin":
        try:
            root.createcommand("::tk::mac::Quit", root.destroy)
        except Exception:
            pass
    ToMdApp(root)
    root.mainloop()


def main():
    # Any non-flag argument means "convert these files headlessly"; with no
    # arguments we fall back to the graphical picker.
    files = [a for a in sys.argv[1:] if not a.startswith("-")]
    if files:
        raise SystemExit(run_cli(files))
    run_gui()


if __name__ == "__main__":
    main()
