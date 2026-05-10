---
name: deliver
description: Goal-driven in-session loop. Take an objective and iterate Claude actions until a completion audit passes. Two modes — pure (Claude self-audit) and paired (codex independent grader). Adapted from openai/codex /goal templates.
tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# /lifeline:deliver — goal-driven in-session loop

Take a free-form objective and iterate Claude actions until a completion audit passes. Two modes share one loop:

- **Pure** — `/lifeline:deliver <objective>` — Claude self-audits each iteration using `references/continuation.md`.
- **Paired** — `/lifeline:deliver pair [N] <objective>` — completion check delegated to `codex exec` as an independent grader (no Claude conversation history visible to grader).

Adapted from OpenAI Codex's `/goal` command. See `NOTICE` for attribution.

## Step 0: Parse `$ARGUMENTS`

Strip leading whitespace. Then:

1. If first whitespace-separated token is `pair`:
   - `MODE = paired`
   - If second token parses as **any integer** (positive, zero, or negative):
     - When ≤ 0: error with `iteration cap must be a positive integer` and stop. Do not enter the loop.
     - When positive: `CAP = int(second token)`, `OBJECTIVE = rest of $ARGUMENTS after the integer`.
   - If second token does **not** parse as an integer: `CAP = 20`, `OBJECTIVE = rest of $ARGUMENTS after pair`.
2. Else: `MODE = pure`, `CAP = 20`, `OBJECTIVE = full $ARGUMENTS`.
3. If `OBJECTIVE` is empty after stripping, use `AskUserQuestion` to collect one before proceeding.

Initialize `ITER = 0`.

## Step 1: Initialize scratch + (paired only) resolve schema

> **Important — Bash state does not persist between tool calls.** Each
> Bash tool invocation runs in a fresh shell. The shell variables you
> set in Step 1 (e.g. `$SCRATCH`, `$SKILL_DIR`, `$SCHEMA_PATH`,
> `$GRADER_TEMPLATE`) **will not be visible** in subsequent Bash calls
> in Step 2. The pattern: read the literal values from this Bash call's
> output, remember them in your reasoning context, and **interpolate
> them as literal strings** into every subsequent Bash invocation.

Run via the Bash tool:

```bash
SCRATCH=$(mktemp -d -t lifeline-deliver-XXXXXX)
echo "SCRATCH=$SCRATCH"
```

Remember the literal `$SCRATCH` path for the rest of the loop.

**Paired mode only:** resolve the skill dir and confirm the schema exists. If resolution fails or the schema is missing, stop immediately — silent fallback to pure mode is the bug we are guarding against.

```bash
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
SKILL_DIR=$("$REPO_ROOT/skills/deliver/scripts/resolve-skill-dir.sh") || {
  echo "ERROR: could not resolve skills/deliver. Set LIFELINE_SKILL_DIR or install the plugin via /plugin install lifeline." >&2
  exit 1
}
SCHEMA_PATH="$SKILL_DIR/schemas/grader-output.json"
GRADER_TEMPLATE="$SKILL_DIR/references/grader-prompt.md"
[ -f "$SCHEMA_PATH" ] || { echo "ERROR: schema not found at $SCHEMA_PATH" >&2; exit 1; }
echo "SKILL_DIR=$SKILL_DIR"
echo "SCHEMA_PATH=$SCHEMA_PATH"
echo "GRADER_TEMPLATE=$GRADER_TEMPLATE"
```

Capture all four values (`SCRATCH`, `SKILL_DIR`, `SCHEMA_PATH`, `GRADER_TEMPLATE`) from this call's stdout and use them as literal paths in every subsequent Bash call this loop makes.

If the resolver exits non-zero or the schema is missing, **report this as a startup error and stop**. Do not enter the loop.

## Step 2: The loop

While `ITER < CAP`:

### 2a. Read continuation template

Read `$SKILL_DIR/references/continuation.md` (pure mode: just read from `skills/deliver/references/continuation.md`). Substitute placeholders in your reasoning context:

- `{{ objective }}` → `$OBJECTIVE`
- `{{ iter_used }}` → current `$ITER`
- `{{ iter_budget }}` → `$CAP`
- `{{ iter_remaining }}` → `$((CAP - ITER))`

The continuation prompt is the audit checklist you must apply this iteration. Keep it in your reasoning context.

### 2b. Take the next concrete action

Use `Edit` / `Write` / `Bash` / `Read` / etc. against the objective. **One action per iteration.** Do not batch multiple unrelated changes.

### 2c. Audit

**Pure mode:** Apply the audit checklist from continuation.md (in your reasoning context) against the action you just took. If the audit returns "complete," go to Step 3 (success).

