# PLAN: REST and GraphQL parity for the gh pr guards
Status: done
Owner: d778be9d
Updated: 2026-09-17

Three pre-bash guards police the `gh pr` command surface and are blind to the REST or GraphQL call that reaches the same GitHub mutation.
The gap is confirmed at CHAIN level rather than per guard, which is the level that matters, since a single-guard probe cannot show whether some sibling covers the form.
`python3 .claude/rediacc_hooks/dispatch.py --chain pre-bash` returns rc=0 on all three bypasses below while the `gh pr` control returns rc=2 in every case. Nothing in the chain covers them.

| guard | control, rc=2 | bypass, chain rc=0 |
|---|---|---|
| `block_admin_merge` (ORDER 27) | `gh pr merge 589 --admin --squash` | `gh api repos/o/r/pulls/589/merge -X PUT -f merge_method=squash` |
| `block_nondraft_pr_create` (ORDER 23) | `gh pr create --title x --body y` | `gh api repos/o/r/pulls -X POST -f title=x -f head=b -f base=main` |
| `block_premature_ready` (ORDER 26) | `gh pr ready 589` | `gh api graphql -f query=markPullRequestReadyForReview` |

`block_admin_merge` is the sharp one. Its `--admin` ban is an outright operator ruling from 2026-07-22, made because an admin merge over a still-pending pointer-bump run left every merged PR permanently red.
The REST merge endpoint walks past that ban along with the review-thread and report-reply hygiene checks behind it.

## Tasks

- [x] Add the REST merge arm to block_admin_merge.py at :170-172, before the gh_pr_at_command_pos early return
- [x] Mirror that arm byte-for-byte into the twin .claude/oracles/pre-bash/block-admin-merge.sh at :28-29
- [x] Add the REST create arm to block_nondraft_pr_create.py at :70-72 and its twin block-nondraft-pr-create.sh at :21-22
- [x] Add the GraphQL ready arm to block_premature_ready.py at :70-72 and its twin block-premature-ready.sh at :23-24, as the two-part raw-versus-scan test
- [x] Extend EDGE_CASES in all three ports with the bypass, the reordered-flag bypass, the GET control and the prose control
- [x] Mirror one BLOCK and one ALLOW per guard into .claude/rediacc_hooks/tests/hookcases.py at the :1052 shape
- [x] Run the four defect plants in a scratch copy and record that each flips the case it is supposed to flip
- [x] Run the full verification list and the live chain matrix, including the refresh-pr-body.sh non-regression

## Outcome

Landed as `b163191d2`, seven files, 188 insertions and no deletions. Every file:line anchor in this plan matched the tree; nothing here had to be re-derived during implementation.

The finding is closed against the measurement that opened it. All three bypasses moved from rc=0 to rc=2 through `--chain pre-bash`, and the three `gh pr` controls still return rc=2.
The false-positive controls all still pass: a GET on the merge endpoint, a `pulls` listing, and a POST to the `comments` sub-endpoint.
The sanctioned PATCH body edit returns rc=2 from `block_raw_pr_body_edit` and rc=0 from both new arms, which is the distinction that kept `refresh-pr-body.sh` working, and that script still passes the chain at rc=0.

The REST create is refused at ORDER 23, which is the live confirmation that `block_stale_pr_branch_date` at ORDER 24 never needed a change of its own.

Differential green across all three ports and their twins, with comment-to-code ratios 1.73, 1.68 and 1.46 against the 0.90 floor. All four planted defects flipped only the case each targeted.

ONE DEVIATION FROM THE PLAN AS WRITTEN, recorded because a plan that quietly absorbs its own deviations stops being evidence.
The oracle-drift plant was specified to run BEFORE the twin edit, as proof the pair is coupled. Each port and twin were instead written in lockstep per pair, so the plant ran against a scratch reversion that removes the arm from the twin only.
The evidence is equivalent -- port rc=2 against twin rc=0, a genuine mismatch the differential rejects -- but the order differs from what this document asked for.

