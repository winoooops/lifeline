---
name: planner
description: Self-contained design-spec writer with automatic Codex review on the result. Walks through brainstorming methodology (clarifying questions → approaches → section-by-section design → spec write + commit), then runs `codex exec` on the committed spec and applies user-approved findings. v1 is spec-only — run /superpowers:writing-plans separately for the implementation plan. Use when starting design for a new feature or refactor.
tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# /lifeline:planner — Design-spec writer with paired Codex review

Pairs the brainstorming methodology with automatic Codex review on the resulting spec. After the methodology produces and commits a design spec, planner runs `codex exec` against it, surfaces findings, and applies user-approved iterations — eliminating the manual copy-paste between Claude Code and the Codex CLI.

## Invocation

```
/lifeline:planner [topic-hint]
```

`topic-hint` is optional; it seeds the first clarifying question with a one-phrase description of what you want to design.

## Why self-contained

`superpowers:brainstorming` chains to `superpowers:writing-plans` at its terminal state, which then chains to execution skills. Invoking either as a skill from planner would not return control at the natural codex-review checkpoint. v1 sidesteps the chain by **not invoking** `superpowers:brainstorming` as a separate skill — instead, planner restates the brainstorming methodology inline and runs the codex hook itself.

This is heavier than a thin wrapper but is the simplest implementable v1 that achieves the goal. v2 paths to add per-section codex review and plan-side review are noted at the bottom.

## File structure

```
~/.claude/plugins/cache/lifeline/lifeline/0.0.1/skills/planner/
├── SKILL.md                                  # this file — orchestrator
├── scripts/
│   ├── codex-review.sh                       # verify.sh-style codex invocation
│   ├── update-footer.sh                      # idempotent HTML-comment footer (POSIX awk + atomic mv)
│   └── discover-artifacts.sh                 # FALLBACK only — combined committed+unstaged+untracked scan
└── references/
    ├── codex-prompts/
    │   └── spec-complete.md                  # review prompt template
    ├── methodology.md                        # the seven-step brainstorming flow (this file points to it)
    └── failure-modes.md                      # FULL / DEGRADED / ABORTED end-state contract
```

Heavy detail lives in `references/`. SKILL.md keeps the orchestration contract.

## Pipeline

### Step 0 — Mode prompt (one question at the very start)

Before anything else, ask the user how they want codex findings handled:

```
AskUserQuestion:
  question: "After codex reviews the written spec, how do you want findings applied?"
  options:
    - label: "Auto-apply"
      description: "Codex's suggestions are applied via Edit. You review one consolidated diff before commit."
    - label: "Per-finding"
      description: "I show you each finding individually. For each, you choose apply / skip / clarify."
```

Capture the answer as `$AUTO_APPLY` (`Y` for auto, `N` for per-finding). Both modes still have a final user gate before commit — auto is faster, per-finding is more granular.

### Step 0.5 — Capture baseline state

```bash
START_SHA=$(git rev-parse HEAD)
SPEC_FILE=""        # populated in methodology Step 5; used by spec-complete hook
```

`START_SHA` is only consumed by the discovery fallback (Step 8.A), but capturing it now is cheap insurance.

### Steps 1–7 — Brainstorming methodology (inline)

Follow `references/methodology.md` end-to-end. The seven steps are:

1. **Explore project context** (git log, CLAUDE.md, recent specs, grep)
2. **Ask clarifying questions** one at a time (multi-choice via `AskUserQuestion` preferred)
3. **Propose 2-3 approaches** with tradeoffs and a recommendation
4. **Present design in sections**, get user approval per section
5. **Write spec** to `docs/superpowers/specs/<YYYY-MM-DD>-<topic>-design.md`. **Capture `SPEC_FILE` as the path you wrote.**
6. **Inline self-review** (placeholders, contradictions, scope, ambiguity)
7. **Commit spec** as `spec(planner): <topic-slug>`

If the user aborts at any step before commit, exit with the **✗ ABORTED** end state (Step 9.C below).

### Step 8 — Spec-complete codex hook

After Step 7 commits the spec, run codex review.

#### 8.A — Resolve `SPEC_FILE` (with fallback)

```bash
if [ -z "$SPEC_FILE" ] || [ ! -f "$SPEC_FILE" ]; then
  # Fallback: only if SPEC_FILE was lost (off-script user, planner resumed).
  # Combined committed + unstaged + untracked scan. Caller filters + prompts on ambiguity.
  CANDIDATES=$(./scripts/discover-artifacts.sh "$START_SHA")
  SPEC_FILE=$(echo "$CANDIDATES" | grep -E '/specs?/.*\.md$' | head -1)
  [ -z "$SPEC_FILE" ] && SPEC_FILE=$(echo "$CANDIDATES" | grep -iE '(design|spec)\.md$' | head -1)

  # Multiple matches OR empty: prompt user to pick from CANDIDATES via AskUserQuestion.
  # Don't guess silently. If user can't disambiguate → ABORT.
fi
```

Normal flow uses the captured path from methodology Step 5 — discovery is for the corner case where SPEC_FILE was lost.

#### 8.B — Run `codex-review.sh`

