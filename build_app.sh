#!/usr/bin/env bash
# build_app.sh — cross-platform build dispatcher for ToMd.
#
# Detects your operating system and runs the matching packaging script:
#   macOS  -> build_macos.sh   (osascript .app + Spotlight)
#   Linux  -> build_linux.sh   (PyInstaller executable + .desktop launcher)
#
# Run from this folder:
#   chmod +x build_app.sh && ./build_app.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$(uname -s)" in
    Darwin)
        exec bash "$HERE/build_macos.sh" "$@"
        ;;
    Linux)
        exec bash "$HERE/build_linux.sh" "$@"
        ;;
    *)
        echo "❌ Unsupported OS: $(uname -s)"
        echo "   ToMd ships build scripts for macOS (build_macos.sh) and"
        echo "   Linux (build_linux.sh). On other platforms you can still run"
        echo "   the app directly:  python3 tomd_cli.py"
        exit 1
        ;;
esac
