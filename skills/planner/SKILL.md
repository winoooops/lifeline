---
name: planner
description: Self-contained design-spec writer with automatic Codex review on the result. Walks through brainstorming methodology (clarifying questions → approaches → section-by-section design → spec write + commit), then runs `codex exec` on the spec and applies user-approved findings. Supports both end-of-spec and per-section codex iteration. Use when starting design for a new feature or refactor.
tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# /lifeline:planner — Design-spec writer with paired Codex review

Pairs the brainstorming methodology with automatic Codex review on the resulting spec. After the methodology produces a design spec, planner runs `codex exec` against it, surfaces findings, and applies user-approved iterations — eliminating the manual copy-paste between Claude Code and the Codex CLI.

Two iteration cadences are supported:

- **End-of-spec** (single review pass after the whole spec is committed). Faster, fewer codex round-trips, but cross-section contradictions are surfaced after revert costs are higher.
- **Per-section** (codex pass after each section is written, then a final whole-spec pass). More codex calls, more cross-section issues caught early, more iteration discipline required.

The user picks the mode at Step 0.

## Invocation

```
/lifeline:planner [topic-hint]
```

`topic-hint` is optional; it seeds the first clarifying question with a one-phrase description of what you want to design.

## Why self-contained

`superpowers:brainstorming` chains to `superpowers:writing-plans` at its terminal state, which then chains to execution skills. Invoking either as a skill from planner would not return control at the natural codex-review checkpoint. Planner sidesteps the chain by **not invoking** `superpowers:brainstorming` as a separate skill — instead, planner restates the brainstorming methodology inline and runs the codex hook itself.

## File structure

```
skills/planner/
├── SKILL.md                                  # this file — orchestrator
├── scripts/
│   ├── resolve-skill-dir.sh                  # shared SKILL_DIR resolver (env / project / git-root / plugin-cache)
│   ├── codex-review.sh                       # `codex exec` invocation; supports {{DEFERRALS}} injection
│   ├── update-footer.sh                      # idempotent HTML-comment footer (POSIX awk + atomic mv)
│   └── discover-artifacts.sh                 # FALLBACK only — combined committed+unstaged+untracked scan
└── references/
    ├── codex-prompts/
    │   ├── spec-complete.md                  # whole-spec review (end-of-spec + final pass after per-section)
    │   └── section-partial.md                # partial-spec review (per-section iteration)
    ├── methodology.md                        # the seven-step brainstorming flow
    └── failure-modes.md                      # FULL / DEGRADED / ABORTED end-state contract
```

The skill resolves its own directory at runtime via `scripts/resolve-skill-dir.sh` — invocations work whether the skill is installed via the plugin cache, checked out into the project as `skills/planner`, or pinned via the `LIFELINE_SKILL_DIR` env var.

Heavy detail lives in `references/`. SKILL.md keeps the orchestration contract.

## Pipeline

### Step 0 — Mode prompts (asked at the very start)

Before anything else, ask three questions back-to-back:

```
AskUserQuestion:
  question: "How do you want codex review iteration to run?"
  options:
    - label: "Per-section + final pass (Recommended)"
      description: "Codex reviews each section as it's added, plus one whole-spec pass at the end. Catches cross-section issues early."
    - label: "End-of-spec only"
      description: "One codex review after the whole spec is written. Fewer codex calls; cross-section issues surface later."

AskUserQuestion:
  question: "After codex returns findings, how should they be applied?"
  options:
    - label: "Per-finding"
      description: "I show each finding individually. For each: apply / skip / clarify."
    - label: "Auto-apply"
      description: "Apply all HIGH/MEDIUM findings, then show a single consolidated diff before commit."

AskUserQuestion:
  question: "Which codex model should review your spec?"
  options:
    - label: "Codex default (Recommended)"
      description: "Codex CLI picks the model for your auth mode. Works for both ChatGPT-account auth and API-key auth. No --model flag passed."
    - label: "Pin a specific model"
      description: "Override with a custom model name (e.g. gpt-5.5). Only works on API-key auth — ChatGPT-account auth rejects explicit --model selection."
```

Capture the answers as:

- `$ITERATION_MODE` — `per-section` or `end-of-spec`.
- `$APPLY_MODE` — `per-finding` or `auto`.
- `$CODEX_MODEL` — empty string for "Codex default", or a non-empty model name when the user picks "Pin a specific model" (in which case ask a follow-up free-text question for the model name and capture it).

