# /lifeline:deliver — pure mode

You arrived here because Step 0 of `SKILL.md` set `$MODE = pure`. The variables `$OBJECTIVE`, `$CAP`, `$ITER` (= 0), and `$START_TS` (Unix seconds, captured in Step 1 of `SKILL.md`) are already in your reasoning context.

Pure mode runs the loop entirely inside Claude — no external grader, no codex subprocess. Each iteration's audit is self-administered against the checklist in `references/continuation.md`.

> **Reminder — Bash state does not persist between tool calls.** Carry literal values (paths, timestamps) forward in your reasoning context and interpolate them as strings into every Bash call.

## Step 1: Initialize scratch + resolve skill dir

Resolution is **inline** here (not via the resolver script) for the same reason `paired-mode.md` inlines it: when the skill runs as an installed plugin in a target repo, `$REPO_ROOT/skills/deliver/scripts/resolve-skill-dir.sh` does not exist — the skill files live in the plugin cache. Without `$SKILL_DIR`, the per-iteration `Read` of `references/continuation.md` would silently miss the file and pure mode would loop without the audit checklist.

```bash
SCRATCH=$(mktemp -d -t lifeline-deliver-XXXXXX)
echo "SCRATCH=$SCRATCH"

# Resolve the deliver skill dir. Order: env override, plugin cache.
#
# **Workspace lookup is intentionally absent.** An earlier version of
# this code looked at `./skills/deliver` and `<git-root>/skills/deliver`
# and tried to gate them on `_is_lifeline_repo()` (grep `"name":
# "lifeline"` in `.claude-plugin/plugin.json`). That check is trivially
# bypassed: any adversarial target repo can drop a 1-line plugin.json
# with the sentinel string and then control `continuation.md`, biasing
# the audit checklist toward whatever it wants. There is no robust way
# to verify a workspace is the lifeline checkout from inside a
# workspace-resident file. So we simply don't look at the workspace.
#
# **Lifeline developers** working on the deliver skill set
# `LIFELINE_SKILL_DIR=$(pwd)/skills/deliver` (or the absolute equivalent)
# in their shell to make local edits effective without re-syncing the
# plugin cache after every change.
SKILL_DIR=""
if [ -n "${LIFELINE_SKILL_DIR:-}" ] && [ -f "$LIFELINE_SKILL_DIR/references/continuation.md" ]; then
  SKILL_DIR="$LIFELINE_SKILL_DIR"
else
  _cache="$HOME/.claude/plugins/cache/lifeline/lifeline"
  if [ -d "$_cache" ]; then
    # Newest-installed wins. Use mtime ordering (portable) instead of
    # `sort -V` which is GNU-only and missing on default macOS/BSD.
    _latest=$(ls -1t "$_cache" 2>/dev/null | head -1)
    if [ -n "$_latest" ] && [ -f "$_cache/$_latest/skills/deliver/references/continuation.md" ]; then
      SKILL_DIR="$_cache/$_latest/skills/deliver"
    fi
  fi
fi

if [ -z "$SKILL_DIR" ]; then
  echo "ERROR: could not resolve skills/deliver. Set LIFELINE_SKILL_DIR or install the plugin via /plugin install lifeline." >&2
  exit 1
fi

echo "SKILL_DIR=$SKILL_DIR"
```

Capture both `SCRATCH` and `SKILL_DIR` from this call's stdout and use them as literal paths in every subsequent Bash call (including the per-iteration `Read` calls for `continuation.md` and `budget_limit.md`). `$SCRATCH` cleans up on success and is preserved on `budget_limited`; `$SKILL_DIR` is read-only — pure mode never writes inside the skill dir.

If `$SKILL_DIR` is empty, **report a startup error and stop**. Continuing without it would mean every iteration silently fails to load the audit checklist.

## Step 2: The loop

While `ITER < CAP`:

### 2a. Read continuation template

Read `$SKILL_DIR/references/continuation.md` (the literal path you captured in Step 1). Substitute placeholders in your reasoning context:

- `{{ objective }}` → `$OBJECTIVE`
- `{{ iter_used }}` → current `$ITER`
- `{{ iter_budget }}` → `$CAP`
- `{{ iter_remaining }}` → `$((CAP - ITER))`

The continuation prompt is the audit checklist you must apply this iteration. Keep it in your reasoning context until 2c.

### 2b. Take the next concrete action

Use `Edit` / `Write` / `Bash` / `Read` / etc. against the objective. **One action per iteration.** Do not batch multiple unrelated changes. The action is the only productive work this iteration; the audit (2c) is verification, not new work.

### 2c. Self-audit

Apply the checklist from continuation.md to the action you just took:

- Restate the objective as concrete deliverables.
- Map every requirement to inspectable evidence (a file, command output, test result, etc.).
- Inspect the actual evidence. Do **not** treat partial progress, "looks correct," or proxy signals (passing tests, complete manifest, substantial effort) as completion unless they cover every requirement.
- Treat uncertainty as **not done** — if anything is missing, incomplete, or unverified, continue the loop.

If the audit returns **complete**, jump to Step 3 (success). Otherwise, continue.

### 2d. Increment

`ITER = ITER + 1`. If `ITER < CAP`, loop back to 2a.

## Step 3: Final report

Compute elapsed time. `START_TS` was echoed by `SKILL.md` Step 1; **rehydrate it from the literal value you captured then** (Bash variables don't survive across tool calls — that's why the dispatcher printed it for you to remember):

```bash
START_TS=<paste the literal Unix-seconds value SKILL.md Step 1 printed>
END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
MINS=$((ELAPSED / 60))
SECS=$((ELAPSED % 60))
echo "${MINS}m ${SECS}s"
```

Capture the literal `${MINS}m ${SECS}s` string for the report.

### Success path

When the audit returns complete, stop emitting tool calls and emit:

```
Deliveries done in <MINS>m <SECS>s.
status: success
mode: pure
iterations: <ITER + 1>
elapsed: <MINS>m <SECS>s
evidence_checked:
  - <each item from your audit notes>
```

Then clean up the scratch dir:

```bash
rm -rf "$SCRATCH"
```

### Budget-limited path

When `ITER == CAP` without a complete verdict, read `$SKILL_DIR/references/budget_limit.md` (the literal path you captured in Step 1), substitute the same placeholders as 2a, and use it for one wrap-up turn. Then emit:

```
Deliveries halted at iteration cap (<MINS>m <SECS>s elapsed).
status: budget_limited
mode: pure
iterations: <CAP>
elapsed: <MINS>m <SECS>s
missing_requirements:
  - <each item from the wrap-up audit>
scratch_dir: <SCRATCH path>
note: scratch dir preserved for postmortem inspection
```

**Do not delete `$SCRATCH`** on `budget_limited`.

## Error handling

| Condition | Behavior |
|---|---|
| Empty objective | Already handled in `SKILL.md` Step 0 via `AskUserQuestion`. |
| Audit ambiguous about whether the objective is truly satisfied | Treat as not-done. Take another concrete verification action next iteration (e.g., re-read the file, run the test) instead of guessing. |