A LATER COMMIT REWROTE THESE FILES' COMMENTS. `b13267223` and the comment-scope reflow after it rewrapped prose across the tree, guard files included, which changes the comment-to-code ratio the differential floors at 0.90. The live probes above were re-run afterwards and still hold.

## What an earlier reading of this got wrong

Three claims that seemed obvious did not survive checking against the tree, and each is recorded because acting on any of them would have produced a broken change.

Commit `bfcae6e0b` is NOT the precedent for a twinned fix. It fixed this same class in `block_prose_style_commit.py`, but that guard declares `TWIN = None` at line 67, so it has no bash oracle and no differential obligation.
The precedent for evolving a TWINNED guard is `fde1e1303`, which widened port and oracle in lockstep. `.claude/oracles/README.md` marks the oracles FROZEN against UNILATERAL fixes, not against lockstep widening.
A `KNOWN_DIVERGENCES` entry cannot paper over a difference here either, because `tests/test_guards_differential.py:781` forbids the exit code itself from diverging.

The twins live at `.claude/oracles/pre-bash/block-*.sh`, and the differential that compares them is `.claude/rediacc_hooks/tests/test_guards_differential.py`. Both paths were verified to exist.

`block_stale_pr_branch_date` (ORDER 24) is a genuine fourth member of the class when probed alone, but it gets NO code change.
`dispatch.run_chain` stops at the first refusal, documented at `dispatch.py:74-96` as deliberate reproduction of the harness's own behaviour, and `block_nondraft_pr_create` sits at ORDER 23.
Banning the REST create there means ORDER 24 never sees the form at all, so the same detection added there would be unreachable code. The chain-level probe after implementation is what proves this.

## Ban by endpoint and method, never by shape

A blanket ban on the `gh api .../pulls/<n>` shape would break a path this repository actively depends on.
`.claude/hooks/post-bash/refresh-pr-body.sh:98` runs the REST PATCH body write, and the comment at `:90` records that `gh pr edit --body-file` cannot work there and never could.
That script is a PostToolUse hook, so the pre-bash chain never sees it. Separately, the same PATCH form typed by the assistant is ALREADY gated by `block_raw_pr_body_edit`, verified at rc=2.
The body path is therefore both legitimate and covered, and it must be left exactly as it is.

| endpoint | method | verdict |
|---|---|---|
| `pulls/<n>` | PATCH | gated already by `block_raw_pr_body_edit`, untouched |
| `pulls/<n>/merge` | PUT | banned, no call site in the tree |
| `pulls` (bare) | POST | banned, no call site in the tree |
| `graphql` carrying `markPullRequestReadyForReview` | any | banned |
| anything else, and every GET | any | allowed |

The ban is outright rather than routed into each guard's existing verification path, because a REST call carries none of the repo, selector or `--auto` shape that `run()` parses out of a `gh pr` segment.
The sanctioned forms `gh pr merge --rebase --auto`, `gh pr create --draft` and `gh pr ready` already pass, so nothing legitimate loses a route.

## Detection

Reuse the idiom at `block_raw_pr_body_edit.py:246-249` and its twin at `block-raw-pr-body-edit.sh:174-176`: split `SCAN` on the shell separators, keep segments with `gh api` at command position, then apply the endpoint and method tests INDEPENDENTLY.
Independence matters because `gh api` flags are order-independent, so the method flag may precede or follow the endpoint.
Per-guard constants are the house pattern here, and no shared `shellscan` helper is added: `shellscan.py` is field-compared against the live `command-scan.sh` that 28 oracles source, and a three-line regex does not justify that blast radius.

The GraphQL arm is a TWO-PART test and cannot be a single grep. `shellscan.scan_target` strips quoted spans, so the mutation name inside a quoted `-f query=` value is gone from SCAN entirely.
The arm requires `gh api graphql` at command position IN SCAN, and the literal mutation name in the RAW command, which is the same raw-versus-scan split `block_admin_merge.py:180` already uses for `--admin`.
One residual is accepted and must be stated in the guard header rather than left silent: a file-fed query is invisible to this test, no call site for it exists, and banning file-fed GraphQL wholesale would over-block.

## Where each arm hooks in

