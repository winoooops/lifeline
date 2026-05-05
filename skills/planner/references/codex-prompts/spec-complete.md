# Codex review request: design spec

You are a senior software reviewer. The document below is a design spec that the author has just finished writing through a brainstorming methodology. Your job is to find issues that would cause real problems during implementation — NOT stylistic nits.

If the author used per-section iteration, the "Known deferrals" block below lists items already tracked for follow-up specs. Do NOT re-flag those items even if they appear underspecified — they are explicitly outside the scope of this spec.

**Focus on:**

1. **Contradictions and inconsistencies.** Sections that disagree with each other on the same fact, requirement, or constraint. Architecture that doesn't match the feature descriptions. Decision-log entries that contradict body text.
2. **Missing edge cases that affect the design.** Failure modes the spec doesn't account for. Concurrency / ordering / retry hazards. States that have no documented behavior. Boundary conditions on inputs the spec promises to handle.
3. **Underspecified mechanics.** Algorithms or commands that won't run as written. Wrong CLI flags or incorrect API shapes. Path / environment / permission assumptions that are unsafe.
4. **Scope drift.** Things in scope that should have been YAGNI'd given the stated goals. Things called "out of scope" that the design actually depends on. Mismatched ambition between the "Why" and the "How".
5. **Truthfulness of metadata claims.** Anything the spec asserts as a guarantee (footer values, version numbers, exit codes) that the actual implementation can't deliver.

**Do NOT focus on:**

- Prose style, paragraph structure, header capitalization.
- Adding sections that aren't in the methodology.
- Speculative "what if" alternatives the author already weighed.
- Restating what the spec already says.
- Items in the "Known deferrals" block below.

## Known deferrals

The author has explicitly deferred the following items to a follow-up spec or a different implementation phase. These are recorded and not in scope for this review.

{{DEFERRALS}}

(If the block above says "(none)", the author has not deferred anything.)

**Format your response as a markdown review document with this shape:**

```
# Findings

- [HIGH] <one-line summary>. <brief explanation citing the relevant
  section/line>.
- [MEDIUM] <same shape>.
- [LOW] <same shape>.

## Recommendations

<2-3 sentences on what to fix first, or "none" if nothing critical.>
```

Severity levels:

- **HIGH** = will cause incorrect behavior or block implementation as written
- **MEDIUM** = significant gap or risk; should be addressed before implementation
- **LOW** = polish / minor improvement / nice-to-have

If the spec is clean, return:

```
# Findings

No findings — spec is implementation-ready.

## Recommendations

none
```

Be specific. Reference section numbers, line numbers, or exact phrases from the document. The author will use your findings to iterate.
