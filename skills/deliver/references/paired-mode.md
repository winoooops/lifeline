# /lifeline:deliver — paired mode

You arrived here because Step 0 of `SKILL.md` set `$MODE = paired`. The variables `$OBJECTIVE`, `$CAP`, `$ITER` (= 0), and `$START_TS` (Unix seconds, captured in Step 1 of `SKILL.md`) are already in your reasoning context.

Paired mode delegates each iteration's "is the objective complete?" decision to `codex exec` running as an independent grader. The grader sees only the objective + current repo evidence — never your conversation history. This mirrors Anthropic's Outcomes pattern and is the whole point of paired mode: an external judge mitigates the confirmation bias of self-audit.

> **Reminder — Bash state does not persist between tool calls.** Carry literal values (paths, timestamps) forward in your reasoning context and interpolate them as strings into every Bash call.

## Step 1: Initialize scratch + resolve skill dir

Run via the Bash tool. Resolution is **inline** here (not via the resolver script) because when the skill runs as an installed plugin in a target repo, `$REPO_ROOT/skills/deliver/scripts/resolve-skill-dir.sh` does not exist — the skill files live in the plugin cache, not in the user's repo. The resolver-script call has a chicken-and-egg problem; inlining the same lookup avoids it.

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
# with the sentinel string and then control `grader-prompt.md` /
# `grader-output.json`, biasing every paired-mode verdict to
# `complete: true` silently. There is no robust way to verify a
# workspace is the lifeline checkout from inside a workspace-resident
# file. So we simply don't look at the workspace.
#
# **Lifeline developers** working on the deliver skill set
# `LIFELINE_SKILL_DIR=$(pwd)/skills/deliver` (or the absolute equivalent)
# in their shell to make local edits effective without re-syncing the
# plugin cache after every change.
SKILL_DIR=""
if [ -n "${LIFELINE_SKILL_DIR:-}" ] && [ -f "$LIFELINE_SKILL_DIR/schemas/grader-output.json" ]; then
  SKILL_DIR="$LIFELINE_SKILL_DIR"
else
  _cache="$HOME/.claude/plugins/cache/lifeline/lifeline"
  if [ -d "$_cache" ]; then
    # Newest-installed wins. Use mtime ordering (portable) instead of
    # `sort -V` which is GNU-only and missing on default macOS/BSD.
    _latest=$(ls -1t "$_cache" 2>/dev/null | head -1)
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
# Tracked-file diff. `git diff HEAD` omits untracked file CONTENTS — for
# objectives that create new files, the grader otherwise sees only the
# filename and can't verify what's inside. Augment the diff below with a
# no-index synthetic diff for each untracked file.
GIT_DIFF_HEAD=$(git diff HEAD 2>/dev/null || true)
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null || true)
GIT_STATUS=$(git status --short 2>/dev/null || true)
FILES_TOUCHED="<bulleted list you maintained mentally — or empty if you did not track. For out-of-repo objectives, include the full path here so the grader knows where to inspect>"

# UNTRACKED_INCLUDE — bash array of paths whose CONTENT (not just
# filename) the grader needs to see. The agent populates this each
# iteration based on the objective. Default is EMPTY: by default the
# grader sees only filenames via {{ untracked_files }}, never bodies.
#
# Why opt-in (not auto-dump everything from `git ls-files --others`)?
# Auto-dump leaks any unrelated untracked content that happens to sit in
# the working tree (.env files, scratch dumps, generated build output,
# secrets-in-progress) to the codex grader on every iteration. Worse,
# large untracked files would also blow up the prompt and may exceed
# codex's input limits.
#
# Set explicitly: UNTRACKED_INCLUDE=(src/foo.py /tmp/output.html)
UNTRACKED_INCLUDE=("${UNTRACKED_INCLUDE[@]:-}")

