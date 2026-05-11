---
name: deliver
description: Goal-driven in-session loop. Take an objective and iterate Claude actions until a completion audit passes. Two modes — pure (Claude self-audit) and paired (codex independent grader). Adapted from openai/codex /goal templates.
tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# /lifeline:deliver — goal-driven in-session loop

Take a free-form objective and iterate Claude actions until a completion audit passes. The loop runs entirely within one Claude assistant turn — no external scheduling, no persistent state.

## Adapted from openai/codex

The `references/continuation.md` and `references/budget_limit.md` files are derivative works of templates from [openai/codex](https://github.com/openai/codex) under the Apache License, Version 2.0. See repo `NOTICE` for the full attribution. The four prompt techniques powering the audit (untrusted-input wrapping, concrete checklist, uncertainty-as-not-done, stop ≠ complete) come straight from the Codex `/goal` design.

## Two modes

| Mode | Invocation | When to use |
|---|---|---|
| **Pure**   | `/lifeline:deliver <objective>` | Lightweight, no external dependencies. Claude self-audits each iteration using `references/continuation.md`. |
| **Paired** | `/lifeline:deliver pair [N] <objective>` | Higher confidence on completion. Each "is it done?" check is delegated to `codex exec` as an independent grader (no Claude conversation history visible). Mirrors Anthropic's Outcomes pattern — independent grader → no confirmation bias. |

## Step 0: Parse `$ARGUMENTS` (decide the mode)

Strip leading whitespace. Then:

1. If first whitespace-separated token is `--`: `MODE = pure`, `CAP = 20`, `OBJECTIVE = rest of $ARGUMENTS after --`. This is the escape hatch for pure-mode objectives that naturally start with a reserved word such as `pair`.
2. If first whitespace-separated token is `pair`:
   - `MODE = paired`
   - If second token parses as **any integer** (positive, zero, or negative):
     - When ≤ 0: error with `iteration cap must be a positive integer` and stop. Do not enter the loop.
     - When > 50: error with `iteration cap must be <= 50` and stop. Do not enter the loop.
     - When 1..50: `CAP = int(second token)`, `OBJECTIVE = rest of $ARGUMENTS after the integer`.
   - If second token does **not** parse as an integer: `CAP = 20`, `OBJECTIVE = rest of $ARGUMENTS after pair`.
   - Before Step 1, emit a visible parse confirmation line: `Mode parse: paired; objective: <OBJECTIVE>`. If the user intended a pure-mode objective beginning with `pair`, tell them to rerun as `/lifeline:deliver -- pair ...`.
3. Else: `MODE = pure`, `CAP = 20`, `OBJECTIVE = full $ARGUMENTS`.
4. If `OBJECTIVE` is empty after stripping, use `AskUserQuestion` to collect one before proceeding.

Initialize `ITER = 0`.

## Step 1: Start the delivery timer

> **Bash state does not persist between tool calls.** Each Bash tool invocation runs in a fresh shell, so any shell variable you set is gone by the next call. The pattern: capture literal values from this call's stdout and interpolate them as literals into every subsequent Bash call. This applies here and in every Bash call in the mode-specific files.

```bash
START_TS=$(date +%s)
echo "START_TS=$START_TS"
```

Remember the literal `$START_TS` value — Step 3 (in the mode file) uses it to compute total elapsed time for the final "Deliveries done" report.

## Step 2: Dispatch to the mode-specific flow

Based on `$MODE` from Step 0, read **one** of the following and follow its instructions end-to-end. The mode file owns scratch initialization, the iteration loop, the final report, and mode-specific error handling.

| `$MODE` | Read this file |
|---------|----------------|
| `pure`  | `references/pure-mode.md` |
| `paired`| `references/paired-mode.md` |

Each mode file is self-contained — do not flip back to this SKILL.md once you've started the mode flow. Both end with a final report that opens with `Deliveries done in Xm Ys` (success) or `Deliveries halted at iteration cap (Xm Ys elapsed)` (budget_limited), computed from `$START_TS`.

## Smoke tests

Run the focused deliver guards:

```bash
python -m pytest -q harness/test_deliver_resolver_mirrors.py harness/test_deliver_skill_contracts.py
```

CI runs the same guard set via `.github/workflows/deliver-guards.yml`.
