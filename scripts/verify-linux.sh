#!/usr/bin/env bash
# Everything about a Linux desktop that can be checked without a human looking.
#
# Run this on the machine you intend to certify, then work through the L column
# of MANUAL_TEST.md for the rest. The split matters: this script can prove the
# paths, the IPC socket, the autostart entry and the fallbacks, but it cannot
# tell you whether the tray icon is legible or the toast landed in the right
# corner. It also cannot substitute for running under both GNOME and KDE.
#
#   ./scripts/verify-linux.sh            # report to stdout and a log file
#   ./scripts/verify-linux.sh --gui      # also launch the GUI and leave it up
set -uo pipefail

cd "$(dirname "$0")/.."
LOG="verify-linux-$(date +%Y%m%d-%H%M%S).log"
LAUNCH_GUI=0
[ "${1:-}" = "--gui" ] && LAUNCH_GUI=1

exec > >(tee "$LOG") 2>&1

FAILED=0
section() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
ok()      { printf '  \033[32mok\033[0m    %s\n' "$1"; }
bad()     { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILED=$((FAILED + 1)); }
note()    { printf '  ...   %s\n' "$1"; }

section "Session"
note "distro       $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || echo unknown)"
note "arch         $(uname -m)"
note "session type ${XDG_SESSION_TYPE:-<unset>}"
note "desktop      ${XDG_CURRENT_DESKTOP:-<unset>}"
note "wayland      ${WAYLAND_DISPLAY:-<unset>}"
note "display      ${DISPLAY:-<unset>}"
note "runtime dir  ${XDG_RUNTIME_DIR:-<unset>}"
case "${XDG_CURRENT_DESKTOP:-}" in
    *GNOME*) note "GNOME needs the AppIndicator extension for any tray at all (checklist item 31)";;
    *KDE*)   note "KDE hosts the tray natively (checklist item 31)";;
esac

section "Qt runtime libraries"
# PySide6 links these even headless; a missing one fails at import, not at draw.
MISSING=""
for lib in libEGL.so.1 libGL.so.1 libxkbcommon.so.0 libdbus-1.so.3 \
           libfontconfig.so.1 libglib-2.0.so.0 libxcb-cursor.so.0; do
    ldconfig -p 2>/dev/null | grep -q "$lib" || MISSING="$MISSING $lib"
done
if [ -n "$MISSING" ]; then
    bad "missing:$MISSING"
    note "sudo apt install -y libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 libglib2.0-0 libxcb-cursor0"
else
    ok "all present"
fi

section "Korean glyph coverage"
# The font stack ends in Noto/DejaVu; stock Ubuntu ships no CJK, so item 17
# fails with tofu unless fonts-noto-cjk is installed.
if fc-list :lang=ko 2>/dev/null | grep -q .; then
    ok "a Korean-capable font is installed ($(fc-list :lang=ko 2>/dev/null | wc -l) faces)"
else
    bad "no font covers Korean - MANUAL_TEST item 17 will show tofu"
    note "sudo apt install -y fonts-noto-cjk"
fi

section "Test suite"
if uv run pytest -q; then ok "pytest"; else bad "pytest"; fi

section "Paths"
uv run tokentray config path
RUNTIME=$(uv run python -c "from tokentray.core import paths; print(paths.runtime_dir())")
note "runtime      $RUNTIME"
case "$RUNTIME" in
    /run/user/*|"${XDG_RUNTIME_DIR:-/nonexistent}"*)
        ok "socket lives in the XDG runtime dir, not the cache" ;;
    *)
        bad "runtime dir is '$RUNTIME'; a cache cleaner deleting the socket reads as 'not running'" ;;
esac

section "Diagnostics"
uv run tokentray doctor || bad "doctor exited non-zero"

section "Secret store without a session bus (checklist item 30)"
env -u DBUS_SESSION_BUS_ADDRESS uv run tokentray doctor 2>&1 | grep -i "secret backend" \
    || bad "doctor gave no secret backend line without DBus"

section "Autostart round trip"
ENTRY="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/tokentray.desktop"
WAS_ENABLED=0
[ -f "$ENTRY" ] && WAS_ENABLED=1 && note "an entry already existed; it will be restored"
[ "$WAS_ENABLED" = 1 ] && cp "$ENTRY" "$ENTRY.verify-backup"

uv run tokentray autostart enable >/dev/null
if [ -f "$ENTRY" ]; then
    ok "wrote $ENTRY"
    sed 's/^/        /' "$ENTRY"
    grep -q "^Icon=" "$ENTRY" || bad "no Icon= line; GNOME will show a placeholder"
    grep -q "X-GNOME-Autostart-Delay" "$ENTRY" || bad "no startup delay; the tray host may not be up yet"
else
    bad "autostart enable wrote nothing"
fi
uv run tokentray autostart disable >/dev/null
[ -f "$ENTRY" ] && bad "disable left the entry behind" || ok "disable removed it"
if [ "$WAS_ENABLED" = 1 ]; then
    mv "$ENTRY.verify-backup" "$ENTRY"
    note "restored the pre-existing entry"
fi

section "Desktop integration"
if [ -x packaging/linux/install.sh ]; then
    ok "install.sh present"
    command -v desktop-file-validate >/dev/null 2>&1 \
        && { desktop-file-validate packaging/linux/*.desktop && ok "desktop entry validates"; } \
        || note "desktop-file-validate not installed (apt install desktop-file-utils)"
else
    bad "packaging/linux/install.sh missing"
fi

section "XWayland selection (checklist items 28-29)"
uv run python - <<'PY'
import os, sys
sys.path.insert(0, "src")
os.environ.pop("QT_QPA_PLATFORM", None)
from tokentray.app import _select_platform_plugin
from tokentray.core.config import Config
_select_platform_plugin(Config({}))
chosen = os.environ.get("QT_QPA_PLATFORM", "<unset: Qt picks its own>")
print(f"  ...   with this session, tokentray would use: {chosen}")
if os.environ.get("WAYLAND_DISPLAY") and chosen != "xcb":
    print("  ...   Wayland session but not redirected - toasts may be misplaced (item 29 territory)")
PY

if [ "$LAUNCH_GUI" = 1 ]; then
    section "GUI"
    note "launching; work through MANUAL_TEST.md items 1-17, 21, 23 and 28-31 by eye"
    uv run tokentray-gui &
    sleep 5
    if uv run tokentray status 2>&1 | grep -q "from the running app"; then
        ok "IPC reaches the running instance (item 19)"
    else
        bad "no answer from the running instance - the socket path may be unusable"
    fi
    note "quit from the tray menu when done, or: uv run tokentray stop"
fi

section "Result"
if [ "$FAILED" = 0 ]; then
    ok "every automated check passed"
else
    bad "$FAILED automated check(s) failed"
fi
cat <<'TXT'

  Still needs a human, on BOTH GNOME and KDE:
    MANUAL_TEST.md items 1-17 (tray, toasts, appearance), 21 (log out and back
    in), 23 (quit), and the Linux section items 28-31.
TXT
echo "  log: $LOG"
exit "$FAILED"
