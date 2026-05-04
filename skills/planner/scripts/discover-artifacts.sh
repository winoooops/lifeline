#!/usr/bin/env bash
# Fallback artifact discovery for /lifeline:planner.
#
# Normal flow: planner captures SPEC_FILE when it writes the spec — no
# discovery needed. This script is invoked ONLY when SPEC_FILE was lost
# (user went off-script, planner was resumed without state).
#
# Combined committed + unstaged + untracked scan against a baseline SHA.
# Returns ALL candidate .md files (caller filters by /specs?/ + design.md
# heuristic and prompts the user when ambiguous).
#
# Usage:
#   ./scripts/discover-artifacts.sh <baseline-sha>

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <baseline-sha>" >&2
  exit 2
fi

START_SHA="$1"

# Combined scan:
#   1. Files added or modified in commits since the baseline
#   2. Files currently unstaged in the working tree
#   3. Untracked but not gitignored files
# The union catches: standard-path spec, custom-path spec, unstaged-only
# spec, modified-existing-file spec, untracked-not-yet-committed spec.
{
  git diff --name-only "$START_SHA..HEAD"
  git diff --name-only
  git ls-files --others --exclude-standard
} | sort -u | grep -E '\.md$' || true