Apply modes still gate on a final user confirmation before each commit.

The model choice is plumbed through to `codex-review.sh` via the `LIFELINE_CODEX_MODEL` env var. Every invocation in this skill uses:

```bash
LIFELINE_CODEX_MODEL="$CODEX_MODEL" "$SKILL_DIR/scripts/codex-review.sh" <hook> <artifact>
```

When `$CODEX_MODEL` is empty, the env var is empty too, and the script omits `--model` entirely (matching the no-pin default).

### Step 0.5 — Capture baseline state

```bash
START_SHA=$(git rev-parse HEAD)
SPEC_FILE=""        # populated in methodology Step 5; consumed by the codex hook
SCRATCH_DIR=".lifeline-planner"
DEFERRALS_FILE="${SCRATCH_DIR}/deferrals.md"
mkdir -p "$SCRATCH_DIR"
: > "$DEFERRALS_FILE"   # truncate so a prior session's deferrals don't leak in
```

`START_SHA` is consumed by the discovery fallback (Step 8.A) if SPEC_FILE is lost.

`DEFERRALS_FILE` is the running list of findings the agent has marked as "address in Section N later" or "address in a follow-up spec". Each entry is one bullet. The agent appends to it whenever a finding is deferred, and `codex-review.sh` injects it into every prompt via the `{{DEFERRALS}}` placeholder so codex stops re-flagging tracked items.

### Steps 1–7 — Brainstorming methodology (inline)

Follow `references/methodology.md` end-to-end. The seven steps are:

1. **Explore project context** (git log, CLAUDE.md, recent specs, grep)
2. **Ask clarifying questions** (one at a time; multi-choice via `AskUserQuestion` preferred)
3. **Propose 2-3 approaches** with tradeoffs and a recommendation
4. **Present design in sections**, get user approval per section
5. **Write spec** to `docs/superpowers/specs/<YYYY-MM-DD>-<topic>-design.md`. **Capture `SPEC_FILE`.**
6. **Inline self-review** (placeholders, contradictions, scope, ambiguity)
7. **Commit spec** as `docs(spec): <topic-slug>`

If the user aborts at any step before commit, exit with the **✗ ABORTED** end state.

### Step 4-bis — Per-section iteration loop (when `$ITERATION_MODE = per-section`)

Insert this loop INSIDE Step 4 of the methodology. For each section:

1. **Draft the section** inline (in the conversation).
2. **Get user approval** on the draft.
3. **Append the section** to `$SPEC_FILE` (creating the file on the first iteration; append on subsequent).
4. **Run codex** against the cumulative file:
   ```bash
   LIFELINE_CODEX_MODEL="$CODEX_MODEL" \
     "$SKILL_DIR/scripts/codex-review.sh" section-partial "$SPEC_FILE"
   ```
   The script reads `$DEFERRALS_FILE` automatically and injects it into the prompt. When `$CODEX_MODEL` is empty, no `--model` flag is passed.
5. **Read the review** at `${SCRATCH_DIR}/section-partial-review.md`.
6. **Walk findings** per `$APPLY_MODE`. For each finding:
   - **Apply**: Edit the spec file. Move on.
   - **Defer**: Append a one-line bullet to `$DEFERRALS_FILE` describing the finding and the section that will resolve it. Codex will not re-flag it on the next pass. Optionally also create a TaskCreate tracker for visibility.
   - **Skip**: Note in the conversation that the finding was reviewed and rejected. No state change.
   - **Clarify**: Ask the user; apply their decision.
7. **Move to the next section.** Repeat from step 1 until all sections are written.

When the loop finishes, proceed to Step 6 (self-review) and Step 7 (commit) of the methodology — the spec is committed once at the end, not per section.

### Step 4-bis-skip — End-of-spec mode

When `$ITERATION_MODE = end-of-spec`, skip the loop above. Methodology Step 4 runs as written: each section is presented for approval, the file is written at Step 5, and codex review runs once at Step 8.

### Step 8 — Codex review hook (whole-spec)

After Step 7 commits the spec, run codex against the whole file. This pass runs in BOTH iteration modes — for end-of-spec, it is the only pass; for per-section, it is the final cross-cutting check after the section-by-section iteration.

