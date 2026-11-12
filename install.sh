#!/bin/sh
# Make the "academy" skill available to Claude Code on this computer.
# It links (not copies) the skill, so pulling a newer kit updates it.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
DEST="$HOME/.claude/skills"
mkdir -p "$DEST"
if [ -e "$DEST/academy" ] && [ ! -L "$DEST/academy" ]; then
  echo "$DEST/academy already exists and is not a link. Move it away first." >&2
  exit 1
fi
ln -sfn "$HERE/skills/academy" "$DEST/academy"
echo "Linked $DEST/academy -> $HERE/skills/academy"
echo "Start a new Claude Code session and ask: \"make an academy from the docs in <folder>\""
