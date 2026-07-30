# ToMd 📄➜📝

A friendly macOS tool that converts documents, emails, and PDFs into clean
`.md` files — output lands right next to the source file.

- Converts many written formats to Markdown (see the table below)
- Native macOS "choose files" dialog, multi-select, mixes any supported types
- Animated interactive terminal app: welcome screen, menu, live conversion,
  report, and a convert-more/quit loop
- `.msg` conversion also extracts attachments into a sibling folder and
  lists each one's SHA-256 hash in the Markdown (handy if you're triaging
  suspicious emails)
- Packaged as a real `.app` — launch it from Spotlight by typing its name,
  no Terminal required after setup

## Supported formats

| Input | Engine | Notes |
|---|---|---|
| `.msg` | extract-msg | Body + attachment SHA-256 table |
| `.pdf` | PyMuPDF | One section per page (text, not OCR) |
| `.docx` | python-docx | Headings, lists, tables, bold/italic |
| `.rtf` | striprtf | Plain text |
| `.html` / `.htm` | markdownify | HTML → Markdown |
| `.txt` / `.log` | built-in | Passed through |
| `.odt`, `.doc`, `.epub`, `.tex`, … | pandoc *(optional)* | Only if the `pandoc` binary is installed |

Each format's library is loaded only when needed, so a missing one just
skips that format with an install hint — it never breaks the app.

## One-time setup

The build system is cross-platform. `build_app.sh` detects your OS and runs
the right packager — `build_macos.sh` on macOS, `build_linux.sh` on Linux.

```bash
chmod +x build_app.sh
./build_app.sh
```

### macOS

`build_macos.sh` installs the Python packages' companion, builds `ToMd.app`
with `osacompile`, and installs it to `~/Applications` plus a `ToMD`
terminal command. Install the Python deps first:

```bash
pip3 install -r requirements.txt
```

First launch: macOS will likely warn that the app is from an unidentified
developer (it's unsigned). Right-click `ToMd.app` in `~/Applications` →
**Open** → **Open** once to approve it; after that Spotlight launches it
normally.

### Linux (Ubuntu 24.04 / elementary OS, etc.)

`build_linux.sh` uses **PyInstaller** to produce a single self-contained
executable, then installs a desktop launcher. It will:

1. create/reuse a `.venv` and install `requirements.txt` + PyInstaller,
2. build `dist/ToMD` (one file, no loose Python sources needed),
3. install the executable to `~/.local/bin/ToMD`,
4. install `~/.local/share/applications/ToMD.desktop` so ToMD appears in
   your Applications menu,
5. use an icon from `assets/ToMD.png` (or `.svg`) if you provide one.

For the graphical mode you also need Tkinter — the script detects this and,
if it's missing, builds the CLI-only launcher and tells you to install it:

```bash
sudo apt install python3-tk
```

The interactive picker uses **zenity** (or **kdialog**) for a native file
dialog; install `zenity` if you don't have it (`sudo apt install zenity`).
Without either, it falls back to typing paths.

## Everyday use

`build_app.sh` installs a `ToMD` terminal command. It has three modes:

### 1. Interactive (default)

Just run it with no arguments:

```bash
ToMD
```

You get the full guided experience — a welcome animation, a menu to pick
which file type you're converting, a **native "choose files" dialog**
(Finder on macOS, zenity/kdialog on Linux), an animated per-file
conversion, a summary report, and then a prompt to convert more or quit.
It loops until you choose to leave. No GUI framework involved (pure
terminal + the OS file dialog), so it always works. Each `.md` lands right
next to its source.

### 2. Convert specific files (scripting)

Pass paths directly and it runs non-interactively, printing a report:

```bash
ToMD ~/Desktop/report.pdf ~/Mail/suspicious.msg
```

Each `.md` is written next to its source; the command exits non-zero if
any file failed — handy in shell pipelines.

### 3. Full graphical app

There's also a Tkinter app with a progress bar and confetti:

```bash
ToMD --gui
```

On macOS you can also launch `ToMd.app` from Spotlight; on Linux the
Applications-menu entry launches this graphical mode when Tkinter is
available.

> The graphical app uses Tkinter. macOS's *system* Tk is deprecated and
> renders a blank window on some setups; if that happens, install a Python
> built against modern Tk (`brew install python-tk@3.12`) and rebuild the
> venv. Modes 1 and 2 don't have this dependency, so they're the
> recommended way to use ToMd.

## Files in this folder

| File | Purpose |
|---|---|
| `tomd_cli.py` | The interactive terminal app (what `ToMD` runs) — animated menu, picker, report loop |
| `app_gui.py` | The GUI app (Tkinter) — picker, progress, summary screens |
| `converter_core.py` | Conversion logic, no GUI code — reusable/testable on its own |
| `build_app.sh` | Cross-platform build dispatcher — detects the OS and runs the right script |
| `build_macos.sh` | macOS packaging — `osacompile` `.app` + Spotlight/terminal launchers |
| `build_linux.sh` | Linux packaging — PyInstaller executable + `.desktop` launcher |
| `requirements.txt` | Conversion dependencies (see the top of the file) |

## Re-building after an edit

If you tweak any of the `.py` files, just re-run `./build_app.sh` — on macOS
it copies the latest sources into the app bundle; on Linux it rebuilds the
PyInstaller executable and reinstalls it.

## Troubleshooting

- **"python3: command not found" alert on launch** — install Xcode Command
  Line Tools (`xcode-select --install`) or make sure `python3` is on your
  `PATH`.
- **Nothing happens when picking a .msg and it errors** — run
  `pip3 install -r requirements.txt` again; the app uses your system
  `python3`, so packages need to be installed there (not in a venv the
  app can't see).
- **Scanned PDFs produce empty pages** — that's expected; this does text
  extraction, not OCR. Say the word if you'd like an OCR fallback added.
