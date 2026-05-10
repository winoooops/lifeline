# /lifeline:deliver — paired mode

You arrived here because Step 0 of `SKILL.md` set `$MODE = paired`. The variables `$OBJECTIVE`, `$CAP`, `$ITER` (= 0), and `$START_TS` (Unix seconds, captured in Step 1 of `SKILL.md`) are already in your reasoning context.

Paired mode delegates each iteration's "is the objective complete?" decision to `codex exec` running as an independent grader. The grader sees only the objective + current repo evidence — never your conversation history. This mirrors Anthropic's Outcomes pattern and is the whole point of paired mode: an external judge mitigates the confirmation bias of self-audit.

> **Reminder — Bash state does not persist between tool calls.** Carry literal values (paths, timestamps) forward in your reasoning context and interpolate them as strings into every Bash call.

## Step 1: Initialize scratch + resolve schema

Run via the Bash tool:

```bash
SCRATCH=$(mktemp -d -t lifeline-deliver-XXXXXX)
echo "SCRATCH=$SCRATCH"

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

Capture all four values (`SCRATCH`, `SKILL_DIR`, `SCHEMA_PATH`, `GRADER_TEMPLATE`) from this call's stdout and use them as literal paths in every subsequent Bash call.

If the resolver exits non-zero or the schema is missing, **report a startup error and stop**. Do not enter the loop. Silent fallback to pure mode is the bug we are explicitly guarding against.

## Step 2: The loop

While `ITER < CAP`:

### 2a. Read continuation template

Read `$SKILL_DIR/references/continuation.md`. Substitute placeholders in your reasoning context:

- `{{ objective }}` → `$OBJECTIVE`
- `{{ iter_used }}` → current `$ITER`
- `{{ iter_budget }}` → `$CAP`
- `{{ iter_remaining }}` → `$((CAP - ITER))`

The continuation prompt is the audit checklist that frames your next action. Keep it in your reasoning context until 2c.

### 2b. Take the next concrete action

Use `Edit` / `Write` / `Bash` / `Read` / etc. against the objective. **One action per iteration.** Do not batch multiple unrelated changes. The action is the only productive work this iteration; the codex grader (2c) is verification.

Optionally maintain a mental list of files you touched this iteration — it gets passed to the grader as orientation context.

### 2c. Run the codex grader

Build the grader prompt and invoke `codex exec`:

```bash
GIT_DIFF_HEAD=$(git diff HEAD 2>/dev/null || true)
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null || true)
GIT_STATUS=$(git status --short 2>/dev/null || true)
FILES_TOUCHED="<bulleted list you maintained mentally — or empty if you did not track. For out-of-repo objectives, include the full path here so the grader knows where to inspect>"

# Render the grader template using bash parameter expansion. The
# ${var//pattern/replacement} form does LITERAL substitution (not regex,
# not & matched-text). Variables preserve embedded newlines so multi-line
# diff content renders intact.
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
    # → log MISSING, continue loop with the next concrete action
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

Compute elapsed time from `$START_TS` (set in `SKILL.md` Step 1):

```bash
END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
MINS=$((ELAPSED / 60))
SECS=$((ELAPSED % 60))
echo "${MINS}m ${SECS}s"
```

Capture the literal `${MINS}m ${SECS}s` string for the report.

### Success path

When the grader (or fallback self-audit) returns complete, stop emitting tool calls and emit:

```
Deliveries done in <MINS>m <SECS>s.
status: success
mode: paired
iterations: <ITER + 1>
elapsed: <MINS>m <SECS>s
grader_verdict: complete
evidence_checked:
  - <each entry from the final grader-N.json (.evidence_checked[])>
```

Then clean up the scratch dir:

```bash
rm -rf "$SCRATCH"
```

### Budget-limited path

When `ITER == CAP` without a complete verdict, read `$SKILL_DIR/references/budget_limit.md`, substitute the same placeholders as 2a, and use it for one wrap-up turn. Then emit:

```
Deliveries halted at iteration cap (<MINS>m <SECS>s elapsed).
status: budget_limited
mode: paired
iterations: <CAP>
elapsed: <MINS>m <SECS>s
missing_requirements:
  - <each entry from the last grader-N.json (.missing_requirements[])>
scratch_dir: <SCRATCH path>
note: scratch dir preserved for postmortem inspection (raw codex verdicts in grader-*.json)
```

**Do not delete `$SCRATCH`** on `budget_limited` — the user inspects raw grader verdicts here.

## Error handling

| Condition | Behavior |
|---|---|
| Empty objective | Already handled in `SKILL.md` Step 0 via `AskUserQuestion`. |
| Schema file resolution fails (Step 1) | Hard error; do not enter loop. Silent degradation to pure mode is exactly what we are guarding against. |
| Codex unavailable / not authed | First grader call fails with non-zero exit; surface its stderr in the warning; route through the grader-fallback path (apply the in-context audit for that iteration only). No upfront preflight on `~/.codex/auth.json` — it's not the only valid auth path (`CODEX_HOME` env override exists). |
| Grader subprocess fails (timeout, non-zero exit, malformed JSON, empty result file) | Same grader-fallback. Mode does NOT switch globally — the next iteration retries codex. |
| `git diff HEAD` errors (no commits yet on this branch) | Pass empty diff; grader still has objective + untracked + status. |
| Out-of-repo objective | Git evidence will be empty. Include the relevant path(s) in `FILES_TOUCHED` so the grader knows where to `cat`/`ls` directly under `--sandbox read-only`. The grader prompt explicitly handles this case. |
