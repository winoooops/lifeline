# Planner failure modes and end states

`/lifeline:planner` produces an end state for **each artifact** it
touches. Per-run, the artifacts are:

- The **spec** (always, when the run reaches Step 7).
- The **plan** (only when the user opted into Step 9 plan generation).

Each artifact independently lands in one of: `FULL`, `DEGRADED`, or
`ABORTED`. The plan side adds one more state, `PARTIAL_PLAN`, for the
case where the plan was written but the reviewer never ran (because
`/superpowers:writing-plans` chained onward into execution despite our
stop-after-write instruction). Each end state is observable in metadata
so a consumer (or future session) can tell what actually happened.

## End-state taxonomy

### ✓ FULL

**Means**: spec written + committed by Step 7 of the methodology, the
spec-complete codex hook returned non-empty review markdown, the user
either approved found-and-applied iterations or codex returned no
findings, the iteration commit (if any) landed, and the HTML-comment
footer was appended:

```html
<!-- codex-reviewed: 2026-05-04T14:32:11Z -->
```

**Surfaced as**: green check in the planner's final summary. Footer
present in the spec file.

**Consumer signal**: `grep -l 'codex-reviewed:' <spec-path>` returns
the path.

### ⚠ DEGRADED

**Means**: spec written + committed (Step 7 succeeded), but the
spec-complete hook failed for one of these reasons:

- `codex` binary not found on `$PATH` (pre-flight check before invoke)
- `timeout` fired (`exit 124` from `codex-review.sh`)
- codex exited non-zero
- codex exited 0 but wrote no output (caught by the empty-result
  guard in `codex-review.sh`)
- user explicitly skipped the review (e.g., declined the prompt)

**No retry. No blocking. No footer.**

**Surfaced as**: yellow warning in the planner's final summary,
naming:
- the spec path that is unreviewed
- the underlying reason (extracted from `codex-review.sh`'s stderr)
- a suggested manual recovery: re-run `scripts/codex-review.sh
  spec-complete <path>` directly, or invoke `/lifeline:planner` again
  to re-iterate from scratch (the spec already exists, so this would
  re-run brainstorming — wasteful unless the user wants to amend the
  design itself)

**Consumer signal**: footer ABSENT from the spec file. The presence of
the spec without the footer is the load-bearing "this is unreviewed"
indicator.

### ✗ ABORTED

**Means**: the methodology never reached Step 7. Possible causes:

- User aborted during clarifying questions (Step 2)
- User aborted during section approval (Step 4)
- An unrecoverable error during spec write or commit (Step 5 or 7)

**Surfaced as**: red X in the planner's final summary, with the step
that aborted and a one-line reason. Planner exits non-zero so callers
(scripts, harness loops) can detect the failure programmatically.

**Consumer signal**: no spec file exists at the discovery path (or the
file exists but isn't committed — Step 5 wrote it but Step 7 never
ran).

### ⚠ PARTIAL_PLAN (plan side only)

**Means**: Step 9 invoked `/superpowers:writing-plans`, which wrote
and committed an implementation plan. But the skill chained onward
into an execution skill (e.g., `executing-plans`,
`subagent-driven-development`) despite the explicit stop-after-write
instruction in the invocation, so control never returned to planner
and codex never reviewed the plan.

**No retry. No blocking. No plan footer.**

**Surfaced as**: yellow warning in the planner's final summary, naming
the plan path and the manual recovery command:

```
$SKILL_DIR/scripts/codex-review.sh plan-complete <plan-path>
```

**Consumer signal**: plan file exists, but the codex-reviewed footer
is absent. Distinguishable from spec-side DEGRADED only by inspecting
which artifact is footer-less.

This state exists because the chain-on-completion behavior of
`/superpowers:writing-plans` is upstream — we ask it not to chain, but
some versions ignore the request. PARTIAL_PLAN is the explicit "the
plan is here, but we never got to review it" signal.

## Why DEGRADED doesn't retry

Three reasons:

1. **User flow priority**: the spec is the user-facing artifact. If
   codex is briefly unavailable, blocking the planner on a retry loop
   would be more disruptive than letting the user proceed with an
   unreviewed-but-flagged spec.
2. **Codex unavailability is usually persistent in a session**: if
   codex isn't on PATH, that won't change mid-session. Blocking is
   pointless.
3. **Manual recovery is one command**: the user can re-run
   `scripts/codex-review.sh spec-complete <spec-path>` later. The
   degraded warning prints this command verbatim.

## Why the footer is the source of truth

Three things could go wrong:
- Planner crashes during the final-summary print
- Planner reports FULL but the iteration commit silently failed
- Future session inspects the spec and wonders if it was reviewed

The HTML-comment footer is appended ONLY in the FULL path, ONLY after
the iteration commit (if any) lands. It's the post-condition check.
Anything else can lie; the footer can't (assuming the planner code is
not buggy at the very last step — and that step is one `printf` away
from observable disk state).

`grep -L 'codex-reviewed:' docs/superpowers/specs/*.md` finds all
unreviewed specs across a project — the inverse-grep is how you'd
audit a backlog.

## Footer hygiene

- The footer is **idempotent**: re-running the planner on the same
  spec replaces the timestamp rather than accumulating multiple
  footer lines (see `scripts/update-footer.sh`).
- The footer uses **HTML comment syntax** so it's invisible in
  rendered Markdown — no display change to existing docs.
- The footer carries **only an ISO-8601 UTC timestamp**, NOT the
  model name. The actual model that `codex exec` uses depends on auth
  mode and codex CLI version; hardcoding a model name would lie. The
  timestamp is truthful and useful for staleness detection.
