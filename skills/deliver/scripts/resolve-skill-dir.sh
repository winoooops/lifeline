#!/usr/bin/env bash
# Resolve the deliver skill directory across install / dev / plugin-cache contexts.
# Adapted from skills/planner/scripts/resolve-skill-dir.sh.
#
# Prints the resolved path to stdout on success. Exits 0 on success, 1 on failure.
#
# Resolution order (first match wins):
#   1. $LIFELINE_SKILL_DIR — explicit override (tests, custom installs).
#   2. ./skills/deliver — project-local copy (lifeline repo dev path).
#   3. <git-root>/skills/deliver — same idea but from a subdirectory of the repo.
#   4. ~/.claude/plugins/cache/lifeline/lifeline/<latest>/skills/deliver —
#      the standard install location.
#
# A directory is "valid" iff it contains schemas/grader-output.json.
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

# 2. Project-local.
if is_valid "skills/deliver"; then
  printf '%s\n' "skills/deliver"
  exit 0
fi

# 3. Git root.
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$GIT_ROOT" ] && is_valid "$GIT_ROOT/skills/deliver"; then
  printf '%s\n' "$GIT_ROOT/skills/deliver"
  exit 0
fi

# 4. Plugin cache (highest semver wins).
CACHE_ROOT="${HOME}/.claude/plugins/cache/lifeline/lifeline"
if [ -d "$CACHE_ROOT" ]; then
  LATEST="$(ls -1 "$CACHE_ROOT" 2>/dev/null | sort -V | tail -1 || true)"
  if [ -n "$LATEST" ] && is_valid "$CACHE_ROOT/$LATEST/skills/deliver"; then
    printf '%s\n' "$CACHE_ROOT/$LATEST/skills/deliver"
    exit 0
  fi
fi

echo "ERROR: could not resolve lifeline skills/deliver directory." >&2
echo "  Tried: \$LIFELINE_SKILL_DIR, ./skills/deliver, <git-root>/skills/deliver, $CACHE_ROOT/<latest>/skills/deliver" >&2
echo "  Set LIFELINE_SKILL_DIR or install the plugin via /plugin install lifeline." >&2
exit 1