Each new arm goes BEFORE the existing `gh pr` early return, since a REST form carries no `gh pr` verb and would otherwise be dismissed before any new code ran.

- `block_admin_merge.py:170-172`, after `scan = ...` and before the `gh_pr_at_command_pos` guard; twin `block-admin-merge.sh:28-29`, between `SCAN=` and its own early exit.
- `block_nondraft_pr_create.py:70-72`; twin `block-nondraft-pr-create.sh:21-22`.
- `block_premature_ready.py:70-72`; twin `block-premature-ready.sh:23-24`.

Each message names the sanctioned alternative, and the create message states explicitly that the PATCH body edit is unaffected, so the guard does not teach a reader to avoid a form that is fine.
Message bytes stay identical across port and twin. Each port's comment-to-code ratio must stay at or above the 0.90 floor enforced at `tests/test_guards_differential.py:889`; current ratios run 1.50 to 1.58, so there is headroom.
Existing `DEFECT` tuples remain valid and are not touched.

## Tests, and the proof that each one can fail

New `EDGE_CASES` in BOTH directions per guard, since a corpus of block-only cases would pass against a guard that refused everything.
Per guard: the bypass, the same bypass with flags in the other order, the GET on the same endpoint as an ALLOW control, and prose naming the banned command inside a commit message as a second ALLOW control.
For the create guard the ALLOW controls additionally cover a POST to the `comments` sub-endpoint and the PATCH body form, which are the two nearest misses to the bare-`pulls` POST.
Every one of these decides before any `gh` call, so the stub limits recorded in the `block_admin_merge.py:21-31` PORT NOTE do not bite, and no new `ENVS` or `FIXTURES` are needed.

One BLOCK and one ALLOW per guard also mirror into `.claude/rediacc_hooks/tests/hookcases.py`, shape at `:1052`, where the per-guard check string is load-bearing for `hook_integrity.py:445`.
No `test-<stem>.py` harness is added: those exist for `TWIN = None` guards per `tests/test_guards_differential.py:588-597`.
Adding one to a twinned guard would credit both directions unconditionally at `hook_integrity.py:464-470` and MASK coverage rather than add it.

Each test is proven to fire by planting a defect in a scratch copy of the port, never in the tree.
Breaking the merge endpoint pattern must flip the new BLOCK cases from rc=2 to rc=0 while leaving the ALLOW cases alone.
Dropping the word-boundary anchor on the bare-`pulls` pattern must flip the `comments` sub-endpoint ALLOW case from rc=0 to rc=2, which proves that negative control is load-bearing rather than decorative.
Replacing the GraphQL two-part test with a bare grep for the mutation name must flip the prose ALLOW case, which proves the raw-versus-scan split earns its complexity.
Applying an arm to the port and NOT to its twin must turn `test_guard_matches_bash` red, and that plant runs BEFORE the twin edit, as the evidence that the pair is genuinely coupled.

## Verification

```
python3 -m pytest .claude/rediacc_hooks/tests/test_guards_differential.py -q
python3 -m pytest .claude/rediacc_hooks/tests/test_shellscan_differential.py .claude/rediacc_hooks/tests/test_dispatch.py -q
bash .claude/hooks/test-hooks.sh
python3 .ci/scripts/quality/check_hook_integrity.py
python3 .ci/scripts/quality/check_guard_mention_anchoring.py
python3 .ci/scripts/quality/check_guard_feature_completeness.py
python3 .ci/scripts/quality/check_language_policy.py
```

Then the live matrix, which is the part that answers the original finding rather than the test suite's opinion of it.
Every bypass in the table at the top must return rc=2 through `--chain pre-bash`, not merely through its own guard.
The REST create must return rc=2 through the chain, which is simultaneously the proof that `block_stale_pr_branch_date` needs no change of its own.
The PATCH body form must still reach `block_raw_pr_body_edit` and return rc=2 from THAT guard rather than from a new arm.
A plain run of `refresh-pr-body.sh` must stay rc=0 through the chain, proving the repository's own body-refresh path was not caught by the fix aimed at its neighbours.
