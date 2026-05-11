#!/usr/bin/env bash
# Resolve the deliver skill directory.
#
# Prints the resolved path to stdout on success. Exits 0 on success, 1 on failure.
#
# Resolution order (first match wins):
#   1. $LIFELINE_SKILL_DIR — explicit override (lifeline-dev workflow, tests).
#   2. ~/.claude/plugins/cache/lifeline/lifeline/<latest>/skills/deliver —
#      the standard plugin install location.
#
# A directory is "valid" iff it contains schemas/grader-output.json.
#
# **Workspace lookup is intentionally absent.** An earlier version of this
# script also tried ./skills/deliver and <git-root>/skills/deliver gated
# on a `_is_lifeline_repo()` check (grep `"name": "lifeline"` in
# .claude-plugin/plugin.json). That check is trivially bypassable — any
# adversarial target repo can drop a 1-line plugin.json with the sentinel
# string and then control grader-prompt.md / grader-output.json, biasing
# every paired-mode verdict to `complete: true` silently. The inline
# resolution code in pure-mode.md and paired-mode.md was already updated
# to drop workspace lookup for the same reason; this script now matches
# that posture for consistency.
#
# Lifeline developers working on the deliver skill set
# `LIFELINE_SKILL_DIR=$(pwd)/skills/deliver` to opt explicitly into a
# working-tree copy.
#
# Usage:
#   SKILL_DIR=$(./scripts/resolve-skill-dir.sh) || { echo "skill not found" >&2; exit 1; }

set -euo pipefail

is_valid() {
  [ -f "${1:-}/schemas/grader-output.json" ]
}

# 1. Env override.
if [ -n "${LIFELINE_SKILL_DIR:-}" ] && is_valid "$LIFELINE_SKILL_DIR"; then
  printf '%s\n' "$LIFELINE_SKILL_DIR"
  exit 0
fi

# 2. Plugin cache (newest-installed wins).
CACHE_ROOT="${HOME}/.claude/plugins/cache/lifeline/lifeline"
if [ -d "$CACHE_ROOT" ]; then
  # Use mtime (`ls -1t`) instead of `sort -V` (GNU-only, missing on
  # default macOS/BSD). `/plugin install` writes a new directory each
  # time, so mtime ordering matches install recency for the typical
  # one-or-two-cached-versions case.
  LATEST="$(ls -1t "$CACHE_ROOT" 2>/dev/null | head -1 || true)"
  if [ -n "$LATEST" ] && is_valid "$CACHE_ROOT/$LATEST/skills/deliver"; then
    printf '%s\n' "$CACHE_ROOT/$LATEST/skills/deliver"
    exit 0
  fi
fi

echo "ERROR: could not resolve lifeline skills/deliver directory." >&2
echo "  Tried: \$LIFELINE_SKILL_DIR, $CACHE_ROOT/<latest>/skills/deliver" >&2
echo "  Set LIFELINE_SKILL_DIR or install the plugin via /plugin install lifeline." >&2
exit 1
