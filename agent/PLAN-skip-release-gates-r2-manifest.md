# PLAN: bump-none must withhold the R2 channel pointer, not just the tag
Status: done
Owner: 854ac1c6
Updated: 2026-08-26 (COMPLETE: remediation landed, T1-T4 green, precondition wired)

## 0. The state, re-verified in this session

| fact | evidence |
|---|---|
| edge channel advertises 1.3.1 | `curl https://releases.rediacc.com/cli/edge/manifest.json` -> `"version":"1.3.1"`, `"commit":"b4b5797e9ec1..."` |
| edge `latest.json` agrees | `{"version":"1.3.1"}` |
| no such tag | `git ls-remote --tags origin 'refs/tags/v1.3.*'` -> only `v1.3.0` (-> `79647ae3`) |
| release notes 404 | `curl -o /dev/null -w %{http_code} .../releases/tag/v1.3.1` -> `404` |
| the bytes ARE serving | `HEAD cli/v1.3.1/rdc-linux-x64` -> `200` |
| the version is NOT sealed | `HEAD cli/v1.3.1/.released` -> `404` (contrast `cli/v1.3.0/.released` -> `200`) |
| stable is still correct | stable manifest -> `1.3.0` / `79647ae3` |

**This has happened THREE times, and the immutable-URL promise is already broken.**

    684d01e4 -> PR #573  labels: documentation,ci,bump-none
    b4b5797e -> PR #574  labels: ci,bump-none
    1c006e53 -> PR #576  labels: ci,bump-none   (2026-08-26T11:26Z, AFTER this plan was written)

The third one is the sharpest evidence that this is a live, recurring bug rather than a
historical accident: it happened DURING the session that wrote this plan, from a merge
that plan's own author performed, and it silently invalidated the `ci_run_id` the
remediation in section 4 was about to use.

Both merges resolved `next_version` to `1.3.1` (only one tag behind them, `v1.3.0`), and
both ran the CLI upload loop. So `cli/v1.3.1/` was written with #573's bytes and then
OVERWRITTEN with #574's. `upload-to-r2.sh:312-313` states the promise being violated in
its own words: *"Versioned URLs are immutable -- the same URL never serves different
content."* Anyone who installed "1.3.1" between the two merges holds bytes whose sha256
does not match the sha256 the live manifest publishes. That is a supply-chain-shaped
defect, not only a cosmetic one.

**Three deadlines, not one.**

1. **2026-09-01** -- the 7-day soak elapses. `promote-stable.yml` (cron `0 6 * * *`,
   `:4-5`) promotes R2 + Docker first (`:70-100`), then calls the worker/account deploys
   with `ref: v1.3.1` (`:133`, `:159`). That ref does not exist; `actions/checkout`
   fails. Result: **stable CLI artifacts and Docker tags at 1.3.1, with
   eu/us/asia.rediacc.com workers still running 1.3.0 code** -- a half-applied production
   release across three regions.
2. **Continuously, now** -- every `rdc` on edge auto-updates to a build whose
   `releaseNotesUrl` 404s (`updater.ts:55` reads `cli/<ch>/manifest.json`;
   `install.sh:340` reads `cli/<ch>/latest.json`).
3. **~2026-09-08** -- `cleanup-versions.sh` Phase 8d reaps versioned prefixes with no
   sentinel and no tag past `R2_ORPHAN_VERSION_AGE_DAYS=14` (`:64`, `:1378-1383`). It
   deletes `cli/v1.3.1/` **while the edge pointer still names it**, at which point every
   edge install and update 404s. Housekeeping runs `0 3 * * *`, three hours ahead of
   promote-stable.

## 1. Cause, stated precisely

`bump-none` is honoured in exactly one place: `finalize-release-sentinel`
(`ci.yml:1585-1667`), which runs `dispatch-release.sh --decide-only` and guards the
sentinel write (`:1636`) and the cd-v2 dispatch (`:1664`).

