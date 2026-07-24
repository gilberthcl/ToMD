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

1. Install the two Python packages this uses:

   ```bash
   pip3 install -r requirements.txt
   ```

2. Build the app (turns these files into `ToMd.app` and installs it to
   `~/Applications`):

   ```bash
   chmod +x build_app.sh
   ./build_app.sh
   ```

3. First launch: macOS will likely warn that the app is from an
   unidentified developer (it's unsigned, since it's your own local build).
   Right-click `ToMd.app` in `~/Applications` → **Open** → **Open**
   once, to approve it. After that, Spotlight launches it normally.

## Everyday use

`build_app.sh` installs a `ToMD` terminal command. It has three modes:

### 1. Interactive (default)

Just run it with no arguments:

```bash
ToMD
```

You get the full guided experience — a welcome animation, a menu to pick
which file type you're converting (`.msg`, `.pdf`, or both), the **native
macOS "choose files" dialog**, an animated per-file conversion, a summary
report, and then a prompt to convert more or quit. It loops until you
choose to leave. No GUI framework involved (pure terminal + Finder
dialog), so it always works. Each `.md` lands right next to its source.

### 2. Convert specific files (scripting)

Pass paths directly and it runs non-interactively, printing a report:

```bash
ToMD ~/Desktop/report.pdf ~/Mail/suspicious.msg
```

Each `.md` is written next to its source; the command exits non-zero if
any file failed — handy in shell pipelines.

### 3. Full graphical app

There's also a Tkinter app with a progress bar and confetti. Launch
`ToMd.app` from Spotlight, or:

```bash
python3 app_gui.py --gui
```

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
| `build_app.sh` | Packages the above into a double-clickable / Spotlight-launchable `.app` |
| `requirements.txt` | The two pip packages needed: `extract-msg`, `pymupdf` |

## Re-building after an edit

If you tweak `app_gui.py` or `converter_core.py`, just re-run
`./build_app.sh` — it copies the latest files into the app bundle.

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
