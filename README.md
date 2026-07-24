# ToMd 📄➜📝

A friendly macOS tool that converts `.msg` (Outlook emails) and `.pdf` files
into clean `.md` files — output lands right next to the source file.

- Native macOS "choose files" dialog, multi-select, mixes `.msg` and `.pdf`
- Animated progress bar + live log while it works
- Confetti + summary screen when it's done
- `.msg` conversion also extracts attachments into a sibling folder and
  lists each one's SHA-256 hash in the Markdown (handy if you're triaging
  suspicious emails)
- Packaged as a real `.app` — launch it from Spotlight by typing its name,
  no Terminal required after setup

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

### Graphical

Press **Cmd+Space**, type **ToMd**, hit **Enter**. Click **Choose
Files…**, select any mix of `.msg`/`.pdf` files, watch it work, then
**Reveal in Finder** to jump straight to the output.

### From the terminal (no GUI)

`build_app.sh` also installs a `ToMD` command. Run it with no arguments
to open the graphical picker, or pass files to convert them straight away
— handy for scripting, and it needs no Tk so it works even where the GUI
doesn't:

```bash
ToMD ~/Desktop/report.pdf ~/Mail/suspicious.msg
```

Each `.md` lands next to its source file; the command exits non-zero if
any file failed.

## Files in this folder

| File | Purpose |
|---|---|
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
