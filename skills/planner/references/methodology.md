# Planner methodology — detailed brainstorming flow

This is the inline brainstorming methodology that `/lifeline:planner`
follows. It's adapted from `superpowers:brainstorming` (v5.0.7) but
restated here so planner doesn't have to invoke that skill (which would
chain to writing-plans automatically — see `failure-modes.md` for the
constraint that drove this self-contained design).

If the upstream `superpowers:brainstorming` evolves significantly,
re-read it and update this file. The spirit is: **understand intent,
explore alternatives, present design incrementally, get approval
section-by-section, write and self-review the spec.**

## The seven steps

### Step 1 — Explore project context

Before asking the user any questions:

- Run `git log --oneline -20` and `git status` to understand recent
  activity and current state.
- Read CLAUDE.md (project-level and the "memory" / dotted index) to
  surface conventions and pointers to related docs.
- Read any specs in `docs/superpowers/specs/` from the last 30 days —
  they often hold context the user assumes you have.
- For specific file/symbol questions, grep before asking.

If the request describes multiple independent subsystems (e.g., "build
a platform with X, Y, Z, billing, analytics"), STOP and decompose first
— don't try to spec the whole thing at once. Each sub-project gets its
own spec → plan → implementation cycle.

### Step 2 — Ask clarifying questions

One question at a time. Use `AskUserQuestion` with multiple-choice
options whenever feasible — it's faster for the user than open-ended.

Focus questions on:
- **Purpose**: what problem does this actually solve, and for whom?
- **Constraints**: deadlines, dependencies, resource limits.
- **Success criteria**: how will the user know this worked?

Avoid questions whose answers you can infer from the codebase. If you
already know the answer, state your assumption and move on.

#### Sizing AskUserQuestion options

Match option count to the real fork:

- **Two options** when the fork is binary (apply/skip, yes/no, A/B).
- **Three options** for a typical recommendation + alternative + "let
  me discuss".
- **Four options** only when there are genuinely four distinct paths.
  Don't pad to four to fill the slot — filler options bias the user
  and add noise.
- **More than four**: ask a filtering question first ("which axis
  matters most?"), then a follow-up with the surviving options. The
  `AskUserQuestion` tool itself caps at four.

Lead with the recommendation. The first option carries
"(Recommended)" when there is a clear default.

For substantive option choices (architecture forks, fix strategies),
render each option as an IDEA block (Intent / Danger / Explain /
Alternatives) before the `AskUserQuestion` call. The structured
comparison resolves choices faster than prose.

### Step 3 — Propose 2-3 approaches with tradeoffs

Once you understand the request, present 2-3 distinct ways to attack
it. For each: a one-line summary, the main tradeoff, and your
recommendation with reasoning. Lead with your recommendation.

If only one viable approach exists, say so explicitly — don't fabricate
alternatives.

### Step 4 — Present design in sections, get approval per section

Break the design into sections scaled to their complexity:
- **Architecture / data flow**: 100-200 words for non-trivial systems
- **Per-component contract**: smaller chunks
- **Failure modes**: explicit, not hand-waved
- **Testing approach**: what proves it works

After each section: stop and ask "does this look right?" Don't move on
until the user confirms or amends. Revisions are cheap; building on a
wrong section is expensive.

### Step 5 — Write spec to standard location

When all sections are approved:

```
docs/superpowers/specs/<YYYY-MM-DD>-<topic>-design.md
```

Use today's date. Topic slug should be hyphenated, lowercase, 2-5
words.

**CAPTURE the path as `SPEC_FILE`** in your working notes — the
spec-complete hook needs this. If the user has steered you to a
different path during the methodology (rare but allowed), use that —
just still capture it.

### Step 6 — Inline self-review

Read the just-written spec back with fresh eyes:

1. **Placeholder scan**: any TBD, TODO, vague "later", incomplete
   sections? Fix them inline.
2. **Internal consistency**: do sections contradict each other? Does
   the architecture match the feature descriptions?
3. **Scope check**: focused enough for one implementation plan?
4. **Ambiguity check**: any requirement interpretable two ways? Pick
   one and make it explicit.

Fix anything found. No need to re-review — just fix and move on.

### Step 7 — Commit the spec

```bash
git add "$SPEC_FILE"
git commit -m "docs(spec): <topic-slug>

<one-paragraph summary of what this spec defines>
"
```

The `docs(spec):` prefix passes `@commitlint/config-conventional`,
which is the default in most projects. If your project's commitlint
adds a custom `spec` type, swap to `spec(planner):` — but the default
is `docs(spec):`.

After this commit, the spec-complete hook (defined in SKILL.md) runs
codex review on `$SPEC_FILE`.

## What NOT to do during the methodology

- Don't invoke `superpowers:brainstorming` as a separate skill — it
  chains to writing-plans at its terminal state, which would derail
  planner's flow. Follow this methodology inline instead.
- Don't write the spec before getting per-section approval. Building on
  unconfirmed sections wastes work.
- Don't skip Step 6. The self-review catches placeholder leakage that
  the codex review would otherwise flag, costing you a re-iteration.
- Don't invoke `superpowers:writing-plans` after the spec is reviewed.
  The user runs that themselves — planner v1 is spec-only.
