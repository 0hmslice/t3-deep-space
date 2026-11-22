#!/bin/sh
# Install the Deep Space theme for T3 Code.
#   curl -fsSL https://raw.githubusercontent.com/0hmslice/t3-deep-space/main/install.sh | sh
# or, from a clone of this repo:  sh install.sh
# Set T3_THEMES_DIR to install somewhere other than ~/.t3/userdata/themes.
set -eu

RAW=https://raw.githubusercontent.com/0hmslice/t3-deep-space/main/themes
DEST=${T3_THEMES_DIR:-$HOME/.t3/userdata/themes}
HERE=""
case "$0" in *install.sh) HERE=$(cd "$(dirname "$0")" && pwd) ;; esac

mkdir -p "$DEST"
for f in deep-space.json deep-space.webp; do
  if [ -n "$HERE" ] && [ -f "$HERE/themes/$f" ]; then
    cp "$HERE/themes/$f" "$DEST/$f.tmp"
  else
    curl -fsSL "$RAW/$f" -o "$DEST/$f.tmp"
  fi
  if [ -f "$DEST/$f" ] && ! cmp -s "$DEST/$f.tmp" "$DEST/$f"; then
    cp "$DEST/$f" "$DEST/$f.previous"   # keep the old copy, in case it had local edits
    echo "Saved your previous $f as $f.previous"
  fi
  mv "$DEST/$f.tmp" "$DEST/$f"
done

# Sanity check: the theme file must be JSON with the right name.
grep -q '"name": "Deep Space"' "$DEST/deep-space.json" || { echo "deep-space.json looks wrong" >&2; exit 1; }

echo "Installed Deep Space to $DEST"
echo "Next: select Deep Space in T3 Code's theme settings, or have your agent call t3_theme_set."
echo "If it was already selected, switch to another theme and back to load the new version."
