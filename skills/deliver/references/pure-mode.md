# /lifeline:deliver — pure mode

You arrived here because Step 0 of `SKILL.md` set `$MODE = pure`. The variables `$OBJECTIVE`, `$CAP`, `$ITER` (= 0), and `$START_TS` (Unix seconds, captured in Step 1 of `SKILL.md`) are already in your reasoning context.

Pure mode runs the loop entirely inside Claude — no external grader, no codex subprocess. Each iteration's audit is self-administered against the checklist in `references/continuation.md`.

> **Reminder — Bash state does not persist between tool calls.** Carry literal values (paths, timestamps) forward in your reasoning context and interpolate them as strings into every Bash call.

## Step 1: Initialize scratch

```bash
SCRATCH=$(mktemp -d -t lifeline-deliver-XXXXXX)
echo "SCRATCH=$SCRATCH"
```

Remember the literal `$SCRATCH` path. Pure mode doesn't need codex/schema/grader-template, but `$SCRATCH` is still useful for any per-iteration notes you want to save (and it gets cleaned up on success or preserved on `budget_limited`).

## Step 2: The loop

While `ITER < CAP`:

### 2a. Read continuation template

Read `references/continuation.md` (resolve relative to your skill dir — same dir as `SKILL.md`). Substitute placeholders in your reasoning context:

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

When `ITER == CAP` without a complete verdict, read `references/budget_limit.md`, substitute the same placeholders as 2a, and use it for one wrap-up turn. Then emit:

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
