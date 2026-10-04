# PLAN: a clean per-commit review appends one ledger line, not a file

Status: approved -- operator 2026-10-04 (/ask): own plan, next PR, QUEUE.md Promoted position 2 ahead of PLAN-ci-consolidation; existing clean records are converted into the ledger and their .md files deleted in the same PR (clean break, no dual format beyond what the converted ledger needs)
Owner: d778be9d
First-Seen: 2026-10-04
Depends-On: no-dep -- builds only on shipped modules (wl_review, pr_labels, review_table, check_plan_implementation); agent/plans/_done/PLAN-per-commit-review.md is done
Priority: P2 -- operator order 2026-10-04: every clean review adds a tracked file and a "ride the next commit" prompt although nothing is left to do; 188 of 277 records under agent/reviews/ are full-coverage clean
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited
Owns: .claude/hooks/stop/wl_review.py, .claude/hooks/post-bash/review_commit.py, .claude/hooks/stop/worklist_messages.py, .ci/rediacc_ci/review/{clean_ledger,pr_labels,review_table}.py, .ci/scripts/quality/{check_plan_implementation,check_durable_paths_tracked}.py, .ci/policy/tree-shape.json, .claude/rediacc_hooks/guards/{block_review_file_edit,block_review_file_shell_write,test-block_review_file_edit,test-block_review_file_shell_write,test-block_push_with_unrecorded_reviews}.py, .claude/rediacc_hooks/tests/{test_review_commit_hook,test_wl_review_check}.py, .ci/rediacc_ci/tests/{test_review_clean_ledger,test_review_pr_labels,test_review_review_table}.py, .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py, .ci/config/shards/quality-pytest.json, agent/reviews/**, docs/agent-reference/ci-gates.md, .claude/agents/pr-babysitter.md, scripts/data/doc-registry.md, agent/plans/QUEUE.md
Worklist: #80ea5d76

**Operator request, 2026-10-04, verbatim:** "btw git commit review process a bit noisy. I think not the all cases require something to do. If haiku finds '(none)' then the system should not ask for a review file. So, we can eliminate growing the codebase for useless things." <!-- style-ok -->

## What was true when this was written (HEAD 64831cd0d)

**The tracked records.** There are 277 tracked files under `agent/reviews/`, and every one is `<branch>/<sha40>.md`:
- 216 are `Verdict: clean`. 188 of them have `Unreviewed: (none)` and `Dropped: 0`. The other 28 had a truncated diff (`truncated: yes` with a non-empty `Unreviewed:` list).
- 55 are `findings`.
- 6 are `skipped (gitlink-only)`, all on 0930-1.
- None is failed.
- Branch directories: 0930-1, 1003-1, 1003-2, 1004-1, main.
- 15 records belong to submodule commits (Repo: private/renet and private/account). They still live in the console's directory, and no submodule tracks an `agent/reviews/`.

**The writer.** `wl_review.run_review` (`.claude/hooks/stop/wl_review.py:1068-1156`) writes one `.md` per verdict, at 1149 (`write_atomic(out_path, render(review))`).

**Readers that glob `*.md` themselves.**
- `review_index` (706-729), which `uncovered` (740-757) uses to look up by sha and by patch-id.
- `branch_state` (1197).
- `surface_new` (1420).
- `find_finding` (1472).
- `pr_labels.read_verdict` and `verdicts` (`.ci/rediacc_ci/review/pr_labels.py:66-92`).
- `review_table.load_records` and `branch_verdicts` (`.ci/rediacc_ci/review/review_table.py:144-154`, `569-580`).
- `check_plan_implementation.review_records` (`.ci/scripts/quality/check_plan_implementation.py:1898-1929`). It reads Commit, Parent and Patch-Id from every branch directory to map rebased commits.

**Readers that go through `branch_state`.**
- The push guard (`.claude/rediacc_hooks/guards/block_push_with_unrecorded_reviews.py:205-211`).
- The merge guard, via `check_state` (`.claude/rediacc_hooks/guards/block_admin_merge.py:153-156`).
- `wl_checks`: the SessionStart line at 1790 and the Stop path at 3992.
- The `--review-run`, `--review-mark` and `--review-commit` verbs (1668-1728).

**Readers that do not care.**
- Retention: `--prune-reviews` → `agent_session_archival.review_branches` (`.ci/rediacc_ci/quality/agent_session_archival.py:318`) works per directory, so a ledger inside the directory is pruned with it.
- The Review Gate and review_status read PR comments only.
- `.claude/hooks/stop/wl_prsignals.py:22` reads only the table comment's marker.
- `scripts/gates` names no review path.
- Edit protection already covers any file under `agent/reviews/` (`.claude/rediacc_hooks/guards/block_review_file_edit.py:22`, `.claude/rediacc_hooks/guards/block_review_file_shell_write.py:23-27`). Only `.claude/hooks/stop/wl_review.py` and `.claude/hooks/stop/worklist.py` are sanctioned shell writers.

**The CI constraint.** CI's `pr-labels` job checks out only `.ci/config/well-known.env`, `.ci/rediacc_ci`, `.github/actions` and `agent/reviews` (`.github/workflows/ci.yml:1903-1908`). The CI-side reader therefore cannot import wl_review. review_table already mirrors the grammar for this reason (`.ci/rediacc_ci/review/review_table.py:43`).

**The prose that needs changing.**
- CLAUDE.md rule 1 (`CLAUDE.md:20`) says only that review records ride the branch and that `--review-commit` commits them. It never says every commit gets a file, so it is NOT edited. `CLAUDE.md:75` stays true too: the ledger is a file.
- These state the per-sha file and are edited:
  - `docs/agent-reference/ci-gates.md:132`
  - `.claude/agents/pr-babysitter.md:123`
  - `.claude/hooks/post-bash/review_commit.py:95`
  - `.claude/hooks/stop/worklist_messages.py:2092`
  - `.ci/policy/tree-shape.json:147`

## Design

**D1. What goes to the ledger.** A verdict leaves no file when all of these hold:
- it is `clean`, `skipped (gitlink-only)` or `skipped (no-review)`;
- there are no findings;
- `truncated` is false and `unreviewed` is empty;
- `dropped == 0`.

These stay `.md` files:
- `findings`, because they have resolutions to mark.
- `failed (...)`, because the attempt counter and retry need it.
- Truncated-clean. Haiku did not see the whole diff, so "(none)" is not a full verdict, and the table's Coverage column shows `n/m files`.
- Clean with `dropped > 0`. Haiku reported something the validator threw away (`validate`, 888-937), so a human may want to see it.

**Gitlink-only records go to the ledger too.** No model call is made and they carry no findings and no labels (`read_verdict` already returns None for them). They are pure coverage proof, which is exactly the "nothing to do" case. `skipped (no-review)` follows the same reasoning.

**Submodule commits follow the same rule.** Their lines carry `repo: private/<x>` in the console's ledger, exactly as their `.md` files carry `Repo:` today.

**D2. Path and schema.** The path is `agent/reviews/<branch-slug>/clean.jsonl`. Each line is one JSON object with sorted keys, `separators=(",",":")` and `ensure_ascii=False`:

```
{"attempt":1,"branch":"1004-1","cost":{"calls":1,"seconds":12.3,"usd":0.0123}|null,"diff":{"bytes":4210,"files":3},
 "labels":{"bump":"patch","kind":["bug"],"why":"..."}|null,"model":"claude-haiku-4-5-20251001","parent":"<sha40>|(root)",
 "patch_id":"<sha40>|(none)","repo":"console","reviewed_at":"2026-10-04T08:00:00Z","sha":"<sha40>","subject":"...","v":1,
 "verdict":"clean"}
```

- There is no `body_sig`. With no findings it is always the same empty-findings constant, and every one of the 216 clean records carries that value.
- There are no truncated, unreviewed, dropped or findings keys. D1 makes them constant, so a line carrying one is malformed.
- The name avoids "ledger" in code identifiers on the CI side, because `pr_labels.LEDGER_PREFIX` already means the label-comment ledger. The module is `clean_ledger`.

**D3. Appending, concurrency and precedence.**

*How a line is appended.* `append_clean(root, branch, review)`:
1. Opens the ledger with `O_WRONLY|O_APPEND|O_CREAT`.
2. Takes `fcntl.flock(LOCK_EX)` on that descriptor.
3. Re-reads the ledger and skips the write if a line for the sha already exists (idempotent).
4. Writes the whole line in ONE `os.write`, then fsyncs and unlocks.

This covers two reviewer children (`max_concurrent` is 2) and two sessions sharing the checkout. `_mark_lock` (1579-1587) is the precedent for using flock.

*Which record wins.* For any sha, a `.md` file beats a ledger line, because it is the stricter state. Every reader applies this rule.
- When a clean result lands over an existing `failed` `.md` (a retry succeeded), the writer appends the line and unlinks the `.md`.
- A `findings` `.md` is never unlinked by a later clean result. The new verdict overwrites the `.md`, as `run_review` does today.

*Rejected: `merge=union` in `.gitattributes`.*
- Ledgers are per branch, and branches land by rebase-merge, so two branches never write the same file.
- Two checkouts on one branch is the only conflict, and keeping both lines is a correct resolution because readers dedupe by sha.
- A `.gitattributes` edit also widens CI scope (`.ci/scripts/ci/scope-map.cjs:47`).

**D4. The readers.**

*wl_review.*
- `read_ledger(path)` returns `(reviews, errors)`. It parses strictly: an unknown or missing key, a bad verdict, a non-40-hex sha, or any D1 key gives `MalformedReviewError(line=n)`.
- `review_index` adds ledger shas and patch-ids, so `uncovered` and `run_review`'s twin check (1099-1103) see them.
- `branch_state`:
  - adds each ledger review as `(ledger_path, review)`;
  - puts ledger errors into `malformed`, with the line number;
  - marks the ledger `uncommitted` when git status shows it dirty;
  - adds deleted tracked `.md` files (status ` D`) to `uncommitted`.
- `recordable` returns the dirty ledger and deleted `.md` paths, with no `lock_live` check for the ledger. A line is written only after its verdict is final, and `release_lock` (1156) runs after the write.
- `commit_reviews` stages with `git add -A -- <paths>`, so deletions are recorded, and picks the trailer by `reviewed_at` instead of mtime.
- `stop_texts` and `describe` name the sha from the ledger line, not `p.stem`.
- `surface_new` marks seen per `clean.jsonl:<sha>`. It prints ONE line for all fresh clean entries (`N clean review(s) appended to agent/reviews/<b>/clean.jsonl: <sha8...>`) and keeps the per-record lines for `.md` files.
- `session_start_line` says "record(s)".

*CI side.* New `.ci/rediacc_ci/review/clean_ledger.py`, stdlib only. It provides a lenient `read(path) -> [dict]` that skips a garbled line with a warning, matching how review_table treats a garbled `.md` file.
- `pr_labels.verdicts` reads the `.md` files plus the ledger, dedupes by sha with `.md` winning, and keeps `read_verdict`'s rule. A new offline mode, `--verdicts-only --branch <b>`, prints `{labels, note, n}` as JSON for the proof.
- `review_table.load_records` builds a `Record` from each line with `file="clean.jsonl"` and `line=n`. `record_url` points at `clean.jsonl#L<n>`. `branch_verdicts` delegates to `pr_labels.verdicts`, keeping one implementation.
- `check_plan_implementation.review_records` also reads every `<branch>/clean.jsonl` through `clean_ledger.read`.
- The push guard, merge guard, `wl_checks`, `--check` and the verbs need no change: they read `branch_state`.

**D5. The migration verb, `wl_review.py --ledger-migrate [--write]`.** It is one-shot and idempotent. Dry run is the default and prints per-branch counts. `.claude/hooks/stop/wl_review.py` is a sanctioned shell writer, and the verb is not a worklist verb, so it adds no catalogue row.

For every directory under `agent/reviews/`, it parses each `.md` with the strict `parse`. Every record that D1 makes eligible is turned into a line, and that line is parsed back with `read_ledger`. The field-by-field comparison with the `Review` must be equal on every field. Cost is null for the 0930-1 records written before `Cost:` existed (`OPTIONAL_HEADERS`, line 100).

After the comparison:
1. It snapshots `review_index` keys and the per-sha `(verdict, labels, repo, parent, patch_id)` map for every branch.
2. It writes the lines in `reviewed_at` order, then unlinks the `.md` files.
3. It snapshots again.
4. If the two snapshots differ, it restores the files from memory and exits 1.

The expected result at HEAD 64831cd0d is 194 lines (188 clean plus 6 skipped) and 194 deleted files. 83 `.md` files stay: 55 findings and 28 truncated-clean. The verb prints the real numbers when it runs.

**D6. Proof of identical coverage and labels.** This is run in T14 and quoted in the migration commit. That commit touches only `agent/reviews/`, so it is review-only (`reviews_only`, 696), and the quoted byte-identity output satisfies `block_unproven_bulk_transform`. For each of 0930-1, 1003-1, 1003-2, 1004-1 and main, run these before the migration and again after it is committed:
- `pr_labels --verdicts-only --branch <b>`;
- `review_table --render-only --branch <b>`, with link targets stripped by `sed -E 's/\]\([^)]*\)/]()/g'`;
- the sorted set from `check_plan_implementation.review_records`.

Also run `wl_review.py --check` on the checked-out branch. Every pair must be byte-identical.

## Tasks
- [ ] T1 Register the plan: add it to `agent/plans/QUEUE.md` `## Promoted` at position 2, move ci-consolidation (`agent/plans/QUEUE.md:12`) and the entries after it down one, then run `npm run check:ci-plan-record -- --update`. Proof: `check:ci-plan-record` rc 0. Control: with the entry removed, the gate reports the plan as unqueued.
- [ ] T2 `.claude/hooks/stop/wl_review.py`: add the D1 predicate `ledger_eligible(review)`, `ledger_path`, the D2 line codec (`ledger_line`, `read_ledger`) and `append_clean` with flock and dedupe. Proof: new cases in `.claude/rediacc_hooks/tests/test_review_commit_hook.py`:
  - the codec round-trips every eligible verdict;
  - each D1 exclusion (truncated, unreviewed, dropped, findings, failed) is refused;
  - an unknown key is malformed with its line number.
  Control: dropping the `truncated` test from `ledger_eligible` makes the truncated case fail.
- [ ] T3 `run_review` writes through `ledger_eligible`: append for an eligible verdict, `.md` for anything else, and unlink a `failed` `.md` when the retry is clean. Proof: in `.claude/rediacc_hooks/tests/test_review_commit_hook.py`, the existing `test_a_commit_starts_a_detached_reviewer...` and `test_a_gitlink_only_commit_is_skipped...` assert that the ledger holds one line and no `.md` exists; a new retry case asserts the failed `.md` is gone. Control: forcing the `.md` path reds both.
- [ ] T4 Concurrency: a new case runs two processes that append 50 lines each to one ledger. It expects 100 parseable lines, no torn line, and a re-append of an existing sha that writes nothing. Control: replacing the single `os.write` with two writes (key half, value half) and removing the lock produces a torn line within the loop count.
- [ ] T5 `review_index`, `uncovered`, `branch_state`, `recordable`, `commit_reviews`, `describe` and `stop_texts` read the ledger per D4. Proof: in `.claude/rediacc_hooks/tests/test_wl_review_check.py`, a ledger-only branch passes `--check`; a dirty ledger is refused as `uncommitted`; a garbled ledger line is refused as `malformed`; a rebased copy whose patch-id is in the ledger counts as covered. Control: making `review_index` skip the ledger turns the clean branch into `uncovered`.
- [ ] T6 `--review-commit` with a dirty ledger and a deleted failed `.md` commits both (`git add -A`). Proof: extend `test_review_commit_records_only_finished_files_with_the_trailer`. Control: plain `git add` leaves the deletion unstaged and the case fails.
- [ ] T7 Push and merge guards: add a ledger-covered world to `.claude/rediacc_hooks/guards/test-block_push_with_unrecorded_reviews.py`, and add the merge arm on that world in `.claude/rediacc_hooks/tests/test_wl_review_check.py`. Proof: the push is allowed and the merge passes; with the ledger line removed both refuse. Control: the guard's existing DEFECT row still flips the answer.
- [ ] T8 `surface_new` prints one compact line for fresh clean entries, and `session_start_line` says "record(s)". Update `.claude/hooks/post-bash/review_commit.py:95` ("lands in clean.jsonl or as `<sha>.md`") and `.claude/hooks/stop/worklist_messages.py:2092`. Proof: `test_the_next_bash_call_surfaces_a_finished_review_exactly_once` is updated for a clean entry, and `.claude/rediacc_hooks/tests/test_wl_message_catalogue.py` passes. Control: keying seen by file mtime prints the line twice.
- [ ] T9 `.ci/rediacc_ci/review/clean_ledger.py` (new). `pr_labels.verdicts` merges `.md` files with the ledger, dedupes by sha with `.md` winning, and gains `--verdicts-only`. Proof: new `.ci/rediacc_ci/tests/test_review_clean_ledger.py`, which holds the contract case (lines written by `wl_review.ledger_line` read back identically by `clean_ledger.read`), plus cases in `.ci/rediacc_ci/tests/test_review_pr_labels.py`:
  - a ledger-only `bump=minor` gives `bump-minor`;
  - all-`none` across `.md` files and the ledger gives `bump-none`;
  - a skipped line casts no vote.
  Control: making `verdicts` read only `*.md` reds the minor case.
- [ ] T10 `review_table`: `load_records` and `record_url` use `clean.jsonl#L<n>`, and `branch_verdicts` delegates to `pr_labels.verdicts`. Proof: in `.ci/rediacc_ci/tests/test_review_review_table.py`, the contract case covers a ledger line; a ledger row shows `full` coverage and a working `#L` link; a superseded ledger record is still listed. Control: dropping the ledger from `load_records` moves the commit to "PR commits with no record".
- [ ] T11 `check_plan_implementation.review_records` reads every `clean.jsonl`. Proof: its `--selftest` gains a ledger fixture that maps a rebased sha, and `npm run check:ci-plan-implementation` stays rc 0. Control: with the ledger read removed, the fixture reports "no review record".
- [ ] T12 Policy and probes:
  - add a ledger probe `agent/reviews/zz-probe/clean.jsonl` to `.ci/scripts/quality/check_durable_paths_tracked.py:37-40`;
  - mention `clean.jsonl` in the `.ci/policy/tree-shape.json:147` text;
  - add a ledger-only directory case to `.ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py`, so `review_branches` still lists the directory;
  - add `clean.jsonl` cases to `.claude/rediacc_hooks/guards/block_review_file_edit.py` and `.claude/rediacc_hooks/guards/block_review_file_shell_write.py` (edit and `>>` are refused).
  Proof: `check:ci-durable-paths-tracked` rc 0, plus the guard suites. Control: narrowing `REVIEW_PATH` to `\.md$` reds the new guard case.
- [ ] T13 Implement `wl_review.py --ledger-migrate [--write]` per D5, with tests:
  - a dry run changes nothing;
  - `--write` on a fixture tree (clean, truncated-clean, dropped-clean, gitlink, findings, failed) converts exactly the eligible records;
  - a second run is a no-op;
  - a forced snapshot mismatch restores every file.
  Control: removing the round-trip comparison lets a codec that drops `labels.why` through, and the test catches it.
- [ ] T14 Run the migration on the real tree in its own commit: capture the D6 proof outputs before, run `--ledger-migrate --write`, commit through `worklist.py --review-commit`, then capture the outputs after. Proof: byte-identical diffs, quoted in the commit message; the commit is review-only, so it is not reviewed again. Control: before the migration, run the after-proof against a scratch copy with one ledger line deleted, and show the `--verdicts-only` or coverage diff is non-empty.
- [ ] T15 Shard placement: add `pytest:.ci/rediacc_ci/tests/test_review_clean_ledger.py` to one leg of `.ci/config/shards/quality-pytest.json`. Proof: `npm run check:ci-shard-manifest-coverage` rc 0. Control: the gate reds before the line is added.
- [ ] T16 Docs:
  - `docs/agent-reference/ci-gates.md:132` and `.claude/agents/pr-babysitter.md:123`: a clean full-coverage verdict is a line in `agent/reviews/<branch>/clean.jsonl`, and everything else is `<sha>.md`;
  - update the `.ci/rediacc_ci/review/pr_labels.py` and `.ci/rediacc_ci/review/review_table.py` module docstrings and the `.claude/hooks/stop/wl_review.py` docstring (line 2);
  - regenerate with `npx tsx scripts/gen/gen-docs.ts --write`; `scripts/data/doc-registry.md:803` counts the new `.py`;
  - leave `CLAUDE.md` unchanged (see "What was true").
  gates.lock.json is unchanged because no gate is added or removed, so the CLAUDE.md gen-docs regions do not move. Proof: `npx tsx scripts/gen/gen-docs.ts` rc 0 and `check:ci-doc-region-parity` rc 0.
- [ ] T17 Full suites: the hook pytest suite (`.claude/rediacc_hooks/tests`, `.claude/hooks/stop/test-*.py`, guard selftests) and the CI pytest suite (`.ci/rediacc_ci/tests`), then `npm run ci:quick`. Proof: rc 0, with counts quoted in the tick.
- [ ] T18 Live check, read-only: make one real commit on the branch, wait for its review, and confirm a clean verdict adds one ledger line and no `.md`, `--check` is clean after `--review-commit`, and `review_table --render-only` shows the row.
