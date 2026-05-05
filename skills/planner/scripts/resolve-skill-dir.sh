#!/usr/bin/env bash
# Resolve the planner skill directory across install / dev / plugin-cache contexts.
#
# Prints the resolved absolute (or repo-relative) path to stdout on success.
# Exits 0 on success, 1 on failure.
#
# Resolution order (first match wins):
#   1. $LIFELINE_SKILL_DIR — explicit override (tests, custom installs).
#   2. ./skills/planner — project-local copy (rare; mainly the lifeline repo dev path).
#   3. <git-root>/skills/planner — same idea but from a subdirectory of the repo.
#   4. ~/.claude/plugins/cache/lifeline/lifeline/<latest-version>/skills/planner —
#      the standard install location when the user runs `/plugin install`.
#
# A directory is "valid" iff it contains references/codex-prompts/ (since that's
# what every dependent script needs). Any candidate without it is skipped.
#
# Usage (sourced or invoked):
#   SKILL_DIR=$(./scripts/resolve-skill-dir.sh) || { echo "skill not found" >&2; exit 1; }
#
# This script is intentionally side-effect free — it just prints and exits.

set -euo pipefail

is_valid() {
  [ -d "${1:-}/references/codex-prompts" ]
}

# 1. Env override.
if [ -n "${LIFELINE_SKILL_DIR:-}" ] && is_valid "$LIFELINE_SKILL_DIR"; then
  printf '%s\n' "$LIFELINE_SKILL_DIR"
  exit 0
fi

# 2. Project-local.
if is_valid "skills/planner"; then
  printf '%s\n' "skills/planner"
  exit 0
fi

# 3. Git root.
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$GIT_ROOT" ] && is_valid "$GIT_ROOT/skills/planner"; then
  printf '%s\n' "$GIT_ROOT/skills/planner"
  exit 0
fi

# 4. Plugin cache (highest semver wins).
CACHE_ROOT="${HOME}/.claude/plugins/cache/lifeline/lifeline"
if [ -d "$CACHE_ROOT" ]; then
  # `ls | sort -V | tail -1` is portable across coreutils and BSD ls.
  LATEST="$(ls -1 "$CACHE_ROOT" 2>/dev/null | sort -V | tail -1 || true)"
  if [ -n "$LATEST" ] && is_valid "$CACHE_ROOT/$LATEST/skills/planner"; then
    printf '%s\n' "$CACHE_ROOT/$LATEST/skills/planner"
    exit 0
  fi
fi

echo "ERROR: could not resolve lifeline skills/planner directory." >&2
echo "  Tried: \$LIFELINE_SKILL_DIR, ./skills/planner, <git-root>/skills/planner, $CACHE_ROOT/<latest>/skills/planner" >&2
echo "  Set LIFELINE_SKILL_DIR or install the plugin via /plugin install lifeline." >&2
exit 1