That job `needs: [initialize, ci-complete]`. `stage-artifacts` -- the job that writes R2
-- is upstream of `ci-complete`. The decision is made **structurally too late to reach
the uploader**, and `cd-stage.yml` receives no skip signal at all (`:18-38`).

`dispatch-release.sh:13-15` already documents the intended contract: *"Merging it skips
the WHOLE release: no tag, no GitHub release, no R2 upload, no edge deploy."* The code
never implemented the "no R2 upload" clause. **This plan implements the policy already
written down; it does not invent one.**

## 2. Q1 -- what exactly is suppressed

**On a release channel with the release skipped, `upload-to-r2.sh` and
`upload-repos-to-r2.sh` write NOTHING** -- channel pointer and versioned path both.

### The channel pointer is unambiguously poison

`upload-to-r2.sh:339-343` writes `cli/<ch>/manifest.json` then `cli/<ch>/latest.json`.
Those two files are the entire contract with three consumers: the installer
(`install.sh:340`), the auto-updater (`updater.ts:55`), and the stable promoter
(`check-edge-manifest.sh`). `upload-repos-to-r2.sh` is pointer-only end to end (`:66`,
`:84-87`).

### The versioned path must ALSO be withheld -- and the original brief's reasoning was inverted

The brief warned that `write_once_guard` "seals it, so writing it now may block a later
real release at that version." **That is not what the guard does.** Verified at
`upload-to-r2.sh:196-232`:

- `write_once_guard` only READS. The seal is written by `write-release-sentinel.sh`,
  already skipped on `bump-none` (`ci.yml:1636`).
- A byte-only orphan hits `return 0` at `:231`, commented *"clean prefix or a byte-only
  orphan from a cancelled run. Do NOT scrub."*

Writing `cli/v1.3.1/` today does **not** block a later real 1.3.1. What it does is what
section 0 measured: successive skipped releases serve different bytes from the same
"immutable" URL, and it plants an orphan Phase 8d deletes under a live pointer.
Withholding costs nothing and removes both harms.

### Not special-cased

- **PR/preview channels (`pr-N`)**: untouched; no tag contract, signal never computed.
- **`cli/<ch>/rdc-*` channel binaries**: inside the whole-script rule, but for the record
  nothing reads them on a release channel (`install.sh:361-366` serves stable/edge from
  `cli/v${VERSION}/`).

### The consequence the brief did not mention, and it is the crux

`validate-install` and `validate-promote` are **pre-publish** validators reading the
staged channel (`test-install-methods.sh:562`, `:732`, `:1152`), then asserting
`--version <next_version>`. Withhold the pointer and they assert the NEW version against
the OLD published one and go red -- the failure `ci.yml:1336-1338` already documents.

**Ruling: when the release is skipped, `validate-install` and `validate-promote` SKIP.**
Not a new judgement -- the same ruling is recorded verbatim at `ci.yml:1340-1343` for the
empty-channel case: *"with no channel there is nothing staged, so the job has no
subject."* Both are `SOFT_REQUIRED` (`assert-ci-complete.sh:46`), which forgives
`skipped`, so `CI Complete` still goes green.

Same reasoning retires `cd-stage.yml:303-309` (`assert-r2-sentinel.sh`) and
`cd-stage.yml:193-207` (the `:edge` Docker retag, a channel pointer of the same family
and the input to `promote-stable.yml:90-98`).

## 3. Q2 -- how the signal reaches the uploader

**Move the ONE existing evaluation earlier, into `initialize`, and let all consumers read
that single output. Do not add a second decision anywhere.**

The `ci.yml:1646-1652` invariant -- *"both carry the SAME guard, evaluated once"* -- is
about the seal and the dispatch being inseparable. It forbids a second, independently
evaluated decision. It does not forbid an EARLIER single evaluation with more readers.
Today one evaluation guards two steps; afterwards one guards five. That strengthens it.

### Wiring

1. **`initialize.sh`** -- after bump-type detection (`:175`, which already makes the same
   `commits/{sha}/pulls` call), run the decision and `write_output "skip_release"`. Gate
   on push-to-`refs/heads/main` only; empty string elsewhere. Reuse
   `dispatch-release.sh --decide-only`; do NOT re-implement the label scan.
