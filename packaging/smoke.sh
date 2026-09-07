#!/usr/bin/env bash
# What a packaged build must be able to do before anyone downloads it.
#
# Shared by the CI bundle job and the release workflow so the two cannot drift.
# Every check here is one that has actually been wrong: the CLI missing from the
# non-Windows bundles, and `--version` on the GUI binary starting an event loop
# instead of answering, which hung the release job rather than failing it.
set -euo pipefail

# `timeout` is coreutils and is absent from a stock macOS runner, so cap the wait
# by hand. A cap turns "it hangs" into a failed job instead of a six-hour one.
run_capped() {
    local limit=$1
    shift
    "$@" &
    local pid=$! waited=0
    while kill -0 "$pid" 2>/dev/null; do
        if [ "$waited" -ge "$limit" ]; then
            kill -9 "$pid" 2>/dev/null || true
            echo "timed out after ${limit}s: $*" >&2
            return 124
        fi
        sleep 1
        waited=$((waited + 1))
    done
    wait "$pid"
}

case "${RUNNER_OS:-$(uname -s)}" in
    Windows | MINGW* | MSYS* | CYGWIN*)
        GUI=./dist/tokentray/tokentray-gui.exe
        CLI=./dist/tokentray/tokentray.exe
        ;;
    *)
        GUI=./dist/tokentray/tokentray-gui
        CLI=./dist/tokentray/tokentray
        ;;
esac

echo "== both executables are present =="
test -x "$GUI" || { echo "missing GUI binary: $GUI" >&2; exit 1; }
test -x "$CLI" || { echo "missing CLI binary: $CLI" >&2; exit 1; }

echo "== the GUI binary answers --version instead of starting a loop =="
run_capped 60 "$GUI" --version

echo "== the CLI works =="
run_capped 60 "$CLI" --version
run_capped 60 "$CLI" config path >/dev/null

if [ -d dist/tokentray.app ]; then
    APP=dist/tokentray.app/Contents/MacOS
    PLIST=dist/tokentray.app/Contents/Info.plist
    echo "== the .app is complete =="
    test -x "$APP/tokentray-gui" || { echo "app bundle has no GUI binary" >&2; exit 1; }
    test -x "$APP/tokentray" || { echo "app bundle has no CLI binary" >&2; exit 1; }
    test -f dist/tokentray.app/Contents/Resources/tokentray.icns \
        || { echo "app bundle has no icon" >&2; exit 1; }

    # An .app whose executable is the CLI would sit there doing nothing when
    # double-clicked; PyInstaller picks it from a sorted TOC, so it can drift.
    executable=$(plutil -extract CFBundleExecutable raw "$PLIST")
    [ "$executable" = "tokentray-gui" ] \
        || { echo "CFBundleExecutable is '$executable', expected tokentray-gui" >&2; exit 1; }

    # LSBackgroundOnly would leave the app unable to show its panel at all.
    if plutil -extract LSBackgroundOnly raw "$PLIST" >/dev/null 2>&1; then
        echo "Info.plist sets LSBackgroundOnly; the app could not show a window" >&2
        exit 1
    fi

    run_capped 60 "$APP/tokentray-gui" --version
    run_capped 60 "$APP/tokentray" --version
fi

echo "smoke OK"