#### 8.A — Resolve `SPEC_FILE` (with fallback)

```bash
if [ -z "$SPEC_FILE" ] || [ ! -f "$SPEC_FILE" ]; then
  CANDIDATES=$("$SKILL_DIR/scripts/discover-artifacts.sh" "$START_SHA")
  SPEC_FILE=$(echo "$CANDIDATES" | grep -E '/specs?/.*\.md$' | head -1)
  [ -z "$SPEC_FILE" ] && SPEC_FILE=$(echo "$CANDIDATES" | grep -iE '(design|spec)\.md$' | head -1)
  # Multiple matches OR empty: prompt the user to pick from CANDIDATES.
  # Don't guess silently. If user can't disambiguate → ABORT.
fi
```

Normal flow uses the captured path from methodology Step 5 — discovery is for the corner case where SPEC_FILE was lost.

#### 8.B — Run `codex-review.sh`

```bash
SKILL_DIR="$("$(dirname "$0")/resolve-skill-dir.sh")" || exit 2

set +e
LIFELINE_CODEX_MODEL="$CODEX_MODEL" \
  "$SKILL_DIR/scripts/codex-review.sh" spec-complete "$SPEC_FILE"
HOOK_EXIT=$?
set -e
```

The script auto-injects the running `$DEFERRALS_FILE` into the prompt so any items the agent deferred during per-section iteration are NOT re-flagged here.

Codex output goes to `${SCRATCH_DIR}/spec-complete-review.md`. Exit-code routing:

- `0` → FULL path (Step 8.C)
- `124` → DEGRADED (codex timed out)
- non-zero → DEGRADED (codex unavailable, exit error, or empty output)

See `references/failure-modes.md` for the full contract.

#### 8.C — FULL path (codex returned non-empty review)

Show the review to the user, then walk findings per `$APPLY_MODE`.