# Per-file size cap (64 KB) prevents a single large untracked file from
# overwhelming the prompt even when the agent did opt to include it.
_MAX_UNTRACKED_BYTES=65536
for _f in "${UNTRACKED_INCLUDE[@]}"; do
  [ -z "$_f" ] && continue
  [ -f "$_f" ] || continue
  # Skip if size cannot be determined (unreadable, ENXIO, etc.). Earlier
  # version used `|| echo "$_MAX_UNTRACKED_BYTES"` here which then
  # failed the `-gt $_MAX_UNTRACKED_BYTES` check (equality is not
  # greater) and the file fell through to a silent empty diff entry.
  if ! _sz=$(wc -c < "$_f" 2>/dev/null); then
    GIT_DIFF_HEAD+=$'\n'"--- skipped (unreadable): $_f"$'\n'
    continue
  fi
  if [ "$_sz" -gt "$_MAX_UNTRACKED_BYTES" ]; then
    GIT_DIFF_HEAD+=$'\n'"--- skipped (>${_MAX_UNTRACKED_BYTES}B): $_f"$'\n'
    continue
  fi
  GIT_DIFF_HEAD+=$'\n'
  GIT_DIFF_HEAD+=$(git diff --no-index --no-color /dev/null -- "$_f" 2>/dev/null || true)
done

# Render the grader template via a single-pass Python substitution.
#
# An earlier version of this used five sequential `${PROMPT//pat/repl}`
# bash expansions. That has a cross-injection bug: if $OBJECTIVE (or any
# evidence value) contains the literal text of a later placeholder
# — e.g. an objective of "Implement {{ git_diff_head }} parser" — that
# text survives the first substitution and gets replaced with real
# evidence in a subsequent pass, smuggling content from one slot into
# another. Python's str.replace runs once per placeholder against the
# ORIGINAL template buffer, so values introduced by one substitution are
# never re-matched.
# Render via files, not env vars. Env vars (along with argv) count
# toward Linux ARG_MAX (~2 MB), so a large GIT_DIFF_HEAD passed as
# ENV would fail python3's exec() before any rendering happened. The
# stdin path below for codex exec is the same fix applied at the
# next layer.
RENDER_DIR="$SCRATCH/render-input-$ITER"
mkdir -p "$RENDER_DIR"
printf '%s' "$OBJECTIVE"      > "$RENDER_DIR/objective"
printf '%s' "$GIT_DIFF_HEAD"  > "$RENDER_DIR/git_diff_head"
printf '%s' "$UNTRACKED"      > "$RENDER_DIR/untracked"
printf '%s' "$GIT_STATUS"     > "$RENDER_DIR/git_status"
printf '%s' "$FILES_TOUCHED"  > "$RENDER_DIR/files_touched"

PROMPT_FILE="$SCRATCH/grader-$ITER.prompt"
: > "$PROMPT_FILE"   # truncate so a stale file doesn't masquerade as success
if GRADER_TEMPLATE="$GRADER_TEMPLATE" RENDER_DIR="$RENDER_DIR" \
   python3 - > "$PROMPT_FILE" 2>"$SCRATCH/grader-$ITER.render-stderr" <<'PY'
import os, re
d = os.environ['RENDER_DIR']
template = open(os.environ['GRADER_TEMPLATE']).read()
mapping = {
    '{{ objective }}':       open(f"{d}/objective").read(),
    '{{ git_diff_head }}':   open(f"{d}/git_diff_head").read(),
    '{{ untracked_files }}': open(f"{d}/untracked").read(),
    '{{ git_status }}':      open(f"{d}/git_status").read(),
    '{{ files_touched }}':   open(f"{d}/files_touched").read(),
}
pattern = re.compile('|'.join(re.escape(k) for k in mapping))
print(pattern.sub(lambda m: mapping[m.group(0)], template), end='')
PY
then : ; fi

# Fail fast on render failure (python3 missing, template missing, etc.).
# Without this guard, an empty prompt would be sent to codex and the
# grader would judge against nothing — silently losing the iteration's
# evidence and likely returning complete=false (or worse, complete=true
# on a vacuous prompt).
if [ ! -s "$PROMPT_FILE" ]; then
  echo "WARN: grader prompt rendering failed (python3 unavailable, template missing, or render error). See $SCRATCH/grader-$ITER.render-stderr." >&2
  CODEX_EXIT=99   # synthetic — routes through the grader-fallback branch below
fi

# GNU `timeout` is optional on some systems (BSD/macOS without coreutils,
# minimal containers). Conditionally apply it; without timeout the existing
# Codex CLI behavior still applies — codex itself exits eventually.
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_PREFIX="timeout 300"
else
  TIMEOUT_PREFIX=""
