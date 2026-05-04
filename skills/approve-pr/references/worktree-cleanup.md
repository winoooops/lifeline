# Worktree audit + safe cleanup — Step 5 of approve-pr

Implementation reference for `../SKILL.md` § Step 5. Removes git worktrees
on the merged branch — but preserves any worktree that shows signs of
active work, so a parallel agent or your in-progress side branch isn't
silently destroyed.

## Three safety conditions

For each worktree whose branch matches `$HEAD_REF`, all three must hold
before removal:

| # | Condition | Detection | If fails |
|---|---|---|---|
| 1 | Not the primary checkout | `git rev-parse --show-toplevel` matches the worktree path | Skip silently |
| 2 | Not locked | `<worktree>/.git/locked` file exists, OR `git worktree list --porcelain` shows `locked` line in this worktree's block | Preserve + list to user |
| 3 | Not dirty | `git -C <worktree> status --porcelain` returns non-empty (any uncommitted tracked change OR untracked file) | Preserve + list to user |

Only when all three pass does `git worktree remove <path>` run.

`Y` (auto-confirm) does NOT bypass these checks — they exist to protect
data, not to be friendly.

## Why "untracked files = dirty"

The minimum signal we have that an agent is mid-task is "files exist in
the worktree that aren't in HEAD". That covers:

- Half-written code an agent hasn't `git add`-ed yet
- Build artifacts a long-running test suite is producing
- Logs / debug dumps the agent might want to inspect after
- A subagent's `.scratch/` working dir

Auto-deleting any of these would silently destroy work. The cost of being
too conservative is "user has to `git worktree remove --force <path>`
themselves after deciding it's safe" — cheap. The cost of being too
aggressive is unrecoverable.

## Implementation

```bash
PRIMARY=$(git rev-parse --show-toplevel)
REMOVED=()
PRESERVED_DIRTY=()
PRESERVED_LOCKED=()

# Parse `git worktree list --porcelain`. Each block has the form:
#   worktree <absolute path>
#   HEAD <sha>
#   branch refs/heads/<name>     # absent if detached
#   locked                        # absent if not locked
#                                 # blank-line separator between blocks
#
# We awk-process the porcelain into per-worktree records (one block per
# input record, fields are the lines), then iterate.

while IFS= read -r block; do
  [ -z "$block" ] && continue

  WT_PATH=$(awk '/^worktree / { sub(/^worktree /, ""); print; exit }' <<< "$block")
  WT_BRANCH=$(awk '/^branch / { sub(/^branch refs\/heads\//, ""); print; exit }' <<< "$block")
  WT_LOCKED=$(awk '/^locked/ { print "yes"; exit }' <<< "$block")

  # Filter: not detached, branch matches the merged ref.
  [ -z "$WT_BRANCH" ] && continue
  [ "$WT_BRANCH" != "$HEAD_REF" ] && continue
  # Skip primary checkout (where this script is running).
  [ "$WT_PATH" = "$PRIMARY" ] && continue

  # Safety check 2: locked.
  if [ "$WT_LOCKED" = "yes" ] || [ -f "$WT_PATH/.git/locked" ]; then
    PRESERVED_LOCKED+=("$WT_PATH")
    continue
  fi

  # Safety check 3: dirty (uncommitted tracked OR untracked).
  if [ -n "$(git -C "$WT_PATH" status --porcelain 2>/dev/null)" ]; then
    PRESERVED_DIRTY+=("$WT_PATH")
    continue
  fi

  # All three checks passed — remove.
  if git worktree remove "$WT_PATH" 2>&1 | sed 's/^/    /'; then
    REMOVED+=("$WT_PATH")
  else
    PRESERVED_DIRTY+=("$WT_PATH (remove failed — see git error above)")
  fi
done < <(git worktree list --porcelain | awk 'BEGIN { RS = ""; ORS = "\n\n" } { print }')

# Report.
echo ""
echo "Worktree cleanup on '$HEAD_REF':"
echo "  Removed:           ${#REMOVED[@]}"
echo "  Preserved (dirty): ${#PRESERVED_DIRTY[@]}"
echo "  Preserved (locked):${#PRESERVED_LOCKED[@]}"
for wt in "${REMOVED[@]}";          do echo "    ✓ removed: $wt"; done
for wt in "${PRESERVED_DIRTY[@]}";  do echo "    ⚠ kept (dirty/uncommitted): $wt"; done
for wt in "${PRESERVED_LOCKED[@]}"; do echo "    🔒 kept (locked): $wt"; done
```

## Awk porcelain parsing notes

`git worktree list --porcelain` separates worktree blocks with blank
lines and emits keyword lines (`worktree`, `HEAD`, `branch`, `bare`,
`locked`, etc.) one per line. Setting `RS=""` in the outer awk treats
the blank-line separator as the record separator, so each block is a
single multi-line awk record. Inner per-block parsing then operates on
one block at a time inside the bash `while read` loop.

## Cascade with Step 6

If any worktree was preserved (locked or dirty), Step 6's `git branch -D
$HEAD_REF` will fail — the branch is still checked out somewhere. That
failure is **expected** and logged as a warning; the user finishes the
work in the preserved worktree, removes it manually, then runs
`git branch -D $HEAD_REF`.

This is a feature, not a bug: the branch is the last remaining anchor
to the in-flight work, so destroying it would orphan that work.

## Manual recovery commands

The skill prints these in its failure message but they're worth having
in one place:

```bash
# Inspect what's dirty in a preserved worktree:
cd <preserved-worktree-path>
git status
git diff
git diff --staged

# Decide: keep, commit, stash, or discard.
# Then back at primary:
cd <primary-checkout>
git worktree remove <preserved-worktree-path>   # only if clean
git branch -D <merged-branch>                    # now succeeds
```

## What we deliberately do NOT do

- **Auto-stash dirty worktrees** before removing — same reason `/lifeline:upsource-review` doesn't auto-stash on abort. Stashes hide changes; an agent debugging "where's my work?" would be worse off.
- **Force-remove dirty worktrees** with `git worktree remove --force`. The `--force` flag exists; we never use it from this skill.
- **Run `git clean`** anywhere. We don't own the contents of the worktree's working tree; cleanup of untracked files is the worktree's owner's call.
- **Touch worktrees on OTHER branches** (the safety filter `[ "$WT_BRANCH" != "$HEAD_REF" ] && continue` is strict). If you want to garbage-collect old worktrees on already-merged branches, that's a different skill.
