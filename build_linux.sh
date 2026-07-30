#!/usr/bin/env bash
# build_linux.sh — packages ToMd as a standalone Linux application using
# PyInstaller, then installs a desktop launcher so it shows up in your
# Applications menu (tested on elementary OS 8.1 / Ubuntu 24.04).
#
# Produces:
#   dist/ToMD                              the single self-contained executable
#   ~/.local/bin/ToMD                      the executable, on your PATH
#   ~/.local/share/applications/ToMD.desktop   the menu launcher
#
# Run from this folder:
#   chmod +x build_linux.sh && ./build_linux.sh
# (or just run ./build_app.sh, which auto-detects Linux and calls this.)
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="ToMD"
VENV="$HERE/.venv"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons"

echo "🐧 Building ${APP_NAME} for Linux ..."

# ---------------------------------------------------------------------------
# 1. Python environment — reuse an active venv if there is one, otherwise
#    create/use the project's .venv so the build is reproducible.
# ---------------------------------------------------------------------------
if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "🐍 Using already-active virtualenv: $VIRTUAL_ENV"
else
    if [ ! -d "$VENV" ]; then
        echo "🐍 Creating virtualenv at $VENV"
        python3 -m venv "$VENV"
    fi
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
fi

# ---------------------------------------------------------------------------
# 2. Dependencies (+ PyInstaller, the build tool itself).
# ---------------------------------------------------------------------------
echo "📦 Installing requirements + PyInstaller ..."
PIP_ARGS=()
# Fall back to public PyPI if a private/broken index is configured.
if ! python -m pip install --upgrade pip >/dev/null 2>&1; then
    PIP_ARGS=(--index-url https://pypi.org/simple/
              --trusted-host pypi.org --trusted-host files.pythonhosted.org)
    python -m pip install --upgrade pip "${PIP_ARGS[@]}"
fi
python -m pip install -r "$HERE/requirements.txt" "${PIP_ARGS[@]}"
python -m pip install pyinstaller "${PIP_ARGS[@]}"

# ---------------------------------------------------------------------------
# 3. Does this interpreter have Tkinter? The GUI (app_gui.py) needs it; the
#    CLI (tomd_cli.py) does not. We build either way, but tailor the launcher.
# ---------------------------------------------------------------------------
if python -c "import tkinter" >/dev/null 2>&1; then
    HAS_TK=1
    echo "🖼️  Tkinter present — GUI mode will be available."
else
    HAS_TK=0
    echo "⚠️  Tkinter not found — building CLI-only."
    echo "    For the graphical mode, install it and re-run:"
    echo "      sudo apt install python3-tk"
fi

# ---------------------------------------------------------------------------
# 4. Build a single self-contained executable with PyInstaller.
#    tomd_cli.py is the entry point: it runs the interactive CLI by default,
#    batch-converts when given file arguments, and launches the GUI with
#    --gui (importing app_gui, which is bundled below).
# ---------------------------------------------------------------------------
echo "🔨 Running PyInstaller ..."
cd "$HERE"
rm -rf build dist "${APP_NAME}.spec"

PYI_ARGS=(
    --name "$APP_NAME"
    --onefile
    --noconfirm
    --clean
    --console
    # Local modules that are imported lazily / conditionally.
    --hidden-import app_gui
    --hidden-import converter_core
    # Conversion libraries are imported inside functions; make sure their
    # code AND data files (e.g. python-docx's default template) come along.
    --collect-all extract_msg
    --collect-all fitz
    --collect-all docx
    --collect-all markdownify
    --hidden-import striprtf.striprtf
    --hidden-import bs4
)
[ "$HAS_TK" -eq 1 ] && PYI_ARGS+=(--hidden-import tkinter)

pyinstaller "${PYI_ARGS[@]}" tomd_cli.py

if [ ! -x "dist/$APP_NAME" ]; then
    echo "❌ PyInstaller did not produce dist/$APP_NAME — see output above."
    exit 1
fi
echo "✅ Built dist/$APP_NAME"

# ---------------------------------------------------------------------------
# 5. Install the executable onto PATH.
# ---------------------------------------------------------------------------
mkdir -p "$BIN_DIR"
install -m 0755 "dist/$APP_NAME" "$BIN_DIR/$APP_NAME"
echo "✅ Installed executable to $BIN_DIR/$APP_NAME"

# ---------------------------------------------------------------------------
# 6. Optional icon — used if you drop one at assets/ToMD.png (or .svg).
# ---------------------------------------------------------------------------
ICON_VALUE=""
for candidate in "$HERE/assets/ToMD.png" "$HERE/assets/ToMD.svg" "$HERE/ToMD.png"; do
    if [ -f "$candidate" ]; then
        mkdir -p "$ICON_DIR"
        cp "$candidate" "$ICON_DIR/ToMD.${candidate##*.}"
        ICON_VALUE="$ICON_DIR/ToMD.${candidate##*.}"
        echo "🎨 Installed icon from $candidate"
        break
    fi
done

# ---------------------------------------------------------------------------
# 7. Desktop launcher so ToMD appears in the Applications menu.
#    With Tkinter -> graphical (Terminal=false, --gui).
#    Without      -> interactive CLI opened in a terminal window.
# ---------------------------------------------------------------------------
mkdir -p "$APPS_DIR"
DESKTOP_FILE="$APPS_DIR/${APP_NAME}.desktop"
if [ "$HAS_TK" -eq 1 ]; then
    EXEC_LINE="$BIN_DIR/$APP_NAME --gui"
    TERMINAL_LINE="false"
else
    EXEC_LINE="$BIN_DIR/$APP_NAME"
    TERMINAL_LINE="true"
fi

{
    echo "[Desktop Entry]"
    echo "Type=Application"
    echo "Name=ToMD"
    echo "GenericName=Document to Markdown converter"
    echo "Comment=Convert documents, emails and PDFs to Markdown"
    echo "Exec=$EXEC_LINE"
    echo "Terminal=$TERMINAL_LINE"
    echo "Categories=Utility;Office;TextTools;"
    echo "Keywords=markdown;convert;pdf;docx;msg;email;"
    [ -n "$ICON_VALUE" ] && echo "Icon=$ICON_VALUE"
} > "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"
echo "✅ Installed launcher to $DESKTOP_FILE"

# Refresh the menu database (harmless if the tool isn't present).
update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# 8. Make sure ~/.local/bin is on PATH for future shells.
# ---------------------------------------------------------------------------
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;  # already there
    *)
        RCFILE="$HOME/.bashrc"
        [ -n "${ZSH_VERSION:-}" ] && RCFILE="$HOME/.zshrc"
        echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RCFILE"
        echo "ℹ️  Added $BIN_DIR to PATH in $RCFILE — run 'source $RCFILE' (or open a new terminal)."
        ;;
esac

echo ""
echo "🎉 Done. Launch ToMD any of these ways:"
echo "  • Applications menu: search for 'ToMD'"
echo "  • Terminal (interactive):  ToMD"
echo "  • Terminal (convert files): ToMD report.docx notes.pdf"
[ "$HAS_TK" -eq 1 ] && echo "  • Graphical app:           ToMD --gui"