fi

if [ "${CODEX_EXIT:-0}" -ne 99 ]; then
  # Pass the prompt via stdin (`- ` positional). Linux ARG_MAX (~2 MB
  # total argv+env) caps how large a single CLI argument can be; a
  # non-trivial prompt (full git diff plus opted-in untracked file
  # bodies plus the template) easily exceeds this. Stdin has no
  # ARG_MAX limit. The prompt was already written to $PROMPT_FILE
  # above by the file-based renderer.
  #
  # `--ephemeral` keeps the grader transcript out of $CODEX_HOME. The
  # prompt contains the full diff and any opted-in untracked file
  # bodies, so persisting the session would leak repo evidence to
  # disk — directly contradicting the no-persistent-state contract
  # ($SCRATCH cleanup is meaningless if codex still wrote the same
  # data to ~/.codex/).
  set +e
  $TIMEOUT_PREFIX codex exec \
    --sandbox read-only \
    --ephemeral \
    --output-schema "$SCHEMA_PATH" \
    --output-last-message "$SCRATCH/grader-$ITER.json" \
    -- - \
    < "$PROMPT_FILE" \
    > "$SCRATCH/grader-$ITER.events.log" \
    2> "$SCRATCH/grader-$ITER.stderr.log"
  CODEX_EXIT=$?
  set -e
fi
```

Parse the verdict. Validate JSON parseability **before** asking jq for `.complete` — `set -e` would otherwise abort the whole bash step on malformed grader output, bypassing the fallback path. **The block must `echo` the verdict** — it runs in the same Bash tool call as the codex invocation above so `$CODEX_EXIT` is in scope, but every parsed value (`VERDICT`, evidence, missing requirements) must be printed to stdout because Bash variables don't survive into the next Bash tool call. The agent reads the printed values out of stdout and carries them forward in its reasoning context:

```bash
# This block must run in the SAME Bash tool call as the codex exec above
# (so $CODEX_EXIT and $SCRATCH/$ITER are still in scope) and must `echo`
# every parsed value — Bash variables disappear when the tool call ends.

VERDICT_SOURCE="grader"  # how this iteration completed (or didn't)
VERDICT="incomplete"

if [ "$CODEX_EXIT" -eq 0 ] && [ -s "$SCRATCH/grader-$ITER.json" ] \
   && jq -e '
       type == "object"
       and (.complete | type == "boolean")
       and (.missing_requirements | type == "array")
       and (.evidence_checked | type == "array")
     ' "$SCRATCH/grader-$ITER.json" >/dev/null 2>&1; then
  # JSON is valid AND matches the schema (object with the three expected
  # fields of the right types). `jq empty` was too lenient — it accepts
  # `true`, `[]`, `"hi"`, or `{"complete":"true"}` (string instead of
  # bool), which would either error under set -e or pass through with the
  # wrong verdict. Schema validation here routes those cases through the
  # grader-fallback branch.
  COMPLETE=$(jq -r '.complete' "$SCRATCH/grader-$ITER.json")
  if [ "$COMPLETE" = "true" ]; then
    VERDICT="complete"
    echo "VERDICT=complete"
    echo "VERDICT_SOURCE=$VERDICT_SOURCE"
    echo "EVIDENCE_CHECKED:"
    jq -r '.evidence_checked[]? | "  - \(.)"' "$SCRATCH/grader-$ITER.json"
    # → go to Step 3 (success)
  else
    echo "VERDICT=incomplete"
    echo "VERDICT_SOURCE=$VERDICT_SOURCE"
    echo "MISSING_REQUIREMENTS:"
    jq -r '.missing_requirements[]? | "  - \(.)"' "$SCRATCH/grader-$ITER.json"
    # → take the next concrete action next iteration
  fi
else
  VERDICT_SOURCE="self-audit-fallback"
  echo "VERDICT=grader_unusable (codex_exit=$CODEX_EXIT, file empty/malformed)" >&2
  echo "VERDICT_SOURCE=$VERDICT_SOURCE"
  echo "FALLBACK: apply continuation.md audit checklist to your last action this iteration"
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
