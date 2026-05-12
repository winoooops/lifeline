# /lifeline:deliver — pure mode

You arrived here because Step 0 of `SKILL.md` set `$MODE = pure`. The variables `$OBJECTIVE`, `$CAP`, `$ITER` (= 0), and `$START_TS` (Unix seconds, captured in Step 1 of `SKILL.md`) are already in your reasoning context.

Pure mode runs the loop entirely inside Claude — no external grader, no codex subprocess. Each iteration's audit is self-administered against the checklist in `references/continuation.md`.

> **Reminder — Bash state does not persist between tool calls.** Carry literal values (paths, timestamps) forward in your reasoning context and interpolate them as strings into every Bash call.

## Step 1: Resolve skill dir

Resolution is **inline** here (not via the resolver script) for the same reason `paired-mode.md` inlines it: when the skill runs as an installed plugin in a target repo, `$REPO_ROOT/skills/deliver/scripts/resolve-skill-dir.sh` does not exist — the skill files live in the plugin cache. Without `$SKILL_DIR`, the per-iteration `Read` of `references/continuation.md` would silently miss the file and pure mode would loop without the audit checklist.

Pure mode uses a `$SCRATCH` directory only for code-rendered prompt templates.
It does not store grader JSON, event logs, or evidence inputs. The scratch
directory is deleted on success and on budget-limited wrap-up.

