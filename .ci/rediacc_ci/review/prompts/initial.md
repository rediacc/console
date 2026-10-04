This is the FIRST automated review of this pull request.

REPO: {{REPO}}
PR NUMBER: {{PR_NUMBER}} HEAD SHA: {{HEAD_SHA}}

Per-commit review records: every commit on this branch was already reviewed on its own, and the records are committed under `agent/reviews/{{HEAD_REF_SLUG}}/` in the checked-out head (one `<sha40>.md` per commit, submodule commits included), each carrying its findings and their resolutions (fixed, not-a-bug, deferred). Read them FIRST.
A finding a record already settles is not raised again unless the PR's final state contradicts its resolution. Spend the budget on what a single-commit diff cannot show: interactions across commits, integration with the rest of the tree, and the whole-PR result.

Budget rule for LARGE diffs (dozens of files or more): work breadth-first so a turn cap still yields a review. First pass the diff stat and description to rank areas by risk; deep-read only the riskiest hunks; post inline comments AS each defect is confirmed (never save them all for the end); and reserve budget to ALWAYS post the summary comment. A partial review that posted is worth more than an exhaustive one that did not.

For VERY large diffs (tens of thousands of lines): never try to hold the whole diff. Work strictly area by area from the diff stat (`gh pr diff -- <path>` scoped reads), deprioritize generated bulk (lockfiles, generated contracts, search indexes, translation bundles, recorded casts), and make the summary comment carry an explicit COVERAGE MAP: areas deep-read, areas skimmed, areas not reviewed and why.
If real coverage was materially partial, the summary says so plainly and recommends an exhaustive `/code-review ultra` pass. An honest partial beats a false exhaustive.

Process:

1. Read the PR description and the full diff (gh pr view, gh pr diff). The PR head is checked out in the working directory for surrounding context.
2. Review ONLY the changes introduced by this PR, in priority order:
   - Correctness: logic errors, broken edge cases, race conditions, missing or wrong error handling, quoting and exit-code bugs in shell.
   - Security: injection, secret exposure or logging, permission widening, unsafe handling of untrusted input.
   - Performance: clear regressions only (repeated I/O or subprocesses in hot paths, quadratic loops over large sets).
3. Inline comments create BLOCKING review threads in this repository's merge gates. Post an inline comment (mcp__github_inline_comment__create_inline_comment) ONLY for a real correctness, security, or performance defect, on the exact file and line.
4. Nits, style preferences, and non-blocking suggestions go ONLY in the summary comment, never inline.
5. Finish with ONE summary comment via gh pr comment: a one-line verdict, defects ordered by severity, nits (if any), and anything that could not be reviewed and why. Post it with a quoted heredoc so backticks reach GitHub as written: `gh pr comment {{PR_NUMBER}} --body-file - <<'EOF'`, the report, then `EOF`. Never backslash-escape a backtick: an escaped fence reads as no fence, and the report then needs a hand reply even when its findings array is empty.
6. END the report with a machine-readable findings block so the workflow can post them as LINE-ANCHORED review comments with severity badges (the inline tools are unavailable in this environment; this block is how the findings reach the exact lines). At most 20 entries, the most important findings first. `line` must be a line IN THE DIFF of the head commit. Exact format, inside a collapsed section at the very end:

<details><summary>machine-readable findings</summary>

   ```json:review-findings
   [{"path": "dir/file.ts", "line": 42, "severity": "high",
     "title": "short imperative title", "body": "full explanation with the
     failure scenario and a concrete fix direction"}]
   ```

</details>

severity is one of: critical, high, medium, low. A review with no findings emits an empty array.

Rules:

- Do not push commits, create branches, or modify files.
- Do not approve or request changes; comments only.
- No emojis. Never include the text "@claude" in any output.
- Skip style and formatting territory covered by this repository's CI gates (lint, shfmt, i18n hashes, generated artifacts).
- If the diff is entirely mechanical (lockfiles, generated artifacts), say so in one short summary comment instead of inventing findings.
- Do NOT lump hand-maintained config files (dependency pin/blocklist files, syncpack config, label definitions, allowlists) in with generated bulk: they are small, human-written, and deserve a sanity pass (a wrong pin or a deleted label entry is a real finding).
- Submodule POINTER moves (gitlink-only changes) are reviewed in the submodule's own PR, not here; note them as out of scope rather than unreviewed.
- Release labels are not part of this review: the PR's bump label comes from the per-commit records.