2. **`ci.yml`** -- add `initialize.outputs.skip_release`; `stage-artifacts` (`:846-877`)
   passes it in `with:`; `validate-install` (`:1322-1355`) and `validate-promote` gain it
   to their `if:`; `finalize-release-sentinel` DELETES its own decide step and both
   guards (`:1636`, `:1664`) read the initialize output. **Inverted polarity preserved
   exactly**, so every degenerate state (missing output, failed initialize, typo) still
   RELEASES. Update the `:1610-1620` and `:1646-1662` comments rather than deleting them.
3. **`cd-stage.yml`** -- new `skip_release` input. **Must land in the same commit as the
   ci.yml `with:` line**: `check-workflow-gates.sh` CHECK 2c fails a caller passing an
   undeclared input, 2b fails the reverse. The two upload steps (`:274-283`, `:285-294`)
   keep `if: inputs.channel != ''` and **pass the signal down** rather than being
   `if:`-skipped -- an `if:` here would make the script-level guard untestable-in-anger
   and therefore vacuous. Docker retag (`:193-207`) and sentinel assert (`:303-309`) DO
   gain the condition, because their policy is not something a script owns.
4. **`upload-to-r2.sh`** -- new `--skip-release` flag (and `SKIP_RELEASE` env for the
   sibling, which takes no argv). After CHANNEL validation (`:73-78`), if truthy AND
   channel is `stable|edge`, print a loud multi-line block naming `bump-none` and the
   fact that nothing was written, then `exit 0`. On other channels, a logged no-op.
5. **`upload-repos-to-r2.sh`** -- same early exit after the `:47-52` require block.
6. **`dispatch-release.sh`** -- header `:11-16` already claims "no R2 upload". Keep the
   words; add a line naming the two upload scripts as the enforcers.

### The one risk, and why it is acceptable

The label is read ~45 minutes earlier than the seal. The window is inert:
`claude-review.yml:10-15` triggers only on PR-branch `workflow_run`,
`pull_request: [ready_for_review]`, and manual dispatch -- none of which a merged PR
receives. Failure directions are asymmetric the right way: a label ADDED mid-run still
releases, which is the fail-open doctrine's preferred error. Say so in the step comment.

## 4. Q3 -- remediating the state that is live right now

> **DONE 2026-08-26T12:55Z.** The operator explicitly authorized "cut the real v1.3.1
> now", and it is landed. Evidence, verified against the LIVE bucket rather than the run
> logs:
>
> | fact | before | after |
> |---|---|---|
> | `v1.3.1` git tag | missing | present -- annotated object `046bc89b` dereferencing to commit **`1c006e53`** |
> | release notes URL | 404 | **200** |
> | `cli/v1.3.1/.released` | 404 | **200** |
> | edge manifest | 1.3.1, untagged | 1.3.1 @ `1c006e53`, consistent |
>
> Runs: Release **32968110599** (success) -> tag + GitHub Release carrying 16 `rdc-*`
> assets; Backfill Release Sentinel dry-run **32970815242** (guards: semver ok, commit
> reachable from `origin/main`, assets present) then execute **32970957023**.
>
> **The `ci_run_id` in step 1 below had to be corrected before dispatch, and that is the
> lasting lesson.** The plan named `32903007256` (`b4b5797e`), correct when written.
> Merging PR #576 -- itself `bump-none` -- advanced the pointer a THIRD time (#573, #574,
> #576), so the live manifest had moved to `1c006e53`. Dispatching the original id would
> have tagged v1.3.1 at a commit whose bytes edge no longer served: the exact
> tag-vs-artifact drift this plan exists to end, reintroduced by the plan's own
> remediation step. **Re-read `cli/edge/manifest.json` immediately before any dispatch.**
>
> All three deadlines in section 0 are cleared. The `#573`-bytes sha256 divergence is
> accepted and unrepairable, as section 4 always said.

