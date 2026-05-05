#!/usr/bin/env bash
# Codex-review hook for /lifeline:planner.
#
# Invokes `codex exec` against a doc-under-review (e.g. a freshly-written
# design spec) using a hook-specific prompt template. Captures the codex
# review markdown to a result file the caller reads back.
#
# Usage:
#   ./scripts/codex-review.sh <hook> <artifact-path> [<scratch-dir>]
#
# Arguments:
#   hook           — one of:
#                      spec-complete    — full spec, end-of-methodology pass.
#                      section-partial  — partial spec, per-section iteration.
#                    Selects the prompt template under references/codex-prompts/.
#   artifact-path  — path to the markdown file under review.
#   scratch-dir    — optional; default ".lifeline-planner". The skill's
#                    .git/info/exclude bootstrap is run against this dir.
#
# Outputs:
#   <scratch-dir>/<hook>-prompt.md    — composed prompt (template + deferrals + artifact)
#   <scratch-dir>/<hook>-review.md    — codex's review markdown (THE result)
#   <scratch-dir>/<hook>-events.log   — codex stdout (event-stream noise)
#   <scratch-dir>/<hook>-stderr.log   — codex stderr
#
# Environment overrides:
#   LIFELINE_CODEX_TIMEOUT  — seconds; default 300. Tests use a small value
#                             (e.g. 1) to force the timeout path.
#   LIFELINE_SKILL_DIR      — explicit path to the planner skill directory.
#                             See resolve-skill-dir.sh for the resolution order.
#   LIFELINE_DEFERRALS_FILE — path to a markdown bullet list of items the
#                             agent has deferred to later sections. Injected
#                             into the prompt via the {{DEFERRALS}} placeholder
#                             so codex stops re-flagging tracked items.
#                             Default: <scratch-dir>/deferrals.md (if present).
#   LIFELINE_CODEX_MODEL    — optional codex model name. When set, this script
#                             passes `--model <name>` to `codex exec`. When
#                             unset (the default), no `--model` flag is added —
#                             codex picks its auth-mode-appropriate default.
#                             Set this only when running on API-key auth, since
#                             ChatGPT-account auth rejects explicit `--model`
#                             selection. Mirrors the policy in harness/review.py
#                             and skills/upsource-review/scripts/verify.sh.
#
# Exit codes:
#   0    — codex returned non-empty review at <hook>-review.md (FULL path).
#   124  — GNU `timeout` fired (DEGRADED path → caller proceeds without footer).
#   *    — any other non-zero. DEGRADED path. Re-routes the
#          exit-0-without-output edge case (codex exits 0 but writes nothing)
#          to a non-zero exit so the caller doesn't false-pass.
#
# Important codex flag notes:
#   - Prompt is passed positionally via `-- "$PROMPT_BODY"` (NOT --prompt-file,
#     which does not exist).
#   - --output-last-message FILE captures the final assistant message (NOT
#     --output-format json, which does not exist).
#   - --model is passed ONLY when LIFELINE_CODEX_MODEL is set. The default is
#     to omit it so codex picks the auth-mode-correct default. ChatGPT-account
#     auth rejects explicit model selection; pinning a model only works on
#     API-key auth.
#   - --sandbox read-only: codex is reviewing, not modifying.
#   - External `timeout` wrapper: codex exec has no built-in timeout flag.
#   - </dev/null on every invocation: codex has been observed to hang waiting
#     on stdin in some agent-runner contexts; closing stdin prevents that.

set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <hook> <artifact-path> [<scratch-dir>]" >&2
  exit 2
fi

HOOK="$1"
ARTIFACT_PATH="$2"
SCRATCH_DIR="${3:-.lifeline-planner}"

if [ ! -f "$ARTIFACT_PATH" ]; then
  echo "ERROR: artifact not found: $ARTIFACT_PATH" >&2
  exit 2
fi

# Resolve the skill directory via the shared helper. Sibling-relative path
# works because this script lives in $SKILL_DIR/scripts/.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOLVER="$SCRIPT_DIR/resolve-skill-dir.sh"
if [ ! -x "$RESOLVER" ]; then
  echo "ERROR: missing or non-executable resolve-skill-dir.sh at $RESOLVER" >&2
  exit 2
fi

SKILL_DIR="$("$RESOLVER")" || {
  # Resolver already printed a helpful message to stderr; just propagate.
  exit 2
}