**`$APPLY_MODE = auto`**:
1. Read each `[HIGH]` / `[MEDIUM]` finding.
2. Apply each as `Edit` operations on `$SPEC_FILE`. (For findings that don't translate to a single mechanical edit — e.g. "this section needs more detail on X" — surface them as comments to the user with a suggested edit, ask for confirmation.)
3. Show one consolidated `git diff $SPEC_FILE`.
4. Ask: "Apply these changes? [Y/n]"
5. On approval: commit with `git commit -am "docs(spec): apply codex feedback"`. On decline: skip the iteration commit and treat as DEGRADED with reason "user declined codex iterations".

**`$APPLY_MODE = per-finding`**:
1. For each finding in severity order (HIGH → MEDIUM → LOW):
   - Show the finding.
   - `AskUserQuestion`: `Apply` / `Skip` / `Clarify` (or `Defer` when applicable — same effect as appending to `$DEFERRALS_FILE` and noting in a follow-up spec).
2. After all findings: if anything was applied, commit with the same message.

After the iteration commit (or after "no findings — spec is implementation-ready"), append the codex-reviewed footer:

```bash
"$SKILL_DIR/scripts/update-footer.sh" "$SPEC_FILE"
git add "$SPEC_FILE"
git commit -m "docs(spec): mark spec codex-reviewed"
```

(Footer commit is separate from the iteration commit so the iteration history shows what changed, while the footer commit records the review status as its own atomic event.)

#### 8.D — DEGRADED path (codex hook failed)

Do NOT retry. Do NOT block. Print a prominent warning naming:

- The spec path
- The reason (extracted from `${SCRATCH_DIR}/spec-complete-stderr.log` or the exit code)
- The manual recovery command:
  ```
  $SKILL_DIR/scripts/codex-review.sh spec-complete <SPEC_FILE>
  ```

**No footer is appended.** The absence of the footer is the load-bearing "this is unreviewed" signal.

### Step 9 — Optional plan generation + plan review

After the spec has been committed and codex-reviewed (Step 8 reached the FULL state), offer the user the option to continue into implementation planning. This is a hand-off to `/superpowers:writing-plans` followed by a codex review of the plan it produces.

```
AskUserQuestion:
  question: "Continue into implementation plan generation?"
  options:
    - label: "Yes, write the plan and review it (Recommended)"
      description: "Invoke /superpowers:writing-plans against the spec. After it returns, codex reviews the plan and we walk findings the same way we did for the spec."
    - label: "Skip — I'll plan separately"
      description: "Stop here. The spec is committed and codex-reviewed; you can run /superpowers:writing-plans yourself later."
```

If the user picks **Skip**: jump to Step 10 (retrospective).

If the user picks **Yes**, run the plan integration:

#### 9.A — Invoke `/superpowers:writing-plans`

Use the `Skill` tool to invoke `superpowers:writing-plans` with the spec path as context. **Important constraint:** `superpowers:writing-plans` chains to execution skills (`executing-plans` / `subagent-driven-development`) at its terminal state by default. Pass an explicit instruction in the invocation:

```
Skill: superpowers:writing-plans
args: |
  Spec: $SPEC_FILE

  Generate the implementation plan for this spec. STOP after the plan is
  written and committed — do NOT chain to executing-plans or any execution
  skill. Control must return to /lifeline:planner so codex can review the
  plan before any implementation begins.
```

Capture the plan path the skill writes (typically `docs/superpowers/plans/<YYYY-MM-DD>-<topic>-plan.md` or whatever the skill's convention is) as `$PLAN_FILE`.

If `superpowers:writing-plans` chains anyway (despite the instruction) and execution begins, abort the plan-review pass and treat the planner run as **PARTIAL_PLAN** — the plan exists but is unreviewed; document this in the final summary so the user knows to run codex against the plan manually.

#### 9.B — Run plan-complete codex hook

```bash
set +e
LIFELINE_CODEX_MODEL="$CODEX_MODEL" \
  "$SKILL_DIR/scripts/codex-review.sh" plan-complete "$PLAN_FILE"
HOOK_EXIT=$?
set -e
```

Codex output goes to `${SCRATCH_DIR}/plan-complete-review.md`. Same exit-code routing as the spec hook (Step 8.B).

The script auto-injects `$DEFERRALS_FILE` (which by this point may include items deferred during spec-side iteration, plus any plan-side deferrals). Codex will skip those tracked items.

#### 9.C — Walk plan findings and commit

Identical to Step 8.C but against `$PLAN_FILE`:

- Walk findings per `$APPLY_MODE`.
- Apply approved findings via Edit on `$PLAN_FILE`.
- Commit applied changes with `docs(plan): apply codex feedback`.
- Append the codex-reviewed footer to the plan via `update-footer.sh`.
- Commit the footer with `docs(plan): mark plan codex-reviewed`.

#### 9.D — Plan-side DEGRADED path

If the plan-complete hook fails for any reason (codex unavailable, timeout, empty output), do NOT retry. Print a warning naming the plan path, the reason, and the manual recovery command:

```
$SKILL_DIR/scripts/codex-review.sh plan-complete <PLAN_FILE>
```

Track the run as **DEGRADED on plan side**; the spec is still FULL.

### Step 10 — Optional retrospective

After Step 9 completes (or was skipped), offer (do not force):

```
AskUserQuestion:
  question: "Write a one-page retrospective of this planner session?"
  options:
    - label: "Yes"
      description: "Save to .lifeline-planner/retros/<YYYY-MM-DD-HHMM>.md. Captures what worked, friction points, and any deferrals tracked."
    - label: "Skip"
      description: "Just print the final summary."
```

If yes: write a markdown file with sections for "What worked", "Friction points", "Deferrals tracked" (read from `$DEFERRALS_FILE`), and "Suggestions for next time". The file is for the user's reference — it is NOT committed automatically.

### Step 11 — Final summary

Print a status block. Shape depends on whether plan generation ran:

When plan generation was skipped:
```
spec: ✓ FULL  | ⚠ DEGRADED  | ✗ ABORTED
path: <SPEC_FILE>
reason: <one-line, only present for DEGRADED or ABORTED>
next: run /superpowers:writing-plans against this spec when ready
```

When plan generation ran:
```
spec: ✓ FULL  | ⚠ DEGRADED  | ✗ ABORTED
plan: ✓ FULL  | ⚠ DEGRADED  | ⚠ PARTIAL_PLAN  | (skipped)
spec-path: <SPEC_FILE>
plan-path: <PLAN_FILE>  (only when plan was written)
reason: <one-line per degraded side, when applicable>
next: <next-step hint based on combined state>
```

Exit code:

- `0` for any combination where at least the spec exists (FULL, DEGRADED, PARTIAL_PLAN)
- non-zero for ABORTED (no spec was produced)

## Conventions when calling AskUserQuestion

- **Match option count to the actual fork.** A binary apply/skip choice is two options. A real four-way design choice is four. Don't pad to four when there are only two real branches — it adds visual noise and biases the user toward the filler.
- **Cap at four; route excess via filtering.** The tool itself caps at four options. When more than four genuine choices exist (e.g., 6+ design alternatives), ask a filtering question first ("which dimension matters most?"), then a follow-up with the surviving options.
- **Lead with the recommendation.** First option carries the "(Recommended)" suffix when there is a clear default.
- **Use the IDEA framework for substantive option choices.** When two options have meaningfully different long-term consequences, render each as an IDEA block (Intent / Danger / Explain / Alternatives) before the AskUserQuestion call. The structured comparison resolves choices faster than prose.

## Commit message convention

All planner commits use the `docs(<scope>):` prefix where `<scope>` is `spec` or `plan` depending on which artifact the commit touches. This passes `@commitlint/config-conventional` (the standard config used by most projects).

Spec-side commits (Step 7 + Step 8):

- `docs(spec): <topic-slug>` — initial spec write (methodology Step 7).
- `docs(spec): apply codex feedback` — iteration commit when findings are applied (Step 8.C).
- `docs(spec): mark spec codex-reviewed` — footer commit (Step 8.C tail).

Plan-side commits (Step 9), only when plan generation runs:

- `docs(plan): <topic-slug>` — initial plan write (written by `superpowers:writing-plans` itself; verify the type, fix it post-hoc with `git commit --amend` if writing-plans uses a different prefix).
- `docs(plan): apply codex feedback` — iteration commit (Step 9.C).
- `docs(plan): mark plan codex-reviewed` — footer commit (Step 9.C tail).

If your project's commitlint adds a custom `spec` or `plan` type, you may swap. The default is `docs(<scope>):`.

## What planner does NOT do (boundaries)

- **Does not invoke `superpowers:brainstorming` as a skill.** It would chain to writing-plans. The methodology is followed inline.
- **Does not auto-execute the plan.** When `/superpowers:writing-plans` is invoked at Step 9, planner explicitly instructs it to stop after writing the plan — the implementation phase is the user's next step.
- **Does not retry codex hooks.** Codex unavailability is treated as a degraded end state.
- **Does not edit the spec's or plan's frontmatter.** Existing specs in most projects don't have YAML frontmatter; the codex-reviewed marker is an HTML-comment footer at end-of-file (see `scripts/update-footer.sh`).
- **Does not auto-commit per section** in per-section mode. The spec is committed once at Step 7 — section-by-section commits would pollute git log without adding value (each section's diff is visible in the codex review files anyway).

## v2 paths

- **Companion `/lifeline:review-doc <path>`** — pure post-hoc codex review on any markdown file. Useful for reviewing plans / specs that planner did not produce. Lower priority now that v1 has plan-side review built in.
- **Inline `superpowers:writing-plans` methodology.** Currently planner invokes the skill with a stop-after-write instruction. If that instruction proves unreliable across superpowers versions, plan-side methodology can move inline (mirroring the brainstorming-inline pattern).

## Notes

- **Codex CLI flag verification date: May 2026.** If `codex exec` changes its flag set (e.g., renames `--output-last-message`), the skill breaks. The invocation is centralized in `scripts/codex-review.sh`.
- **`LIFELINE_CODEX_TIMEOUT`** overrides the default 300s codex timeout. Tests use a small value to force the DEGRADED-on-timeout path.
- **`LIFELINE_SKILL_DIR`** overrides skill-directory resolution. See `scripts/resolve-skill-dir.sh` for the lookup order.
- **`LIFELINE_DEFERRALS_FILE`** overrides the deferrals-list path. Default: `${SCRATCH_DIR}/deferrals.md`.
- **`LIFELINE_CODEX_MODEL`** pins the codex model via `--model <name>`. Empty / unset (the default) omits the flag, letting codex pick its auth-mode-appropriate default. Pinning only works on API-key auth — ChatGPT-account auth rejects explicit model selection.