```bash
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
#
# ──────────────────────────────────────────────────────────────────────
# MIRROR OF skills/deliver/scripts/resolve-skill-dir.sh — keep in sync.
# Same lookup logic also lives in paired-mode.md Step 1. When changing
# any of these (sentinel filename, ordering, .DS_Store filter, etc.)
# update all THREE copies. Guarded by harness/test_deliver_resolver_mirrors.py.
# ──────────────────────────────────────────────────────────────────────
# BEGIN RESOLVER
SKILL_DIR=""
version_key() {
  local _major _minor _patch _rest
  IFS=. read -r _major _minor _patch _rest <<< "$1"
  case "$_major" in ""|*[!0-9]*) _major=0 ;; esac
  case "$_minor" in ""|*[!0-9]*) _minor=0 ;; esac
  case "$_patch" in ""|*[!0-9]*) _patch=0 ;; esac
  case "${_rest:-}" in
    "") _rest= ;;
    *[!0-9]*)
      echo "WARN: ignoring non-numeric fourth version component in cache entry: $1" >&2
      _rest=
      ;;
    *) _rest=$(printf '%010d' "$((10#$_rest))") ;;
  esac
  printf '%010d.%010d.%010d.%s\n' "$((10#$_major))" "$((10#$_minor))" "$((10#$_patch))" "${_rest:-}"
}
# Validity sentinel is `schemas/grader-output.json` for consistency with
# paired-mode.md and resolve-skill-dir.sh — the canonical "is this a
# real deliver skill dir?" check across the codebase. Pure mode doesn't
# use the schema itself, but a single sentinel everywhere means
# LIFELINE_SKILL_DIR has the same accept/reject semantics in both modes.
if [ -n "${LIFELINE_SKILL_DIR:-}" ]; then
  if [ -f "$LIFELINE_SKILL_DIR/schemas/grader-output.json" ]; then
    SKILL_DIR="$LIFELINE_SKILL_DIR"
  else
    echo "WARN: LIFELINE_SKILL_DIR set but sentinel missing at $LIFELINE_SKILL_DIR/schemas/grader-output.json; falling back to plugin cache" >&2
  fi
fi

if [ -z "$SKILL_DIR" ]; then
  _cache="$HOME/.claude/plugins/cache/lifeline/lifeline"
  if [ -d "$_cache" ]; then
    # Newest-installed wins by mtime, with a zero-padded version-key
    # tiebreaker for equal mtimes. Use Bash's portable -nt check instead
    # of `sort -V` (GNU-only, missing on default macOS/BSD). Enumerate
    # with null-delimited find output so directory names are not parsed
    # through `ls`; `-type d` filters files such as `.DS_Store`.
    _latest=""
    while IFS= read -r -d '' _entry_path; do
      _e=${_entry_path##*/}
      if [ ! -f "$_entry_path/skills/deliver/schemas/grader-output.json" ]; then
        echo "WARN: skipping cache entry missing sentinel: $_entry_path/skills/deliver/schemas/grader-output.json" >&2
        continue
      fi
      if [ -z "$_latest" ] || [ "$_entry_path" -nt "$_cache/$_latest" ]; then
        _latest="$_e"
      elif [ ! "$_cache/$_latest" -nt "$_cache/$_e" ] \
        && [ ! "$_entry_path" -nt "$_cache/$_latest" ] \
        && [[ "$(version_key "$_e")" > "$(version_key "$_latest")" ]]; then
        _latest="$_e"
      fi
    done < <(find "$_cache" -maxdepth 1 -mindepth 1 -type d -print0 2>/dev/null)
    if [ -n "$_latest" ]; then
      SKILL_DIR="$_cache/$_latest/skills/deliver"
    fi
  fi
fi

if [ -z "$SKILL_DIR" ]; then
  echo "ERROR: could not resolve skills/deliver. Required sentinel: schemas/grader-output.json; runtime templates also require references/continuation.md and references/budget_limit.md. Set LIFELINE_SKILL_DIR or install the plugin via /plugin install lifeline." >&2
  exit 1
fi
# END RESOLVER

[ -f "$SKILL_DIR/references/continuation.md" ] || { echo "ERROR: continuation.md not found at $SKILL_DIR/references/continuation.md" >&2; exit 1; }
[ -f "$SKILL_DIR/references/budget_limit.md" ] || { echo "ERROR: budget_limit.md not found at $SKILL_DIR/references/budget_limit.md" >&2; exit 1; }
RENDER_TEMPLATE="$SKILL_DIR/scripts/render-template.sh"
[ -x "$RENDER_TEMPLATE" ] || { echo "ERROR: render-template.sh not executable at $RENDER_TEMPLATE" >&2; exit 1; }

# Paste the objective exactly as parsed in SKILL.md Step 0. Replace the
# single-quoted placeholder below with the exact objective as a Bash
# single-quoted literal. Single-quoted Bash strings may span lines;
# escape every literal single quote in the objective as: '\''. Do not
# use a here-doc; delimiter collisions can truncate objectives.
OBJECTIVE_RAW='__OBJECTIVE_SINGLE_QUOTED_PLACEHOLDER__'
if [ "$OBJECTIVE_RAW" = "__OBJECTIVE_SINGLE_QUOTED_PLACEHOLDER__" ]; then
  echo "ERROR: replace the objective single-quoted placeholder before running pure mode Step 1." >&2
  exit 1
fi
OBJECTIVE_HTML=$(printf '%s' "$OBJECTIVE_RAW" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g')
SCRATCH=$(mktemp -d -t lifeline-deliver-pure-XXXXXX)
OBJECTIVE_HTML_FILE="$SCRATCH/objective.html"
printf '%s' "$OBJECTIVE_HTML" > "$OBJECTIVE_HTML_FILE" || { echo "ERROR: failed to write objective HTML at $OBJECTIVE_HTML_FILE" >&2; exit 1; }

ITER=0   # explicit initial value; echoed so the first loop has the
         # same mechanical counter handoff as subsequent Step 2d echoes.

echo "SCRATCH=$SCRATCH"
echo "SKILL_DIR=$SKILL_DIR"
echo "RENDER_TEMPLATE=$RENDER_TEMPLATE"
echo "OBJECTIVE_HTML_FILE=$OBJECTIVE_HTML_FILE"
echo "ITER=$ITER"
```

Capture `SCRATCH`, `SKILL_DIR`, `RENDER_TEMPLATE`, `OBJECTIVE_HTML_FILE`, and `ITER` from this call's stdout. Use those literal values in every subsequent Bash call. Do not substitute `{{ objective }}` manually; every continuation and budget-limit prompt must be rendered through `RENDER_TEMPLATE`, which reads the code-generated `OBJECTIVE_HTML_FILE`. Use the captured `ITER` as the source of truth for loop placeholders and budget checks until Step 2d echoes the next value. `$SKILL_DIR` is read-only — pure mode writes only inside `$SCRATCH`.

If `$SKILL_DIR` is empty, **report a startup error and stop**. Continuing without it would mean every iteration silently fails to load the audit checklist.

## Step 2: The loop

While `ITER < CAP`:

### 2a. Read continuation template

Render the continuation template into `$SCRATCH`, then read the rendered file. Rehydrate the captured values literally:

```bash
ITER=<paste the literal ITER value from Step 1 or the previous Step 2d echo, e.g. ITER=0 or ITER=2>
CAP=<paste the literal CAP value from SKILL.md Step 0, e.g. CAP=20>
SCRATCH=<paste the literal SCRATCH value from Step 1>
SKILL_DIR=<paste the literal SKILL_DIR value from Step 1>
RENDER_TEMPLATE=<paste the literal RENDER_TEMPLATE value from Step 1>
OBJECTIVE_HTML_FILE=<paste the literal OBJECTIVE_HTML_FILE value from Step 1>
: "${ITER:?ITER must be rehydrated before rendering continuation.md}"
: "${CAP:?CAP must be rehydrated from SKILL.md Step 0}"
: "${SCRATCH:?SCRATCH must be rehydrated from Step 1 echo}"
: "${SKILL_DIR:?SKILL_DIR must be rehydrated from Step 1 echo}"
: "${RENDER_TEMPLATE:?RENDER_TEMPLATE must be rehydrated from Step 1 echo}"
: "${OBJECTIVE_HTML_FILE:?OBJECTIVE_HTML_FILE must be rehydrated from Step 1 echo}"

CONTINUATION_RENDERED="$SCRATCH/continuation-$ITER.rendered"
"$RENDER_TEMPLATE" \
  "$SKILL_DIR/references/continuation.md" \
  "$OBJECTIVE_HTML_FILE" \
  "$CONTINUATION_RENDERED" \
  --iter-used "$ITER" \
  --iter-budget "$CAP" \
  --iter-remaining "$((CAP - ITER))" || exit 1
echo "CONTINUATION_RENDERED=$CONTINUATION_RENDERED"
```

Read the rendered file path printed after `CONTINUATION_RENDERED=`. Do not read `continuation.md` directly and do not perform in-context placeholder substitution. The rendered continuation prompt is the audit checklist you must apply this iteration. Keep it in your reasoning context until 2c.

### 2b. Take the next concrete action

Use `Edit` / `Write` / `Bash` / `Read` / etc. against the objective. **One action per iteration.** Do not batch multiple unrelated changes. The action is the only productive work this iteration; the audit (2c) is verification, not new work.

### 2c. Self-audit

Apply the checklist from continuation.md to the action you just took:

- Restate the objective as concrete deliverables.
- Map every requirement to inspectable evidence (a file, command output, test result, etc.).
- Inspect the actual evidence. Do **not** treat partial progress, "looks correct," or proxy signals (passing tests, complete manifest, substantial effort) as completion unless they cover every requirement.
- Treat uncertainty as **not done** — if anything is missing, incomplete, or unverified, continue the loop.

If the audit returns **complete**, jump to Step 3 (success) — **do not execute Step 2d**. Otherwise, continue. (Without the explicit "do not execute Step 2d" guard, an LLM following sections sequentially would increment `ITER` first, inflating the iteration count in the success report by 1.)

### 2d. Increment

Rehydrate `ITER` from the last echo, increment, then echo the new value. This mirrors paired mode's counter handoff and keeps budget enforcement mechanical across Bash tool-call boundaries.

```bash
ITER=<paste the literal ITER value from Step 1 or the previous Step 2d echo, e.g. ITER=0 or ITER=2>
: "${ITER:?ITER must be rehydrated from Step 1 or previous Step 2d echo}"
ITER=$((ITER + 1))
echo "ITER=$ITER"
```

Capture the printed `ITER`. If `ITER < CAP`, loop back to 2a and use that captured value when rendering the next continuation prompt.

## Step 3: Final report

Compute elapsed time. `START_TS` was echoed by `SKILL.md` Step 1; **rehydrate it from the literal value you captured then** (Bash variables don't survive across tool calls — that's why the dispatcher printed it for you to remember):

```bash
START_TS=<paste the literal Unix-seconds value SKILL.md Step 1 printed>
: "${START_TS:?START_TS must be rehydrated from SKILL.md Step 1 echo}"
END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
MINS=$((ELAPSED / 60))
SECS=$((ELAPSED % 60))
echo "ELAPSED=${MINS}m ${SECS}s"
```

Capture the value after `ELAPSED=` for the `<MINS>m <SECS>s` placeholders.

### Success path

When the audit returns complete, compute the success-only iteration count, delete the pure-mode scratch directory, then stop emitting tool calls and emit:

```bash
ITER=<paste the literal ITER value from Step 1 or the previous Step 2d echo>
SCRATCH=<paste the literal SCRATCH value from Step 1>
: "${ITER:?ITER must be rehydrated before computing the success report}"
: "${SCRATCH:?SCRATCH must be rehydrated before cleanup}"
SUCCESS_ITERATIONS=$((ITER + 1))
echo "SUCCESS_ITERATIONS=$SUCCESS_ITERATIONS"
if [[ -n "$SCRATCH" && "$SCRATCH" == *"/lifeline-deliver-pure-"* ]]; then
  rm -rf "$SCRATCH"
else
  echo "WARN: $SCRATCH does not contain '/lifeline-deliver-pure-' — skipping cleanup to avoid destroying the wrong path." >&2
fi
```

Capture the value after `SUCCESS_ITERATIONS=` for the success report.

```
Deliveries done in <MINS>m <SECS>s.
status: success
mode: pure
iterations: <SUCCESS_ITERATIONS>
elapsed: <MINS>m <SECS>s
evidence_checked:
  - <each item from your audit notes>
```

### Budget-limited path

When `ITER == CAP` without a complete verdict, render `$SKILL_DIR/references/budget_limit.md` through the same code path and use the rendered file for one wrap-up turn. The renderer supplies `{{ objective }}` from `OBJECTIVE_HTML_FILE`, `{{ iter_used }}` from `ITER`, `{{ iter_budget }}` from `CAP`, and `{{ iter_remaining }}` from `$((CAP - ITER))`:

```bash
ITER=<paste the literal ITER value from the final Step 2d echo; it must equal CAP>
CAP=<paste the literal CAP value from SKILL.md Step 0, e.g. CAP=20>
SCRATCH=<paste the literal SCRATCH value from Step 1>
SKILL_DIR=<paste the literal SKILL_DIR value from Step 1>
RENDER_TEMPLATE=<paste the literal RENDER_TEMPLATE value from Step 1>
OBJECTIVE_HTML_FILE=<paste the literal OBJECTIVE_HTML_FILE value from Step 1>
: "${ITER:?ITER must be rehydrated before rendering budget_limit.md}"
: "${CAP:?CAP must be rehydrated from SKILL.md Step 0}"
: "${SCRATCH:?SCRATCH must be rehydrated from Step 1 echo}"
: "${SKILL_DIR:?SKILL_DIR must be rehydrated from Step 1 echo}"
: "${RENDER_TEMPLATE:?RENDER_TEMPLATE must be rehydrated from Step 1 echo}"
: "${OBJECTIVE_HTML_FILE:?OBJECTIVE_HTML_FILE must be rehydrated from Step 1 echo}"

BUDGET_LIMIT_RENDERED="$SCRATCH/budget-limit.rendered"
"$RENDER_TEMPLATE" \
  "$SKILL_DIR/references/budget_limit.md" \
  "$OBJECTIVE_HTML_FILE" \
  "$BUDGET_LIMIT_RENDERED" \
  --iter-used "$ITER" \
  --iter-budget "$CAP" \
  --iter-remaining "$((CAP - ITER))" || exit 1
echo "BUDGET_LIMIT_RENDERED=$BUDGET_LIMIT_RENDERED"
```

Read the rendered file path printed after `BUDGET_LIMIT_RENDERED=`. Do not read `budget_limit.md` directly and do not perform in-context placeholder substitution. After the wrap-up audit, delete the pure-mode scratch directory:

```bash
SCRATCH=<paste the literal SCRATCH value from Step 1>
: "${SCRATCH:?SCRATCH must be rehydrated before cleanup}"
if [[ -n "$SCRATCH" && "$SCRATCH" == *"/lifeline-deliver-pure-"* ]]; then
  rm -rf "$SCRATCH"
else
  echo "WARN: $SCRATCH does not contain '/lifeline-deliver-pure-' — skipping cleanup to avoid destroying the wrong path." >&2
fi
```

Then emit:

```
Deliveries halted at iteration cap (<MINS>m <SECS>s elapsed).
status: budget_limited
mode: pure
iterations: <CAP>
elapsed: <MINS>m <SECS>s
missing_requirements:
  - <each item from the wrap-up audit>
```

(Pure mode uses `$SCRATCH` only for rendered prompt templates. Do not reference `$SCRATCH` in the pure-mode budget_limited report after cleanup.)

## Error handling

| Condition | Behavior |
|---|---|
| Empty objective | Already handled in `SKILL.md` Step 0 via `AskUserQuestion`. |
| Audit ambiguous about whether the objective is truly satisfied | Treat as not-done. Take another concrete verification action next iteration (e.g., re-read the file, run the test) instead of guessing. |