```bash
SKILL_DIR="skills/planner"
[ -d "$SKILL_DIR/scripts" ] || SKILL_DIR="$(git rev-parse --show-toplevel)/skills/planner"

set +e
"$SKILL_DIR/scripts/codex-review.sh" spec-complete "$SPEC_FILE"
HOOK_EXIT=$?
set -e
```

Codex output goes to `.lifeline-planner/spec-complete-review.md`. The script's exit code routes the next step:
- `0` → FULL path (Step 8.C)
- `124` → DEGRADED (codex timed out)
- non-zero → DEGRADED (codex unavailable, exit error, or empty output)

See `references/failure-modes.md` for the full contract.

#### 8.C — FULL path (codex returned non-empty review)

Read the review markdown:

```bash
REVIEW_MD=".lifeline-planner/spec-complete-review.md"
```

Show the review to the user, then:

**Auto-apply mode (`$AUTO_APPLY = Y`)**:
1. Read each `[HIGH]` / `[MEDIUM]` finding in `REVIEW_MD`.
2. Apply each as `Edit` operations on `$SPEC_FILE`. (For findings that don't translate to a single mechanical edit — e.g., "this section needs more detail on X" — surface them as comments to the user with a suggested edit, ask for confirmation.)
3. Show the user one consolidated `git diff $SPEC_FILE` covering all changes.
4. Ask: "Apply these changes? [Y/n]"
5. If approved: commit with `git commit -am "review(planner): apply codex feedback to spec"`. If declined: skip the iteration commit, treat as DEGRADED with reason "user declined codex iterations".

**Per-finding mode (`$AUTO_APPLY = N`)**:
1. For each finding in severity order (HIGH → MEDIUM → LOW): show it, then `AskUserQuestion`:
   - `Apply` → run the Edit, stage it
   - `Skip` → move on
   - `Clarify` → ask the user what they want to do (free-text); apply their decision
2. After all findings: if anything was applied, commit with the same message.

After the iteration commit (or after "no findings — spec is implementation-ready"), append the codex-reviewed footer:

```bash
"$SKILL_DIR/scripts/update-footer.sh" "$SPEC_FILE"
git add "$SPEC_FILE"
git commit -m "spec(planner): mark spec codex-reviewed"
```

(The footer commit is separate from the iteration commit so the iteration history shows what changed and why, while the footer commit records the review status as its own atomic event.)

#### 8.D — DEGRADED path (codex hook failed)

Do NOT retry. Do NOT block. Print a prominent warning naming:
- The spec path
- The reason (extracted from `.lifeline-planner/spec-complete-stderr.log` or the exit code)
- The manual recovery command:
  ```
  scripts/codex-review.sh spec-complete <SPEC_FILE>
  ```

**No footer is appended.** The absence of the footer is the load-bearing "this is unreviewed" signal.

### Step 9 — Final summary

Print a 4-line status block:

```
spec: ✓ FULL  | ⚠ DEGRADED  | ✗ ABORTED
path: <SPEC_FILE>
reason: <one-line, only present for DEGRADED or ABORTED>
next: run /superpowers:writing-plans against this spec when ready
```

Exit code:
- `0` for FULL or DEGRADED (the spec exists and is the user's to act on)
- non-zero for ABORTED (no spec was produced)

## What planner does NOT do (v1 boundaries)

- **Does not invoke `superpowers:writing-plans`.** The plan is the user's next step. Codex review of the plan is deferred to v2.
- **Does not invoke `superpowers:brainstorming` as a skill.** It would chain to writing-plans. The methodology is followed inline (see `references/methodology.md`).
- **Does not run codex on individual sections.** Per-section review would require either forking brainstorming or a fragile instruction-override. Reviews happen on the WHOLE spec after Step 7.
- **Does not retry codex hooks.** Codex unavailability is treated as a degraded end state, not a failure to recover.
- **Does not edit the spec's frontmatter.** Existing specs in most projects don't have YAML frontmatter; the codex-reviewed marker is an HTML-comment footer at end-of-file (see `scripts/update-footer.sh`).

## v2 paths (briefly noted, not implemented)

- **Companion `/lifeline:review-doc <path>`** — pure post-hoc codex review on any markdown file. User invokes after `/superpowers:writing-plans` returns. Smallest implementation surface for plan-side review.
- **`/lifeline:planner --plan-mode <spec-path>`** — symmetric to v1: a self-contained writing-plans methodology + codex review, mirroring this file.

Either becomes the v2 entry point when v1 spec-side proves stable.

## Notes

- **Codex CLI flag verification date: May 2026.** If `codex exec` changes its flag set (e.g., renames `--output-last-message`), this skill breaks. The invocation is centralized in `scripts/codex-review.sh` for one-place updates.
- **`LIFELINE_CODEX_TIMEOUT` env var** overrides the default 300s codex timeout. Tests use this to force the DEGRADED-on-timeout path.
- **Generic-noun "harness" in upstream prose** (e.g., "harness/agent timeout" comments in `upsource-review/scripts/verify.sh`) is intentionally left as-is throughout lifeline — refers to the wrapper concept, not the plugin name.
