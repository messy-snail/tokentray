#!/usr/bin/env sh
# Register tokentray with the desktop: an application entry so it appears in the
# launcher, and hicolor icons so it has a face there and under Wayland, where a
# compositor identifies a window only by its desktop file name.
#
# Per-user and reversible - no root, no package manager. Pass --uninstall to undo.
# Runs both from a release tarball and from a git checkout.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
APP_ID=io.github.messy-snail.tokentray
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
SIZES="16 24 32 48 64 128 256 512"

refresh_caches() {
    # Best effort: some desktops notice on their own, others need the nudge.
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPS" || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f "$ICONS" || true
    fi
}

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$APPS/$APP_ID.desktop"
    for size in $SIZES; do
        rm -f "$ICONS/${size}x${size}/apps/$APP_ID.png"
    done
    refresh_caches
    echo "removed $APP_ID"
    exit 0
fi

# Tarball layout puts the PNGs beside this script; the checkout keeps them one
# level up in packaging/resources.
if [ -d "$HERE/resources" ]; then
    RESOURCES="$HERE/resources"
else
    RESOURCES="$HERE/../resources"
fi
[ -f "$RESOURCES/tokentray-256.png" ] || {
    echo "icon assets not found next to $0" >&2
    exit 1
}

# A tarball is unpacked wherever the user likes, so `tokentray-gui` is not on
# PATH; point Exec at the shipped binary when there is one.
EXEC=tokentray-gui
for candidate in "$HERE/tokentray/tokentray-gui" "$HERE/../tokentray/tokentray-gui"; do
    if [ -x "$candidate" ]; then
        EXEC=$(cd "$(dirname "$candidate")" && pwd)/tokentray-gui
        break
    fi
done

mkdir -p "$APPS"
sed "s|^Exec=.*|Exec=$EXEC|" "$HERE/$APP_ID.desktop" > "$APPS/$APP_ID.desktop"
for size in $SIZES; do
    mkdir -p "$ICONS/${size}x${size}/apps"
    cp "$RESOURCES/tokentray-$size.png" "$ICONS/${size}x${size}/apps/$APP_ID.png"
done
refresh_caches
echo "installed $APP_ID"
echo "  entry  $APPS/$APP_ID.desktop"
echo "  exec   $EXEC"
