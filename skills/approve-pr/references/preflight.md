# Pre-flight checks — Step 1 of approve-pr

Implementation reference for `../SKILL.md` § Step 1. Verifies that the PR is in
a state where merging makes sense before any irreversible action runs.

## Three checks

1. **PR state == OPEN.** Closed/merged PRs can't be merged again; surface the
   actual state to the user instead of silently aborting.
2. **`mergeStateStatus == CLEAN`.** GitHub-side mergeability incorporating
   branch protection rules, required reviews, and CI status. Other states each
   have a distinct fix path:
   - `BLOCKED` → required review or status check missing.
   - `UNSTABLE` → non-required check failing (some teams still want to gate).
   - `DIRTY` → merge conflicts; resolve on branch first.
   - `BEHIND` → branch behind base; rebase or merge base in.
3. **Non-review CI green.** Filter `gh pr checks` output, ignore the
   `Codex Code Review` and `Claude Code Review` jobs (which may be running
   indefinitely or be advisory), abort on any other failure.

## Implementation

```bash
PR_STATE=$(gh pr view "$PR_NUMBER" --json state --jq .state)
if [ "$PR_STATE" != "OPEN" ]; then
  echo "ERROR: PR #$PR_NUMBER is $PR_STATE, not OPEN. Nothing to merge." >&2
  exit 1
fi

MERGE_STATE=$(gh pr view "$PR_NUMBER" --json mergeStateStatus --jq .mergeStateStatus)
case "$MERGE_STATE" in
  CLEAN) ;;  # ready
  BLOCKED|UNSTABLE)
    echo "ERROR: PR #$PR_NUMBER mergeStateStatus = $MERGE_STATE." >&2
    echo "Required checks failing or branch out-of-date." >&2
    echo "Fix CI / rebase, or use 'gh pr merge $PR_NUMBER --squash --admin'" >&2
    echo "manually if you want to override branch protection." >&2
    exit 1
    ;;
  DIRTY)
    echo "ERROR: PR #$PR_NUMBER has merge conflicts. Resolve them first." >&2
    exit 1
    ;;
  BEHIND)
    echo "ERROR: PR #$PR_NUMBER is behind '$BASE_REF'. Rebase or merge base in." >&2
    exit 1
    ;;
  *)
    echo "ERROR: PR #$PR_NUMBER mergeStateStatus = $MERGE_STATE (unexpected)." >&2
    exit 1
    ;;
esac

# Non-review CI gate.
# `gh pr checks` is tab-separated: <name>\t<status>\t<duration>\t<url>
# We filter on column 2 == "fail" AND column 1 not matching the review-job names.
FAILING_NON_REVIEW=$(gh pr checks "$PR_NUMBER" 2>/dev/null \
  | awk -F'\t' '$2 == "fail" && $1 !~ /Codex Code Review|Claude Code Review/ { print $1 }')
if [ -n "$FAILING_NON_REVIEW" ]; then
  echo "ERROR: non-review CI checks failing on PR #$PR_NUMBER:" >&2
  echo "$FAILING_NON_REVIEW" | sed 's/^/  /' >&2
  echo "" >&2
  echo "Inspect logs: gh pr checks $PR_NUMBER" >&2
  exit 1
fi
```

## Why review-side jobs are skipped

Both `Codex Code Review` (when re-enabled) and `Claude Code Review` are
**advisory** — they post comments on the PR but do not gate the merge. They
also tend to take 5–30 minutes, much longer than other CI. Gating on them
would block legitimate merges of PRs whose review jobs happen to be slow or
mid-flight. The `/lifeline:upsource-review` loop already handles
review-job findings before the user reaches `/approve-pr`.

## Override path

The skill itself does NOT expose an override flag. If you need to merge
something the pre-flight refuses, run `gh pr merge <N> --squash --admin`
manually, then re-run `/approve-pr` from main with the PR number to do
just the local + worktree cleanup steps (the merge step will fail
gracefully with "PR already merged" and the cleanup proceeds).
