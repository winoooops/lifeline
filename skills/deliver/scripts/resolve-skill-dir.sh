#!/usr/bin/env bash
# Resolve the deliver skill directory.
#
# Prints SKILL_DIR=<resolved path> to stdout on success. Exits 0 on success,
# 1 on failure.
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
#   _resolver_output=$(./scripts/resolve-skill-dir.sh) || { echo "skill not found" >&2; exit 1; }
#   SKILL_DIR=${_resolver_output#SKILL_DIR=}

set -euo pipefail

# ────────────────────────────────────────────────────────────────────
# DEVELOPER / TEST HELPER — NOT called at runtime by the deliver skill.
# At runtime, both pure-mode.md and paired-mode.md inline equivalent
# logic, because target repos with the installed plugin don't carry
# this script. The inline copies are the OPERATIVE versions; this
# script is for manual debugging from a lifeline checkout.
#
# When changing the sentinel filename, ordering, or .DS_Store filter,
# update ALL THREE copies (pure-mode.md, paired-mode.md, and this
# script). The mirror behavior is guarded by
# harness/test_deliver_resolver_mirrors.py — runtime correctness depends
# on the mode files, not this script.
# ────────────────────────────────────────────────────────────────────

# BEGIN RESOLVER
is_valid() {
  [ -f "$1/schemas/grader-output.json" ]
}

version_key() {
  local _major _minor _patch _rest
  IFS=. read -r _major _minor _patch _rest <<< "$1"
  case "$_major" in ""|*[!0-9]*) _major=0 ;; esac
  case "$_minor" in ""|*[!0-9]*) _minor=0 ;; esac
  case "$_patch" in ""|*[!0-9]*) _patch=0 ;; esac
  printf '%010d.%010d.%010d.%s\n' "$((10#$_major))" "$((10#$_minor))" "$((10#$_patch))" "${_rest:-}"
}

# 1. Env override.
if [ -n "${LIFELINE_SKILL_DIR:-}" ] && is_valid "$LIFELINE_SKILL_DIR"; then
  printf 'SKILL_DIR=%s\n' "$LIFELINE_SKILL_DIR"
  exit 0
fi

# 2. Plugin cache (newest-installed wins).
CACHE_ROOT="${HOME}/.claude/plugins/cache/lifeline/lifeline"
if [ -d "$CACHE_ROOT" ]; then
  # Newest-installed wins by mtime, with a zero-padded version-key
  # tiebreaker for equal mtimes. Use Bash's portable -nt check instead
  # of `sort -V` (GNU-only, missing on default macOS/BSD). Filter to
  # directories only — on macOS Finder writes `.DS_Store` with a newer
  # mtime than the version subdirs whenever the user browses the cache.
  LATEST=""
  while IFS= read -r _entry; do
    [ -d "$CACHE_ROOT/$_entry" ] || continue
    if [ -z "$LATEST" ] || [ "$CACHE_ROOT/$_entry" -nt "$CACHE_ROOT/$LATEST" ]; then
      LATEST="$_entry"
    elif [ ! "$CACHE_ROOT/$LATEST" -nt "$CACHE_ROOT/$_entry" ] \
      && [ ! "$CACHE_ROOT/$_entry" -nt "$CACHE_ROOT/$LATEST" ] \
      && [[ "$(version_key "$_entry")" > "$(version_key "$LATEST")" ]]; then
      LATEST="$_entry"
    fi
  done < <(ls -1 "$CACHE_ROOT" 2>/dev/null)
  if [ -n "$LATEST" ] && is_valid "$CACHE_ROOT/$LATEST/skills/deliver"; then
    printf 'SKILL_DIR=%s\n' "$CACHE_ROOT/$LATEST/skills/deliver"
    exit 0
  fi
fi

echo "ERROR: could not resolve lifeline skills/deliver directory." >&2
echo "  Tried: \$LIFELINE_SKILL_DIR, $CACHE_ROOT/<latest>/skills/deliver" >&2
echo "  Required sentinel: schemas/grader-output.json (plus references/*.md templates for runtime)." >&2
echo "  Set LIFELINE_SKILL_DIR or install the plugin via /plugin install lifeline." >&2
exit 1
# END RESOLVER