**Paired mode:** Build the grader prompt and invoke `codex exec`:

```bash
GIT_DIFF_HEAD=$(git diff HEAD 2>/dev/null || true)
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null || true)
GIT_STATUS=$(git status --short 2>/dev/null || true)
FILES_TOUCHED="<bulleted list you maintained mentally — or empty if you did not track>"

# Render the grader template using bash parameter expansion. The
# ${var//pattern/replacement} form does LITERAL substitution (not regex,
# not & matched-text). Variables preserve embedded newlines, so
# multi-line diff content renders intact.
PROMPT=$(cat "$GRADER_TEMPLATE")
PROMPT="${PROMPT//\{\{ objective \}\}/$OBJECTIVE}"
PROMPT="${PROMPT//\{\{ git_diff_head \}\}/$GIT_DIFF_HEAD}"
PROMPT="${PROMPT//\{\{ untracked_files \}\}/$UNTRACKED}"
PROMPT="${PROMPT//\{\{ git_status \}\}/$GIT_STATUS}"
PROMPT="${PROMPT//\{\{ files_touched \}\}/$FILES_TOUCHED}"

set +e
timeout 300 codex exec \
  --sandbox read-only \
  --output-schema "$SCHEMA_PATH" \
  --output-last-message "$SCRATCH/grader-$ITER.json" \
  -- "$PROMPT" \
  < /dev/null \
  > "$SCRATCH/grader-$ITER.events.log" \
  2> "$SCRATCH/grader-$ITER.stderr.log"
CODEX_EXIT=$?
set -e
```

Parse the verdict:

```bash
if [ "$CODEX_EXIT" -eq 0 ] && [ -s "$SCRATCH/grader-$ITER.json" ]; then
  COMPLETE=$(jq -r '.complete' "$SCRATCH/grader-$ITER.json")
  if [ "$COMPLETE" = "true" ]; then
    EVIDENCE=$(jq -r '.evidence_checked[]' "$SCRATCH/grader-$ITER.json")
    # → go to Step 3 (success)
  else
    MISSING=$(jq -r '.missing_requirements[]' "$SCRATCH/grader-$ITER.json")
    # → log MISSING, continue loop
  fi
else
  echo "WARN: codex grader failed (exit $CODEX_EXIT); falling back to in-context audit for this iteration only" >&2
  # → apply continuation.md audit checklist to your last action
  # → if audit returns complete, go to Step 3; else continue loop
  # → mode does NOT switch globally; next iteration retries codex
fi
```

### 2d. Increment

`ITER = ITER + 1`. If `ITER < CAP`, loop back to 2a.

## Step 3: Final report

### Success path (`status: success`)

When the audit/grader returns complete, stop emitting tool calls and emit this report:

```
status: success
iterations: <ITER>
evidence_checked:
  - <each entry from grader output (paired) or your audit notes (pure)>
```

Then clean up the scratch dir:

```bash
rm -rf "$SCRATCH"
```

### Budget-limited path (`status: budget_limited`)

When `ITER == CAP`, read `$SKILL_DIR/references/budget_limit.md`, substitute placeholders, and use it for one wrap-up turn. Then emit:

```
status: budget_limited
iterations: <CAP>
missing_requirements:
  - <each entry from last grader output or audit>
scratch_dir: <SCRATCH path>
note: scratch dir preserved for postmortem inspection
```

**Do not delete `$SCRATCH`** on `budget_limited` — the user should be able to inspect the raw grader verdicts.

## Error handling

| Condition | Behavior |
|---|---|
| Empty objective | `AskUserQuestion` to collect one before Step 1. |
| Schema file resolution fails (paired mode) | Hard error at Step 1; do not enter loop. |
| Codex unavailable / not authed (paired mode) | First grader call fails; surface stderr in the warning and route through grader-fallback (apply in-context audit for that iteration only). |
| Grader subprocess fails (timeout, non-zero exit, malformed JSON, empty result file) | Same grader-fallback. Mode does NOT switch globally. |
| `git diff HEAD` errors (no commits yet) | Pass empty diff; grader still has objective + untracked + status. |

## Out-of-repo objectives

If the objective concerns paths outside the git repo (e.g., `/tmp/...`), `git diff HEAD` and `git ls-files` will be empty. The objective string must name the relevant paths so the grader can `cat`/`ls` them under `--sandbox read-only`. The grader prompt explicitly handles this case.

## Smoke tests

See `docs/superpowers/specs/2026-05-10-lifeline-deliver-design.md` (Testing strategy section).
