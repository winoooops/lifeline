#!/usr/bin/env bash
# Idempotent codex-reviewed footer update for a markdown file.
#
# Appends or replaces an HTML-comment marker:
#
#     <!-- codex-reviewed: <ISO-timestamp> -->
#
# Why HTML comment instead of YAML frontmatter: existing specs in this repo
# (and most projects) are plain Markdown headers without YAML frontmatter,
# so "append to frontmatter" isn't a safe mechanical edit. HTML comments
# render as invisible in any markdown viewer, are greppable, and don't
# conflict with heading parsers.
#
# Why ISO timestamp instead of the model name: the actual model that
# `codex exec` runs is environment-dependent (depends on auth mode + codex
# CLI version). Hardcoding a model name would lie. The timestamp is
# truthful and useful for staleness detection.
#
# Why POSIX awk + atomic mv instead of `sed -i`: GNU and BSD/macOS sed
# differ on the -i flag's semantics (BSD requires an empty backup-suffix
# arg). awk is POSIX everywhere. mv is atomic on the same filesystem.
#
# Usage:
#   ./scripts/update-footer.sh <markdown-file> [<timestamp>]
#
# If <timestamp> is omitted, defaults to `date -u +%Y-%m-%dT%H:%M:%SZ`.

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <markdown-file> [<timestamp>]" >&2
  exit 2
fi

FILE="$1"
TS="${2:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
MARKER='codex-reviewed:'

if [ ! -f "$FILE" ]; then
  echo "ERROR: file not found: $FILE" >&2
  exit 2
fi

if grep -q "<!-- $MARKER" "$FILE"; then
  # Replace existing footer line via temp-file rewrite.
  awk -v marker="$MARKER" -v ts="$TS" '
    /<!-- codex-reviewed:/ { print "<!-- " marker " " ts " -->"; next }
    { print }
  ' "$FILE" > "$FILE.tmp" && mv "$FILE.tmp" "$FILE"
else
  # Append, ensuring a blank line separates from prior content.
  if [ -n "$(tail -c1 "$FILE")" ]; then
    printf '\n' >> "$FILE"
  fi
  printf '\n<!-- %s %s -->\n' "$MARKER" "$TS" >> "$FILE"
fi