TEMPLATE="$SKILL_DIR/references/codex-prompts/${HOOK}.md"
if [ ! -f "$TEMPLATE" ]; then
  echo "ERROR: no prompt template for hook '$HOOK' at $TEMPLATE" >&2
  echo "  Available hooks:" >&2
  ls -1 "$SKILL_DIR/references/codex-prompts/" 2>/dev/null | sed 's/\.md$//; s/^/    /' >&2 || true
  exit 2
fi

# Self-bootstrap the scratch dir's git exclusion (idempotent).
ensure_excluded() {
  local pattern="$1"
  local excludes
  excludes="$(git rev-parse --git-path info/exclude 2>/dev/null)" || return 0
  [ -f "$excludes" ] || return 0
  grep -qxF "$pattern" "$excludes" || printf '%s\n' "$pattern" >> "$excludes"
}
ensure_excluded "${SCRATCH_DIR}/"

mkdir -p "$SCRATCH_DIR"

PROMPT_FILE="${SCRATCH_DIR}/${HOOK}-prompt.md"
RESULT_MD="${SCRATCH_DIR}/${HOOK}-review.md"
EVENTS_LOG="${SCRATCH_DIR}/${HOOK}-events.log"
STDERR_LOG="${SCRATCH_DIR}/${HOOK}-stderr.log"

# Resolve deferrals content.
# Precedence: explicit env var > scratch-dir/deferrals.md > "(none)".
DEFERRALS_FILE="${LIFELINE_DEFERRALS_FILE:-${SCRATCH_DIR}/deferrals.md}"
if [ -f "$DEFERRALS_FILE" ] && [ -s "$DEFERRALS_FILE" ]; then
  DEFERRALS_CONTENT="$(cat "$DEFERRALS_FILE")"
else
  DEFERRALS_CONTENT="(none)"
fi

# Compose the prompt: template (with {{DEFERRALS}} substituted) + the artifact.
# We use awk for the substitution rather than sed because the deferrals
# content can contain arbitrary characters (slashes, backslashes, etc.).
{
  awk -v deferrals="$DEFERRALS_CONTENT" '
    /\{\{DEFERRALS\}\}/ { print deferrals; next }
    { print }
  ' "$TEMPLATE"
  printf '\n\n---\n\n## Document under review (`%s`)\n\n```markdown\n' "$ARTIFACT_PATH"
  cat "$ARTIFACT_PATH"
  printf '\n```\n'
} > "$PROMPT_FILE"

PROMPT_BODY=$(cat "$PROMPT_FILE")

CODEX_TIMEOUT="${LIFELINE_CODEX_TIMEOUT:-300}"
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_PREFIX="timeout $CODEX_TIMEOUT"
else
  echo "WARNING: 'timeout' not available — running codex without external cap." >&2
  TIMEOUT_PREFIX=""
fi

# Build the optional `--model <name>` flag pair. Passing the array
# expansion via `${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"}` is portable under
# `set -u` even when MODEL_ARGS is empty (older bash + set -u rejects
# the bare `"${MODEL_ARGS[@]}"` expansion when the array is unset).
PINNED_MODEL="${LIFELINE_CODEX_MODEL:-}"
MODEL_ARGS=()
if [ -n "$PINNED_MODEL" ]; then
  MODEL_ARGS+=("--model" "$PINNED_MODEL")
fi

set +e
$TIMEOUT_PREFIX codex exec \
  --sandbox read-only \
  --output-last-message "$RESULT_MD" \
  ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
  -- "$PROMPT_BODY" \
  < /dev/null \
  > "$EVENTS_LOG" \
  2> "$STDERR_LOG"
CODEX_EXIT=$?
set -e

# Guard against the codex-exits-0-without-output edge case. Disk-full, codex
# bug, or an --output-last-message path issue can let codex return 0 without
# writing the result. Without this guard, the caller would treat that as
# "codex review succeeded with no findings" — wrong.
if [ "$CODEX_EXIT" -eq 0 ] && [ ! -s "$RESULT_MD" ]; then
  echo "ERROR: codex exited 0 but $RESULT_MD was not written or is empty." >&2
  echo "  See $STDERR_LOG and $EVENTS_LOG." >&2
  CODEX_EXIT=2
fi

exit "$CODEX_EXIT"
