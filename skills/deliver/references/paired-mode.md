# /lifeline:deliver — paired mode

You arrived here because Step 0 of `SKILL.md` set `$MODE = paired`. The variables `$OBJECTIVE`, `$CAP`, `$ITER` (= 0), and `$START_TS` (Unix seconds, captured in Step 1 of `SKILL.md`) are already in your reasoning context.

Paired mode delegates each iteration's "is the objective complete?" decision to `codex exec` running as an independent grader. The grader sees only the objective + current repo evidence — never your conversation history. This mirrors Anthropic's Outcomes pattern and is the whole point of paired mode: an external judge mitigates the confirmation bias of self-audit.

> **Reminder — Bash state does not persist between tool calls.** Carry literal values (paths, timestamps) forward in your reasoning context and interpolate them as strings into every Bash call.

## Step 1: Initialize scratch + resolve skill dir

Run via the Bash tool. Resolution is **inline** here (not via the resolver script) because when the skill runs as an installed plugin in a target repo, `$REPO_ROOT/skills/deliver/scripts/resolve-skill-dir.sh` does not exist — the skill files live in the plugin cache, not in the user's repo. The resolver-script call has a chicken-and-egg problem; inlining the same lookup avoids it.

```bash
SCRATCH=$(mktemp -d -t lifeline-deliver-XXXXXX)
echo "SCRATCH=$SCRATCH"

# Resolve the deliver skill dir. Order: env override, project-local
# (lifeline dev checkout), git-root (lifeline subdir), plugin cache.
SKILL_DIR=""
if [ -n "${LIFELINE_SKILL_DIR:-}" ] && [ -f "$LIFELINE_SKILL_DIR/schemas/grader-output.json" ]; then
  SKILL_DIR="$LIFELINE_SKILL_DIR"
elif [ -f "./skills/deliver/schemas/grader-output.json" ]; then
  SKILL_DIR="./skills/deliver"
elif _gr=$(git rev-parse --show-toplevel 2>/dev/null) && [ -f "$_gr/skills/deliver/schemas/grader-output.json" ]; then
  SKILL_DIR="$_gr/skills/deliver"
else
  _cache="$HOME/.claude/plugins/cache/lifeline/lifeline"
  if [ -d "$_cache" ]; then
    _latest=$(ls -1 "$_cache" 2>/dev/null | sort -V | tail -1)
    if [ -n "$_latest" ] && [ -f "$_cache/$_latest/skills/deliver/schemas/grader-output.json" ]; then
      SKILL_DIR="$_cache/$_latest/skills/deliver"
    fi
  fi
fi

if [ -z "$SKILL_DIR" ]; then
  echo "ERROR: could not resolve skills/deliver. Set LIFELINE_SKILL_DIR or install the plugin via /plugin install lifeline." >&2
  exit 1
fi

SCHEMA_PATH="$SKILL_DIR/schemas/grader-output.json"
GRADER_TEMPLATE="$SKILL_DIR/references/grader-prompt.md"
[ -f "$GRADER_TEMPLATE" ] || { echo "ERROR: grader template not found at $GRADER_TEMPLATE" >&2; exit 1; }

echo "SKILL_DIR=$SKILL_DIR"
echo "SCHEMA_PATH=$SCHEMA_PATH"
echo "GRADER_TEMPLATE=$GRADER_TEMPLATE"
```

Capture all four values (`SCRATCH`, `SKILL_DIR`, `SCHEMA_PATH`, `GRADER_TEMPLATE`) from this call's stdout and use them as literal paths in every subsequent Bash call.

If `$SKILL_DIR` ends up empty or the grader template is missing, **report a startup error and stop**. Do not enter the loop. Silent fallback to pure mode is the bug we are explicitly guarding against.

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

# GNU `timeout` is optional on some systems (BSD/macOS without coreutils,
# minimal containers). Conditionally apply it; without timeout the existing
# Codex CLI behavior still applies — codex itself exits eventually.
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_PREFIX="timeout 300"
else
  TIMEOUT_PREFIX=""
fi

set +e
$TIMEOUT_PREFIX codex exec \
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

Parse the verdict. Validate JSON parseability **before** asking jq for `.complete` — `set -e` would otherwise abort the whole bash step on malformed grader output, bypassing the fallback path:

```bash
VERDICT_SOURCE="grader"  # remember how this iteration completed (or didn't)
COMPLETE="false"

if [ "$CODEX_EXIT" -eq 0 ] && [ -s "$SCRATCH/grader-$ITER.json" ] \
   && jq empty "$SCRATCH/grader-$ITER.json" 2>/dev/null; then
  # Valid JSON — read the verdict; tolerate missing keys.
  COMPLETE=$(jq -r '.complete // false' "$SCRATCH/grader-$ITER.json")
  if [ "$COMPLETE" = "true" ]; then
    EVIDENCE=$(jq -r '.evidence_checked[]?' "$SCRATCH/grader-$ITER.json")
    # → go to Step 3 (success), record VERDICT_SOURCE=grader
  else
    MISSING=$(jq -r '.missing_requirements[]?' "$SCRATCH/grader-$ITER.json")
    # → log MISSING, continue loop with the next concrete action
  fi
else
  echo "WARN: codex grader unusable (exit $CODEX_EXIT, file empty/malformed); falling back to in-context audit for this iteration only" >&2
  VERDICT_SOURCE="self-audit-fallback"
  # → apply continuation.md audit checklist to your last action
  # → if audit returns complete, go to Step 3 (record VERDICT_SOURCE=self-audit-fallback)
  # → else continue loop
  # → mode does NOT switch globally; next iteration retries codex
fi
```

Carry `VERDICT_SOURCE` ("grader" or "self-audit-fallback") forward to Step 3 — the success report needs it to decide where evidence comes from.

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

When the grader (or fallback self-audit) returns complete, stop emitting tool calls and emit one of the two reports below — pick the variant matching `$VERDICT_SOURCE` from the iteration that completed.

**If `VERDICT_SOURCE = grader`** (codex grader returned `complete: true`):

```
Deliveries done in <MINS>m <SECS>s.
status: success
mode: paired
verdict_source: codex grader
iterations: <ITER + 1>
elapsed: <MINS>m <SECS>s
evidence_checked:
  - <each entry from the final grader-N.json (.evidence_checked[])>
```

**If `VERDICT_SOURCE = self-audit-fallback`** (codex was unavailable / timed out / returned malformed JSON, and the in-context audit declared completion):

```
Deliveries done in <MINS>m <SECS>s.
status: success
mode: paired
verdict_source: in-context fallback (codex was unavailable for this iteration)
iterations: <ITER + 1>
elapsed: <MINS>m <SECS>s
evidence_checked:
  - <each item from your in-context audit notes for the completing iteration>
note: paired mode degraded to self-audit for the final iteration — re-run when codex is reachable for an independent verdict.
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
  - <pull from the last iteration's grader-N.json (.missing_requirements[]) if VERDICT_SOURCE=grader,
     OR from your in-context audit notes for that iteration if VERDICT_SOURCE=self-audit-fallback>
scratch_dir: <SCRATCH path>
note: scratch dir preserved for postmortem inspection. Raw codex verdicts (when present) are in grader-*.json.
```

**Do not delete `$SCRATCH`** on `budget_limited` — the user inspects raw grader verdicts (and event/stderr logs from any failed grader runs) here.

## Error handling

| Condition | Behavior |
|---|---|
| Empty objective | Already handled in `SKILL.md` Step 0 via `AskUserQuestion`. |
| Schema file resolution fails (Step 1) | Hard error; do not enter loop. Silent degradation to pure mode is exactly what we are guarding against. |
| Codex unavailable / not authed | First grader call fails with non-zero exit; surface its stderr in the warning; route through the grader-fallback path (apply the in-context audit for that iteration only). No upfront preflight on `~/.codex/auth.json` — it's not the only valid auth path (`CODEX_HOME` env override exists). |
| Grader subprocess fails (timeout, non-zero exit, malformed JSON, empty result file) | Same grader-fallback. Mode does NOT switch globally — the next iteration retries codex. |
| `git diff HEAD` errors (no commits yet on this branch) | Pass empty diff; grader still has objective + untracked + status. |
| Out-of-repo objective | Git evidence will be empty. Include the relevant path(s) in `FILES_TOUCHED` so the grader knows where to `cat`/`ls` directly under `--sandbox read-only`. The grader prompt explicitly handles this case. |
