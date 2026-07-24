#!/bin/bash
# build_app.sh — packages ToMd as a real macOS Application so you can
# launch it from Spotlight (Cmd+Space, type "ToMd", hit Enter) instead
# of ever touching Terminal or "running the .py script" again.
#
# Run this ONCE on your Mac, from this folder:
#   chmod +x build_app.sh && ./build_app.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="ToMd"
BUILD_DIR="$HERE/build"
APP_PATH="$BUILD_DIR/${APP_NAME}.app"
DEST="$HOME/Applications"

echo "🔧 Building ${APP_NAME}.app ..."
mkdir -p "$BUILD_DIR"
rm -rf "$APP_PATH"

# 1. Compile a tiny AppleScript launcher into an .app bundle.
#    It finds its own location at runtime and runs the bundled python files
#    from there, so the app is fully self-contained and relocatable.
cat > "$BUILD_DIR/launcher.applescript" <<'APPLESCRIPT'
on run
    set appPosixPath to POSIX path of (path to me)
    set scriptPath to appPosixPath & "Contents/Resources/app_gui.py"
    try
        do shell script "/usr/bin/env python3 " & quoted form of scriptPath
    on error errMsg number errNum
        if errNum is not -128 then
            display alert "ToMd hit a snag" message errMsg
        end if
    end try
end run
APPLESCRIPT

osacompile -o "$APP_PATH" "$BUILD_DIR/launcher.applescript"

# 2. Drop the real python source into Contents/Resources so the launcher
#    can find it, and Spotlight sees one tidy .app.
cp "$HERE/app_gui.py" "$APP_PATH/Contents/Resources/"
cp "$HERE/converter_core.py" "$APP_PATH/Contents/Resources/"

# 3. Make it a background-only app (no Dock icon needed since it's a
#    quick utility) — optional, comment out if you'd rather see it in the Dock.
PLIST="$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleName string ${APP_NAME}" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string ${APP_NAME}" "$PLIST" 2>/dev/null || true

# 4. Install into ~/Applications so Spotlight indexes it immediately.
mkdir -p "$DEST"
rm -rf "$DEST/${APP_NAME}.app"
cp -R "$APP_PATH" "$DEST/"

echo "✅ Installed to $DEST/${APP_NAME}.app"
echo ""
echo "Give Spotlight a moment to index it, then press Cmd+Space, type"
echo "'ToMd', and hit Enter — no Terminal, no 'python3 script.py'."