**OPERATOR-ONLY.** It writes production R2, creates a tag on `main`, and publishes a
GitHub Release. Per CLAUDE.md, no session performs any of it unasked.
Door: `door:operator-only`.

### Roll forward, do not roll back

An edge client that already auto-updated to "1.3.1" will never move to a LATER real
1.3.1 -- identical version string, and the updater compares versions. Rolling back
manufactures a cohort permanently stranded on untagged bytes. Cutting the real release
makes reality match what is already published.

### Exact sequence

1. **Cut the release.** `Release` workflow (`cd-v2.yml`), `release_mode=patch`,
   **`ci_run_id=32961178698`** (the successful push-to-main CI run for `1c006e53`).
   CORRECTED 2026-08-26T12:2xZ: this plan originally named `32903007256`
   (`b4b5797e`), which was right when it was written and is now WRONG. Merging
   PR #576 -- itself `bump-none` -- advanced the edge pointer a THIRD time, so
   the live manifest reads `"commit": "1c006e53..."`, `releaseDate
   2026-08-26T11:26:48Z`. Tagging v1.3.1 at `b4b5797e` would point the tag at a
   commit whose bytes edge is no longer serving, which is the same
   tag-vs-artifact drift this whole plan exists to end. Always re-read the live
   manifest immediately before dispatching; each further bump-none merge moves
   it again. With
   `v1.3.0` latest it computes `next_version=1.3.1`, and `cd-v2.yml:187-196`
   independently confirms the staged artifacts really are 1.3.1 before tagging.
2. **Seal the version.** `Backfill Release Sentinel`, `version=v1.3.1`, `channel=edge`,
   `dry_run=true` first, then `dry_run=false` +
   `confirmation=I_UNDERSTAND_THIS_WRITES_TO_R2=yes`. REQUIRED, not optional:
   `rsv_assert_bijection` is bidirectional, and once `v1.3.1` is tagged the next
   push-to-main computes `IN_FLIGHT=v1.3.2`, so an unsealed `v1.3.1` becomes
   `DRIFT v1.3.1: git tag present, cli sentinel missing` and reddens
   `check-release-state` on every later merge. Backfill guard 2 requires the GitHub
   Release to exist, which is why step 1 comes first.
3. **Re-verify** the section 0 rows: tag resolves, notes 200, `cli/v1.3.1/.released` 200,
   `npm run check:ci-release-state` clean.
4. **Only then land T3.** T3 correctly fails on the live bucket until this is done;
   landing it first blocks every push-to-main behind an operator action.

### Accept and record the sha256 divergence

The #573-bytes cohort cannot be repaired retroactively. Note it in the v1.3.1 release
body rather than leaving it undocumented.

## 5. Q4 -- should promote-stable defend itself? YES

1. **It is the only defense not depending on the upstream fix being right.** Any future
   cause of an untagged pointer arrives at this workflow with the same shape.
2. **The failure is ordered catastrophically today.** R2 and Docker promotion
   (`:70-100`) both succeed, and only then does `ref: v<version>` fail (`:133`, `:159`).
   Failing at step 2 turns a half-applied three-region release into a loud no-op.
3. **Its oracle is independent of its subject.** Manifest is the subject; git tags and
   the Releases API are the judge.

**Against, and the rebuttal:** it duplicates the section 2 invariant -- and that is the
point. Different causes, different blast radii, different failure times. Defense in depth
at a production boundary is not redundancy.

### Design

New `.ci/scripts/release/assert-edge-tag-exists.sh`, run in `promote-stable.yml`
immediately after `Check edge manifest` (`:31-33`) and before `Check stable manifest`
(`:35-40`) -- before ANY promotion write. Guarded by the same
`steps.edge.outputs.skip != 'true'`. Asserts, for `v<EDGE_VERSION>`: the git ref returns
200; `gh release view` exists; `cli/v<V>/.released` exists in R2.

- **Use the API, not `git rev-parse`.** The checkout at `:29` is shallow with no tags; a
  `git rev-parse` would fail on a perfectly good tag.
