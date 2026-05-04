---
name: approve-pr
description: Merge a PR end-to-end — squash + delete remote branch, sync local main, delete the local feature branch, and clean up associated git worktrees (safely; dirty/locked worktrees are preserved). Use when finishing a PR. Args - `Y` to skip confirmation (apt-style); optional PR number to target a specific PR (defaults to current branch's PR).
tools: Bash
---

# /approve-pr — Finish a PR end-to-end

Merge → delete remote branch → sync local main → delete local branch → reap worktrees, in one command.

## Invocation

```
/approve-pr               # current branch's PR, prompt to confirm
/approve-pr 112           # PR #112, prompt to confirm
/approve-pr Y             # current branch's PR, auto-confirm (apt-style)
/approve-pr 112 Y         # PR #112, auto-confirm
```

`Y` / `y` anywhere in args = skip the confirmation prompt. `Y` does NOT relax worktree safety — dirty / locked worktrees are still preserved (see `references/worktree-cleanup.md`).

## File structure

```
~/.claude/skills/approve-pr/
├── SKILL.md                            # this file — orchestrator
└── references/
    ├── preflight.md                    # Step 1: PR state + mergeStateStatus + non-review CI gate
    └── worktree-cleanup.md             # Step 5: 3-condition safety check + porcelain parsing
```

Implementation details for the two heavy steps live in `references/`. SKILL.md keeps the contract and the per-step bash gist; reach for the reference when you need the full logic.

## Pipeline

```
Step 0 — Parse args + resolve PR_NUMBER, HEAD_REF, BASE_REF
Step 1 — Pre-flight: PR open + mergeable + non-review CI green   (see references/preflight.md)
Step 2 — Confirmation prompt                                       (skipped if Y)
Step 3 — gh pr merge --squash --delete-branch                     (merge + remote-branch delete)
Step 4 — Local main sync                                           (handles squash-divergence)
Step 5 — Worktree audit + safe cleanup                            (see references/worktree-cleanup.md)
Step 6 — Local branch delete
Step 7 — Stash check (informational only)
Step 8 — Final state report
```

## Key invariants

1. **`Y` only skips the merge confirmation.** Worktree safety checks are non-overridable — you cannot `Y` your way into deleting another agent's dirty worktree.
2. **No branch guard.** Unlike `/lifeline:upsource-review`, this skill can run from anywhere — main with explicit PR#, or the feature branch directly. Step 4 switches you to main first; nothing requires you start there.
3. **Branch delete failure is expected when worktrees were preserved.** The branch is still checked out somewhere; that's the safety check working as designed.

## Step 0 — Argument parsing + PR resolution

```bash
ARGS="${1:-}"
PR_NUMBER=""
AUTO_CONFIRM=0
for tok in $ARGS; do
  case "$tok" in
    [Yy]) AUTO_CONFIRM=1 ;;
    [0-9]*) PR_NUMBER="$tok" ;;
    *) echo "WARN: unrecognized arg '$tok' (expected PR number or Y)" >&2 ;;
  esac
done

if [ -z "$PR_NUMBER" ]; then
  PR_NUMBER=$(gh pr view --json number --jq .number 2>/dev/null) || {
    echo "ERROR: No PR number provided AND current branch has no open PR." >&2
    echo "Either pass an explicit PR number (/approve-pr <N>) or switch to the PR's head branch." >&2
    exit 1
  }
fi

REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
HEAD_REF=$(gh pr view "$PR_NUMBER" --json headRefName --jq .headRefName)
BASE_REF=$(gh pr view "$PR_NUMBER" --json baseRefName --jq .baseRefName)
PR_TITLE=$(gh pr view "$PR_NUMBER" --json title --jq .title)
```

## Step 1 — Pre-flight

Three checks must pass before merging: PR is OPEN, `mergeStateStatus == CLEAN`, and non-review CI is green (Codex/Claude review jobs are skipped — they're advisory, not gating). On any failure, abort with a diagnostic before any irreversible action runs.

See `references/preflight.md` for the full bash with per-state error messages and the rationale for ignoring review-side jobs.

## Step 2 — Confirmation prompt

```bash
echo ""
echo "==================================================================="
echo "  Ready to merge PR #$PR_NUMBER"
echo "==================================================================="
echo "  Title:       $PR_TITLE"
echo "  Repo:        $REPO"
echo "  Head branch: $HEAD_REF"
echo "  Base branch: $BASE_REF"
echo "  Strategy:    squash + delete remote branch"
echo "==================================================================="

if [ "$AUTO_CONFIRM" -eq 1 ]; then
  echo "Auto-confirm (Y) supplied — proceeding without prompt."
else
  read -r -p "Merge this PR? [y/N] " response
  case "$response" in
    [Yy]|[Yy][Ee][Ss]) ;;
    *) echo "Aborted by user."; exit 0 ;;
  esac
fi
```

If invoked by an autonomous agent (no interactive stdin), `read` returns immediately with empty input → abort. Pass `Y` to bypass.

## Step 3 — Merge + remote branch delete

```bash
gh pr merge "$PR_NUMBER" --squash --delete-branch || {
  echo "ERROR: gh pr merge failed. Inspect: gh pr view $PR_NUMBER" >&2
  exit 1
}
echo "✓ PR #$PR_NUMBER merged + remote branch '$HEAD_REF' deleted."
```

`--delete-branch` deletes both the remote branch (always) AND the local branch when possible (best-effort; Step 6 handles the local case explicitly).

## Step 4 — Local main sync

```bash
git switch "$BASE_REF"
git fetch origin "$BASE_REF" --no-tags

# Squash collapses N commits into 1 — local <BASE_REF> often diverges from
# origin (the local-only commits live in the squash). Try fast-forward
# first; if divergent, hard-reset (no work lost — content is in the squash).
if ! git pull --ff-only origin "$BASE_REF" 2>/dev/null; then
  echo "Local '$BASE_REF' diverged from origin (expected after squash) — resetting hard."
  git reset --hard "origin/$BASE_REF"
fi
echo "✓ Local '$BASE_REF' now at $(git rev-parse --short HEAD)"
```

## Step 5 — Worktree audit + safe cleanup

For each worktree on `$HEAD_REF`, check three safety conditions: not the primary checkout, not locked, not dirty (uncommitted tracked OR untracked files). Worktrees passing all three are removed; failures are preserved + listed for the user. `Y` does NOT bypass these checks.

See `references/worktree-cleanup.md` for the porcelain-parsing logic, the full safety implementation, and the rationale for treating untracked files as "dirty".

## Step 6 — Local branch delete

```bash
if git branch -D "$HEAD_REF" 2>&1 | sed 's/^/  /'; then
  echo "✓ Local branch '$HEAD_REF' deleted."
else
  echo "⚠ Could not delete local branch '$HEAD_REF' — likely still checked out in a preserved worktree."
  echo "  Resolve the dirty/locked worktree(s) above, then: git branch -D $HEAD_REF"
fi
```

The failure path is the safety check working as designed (Step 5 preserved a worktree → branch is still checked out → `-D` correctly refuses). The user finishes the work, removes the worktree, then deletes the branch.

## Step 7 — Stash check (informational only)

```bash
STASH_MATCHES=$(git stash list 2>/dev/null | grep -F "$HEAD_REF" || true)
if [ -n "$STASH_MATCHES" ]; then
  echo ""
  echo "⚠ Found git stash entries referencing '$HEAD_REF':"
  echo "$STASH_MATCHES" | sed 's/^/  /'
  echo "  Stashes are NOT auto-deleted (may carry uncommitted work)."
  echo "  Inspect: git stash show <stash@{N}>"
  echo "  Drop:    git stash drop <stash@{N}>"
fi
```

## Step 8 — Final state report

```bash
WORKTREE_TOTAL=$(git worktree list | wc -l)
echo ""
echo "==================================================================="
echo "  ✓ /approve-pr complete"
echo "==================================================================="
echo "  PR:           #$PR_NUMBER (merged + remote branch deleted)"
echo "  Local branch: $(git branch --show-current) @ $(git rev-parse --short HEAD)"
echo "  Worktrees:    $WORKTREE_TOTAL total ($((WORKTREE_TOTAL - 1)) non-primary)"
echo "==================================================================="
```

## Failure modes

| Stage | Failure | Behavior |
| --- | --- | --- |
| Step 0 | No PR found + no arg | Loud error, exit 1 |
| Step 1 | PR not OPEN / not CLEAN / non-review CI red | Loud error, exit 1 (no merge attempted). See `references/preflight.md` for per-state guidance. |
| Step 2 | User says no | Quiet abort, exit 0 |
| Step 3 | `gh pr merge` fails | Loud error, exit 1; PR state untouched |
| Step 4 | Local sync fails (rare — network) | Loud error; PR is already merged on origin so re-running from main resumes from Step 5 |
| Step 5 | Worktree dirty/locked | Preserved, listed; cycle continues. See `references/worktree-cleanup.md`. |
| Step 6 | Branch delete fails | Warned + listed; cycle continues. Expected when Step 5 preserved a worktree. |
| Step 7 | Stashes found | Listed only, never auto-deleted |

## Troubleshooting

- **"PR mergeStateStatus = BLOCKED"** — branch protection rules require additional reviews/checks. Either get the missing approval or merge manually with `gh pr merge --admin`, then re-run `/approve-pr <N>` from main to do just the cleanup.
- **"Worktree remove failed"** — usually means there's an in-progress git operation (lock file). Wait for the other agent to finish, then re-run.
- **"Local branch delete failed after worktree cleanup"** — a worktree was preserved (dirty). Run `git worktree list` to see which one; finish the work there, then `git worktree remove <path> && git branch -D <branch>`.
- **"Squash divergence on local main"** — Step 4's `git reset --hard origin/main` handles this. The discarded local commits are preserved in the squash commit on origin.