- **FAIL (exit 1), never skip.** A skip is how `label:rollback` silently never fired. A
  daily red cron is a correct alarm; a daily silent no-op is not.
- **"Could not tell" is a failure.** 404 confirms; 403/500/network means the check did
  not run, and a check that did not run must not read as a pass.
- `permissions:` already carries `contents: read`; the Releases read needs no extra grant.

## 6. Verification -- every test names its planted defect and its expected red

### 6.1 T1 -- the uploader's own guard

**New:** `.ci/scripts/test/gates/test-skip-release-channel-pointer.sh`. Auto-discovered
by `run-all.sh` (glob over `gates/test-*.sh`), classified **T** (mktemp-isolated; do NOT
add to `WRITER_TESTS`/`SCANNER_TESTS`). Uses the fake-`aws`-on-`PATH` recorder from
`test-write-once-guard.sh:33-59`. Drives the REAL script, not an extracted function.

| case | planted defect | expected |
|---|---|---|
| a. FIRE | delete the `SKIP_RELEASE` early-exit | `aws.log` regains `cli/edge/manifest.json`, `latest.json`, `cli/<V>/` -> red |
| b. SILENT-WHEN-CLEAN | make the guard unconditional | no-flag `--channel edge` writes nothing -> red. The more important half: a silently withheld release is the failure `dispatch-release.sh:24-28` is built around |
| c. narrowness | make the guard ignore `CHANNEL` | `--channel pr-7 --skip-release` stops uploading -> red |
| d. anti-vacuity | -- | zero binaries in the fixture, or an empty `aws.log` in (b), FAILS. Print the observed call count on success |

Sibling for `upload-repos-to-r2.sh` in the same file.

**Stated blind spot** (in the header AND the success output): this cannot see whether any
workflow passes the flag. T2 owns that.

### 6.2 T2 -- the wiring, so T1 is not a flag nobody passes

**Extend** `.ci/scripts/security/check-ci-workflow-invariants.sh` with a
`skip-release-threading` invariant (it already parses `ci.yml` with python3 and carries
the `WORKFLOW_FILE` seam at `:47` for driving mutated copies). Gate test:
`.ci/scripts/test/gates/test-ci-workflow-invariants.sh`.

Asserts: `initialize` declares the output; `stage-artifacts` passes it; `validate-install`
and `validate-promote` reference it; `finalize-release-sentinel` contains NO
`--decide-only` step and its two guards are one expression; `cd-stage.yml` declares the
input, forwards it in both upload steps, and conditions the retag and sentinel-assert.

| planted defect (mutated copy) | expected |
|---|---|
| delete `skip_release:` from `stage-artifacts`'s `with:` | exit 1 |
| re-add a second `--decide-only` step | exit 1 |
| drop the input from `cd-stage.yml` | exit 1 |
| unmutated tree | exit 0, printing the relation count |

Inherited free: `check-workflow-gates.sh` CHECK 2b/2c catch declared-but-unpassed and the
reverse.

### 6.3 T3 -- the live relation: a channel pointer must name a tagged version

**Extend** `.ci/scripts/lib/release-state-validator.sh` with
`rsv_assert_channel_pointer_tagged`, called from `check-release-state.sh` (npm
`check:ci-release-state`, `package.json:137`; job at `ci.yml:816-838`).

For `edge` and `stable`: read `latest.json` and `manifest.json`, require the version to
carry a git tag, exclude `IN_FLIGHT_VERSION`, and require the two files to AGREE
(written seconds apart at `:340`/`:343`; disagreement means a torn write).

**Why the ordering is safe -- verify before trusting.** `check-release-state` runs
*before* `stage-artifacts` (`ci.yml:810-812` says so), so the pointer it reads is the
previous release's. Back-to-back merges resolve themselves: if release X's tag is not
pushed, `initialize` computed `next_version = X` from the same tag-less state, so
`IN_FLIGHT = vX` equals the pointer and is excluded; if pushed, `IN_FLIGHT = vX+1` and
X has its tag.

| planted defect | expected |
|---|---|
| fixture manifest naming an untagged version | exit 1 with a `DRIFT` line naming the channel |
| `latest.json` and `manifest.json` disagreeing | exit 1 |
| zero channels resolvable (network/credential failure) | exit 1 -- anti-vacuity |
| ~~today's real bucket~~ | ~~**exit 1**, correctly~~ -- **NO LONGER TRUE as of 2026-08-26T12:55Z**: the bucket is honest (v1.3.1 tagged and sealed), so T3 is UNBLOCKED and should now pass against it. Verify that before landing, and treat a red as a real finding rather than the expected state |

Unit coverage in the existing `test-release-state-consistency.sh`. Secondary placement
worth taking: also call it from `housekeeping.yml` (`0 3 * * *`, three hours ahead of
promote-stable), closing the one-merge latency on a repo that can go days without a merge.

### 6.4 T4 -- the promote-stable precondition

Gate test with a fake `gh` and fake `aws`.

| case | expected |
|---|---|
| FIRE: version with no tag ref (today's 1.3.1) | exit 1, before any promotion step |
| FIRE: tag exists, Release absent | exit 1 |
| FIRE: tag + release, `.released` absent | exit 1 |
| CLEAN: `v1.3.0` shape | exit 0 |
| "could not tell": `gh` 403 | exit 1, NOT 0 |
| planted defect: 403 arm returns 0 | that case goes green -> red |

Plus a wiring assertion in T2 that `promote-stable.yml` runs the precondition and its
step index is BEFORE `Promote R2 artifacts`. A precondition running after the promotion
is worth nothing, and step order is exactly what a later edit reorders silently.

### 6.5 Registration

For a gate test under `.ci/scripts/test/gates/` only the manifest point is needed, and
this is how the battery is wired, not a shortcut:

- **No `package.json` key**, **no new `ci-quality.yml` step**: `run-all.sh` globs
  `gates/test-*.sh` (`:73`, `:165-171`) and the existing `Quality-gate unit tests` step
  runs the battery.
- **`scripts/ci-runner/manifest.ts` IS required**, one entry per gate test.
  `check-ci-parity.ts:542-556` (assertion 7) compares `qualityGateTest: true` entries
  against the on-disk glob in BOTH directions. Copy `gate-test:edge-verify-retries`
  (`manifest.ts:1115-1127`).

**Coordination warning:** `scripts/ci-runner/manifest.ts` and `.github/workflows/ci.yml`
both hold uncommitted work in this tree. Confirm with the operator before editing either.

### 6.6 Existing gates that will react

| gate | why it moves | action |
|---|---|---|
| `check:ci-parity` | new `gates/` file without a manifest entry fails assertion 7 | add the entry |
| `check-workflow-gates.sh` 2b/2c | declared-vs-passed must match | land ci.yml + cd-stage.yml in ONE commit |
| `check-workflows.sh` | `INLINE_MAX_LOGIC=8`; `continue-on-error` banned | keep the new step a one-line script call |
| `check-release-state.sh` | gains a relation, red on the live bucket | remediate BEFORE landing T3 |
| `assert-ci-complete.sh` | the two validators newly `skipped` | none -- both `SOFT_REQUIRED` at `:46` |
| `check-shell-format` | every touched `.sh` | `shfmt -w -i 4` |

## 7. Sequencing

**COMPLETE as of 2026-08-26T14:0xZ.** Every step below landed:
step 1 remediation (section 4); step 2 both upload guards + `assert-edge-tag-exists.sh`
+ T1/T4; step 3 the workflow threading (`initialize.sh` step 6b -> `ci.yml` ->
`cd-stage.yml`) with `finalize-release-sentinel` now READING the shared decision instead
of re-deciding; T2 in `check-ci-workflow-invariants.sh` (real ci.yml clean, all five
planted defects fire); T3 `rsv_assert_channel_pointer_tagged` wired into
`check-release-state.sh` for edge and stable. The section-5 precondition is wired at
`promote-stable.yml:55`, BEFORE `Promote R2 artifacts` at `:92` -- it existed as a script
for a while with nothing running it, which is the same "a guard nothing invokes" failure
T2 exists to prevent, caught by the plan-freshness check.

**T3's decisive proof:** replayed against the pre-remediation tag list it emits
`DRIFT edge: the channel pointer names 'v1.3.1', which has NO git tag` (rc=1), and with
`IN_FLIGHT` set it correctly returns 0. It would have caught the original bug.

**Superseded note:** the earlier progress line said `promote-stable.yml` and T2 were not
done. Both are now.

**Historical progress as of 2026-08-26T12:55Z:** step 1 DONE (section 4). Step 2 DONE — both upload
scripts guarded, `assert-edge-tag-exists.sh` written, T1 and T4 green with planted
defects proven to fire, manifest entries added (`check-ci-parity` 298 gates / 111 battery,
gate-reachability 295, both green). Step 3 DONE for `initialize.sh`, `ci.yml` and
`cd-stage.yml`; **`promote-stable.yml` and T2 are NOT done**. Step 4 (T3) is now
UNBLOCKED. Step 5 not reached.

**T2 is the one that must not be skipped.** Until it exists, `--skip-release` is a flag
with no gate proving any workflow passes it, and both T1 and T4 name exactly that as
their declared blind spot. A guard nothing invokes is the vacuity failure this repo keeps
paying for.

**An instrument this plan depends on was broken, and is now fixed.** Step 5 says to watch
the next bump-none merge. Watching a dispatched run was impossible: a branch's GraphQL
`statusCheckRollup` does not contain a `workflow_dispatch` run's check runs. Measured on
Release run 32968110599 -- the REST check-runs API for `1c006e53` showed
`in_progress  Tag & Release` while the branch rollup returned 81 contexts, state SUCCESS,
none in flight. `ci-trace.py --wait --ref main` therefore printed GREEN and exited 0
mid-release, twice, including with `--until-final`; and the obvious CLI alternative is
hook-blocked as unreliable. `ci-trace.py` now takes `--run RUN_ID`, reading per-JOB
conclusions (verified: in-flight -> exit 2, completed-success -> 0, unreadable -> 2).
`/pr-merge` step 5 still documents the false-green form and must be corrected.

1. ~~**Operator, first and alone:** section 4 remediation.~~ **DONE** — see section 4.
2. Scripts + tests: `upload-to-r2.sh`, `upload-repos-to-r2.sh`,
   `assert-edge-tag-exists.sh`, T1, T4, manifest entries.
3. Workflow threading in ONE commit: `initialize.sh`, `ci.yml`, `cd-stage.yml`,
   `promote-stable.yml`, plus T2.
4. T3 last, after step 1 is confirmed green against the live bucket.
5. **The real first live run is the verification.** A `bump-none` merge is the only thing
   that exercises the whole path; PR CI structurally cannot (PR runs carry `channel=pr-N`).
   Watch the next bump-none merge: `stage-artifacts` green with a loud "wrote nothing"
   block, the two validators skipped, `CI Complete` green, and `cli/edge/latest.json`
   unchanged -- confirm that last one by curl, not by reading the log.

## 8. Documentation to update in the same change

- `CLAUDE.md` "Release Channels" -- a `bump-none` merge advances no channel pointer.
- `docs/agent-reference/ci-gates.md` -- the `bump-none` row and the new gate names.
- `.github/labels.yml:90` -- the `bump-none` description promises behaviour that only
  becomes true with this change.

## 9. Open, unverified

- That `initialize`'s token has the scope `--decide-only` needs. Same
  `commits/{sha}/pulls` endpoint `detect-bump-type.sh` already calls with `GH_TOKEN` in
  that job, so it should hold -- hypothesis until run.
- Whether `promote-stable.yml`'s `contents: read` suffices for `gh release view`.
- End-to-end behaviour: only a real `bump-none` merge exercises it.
- `private/` submodules were not checked for other readers of the edge manifest.
