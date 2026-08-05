# Progress: what has actually been built

The other documents in this folder describe the plan. This one records what
landed, with evidence, and it is the file to update when the code moves. It was
created on 2026-07-29 because the design docs had drifted **44 commits** behind
`.ci/`, `.github/` and `.claude/` on branch `0728-2`, which is exactly the
failure the Stop hook's design-doc check now blocks.

Everything below is on **PR #543** (branch `0728-2`) unless stated otherwise.
README's line "Nothing in it has been built" is no longer true; start here.

---

## Wave A: landed and MERGED (PR #541, 2026-07-28T02:51Z)

**A2 is proven on real scheduled traffic**, with a boundary that lands exactly on
the merge:

    2026-07-24 cancelled   2026-07-25 cancelled
    2026-07-26 cancelled   2026-07-27 cancelled
    <- #541 merges ->
    2026-07-28 FAILURE     2026-07-29 FAILURE

Twelve consecutive nights of failures laundered into `cancelled`, then honest
failures the first night Wave A's code was on main. A2b fired too: issue **#544
"Nightly CI is red"** is open.

**A5 clause 1 (a GREEN scheduled run) is still unmet.** The 2026-07-29 nightly
failed only `Quality / Code` (plus `CI Complete` as a consequence), on
`docker/login-action v4.5.1 -> v4.5.2`. That needs no work: main's
`scripts/check-actions.ts` has **zero** references to `isReleaseDeferred`, while
this branch adds 107 lines including it, so main is running the gate without its
release-age window. #543 is the fix.

## Wave B: built, two acceptance criteria still open

Against `05-execution-guide.md`:

| Criterion | State |
|---|---|
| (a) a reduced run demonstrated | **NO** - needs a throwaway PR |
| (b) `pointer_bump_only` observed TRUE | **NO** - needs a pointer-only push |
| (c) reconciler fails on a planted mismatch | **YES**, locally: 62 assertions, controls fire |
| (d) every new gate seen to fire | **YES** |

**D9 is fixed and the proof is in its own reason string.** It was
`merge commit <x> in the walk` on 13 of 13 runs, meaning the walk aborted
immediately on the synthetic `refs/pull/N/merge` head. It now reads
`no baseline within 5 commits`: the walk runs and terminates on its own cap.

**The baseline resolver is FOUR of five conditions on real traffic.** Round 23's
`scope-baseline.json` rejected the green commit `bb9dd6794` with
`unreconciled-outcome`, not `not-green`. Reading `scope-engine.cjs:151-164`, that
is the *last* of five checks (`plan.reconciled !== true`, line 161). So that
commit was green, carried an attested skip plan, and the plan was full-mode. Only
the `reconciled` flag is missing, and the shadow reconciler never sets it. One
flag is the entire remaining distance, and D-1 forbids closing it until the
reconciler is trusted.

**The reconcile shadow's "WOULD HAVE PASSED" is vacuous and must not be banked.**
It runs on `ubuntu-slim` in ~8-11s against `ci-complete`'s `timeout-minutes: 5`
(ci.yml:1197 -- an earlier draft of this file said 15, which was wrong and matters,
because a slim job that runs out of time is marked cancelled with no failed step
and that reads as neither pass nor fail), node present,
and reports 17 planned keys against 93-94 jobs. But all 17 entries are
`{"run": true, "reason": "full"}`, so it reconciles trivially. It proves the
reconciler does not crash, not that it can detect anything. **#543 can never
produce a non-vacuous reconcile**, because it touches `.ci/` and is therefore
fail-closed to `mode: full`.

**FIRST GREEN RUN: `30472960194` on `2469e5d72`, 95 jobs, zero failed, zero
cancelled.** It exists only because the session stopped pushing: the eleven runs
before it were all `cancelled` with ZERO failed jobs, each superseded by the next
push, and the pointer-bump detector had named the consequence precisely
(`baseline 3e483a6 has no successful CI Complete`). Not pushing was the work.
Note the run grew 92 -> 95 jobs while being read, so a job count is never a
terminal-state signal.

Shadow evidence from that run, recorded verbatim rather than summarised:

- **D9's fix is confirmed on real traffic.** Initialize reports
  `pointer_bump_only=false -- no baseline within 5 commits`. The old reason was
  `merge commit <x> in the walk` on 13 of 13 runs, meaning the walk aborted
  instantly on the synthetic `refs/pull/N/merge` head. It now runs and stops on
  its own cap.
- **Baseline resolver: `baseline:none-usable`, `"baseline": null`**, as expected
  until an attested plan exists upstream of a green run.
- **The `ubuntu-slim` question is ANSWERED: node IS available.** The reconcile
  shadow ran to completion in 3.4s against `ci-complete`'s `timeout-minutes: 5`,
  so the "cannot reconcile: node is not available" branch is not the live one.
- **And the reconcile is still VACUOUS, confirmed by reading the artifact rather
  than the summary.** `ci-skip-plan`'s `plan.json` is `mode: full` with 17 keys,
  and all 17 are `{"run": true, "reason": "full"}`, so it reconciles trivially.
  `WOULD HAVE PASSED` means the reconciler does not crash, nothing more. #543
  touches `.ci/`, so it is fail-closed to full mode and can never produce a
  non-vacuous reconcile; that prediction is now live-verified, not inferred.

**THE BASELINE WAS NEVER ONE FLAG AWAY. It was one NUMBER away.** Round 23's
reading, that only `plan.reconciled` was missing, was true of that run and
became the wrong thing to chase. On run `30478917957` the walk rejected all five
candidates with `not-green`, and the genuinely green commit `2469e5d72` (run
`30472960194`, 95 jobs, zero failed) sat **seven** steps back, one row past
`DEFAULT_CANDIDATE_LIMIT = 5`. A baseline that exists but cannot be reached
reads identically to one that does not exist.

The old value's stated reason was that "the headline case is satisfied by the
FIRST candidate (the commit immediately before this push)". That is false on the
branch this engine was built to serve: a babysat PR accumulates a run of red and
superseded commits between greens, so the nearest green ancestor is never the
first candidate. The limit is now 20. Walking further can only find an OLDER
baseline, hence a BIGGER net delta and MORE jobs, so overshooting is safe and
undershooting is not.

**And no test could have caught it, which is the more important finding.** The
fixture's `rev-list` mock returned every candidate regardless of `--max-count`,
so walk depth was invisible to the whole suite. The mock now truncates like the
real command, and case (m) pins the behaviour with a control: a chain whose only
green ancestor sits at depth 7 must be UNREACHABLE at limit 5 and REACHED at the
engine default. Without the control half, the case would pass on a fixture that
proves nothing.

**THE BASELINE RESOLVED, first time ever, on run `30486245900`.** With the walk
at 20 the trail reads `623e87092 not-green` then
**`681443ad3 full-green-attested`**, and `"baseline"` is a real object instead of
`null`. Everything the design assumed but had never observed is now on real
traffic: the walk reaches a green ancestor, the plan behind it attests, and the
delta is computed from there.

**And the engine measurably narrows the diff.** From that baseline the net delta
is **2 files** (`scope-engine.cjs`, `test-scope-baseline-attest.sh`); the
merge-base classify over the same head lists **80+**. That is the entire point
of scoping to the last green rather than to the merge base, shown rather than
argued.

It still reports `mode: full`, for an honest reason: both files are `harness:`
under `.ci/`. **So the recipe for the first reduced run is now known and needs no
throwaway PR**: push a delta that touches only paths carrying no `full:` reason.
A `docs/`-only push qualifies, because `docs` appears in no job surface. This is
what the operator meant by "we don't need a new PR": the net delta from the green
baseline is what is classified, not the PR's whole diff.

**D5 has a live receipt.** `web-27a7cd16729b` and `rdc-334c6306793e` are now
distinct where `RDC_TAG` was literally assigned `"$WEB_TAG"`. Changing
`--extra` (the renet tag) changes the web tag, which closes the most likely
stale-reuse hole. The weekly bucket is at `generate-tag.sh:269`.

**#538 is fixed and proven by execution**, not by reading: `printf -v` replaces
three `eval` sites in `common.sh`, and the CI-path proof arrived when
`Stage Artifacts` went green (it runs the `build-pages.sh --output` caller).

**`generate-tag.sh`'s renet input list: the plan was wrong.** It wanted
`.ci/scripts/infra/build-renet.sh` added because nine jobs run it. It must not
be: that script builds a dev binary for jobs that never receive this tag
(`ct-tests.yml` declares exactly two inputs, `full_suite` and
`pointer_bump_only`, and never references `renet_tag`). Adding it would cost a
45-minute rebuild on every harmless edit. The exclusion and its reason are now
recorded at `generate-tag.sh:105-112`.

## Wave C: LANDED, dark

Both halves are on `0728-2` and the workflow is **inert**: all six stage flags
are repo variables (`AUTOPILOT_ENABLED`, `ALLOW_STATE`, `ALLOW_FINISH`, `MODEL`,
`ALLOW_PUSH`, `ALLOW_SUBMODULES`) and none of them exist, so absent means off.
Enabling a stage still waits for Wave B on real traffic; that was always a
separate event from landing, and conflating the two parked this wave for a day.

**Harness** `b5c2e8f90`, `.ci/scripts/autopilot/`, 1509 lines plus 972 of test.
**Workflow** `ad058d085`, `.github/workflows/autopilot.yml` (486 lines), its
invariants gate (172) and that gate's test (146).

Both non-negotiables are STRUCTURAL, not documented:

- **The model never holds a write token.** In the file: the first app-token mint
  is at `autopilot.yml:360`, after `claude-code-action` at `:318`. The gate job
  can never mint one at all, and both facts are mutation-tested.
- **Wall 4.** Every checkout carries `persist-credentials: false` (five sites),
  the first checkout of every job is pinned to `rediacc/console@main`, and the
  restore/assert pair runs live around the PR-head checkout. Its control fires
  in the direction that matters: it detects the tampered config when restore is
  NOT run.

**The invariants gate mutates the LIVE workflow, not a frozen fixture**, so its
proofs cannot rot as the workflow changes. Eight failure-direction cases, each
with an `assert_mutated` guard so a drifted workflow fails loudly instead of
silently testing nothing.

**Both defects found while landing this were in the CHECKING side and in the
cry-wolf direction**, which is the dangerous one: the gate judged a checkout's
`with:` block by the `uses:` indent and so fired on a correct `- name:` step,
and the test asserted a success line on stdout while `log_info` writes to
stderr. A gate that cries wolf on a correct tree is worse than an absent one,
because it teaches everyone to ignore it.

Not verified, and only S1 shadow can: `workflow_run` delivery, artifact handoff
between jobs, app-token minting, and the action's behaviour under this prompt
shape. The workflow cannot be tested pre-merge (`03-v2-autonomy.md` section 8).

## Three regression gates added, from defects found this session

The operator's standing rule is that a fix without a mechanism is how the same
bug returns. Each of these came from a real defect found tonight:

- **`check-gate-reachability.ts`** (`e91cfad58`): fails when a `check:ci-*` gate
  is defined but never run. `check-ci-chain-parity.ts` cannot catch it, by
  design: it enforces only that gates a WORKFLOW names are reachable, never the
  reverse. Reachability is TRANSITIVE and a substring test over `scripts.ci` is
  wrong; that error produced two false dead-gate reports before the walk
  replaced it, and is now a control assertion.
- **`check-jq-boolean-default.ts`** (`9a7e7edf8`): jq's `//` treats false as
  empty, so `.draft // true` is true whenever draft is absent OR false. The live
  instance made a NON-draft PR read as a draft, so the autopilot could never
  conclude a PR was done. `// false` is deliberately not flagged, because that
  direction cannot invert and flagging it would make the gate noise.
- **The cross-locale gate's dead fire-proof** (`b424900ff`): it shipped with a
  planted-defect selftest behind a `--selftest` flag that NOTHING invoked, so
  the gate sat in the `ci` chain with its only proof dead. The control now runs
  inline, which turns "did the control fire" into "did the gate exit 0".

The anti-vacuity registry earned its keep twice here: it caught the jq gate
CRASHING on an empty tree instead of refusing, and it caught a registry entry of
mine using a basename where `.sh` entries are repo-root-relative.

## The Stop hook now enforces the regression rule itself

`1a45b061a`. On a stop where a fix landed, the judge is asked what property of
the defect made every existing check blind to it, and is handed the REAL
`check:ci-*` key list so a claimed gate name is verifiable and a hallucinated
one fails closed. It blocks only on recurring AND ungated AND unproven AND
undeferred. Also `0a84216a9`: cross-session requests, because a finding written
into a commit message reached nobody and the operator had to relay it by hand.

## Wave C: the App, validated earlier

**The `rediacc-autopilot` App EXISTS and is validated.** app_id `4409539`,
installation `149445627`. It holds **no bypass** on console ruleset `12344707`
(the actors are `RepositoryRole:5` and `Integration:2772000`), and its
permissions are `actions:write, contents:write, issues:write, metadata:read,
pull_requests:write` - notably **no `administration` and no `workflows`**, so it
cannot rewrite the CI that judges it. Credentials are staged as
`AUTOPILOT_APP_ID` and `AUTOPILOT_PRIVATE_KEY`.

That invariant is now pinned by `.ci/scripts/quality/check-autopilot-no-bypass.sh`
with six controls. The gate is built around a measured trap: console is public,
so an unauthenticated GET of the ruleset answers **200 and silently omits
`bypass_actors`**, which would make a naive gate pass for ever. Presence of the
field is asserted before its contents.

Not wired into `npm run ci`: reading `bypass_actors` needs `Administration: read`,
which no current app token grants and which would collide with
`check-no-app-admin-perm.sh`. Unverified: the App's `repository_selection` list
is unreadable from a session, so "it can mint a token for console" is untested.

**Landing Wave C is NOT gated on Wave B.** `05-execution-guide.md:108` says it
"Lands with **every stage flag off**", and only *enabling* a stage waits for
Wave B's two live observations. These were collapsed into one blocker in an
earlier status report, which is why Wave C sat still with nothing blocking it.

**Two S0 prerequisites recorded as "moved into PR-B" (`03-v2-autonomy.md:332-334`
and `:377`) were never done. Both are fixed here**, found by the Wave C planning
agent and verified before acting:

- `check-resolved-threads.sh` asked for `reviewThreads(first: 100)` with no
  cursor. Because the gate only ever reports UNRESOLVED threads, an unresolved
  thread at position 101 read as "all threads resolved": a silent green on a
  merge-blocking check, the same failure class as the `|| echo "[]"` bug already
  fixed in that file. It now paginates, fails closed on a non-advancing cursor,
  checks for GraphQL errors per page, and re-wraps into the original response
  shape so every consumer is unchanged. Proven live on PR #543 (2 threads) and
  #541 (1 thread), so it still SEES rather than merely not crashing. The
  now-unreachable duplicate error check after the loop was deleted rather than
  left looking like a safety net.
- `worklist.py` had no CI branch (zero `GITHUB_ACTIONS` references). `CLAUDE.md`
  tells a session to append `- [ ]` items and this hook refuses to end a turn
  while any remain, so an unattended model in Actions burns its turn budget
  against a gate no human will answer. It now exits 0 when
  `GITHUB_ACTIONS=true`, placed **after** the read-only query modes so `--path`
  and `--handover` keep working on a runner. Three cases added (46-48) including
  a control that the same worklist state still blocks off a runner, and that a
  value other than `true` is not a runner. 46/46.

**S-2 was unproven and is now SETTLED (2026-07-30).** The paragraph that stood
here said no live `--max-budget-usd 0.01` run was recorded anywhere and that
therefore no dollar stop was known to exist. That was true when written and is
false now; full evidence in `spike-s1-s2.md`.

It did not need a CI dispatch. The action pin `fa7e2f0a` is v1.0.180, which
bundles Claude Code 2.1.217, and that exact build was already on the dev machine
under `claudeAiOauth` with no `ANTHROPIC_API_KEY`, i.e. the same auth class as
`CLAUDE_CODE_OAUTH_TOKEN`. So the experiment ran on the real pinned binary under
real OAuth, for $0.49.

**The flag BINDS, but as a post-hoc stop, not a ceiling.** Cap `0.01` produced
exit 1, `subtype: error_max_budget_usd`, `terminal_reason: budget_exhausted`,
and `total_cost_usd: 0.2340351`. A 23x overshoot, because the check compares
ACCUMULATED cost against the cap BETWEEN turns and nothing bounds a single
request, so the real guarantee is *total <= budget + one more turn*. A control
run at `--max-budget-usd 100` spent $0.22 without halting, proving it is not a
blanket abort. **Say a dollar stop exists; never say a hard cap does.**
`03-v2-autonomy.md`'s cost section has been rewritten accordingly, and
`01-verified-context.md:413`'s "do not claim it binds" warning is marked
superseded.

S-1 is likewise resolved and the reading is unchanged: issue #539 is a cosmetic
label bug, not a review-quality one, so every finding received so far came from
the requested model. Corroborated independently of the original argument by
comment `5102584893` reading `Cost: $5.9255 (claude-sonnet-5) | 61 turns`, and
by `claude-review-gate.sh:280-300` joining EVERY `modelUsage` key with `", "`,
so one name with no comma proves exactly one key.

**One design consequence Wave C must not discover in production**, derived from
the `if:` conditions rather than observed: `error_max_budget_usd` carries
`is_error: true`, so the step FAILS, and the three steps after it in
`claude-review-reusable.yml` carry only a `gate.outputs.go` condition with no
status function, so implicit `success()` skips all three. A budget halt would
therefore mean a red job, no report, no findings, and **no marker SHA**, so the
next run re-reviews the same commit and pays again. If the flag is wired in,
decide deliberately whether those steps get `always()`.

## The Stop hook (`.claude/hooks/stop/worklist.py` v5)

Not in the original plan; added 2026-07-29 because the old gate watched the wrong
queue. It blocked only on `- [ ]`, and this session held **zero** open items all
night while the harness Task list carried six pending.

Now: harness task-list awareness, a required `## Remaining` section naming every
open task id, `DEFAULT:` on every deferral, a session brief, one-cron enforcement
read from `session_crons`, a 250-600 character single-paragraph handover, a
`PostCompact` hook that hands it back, a `SessionStart` hook that forces these
design docs into context, this drift check, and a haiku judge on quiet stops.
`MAX_BLOCKS` is deleted: there is no escape hatch.

Two measured facts that constrain any future change:

- **`claude -p` fires the project's Stop hook**, and `--settings '{"hooks":{}}'`
  does NOT suppress it. The `STOPHOOK_CHILD` env guard is the only thing that
  works, and it is the first statement of `main()`.
- **The Stop event already carries** `last_assistant_message`, `session_crons`
  and `background_tasks`. Do not reconstruct any of them from the transcript;
  doing so is what made the gate fire on its own author.

## Corrections to the other documents

- README: "Nothing in it has been built" was stale. FIXED 2026-07-30; the README
  now points at this file and records both spikes as settled.
- `01-verified-context.md`: the nightly was red **12 of 12**, not four nights.
- The plan's `generate-tag.sh` renet-input instruction is wrong; see above.
- Wave C's App blocker is closed. The App exists and is validated.

## The classifier chain is dark in production (A3 follow-up, 2026-07-30)

A3 shipped the three-tier chain and the fail-closed allowlist. Live evidence from
run `30509062386` (watchdog job `90767439738`, 03:04:40Z) is that **both AI tiers
are declining and the chain is running on the safety net alone**:

    [AI] Cloudflare classifier returned HTTP 402
    [AI] Claude classifier returned HTTP 400

402 on Cloudflare is quota. **400 on Anthropic is a malformed request, so it is
most likely our bug rather than an outage** and is worth chasing. The A3 design
behaved correctly here: it warned, fell back to the allowlist, and retried an
allowlisted leg. But that means every allowlisted failure currently takes a blind
retry, roughly 500 machine-minutes, with no classification behind it.

Neither status was diagnosable, because both non-ok branches logged the status and
threw the body away. Fixed in `6706399e2`: a shared `errorBody()` logs the
provider's own explanation, truncated to 300 chars for a public run log. The
classifier-chain test's stub gained `text()` (without it the new path logs
`(body unreadable)` and any assertion is vacuous) plus real provider error bodies,
and the new case pins both fallback strings as controls. Proven to fail with the
fix reverted. **Root-cause the 400 once a live run prints it.**

### The E2E flake this surfaced, still unfixed

`E2E Workers (opensuse-16.0)` failed in 11 minutes against a ~44 minute normal
duration, in Playwright global setup, before any test ran:

    Error: failed to start RustFS: ssh command failed: exit status 125
    docker: failed to copy: httpReadSeeker: ... read: connection reset by peer

Docker Hub's CDN reset the same blob twice, 8 seconds apart, while the bridge VM
pulled `rustfs/rustfs:latest`. The pull is an **unguarded single shot**:
`private/renet/pkg/infra/docker/service.go:381-405` runs a bare `docker pull` with
no retry, and `packages/e2e-tests/src/base/bridge-global-setup.ts:193-201` throws
on the first failure. The image is not prepulled (`ct-tests.yml:235` covers only
debian and ubuntu), so the VM pulls it anonymously and uncached every run. One
reset kills the pipeline's slowest leg. Fix is a retry with backoff around the
pull, or prepull on the runner and `docker save`/`load` into the VM. Deferred to
a follow-up renet PR: the allowlist already retries this leg, so today it costs a
retry rather than a red.

### Tooling defect fixed in passing

`gh run view --log-failed` is **run-scoped even when given `--job`**. It refuses
while the run is in progress, exits 1, and writes the explanation to stderr, so a
`2>/dev/null` capture looks like an empty log. Use
`gh api repos/OWNER/REPO/actions/jobs/<id>/logs` for a completed job inside a live
run. The watchdog already does exactly this.

## Second full green, and the reduced-run demonstration (2026-07-30)

Run `30517957988` on `0b04a6f38` finished **completed/success, 95 jobs, zero
failures**, and PR #543 moved from `BLOCKED` to `CLEAN`. That is the second full
green on this branch; the first was `30509062386` on `43ecb261a`.

This commit is deliberately **docs-only and pushed FIRST after that green**,
because the scope engine computes its net delta from the last green ancestor
rather than from the PR diff. Classified offline before pushing:

    mode: reduced   full_reasons: []   jobs OFF: 17 of 17

Three controls confirm the classifier discriminates rather than always saying
`reduced`: a `.ci/` harness change returns `full` with
`harness:.ci/scripts/ci/watchdog-monitor.cjs`, a real 16-file delta returns
`full`, and an unmapped path fails closed to `full` with `unclassified:`.

### The skip plan now encodes pre-existing skips, so the reconcile stops being vacuous

The reconcile shadow had never once produced a meaningful verdict, for two
separate reasons, and only one of them was known. The first is recorded above:
every PR in this program touches `.ci/`, so the plan is fail-closed to
`mode: full` and reconciles trivially. **The second is worse and would have
survived the fix to the first: the plan encoded only what SCOPE wants, while
`ci.yml` has skipped whole columns since long before this engine existed.**

Three conditions, all verified in the tree rather than assumed:

- **`full_suite`** (`ci.yml:118`, `github.event_name != 'push'`) gates 16 of the
  17 planned keys: the twelve `ct-tests` leaves by their own `if:`
  (`ct-tests.yml:122, 134, 320, 454, 597, 733, 875, 1018, 1182, 1343, 1474,
  1514`), plus `ops` (`ci.yml:717`), `elite_run` (`:739`), `update_flow`
  (`:568`) and `package_tests` (`:584`).
- **`pointer_bump_only`** (`ci.yml:123`) gates **all seventeen**, and ten of
  them TRANSITIVELY, which is exactly why this could not be read off the leaves'
  own `if:`: `build-renet` skips (`ci.yml:493`) and everything below inherits
  through `build-docker-fast` (`:532`), `build-cli` (`:553`) and `build-docker`
  (`:512`). The twelve `ct-tests` leaves never mention `pointer_bump_only` and
  all twelve skip on one.
- **`is_bot`** (`ci.yml:105`) reaches exactly one key, `install_methods`, via
  `stage-artifacts` (`ci.yml:658`).

**The edge that matters is `install_methods` under `full_suite`.**
`validate-install` (`ci.yml:1081-1083`) hangs off `stage-artifacts`, which
carries no `full_suite` clause, so the install matrix genuinely DOES run on
push-to-main. Exempting it there would have excused a real skip permanently.
That asymmetry is a test pair, not a comment.

So a live gate today would report **seventeen** `planned-run-but-skipped`
failures on any pointer-bump PR, a run where nothing is wrong. Measured, not
predicted: the unannotated plan against an all-skipped jobs payload exits 1 and
names `unit` and `install_methods` among them.

`plan.conditions` now records the observed values and each job entry carries the
condition that will skip it, written by the REAL `annotatePlan()` that
`scope-shadow.sh` calls, so writer and reader share one table instead of two
that can drift. The reader re-derives from `plan.conditions` and hard-fails on
disagreement (`preexisting-claim-mismatch`), in both directions: a forged
per-job exemption and a stale writer that dropped one are equally loud.

**The sharpest decision is that `honorPreexisting` DEFAULTS TO FALSE.** The two
consumers of `reconcile()` want opposite things. The GATE must not red a
pointer-bump run. The BASELINE READER, `scope-engine.cjs`'s `attestPlan`, must
not accept that run as proof: a baseline is "the last run where everything
passed", and a run where all seventeen keys skipped passed nothing. Had the
exemption been opt-out, this change would have silently widened what counts as a
usable baseline and let the delta since a pointer bump go unvalidated. The CLI
opts in; `attestPlan` never hears of the flag and keeps refusing.

**Non-vacuity is now visible rather than assumed.** The CLI prints the excused
keys and the headline counts VERIFIED keys, not planned ones:
`0 of 17 planned keys verified` is what a pointer-bump run reports, which reads
as the empty result it is instead of as a pass.

Evidence, all run locally with stdout and stderr captured separately:

- `test-skip-plan-reconcile.sh` exit 0, **118 assertion call sites** (was 62).
  Nine new cases, each a FIRE/SILENT pair.
- **Five mutants, each caught by a different assertion**, run in a sandbox copy
  so the shared tree was never touched: force `honorPreexisting` true, make
  `preexistingSkip` return null, widen `full_suite` to cover `install_methods`,
  delete the claim-mismatch check, compare conditions as strings. Restored copy
  back to exit 0.
- `test-gate-anti-vacuity.sh` exit 0; `test-scope-engine.sh` exit 0 (84);
  `test-scope-baseline-attest.sh` exit 0 (125), which is the `attestPlan`
  consumer.
- The real `scope-shadow.sh` driven against a real merge commit writes a plan
  whose `conditions` and per-job `preexisting_skip` are correct, and an unset
  variable is OMITTED rather than defaulted (defaulting `full_suite` to false
  would have exempted sixteen keys on no evidence).
- `actionlint .github/workflows/ci.yml` exit 0; `shfmt -i 4 -ci -d` clean on all
  three shell files.

**One defect fixed in passing, in the file being edited.** The plan writer ended
in `2>/dev/null || true`, and the upload step carries
`if-no-files-found: ignore`, so a crash in the writer produced no artifact and
the reconcile shadow then reported the benign-sounding "no attested plan for
this run" with the exception thrown away. A writer failure is now printed. Proven
by making the write fail (`plan.json` as a directory): the script still exits 0,
as a shadow observer must, but the exception is readable.

**One workflow change, and it is the minimum.** `ci.yml`'s scope-shadow step
gained three `env:` entries. Two of the three are `steps.init` outputs and
cannot be derived inside the script; the third is derived from
`github.event_name` for symmetry. Nothing else in `ci.yml` moved, and the engine
is still in shadow: flipping it live remains decision D-1.

**Still vacuous for a different reason, and this is the honest caveat.** The
plan is authored only on `pull_request` (`ci.yml:230, 241, 257`), where
`full_suite` is always true and `is_bot` always false, so only
`pointer_bump_only` can fire on today's traffic. The other two become live the
moment the plan is authored on push. A docs-only PR would now reconcile
non-vacuously in the sense that matters most (a `reduced` plan whose `run: false`
keys are checked against a run that really skipped them), but "non-vacuous" for
the exemption path specifically needs a pointer-bump PR, which is Wave B
acceptance criterion (b) and still unmet.

### Merge strategy changed, and it changes how you audit branches

All five repos moved to **rebase-merge only** with `delete_branch_on_merge=true`
on 2026-07-30, replacing squash. Squash collapsed huge PRs into one commit (#520
was 100 commits, 1314 files, +226k/-101k), so `git blame` pointed at a commit
that explained nothing.

The trap this leaves behind is permanent and worth stating plainly: **rebase
rewrites every SHA, so a merged branch shares no commit with `main` and
`git branch --merged` reports it as unmerged.** That test called all 75 console
local branches unsafe to delete when 59 had merged PRs. Ask the PR, never
ancestry. Settings were also inconsistent before this: `delete_branch_on_merge`
was false on renet, account and homebrew-tap and true on console and elite,
which is exactly why those three accumulated stale remote branches and the other
two stayed tidy.

### The watchdog reported red for supersession, and the classifier is live

Two findings from one artifact: watchdog run `30534675663`, monitoring console
run `30530991847` on `0730-2`, 2026-07-30.

**The good half, and it is the first real-traffic proof of Wave A's A3 work.**
The log carries both halves of that item working on live traffic rather than on
a hand-run probe:

    [logs] captured the full log for "Quality / Content" (61415 bytes) before any retry
    Retrying: classifier returned transient at confidence 0.8 -- treating as transient

The pre-retry log capture persisted 61 KB, and the Workers AI classifier
returned a real verdict at confidence 0.8. The classifier had been answering
HTTP 402 on every failure and falling back to `confidence: 0`; the fix was the
model and route change to `@cf/meta/llama-3.3-70b-instruct-fp8-fast` on the
native `/ai/run/` endpoint, and this is it working outside a probe.

**The defect.** A push created run `30534726467` fifteen seconds before the
first poll, superseding `30530991847` by concurrency group. The watchdog polled:

    [0m] Run: in_progress | Jobs: 10 done, 7 running, 0 queued, 0 failed, 2 cancelled
    ##[error]Job cancelled (likely manual / supersession): "Quality / Content"

**Zero failed, two cancelled**, an unambiguous supersession signature, and the
watchdog nonetheless treated it as a failure: it spent a billed Workers AI
classification and called `core.setFailed`, so the step concluded `failure` for
a run nobody broke. The existing mass-cancellation guard could not help, because
it only fires at `cancelled >= completed / 2`; during a supersession jobs flip a
few at a time, so on the first poll the ratio is nowhere near met and by the
time it is met `setFailed` has already stuck.

This is the **mirror image** of the defect Wave A exists to fix. Laundering
`failure` into `cancelled` hid twelve red nightlies. Reporting `failure` for the
most ordinary event in the repo trains the operator to ignore watchdog reds,
which eventually hides a real one just as effectively.

**Fix**: `evaluateSupersession` plus `hasNewerRun` in `watchdog-monitor.cjs`,
checked at the top of the poll and **before** anything can classify, since
reaching `classifyFailure` is what spends the request and leads to `setFailed`.
The verdict requires all three of: no job failed, at least one was cancelled,
and a newer run demonstrably exists for the same workflow and branch. The API
lookup runs only once the cheap local half already holds, so a healthy run pays
nothing, and any error resolves to `false`.

**The polarity is deliberately lopsided.** Too loud costs a spurious red; too
quiet silently swallows a genuine failure, which is strictly worse. Pushing a
fix while the old run is still red is the normal way this arises, so
"a newer run exists" must never on its own excuse a failure. That case is the
single most important assertion in `test-watchdog-supersession.sh`.

Both controls were **run, not reasoned**: dropping `noFailures` from the
predicate flips the real-failure case red, and relaxing `newerRunExists === true`
to `Boolean(...)` flips the strict-comparison case red. The gate is deliberately
not in the anti-vacuity registry, and that was measured too: it passes all nine
assertions against the empty fixture, because its only repo dependency is the
watchdog module the harness copies in, so an entry there could never fail. The
exclusion is documented in `test-gate-anti-vacuity.sh` alongside the others.

### The retry allowlist now OVERRIDES a confident code-change verdict (operator, 2026-07-30)

A policy reversal, made with its cost stated, so it is recorded rather than
discovered later in a diff.

**What forced it.** Run `30540751569`, job `90867219911`. `Tests + Infra / E2E Ceph`
failed on `failed to install Docker on node 21: ssh command failed: exit status 6`,
preceded by a `manifest unknown` image-pull warning. That is infrastructure. The
classifier answered **code-change at 0.9**, reasoning that "the error message
indicates a setup error and E2E tests failed, which suggests a problem with the
code under test" -- a tautology over the words "Setup failed", not an analysis.
Because 0.9 clears the threshold it suppressed the retry, and the watchdog
force-cancelled eighteen healthy siblings around the one red job.

**The decision.** The operator was offered a prompt-side fix (demand a cited
root-cause line) and chose the policy-side one: for jobs on
`WATCHDOG_RETRY_ALLOWLIST_PATTERNS` the allowlist now beats a confident
code-change verdict. The recommendation had been prompt-side; this is an
override and is marked as one.

**Why it is defensible.** Allowlist membership is a claim about the JOB (it boots
VMs, it pulls images across the network), and a claim about a job cannot be wrong
about a particular failure the way a model's reading of one log can. The cost is
bounded: `MAX_ATTEMPTS` caps this at ONE extra attempt.

**What it costs, stated plainly.** It re-opens part of #537, whose complaint was
that everything retried on a judgment nobody made. The mitigation is that the
override is narrow (allowlisted jobs only), loud (the reason string names it),
and bounded (one attempt).

**What still outranks it.** `guardForced`. The binary-exec guard SYNTHESISES a
code-change verdict at confidence 1 specifically to block a retry of a job that
downloads and executes a released binary, and the allowlist must never undo a
deliberate safety check. That distinction now travels with the verdict as an
explicit flag rather than being inferred from confidence, because a real
classifier can also answer 1.0 -- the old test stood on exactly that proxy, and
it would have silently handed the guard's authority to any confident model. No
install-validation job matches the current allowlist, so this is defence in depth
rather than a live conflict, and it stays correct if either list moves.

Proven by mutation, not by reading: deleting the `!guardForced` term makes
`test-watchdog-retry-allowlist.sh` exit 1, and the file was restored and verified
by sha256 checksum. Battery 56 gates / 601 assertions green.

### D5, the remaining half: the closure key ignored the released version

**The D5 tag split was already done and the plan's description of it is stale.**
`05-execution-guide.md` still describes `RDC_TAG="$WEB_TAG"` with one tag serving
two images; `initialize.sh:159-160` has computed separate `--closure web` and
`--closure rdc` tags for some time. The remaining defect was narrower and had
nothing to do with the split.

**What was actually broken.** Both closure images BAKE a version in (the rdc SEA
reports it from `rdc --version`, the www footer from `APP_VERSION`), and that
version derives from the latest git TAG. A tag is not a path, so no
`CLOSURE_PATHS` entry could ever cover it. The irony is exact:
`generate-tag.sh` documented its OID-at-HEAD hashing as being *"immune to the
in-job version bump that dirties package.json"*. That immunity is right for a
dirty working file and precisely wrong here, so the key went insensitive to the
one input the image is stamped with.

**Reproduced twice on real traffic, and it was not a race.** Release `v1.2.12`
landed 2026-07-30T10:16:14Z mid-PR. Runs `30534726467` and `30542942037` both
failed `Validate Install Methods / Linux` with
`Version mismatch: expected '1.2.13', got '1.2.12'`. In both,
`Build (Docker) / CLI Docker` was **skipped** while `CLI Docker (cached)`
succeeded, so the mutable `pr-546` tag kept serving a pre-release image while
every run computed the next version afresh. Nothing on the branch could break the
tie, because cutting a tag does not move the closure. **Deterministic and
self-perpetuating: PR #546 could not have gone green without this fix.** An
earlier note in this session called it a one-off release race; that was wrong and
is corrected here.

**Fix**: closure mode now folds `resolve-version.sh --current` into the key.
Resolved inside `generate-tag.sh` rather than passed by the caller, so no call
site can forget it, and `--current` rather than the computed next version because
the bump type is not known until after `initialize.sh` has already called this
script, and reordering that is release-affecting. An unresolvable version (a
shallow clone, a fresh fork) degrades to an empty marker rather than failing the
build. Residual, stated rather than hidden: two runs on the same base tag that
resolve different bump types would bake different versions behind one key; that
cannot produce the failure above, which required the base tag to move, and the
weekly bucket bounds it anyway.

**Also corrected: a comment claiming this mode was inert.** `generate-tag.sh`
said *"NOT WIRED INTO initialize.sh YET, deliberately"* while `initialize.sh`
calls it and `cd-stage.yml:195-196` retags the result straight onto a release
channel. A reader who believes a key is inert will not scrutinise it, which is
roughly how the missing version survived. Of the two blockers that comment said
had to be settled first, the unbounded staleness window IS handled by the weekly
bucket; "same tag implies same bytes" is still FALSE (unpinned `npm install` for
private/account, floating base images, a build-arg public key) and remains a
known limitation rather than a solved one.

Proven by mutation, not by reading: deleting the version line makes
`test-generate-tag-inputs.sh` exit 1 with "the rdc closure tag did NOT move when
the released version moved", and both the script and `resolve-version.sh` were
restored and verified byte-identical by sha256 (the test swaps a real tracked
file in a shared tree, so that check is not optional). Battery 56 gates / 603
assertions.

### The pre-existing conditions are RECORDED on live traffic (2026-07-30)

First live confirmation, read out of the artifact rather than inferred from the
diff. `ci-skip-plan` from run `30547421380` on `732fb7e9c`:

    mode: full   keys: 17   run=true: 17   run=false: 0
    conditions: {pointer_bump_only: false, full_suite: true, is_bot: false}
    preexisting_skip entries: []
    reconciled: null

Every value is the correct one for this run, and each says something different:

- **`conditions` is populated at all**, which is the whole point. Before this
  change the plan recorded no non-scope conditions, so the reconciler could not
  tell a scope skip from one `ci.yml` always makes, and a live gate would have
  redded seventeen keys on a pointer-bump PR.
- `mode: full` is HONEST, not a failure: this push touches `.ci/`, so the engine
  is fail-closed to full. It is why #546 itself can never produce a non-vacuous
  reconcile, which was predicted and is now observed again.
- `preexisting_skip` is empty and MUST be, because `full_suite` is true and
  `pointer_bump_only` is false, so nothing is exempt. An entry here would have
  been the bug, not the feature.
- `reconciled: null` is correct in shadow mode; only the live gate sets it, and
  D-1 keeps the engine in shadow until `pointer_bump_only` is seen true.

What this does NOT yet show, stated so nobody banks it: the exemption path is
still unexercised, because exempting anything requires `pointer_bump_only: true`
or a plan authored on `push`, and today plans are authored only on
`pull_request` (ci.yml:230, 241, 257).

### The review cost model: a pass that produced nothing now costs budget

Measured, not designed from theory. PR #546's first review (run `30552035566`)
ended `"subtype": "error_max_turns"` after **51 turns and $2.8468**, posted
nothing, and left ZERO github-actions comments on the PR.

Every step after the model call carried no status function, so implicit
`success()` skipped all three, including the marker. Since the cap counts POSTED
reports, that pass counted as **zero**, the budget never advanced, and the same
SHA would have been re-reviewed at full price on every later green push, able to
fail identically forever.

The S-2 spike predicted exactly this shape for a budget halt: "red job, no
report, no findings, no marker SHA, and the next run re-reviews the same SHA and
pays again". It arrived via `max_turns` rather than `max_budget`, which is a
useful confirmation that the spike's reasoning generalised.

**A spent attempt is not a reviewed marker**, and that distinction is the whole
safety property. It carries its own `ATTEMPT_PREFIX` so `last_marker_sha` cannot
see it (a pass that read nothing must never suppress a later genuine review of
the same SHA), while `spent_attempt_count` does, so it consumes budget. It
records the failure subtype, because "we stopped reviewing this PR" is only
defensible if it says what the budget was spent on. `always()` went on the marker
step and nowhere else: post-report and post-findings have nothing to post when
the model produced nothing, so running them would only add two ways to fail.

### `modelUsage` is sound; the earlier empty render was a one-off

Closed from the FIRST preserved execution artifact, which exists only because the
upload step is `always()`-guarded and therefore survived the review's own
failure. Artifact `claude-review-execution-732fb7e9c...` (id 8763349532, 806969
bytes, 285 records):

    modelUsage keys : ['claude-sonnet-5']
    outputTokens    : 17040
    usage.output_tokens : 17040

The field is populated and the two agree exactly, so run `30527484990`'s empty
render was a one-off in a since-superseded run rather than a live defect. Third
independent confirmation of spike S-1 along the way: one model key, sonnet, no
haiku.

### Wave B acceptance (a): the REDUCED RUN is demonstrated on live traffic

Run `30562133323` on `826b6834a`, the docs-only push made as the FIRST push
after green run `30557767857`. Read from the run's own `scope-shadow` artifact,
not from a local classify, and the two files in it are the whole argument side
by side:

`scope-baseline.json`, the net-delta-from-last-green engine:

    mode: reduced   modules: [docs]
    reasons: [docs/ci-overhaul/06-progress.md -> docs]
    all 17 job keys: run=false, reason out-of-scope
    baseline: 24a4e4d0e (run 30557767857)
    baseline_trail: [{24a4e4d0e, usable, full-green-attested}]

`scope-classify.json`, the merge-base view of the SAME head:

    mode: full   (16 harness:/workflow-closure: reasons, .ci/ and .github/)

Same commit, same run: the cumulative frame says full, the incremental frame
says reduced with seventeen jobs cut. The 5-percent-versus-30-percent economics
this program was built on is now SHOWN on live traffic rather than measured
offline. The engine stayed in SHADOW per D-1, so no job was engine-skipped (the
run's 19 skips are the ordinary cache- and condition-driven set); the
demonstration is the artifact, which is exactly what shadow mode is for.

Remaining for full Wave B acceptance: (b) `pointer_bump_only` observed TRUE,
which is also the only way to exercise the plan's exemption path.

### `Review Complete` is NOT self-healing: `claude-review.yml`'s `workflow_run` stopped firing (2026-07-30)

Previously assumed self-healing ("a green current head triggers a fresh
review"). Disproven on live traffic: `claude-review.yml`'s `workflow_run`
listener (`workflows: ["Console CI"], types: [completed]`) fired exactly ONCE
for branch `0730-2` -- run `30552035566` on head `732fb7e9c`, 2026-07-30
14:30:29Z, which itself FAILED (the review-cost leak `4e38553c1` fixed) --
and then never again. Confirmed against the real endpoint
(`gh api repos/rediacc/console/actions/workflows/claude-review.yml/runs`,
NOT the ambiguous `/actions/runs?workflow_id=` form, which silently ignores
the filter and returns every workflow): zero runs of any conclusion for any
later `0730-2` head, including the head whose own "Console CI" pull_request
run (`30572143752`) completed green at attempt 2, `19:45:54Z` -- still
nothing 25+ minutes later. `claude-review.yml` itself is byte-identical to
`origin/main` (`git diff origin/main -- .github/workflows/claude-review.yml`
empty), so this is not the usual "default-branch-runs-a-stale-copy" trap.
Root cause of the non-delivery is still open (GitHub Actions `workflow_run`
delivery semantics, or a platform-side issue); not chased further this round.

**Fix landed (`32d26034`, small and local): a `workflow_dispatch` escape
hatch on console's caller.** The gate script and the reusable already had a
complete `workflow_dispatch`/`pr_number` code path (see `claude-review-gate.sh`'s
`pull_request | workflow_dispatch` case) -- both submodule callers
(`private/renet`, `private/account`) already wire it. Console's caller was the
one missing the trigger declaration; this closes that one gap rather than
adding new logic, and keeps the same safety invariant (the gate re-checks
`required_check` is green on the CURRENT head before reviewing anything).
Manual escape hatch, not a fix for the delivery gap itself: `gh workflow run
claude-review.yml --ref <branch> -f pr_number=<n>` when `workflow_run` fails
to fire again. **`--ref` is mandatory while this trigger is unmerged**: GitHub
resolves whether a workflow accepts `workflow_dispatch` from the DEFAULT
BRANCH's copy of the file, so the bare form fails closed with a 422 ("Workflow
does not have 'workflow_dispatch' trigger") until main has this block too.
Observed live and worked end-to-end once `--ref 0730-2` was added: dispatched
run `30588312405`, `event: workflow_dispatch`, head `c09848cc0` (the current
PR head at the time).

### `main` has been red for real, 3 nights running (2026-07-28/29/30)

All three nightly runs (`30327872124`, `30421536380`, `30512465488`) failed
with `conclusion: failure` (not the old `cancelled`-laundering bug -- A2's fix
is holding) on the SAME head `b549047790` (#541, the last merge to main). Two
live, unrelated-to-this-program defects block task #9's real-scheduled-run
acceptance criterion:

- `Quality / Content` -- 15 tutorial x language combos with flat/estimated
  word timing (caption-sync gate, owned by the solution-video/VoxCPM2
  campaign, not this program). Deliberately left untouched.
- `Quality / Packages` -- **corrected from an earlier misdiagnosis in this
  doc**, which blamed "13 knip unused-import errors." Re-verified against the
  raw job log: those 13 Biome findings are explicitly marked non-blocking
  ("Frontend lint issues found (non-blocking)") and are not what failed the
  job. The actual failure is `src/adapters/__tests__/storage.test.ts` >
  `ConfigFileStorage` > `stress tests` > `should not corrupt file under
  concurrent writes`: `ENOENT` on `rename(tempPath, configPath)`.
  `tempPath` was `${configPath}.tmp.${process.pid}.${Date.now()}` -- two
  `saveUnlocked` calls for the same config name landing in the same
  millisecond compute an identical path, and whichever renames second hits
  `ENOENT` because the first already moved it away. Did not reproduce under
  15 sequential local runs, 6 parallel processes, or 3 runs under synthetic
  20-core CPU load, consistent with a CI-runner-load-dependent race. Fixed
  in PR #547 (branch `0731-1`, off main, in a separate worktree) by appending
  a `randomUUID()` to `tempPath`. Verified: `tsc --noEmit` clean, `biome
  check` clean, `test:unit --workspace=@rediacc/cli` 159/159 files, 2132/2132
  tests. PR #547 does not touch the caption-sync failure above.

### The `supervised` stuck-detector exemption was not correlated to the live worker

Real review finding (PR #546, comments `3686789736` and `3686791985`,
duplicated because two review passes caught it independently before the
fix landed): `wl_checks.py`'s `_supervised` computation took the freshest
`[>]` in-flight record across *all* of the session's records, with no
check that its `worker:<id>` tag names the same background task as
`live_bg`. A session holding two concurrent leases -- one genuinely
tracking the watched job, one unrelated and still being renewed for some
other reason -- would compute `_supervised = True` off the unrelated
item, silencing the exempt-overrun fire even while the item tracking the
actual job had gone stale. Fixed by correlating via `worker:<id>`,
mirroring `wl_liveness.ladder()`'s existing `wid not in now_bg` pattern.
Added cases 155/155b to `test-worklist-v5.sh` and proved them meaningful:
reverted the fix, confirmed case 155 failed exactly as predicted, then
restored byte-identical (diffed against a backup) and confirmed both
pass. Verified: `test-worklist-v5.sh` 284/284 with `GITHUB_ACTIONS` unset
and set.

### Wave B half (b) closed: `pointer_bump_only=true` observed on a real push

Observed 2026-07-31, run `30612674911`, head `9ea0b5e07`. The push was a pure
`private/account` gitlink bump (`9890f5eff -> b200794`) over a green head, made
to fix the nightly's Submodule Branches finding (main's pointer was the
pre-rebase head of merged account PR #71). initialize reported:

    pointer_bump_only=true -- baseline 07f3db1 passed CI Complete;
    private/account 9890f5e->b200794 (tree-identical, on rediacc/account main)

and the shadow scope plan exempted every expensive key on it
(`unit:pointer_bump_only`, the full `e2e_*` family). This was the last
unexercised exemption path in the skip plan; it fired on a REAL, needed bump
rather than a synthetic one, exactly as the deferral's DEFAULT prescribed.

Found in the same round, worth its own trap note: `gh pr edit --body` with an
IDENTICAL body does not bump `lastEditedAt`, so a "refresh" that changes
nothing does not satisfy the PR-description freshness gate. A refresh must
actually change the body.

## D-1 GO-LIVE: the engine leaves shadow (branch 0731-2, 2026-07-31)

Context that landed just before this wave: PR #546 (0730-2) MERGED as
af0da029f (operator decision, 09:50:11Z) and shipped release v1.2.13; the
merge cures both scheduled-nightly causes. D-7
`strict_required_status_checks_policy` flipped TRUE on ruleset 12344707
(verified on the PUT response), so every PR must now be up to date with main
before merging. Issue #548 files the v2 deferrals with reasons. Issues
#533/#534/#537/#538/#539 closed with evidence comments.

**Item 2 of the wave (submodule review) needed NO code.** The bootstrap
defect recorded at 01-verified-context.md:426-435 was already fixed on main
by b54904779: the reusable checks out rediacc/console@main into
.review-scripts (claude-review-reusable.yml:110-115), hard-asserts the gate
script arrived, and stages it into RUNNER_TEMP. CLAUDE_CODE_OAUTH_TOKEN is
set repo-level on renet/account/elite (org-level cannot cover private repos
on the free tier). Remaining: one live dispatch on a submodule PR to confirm
end to end.

**The flip itself.** scope-shadow.sh (same filename) is now the decider:
kill switches first (`full-ci` label per PR, `FULL_CI` repo variable
globally, and deleting the step entirely, all revert-free), then the plan
is written FROM scope-baseline.json (the deciding plan and the reconciled
plan are the same object; the merge-base classify stays as a diagnostic),
then outputs are emitted ONLY as `run_<key>=false` lines plus `scope_mode`,
buffered and appended once, only after plan.json wrote. Fail-open lives in
the encoding: consumers test `!= 'false'`, so every failure mode leaves
full CI. initialize exposes 17 outputs; the tests caller forwards 12 as
inputs; five top-level jobs append the condition; migration-test is
untouched. assert-ci-complete.sh needed nothing: all five skippable
top-level jobs were already SOFT_REQUIRED.

**The reconciler goes hard exactly when work was skipped.**
SCOPE_MODE=reduced arms it: a missing plan, an unreadable Jobs API, or a
reconcile failure is exit 1, because a reduction nobody can verify is a
skip nobody attested. Any other mode keeps the tolerant shadow behavior.
The rerun question was settled with `filter=all` on the Jobs API, so the
gate applies to every attempt rather than being scoped to attempt 1.

**E2E account-trees cut**: `account: 'true'` removed from the 8 VM/E2E
jobs' setup-workspace blocks (kept for test-account-e2e, which targets
private/account). Saves the nma- cache restore of three node_modules trees
per job (three npm ci runs on a miss) and removes account-lockfile changes
from the E2E invalidation surface. No measured seconds existed before the
cut; take before/after from the first post-merge run.

**Proofs run, not reasoned**: test-scope-gate-outputs.sh (6 cases, each
with a control; the dead-emitter control re-proven by planted defect at
integration time: suppressing the run_*=false push fails exactly the
anti-vacuity case and nothing else); the 17 emitted names are pinned
against ci.yml byte for byte; test-skip-plan-reconcile.sh,
test-scope-engine.sh, test-scope-baseline-attest.sh all green; actionlint
and check-workflow-gates clean.

**First live-reduced observation plan**: this PR touches .ci/ and .github/,
so the engine decides FULL on its own PR and the hard reconciler verifies
all 17 planned-run keys on every green run of the PR itself. The first
reduced run comes from the next docs-only push after a green baseline,
observed (initialize run_* lines, 17 job skips, reconcile verified counts)
before that PR merges. The nightly stays full by construction: no scope
outputs exist on schedule events.

**Stop-hook work riding this branch** (the local-only ban was lifted by the
operator): v13 F2 SES email channel with mail-optional skip semantics, v14
six gap fixes, v15 pure-background-wait with the 15-minute worker check-in,
the Stop hook timeout raised 15s to 300s (the judge alone budgets 120s;
the 15s registration was killing every judge-consulting stop, which
surfaced as the operator-reported EAGAIN), and 12 stale teammate tasks
stopped to relieve harness process pressure.

## 2026-07-31 (later): the silent-failure gate was doubly dead, repaired with a 28-site sweep

Chasing the D-1 wave's one non-transient red (Migration Test attempt 2 on run
30628110972: the asia D1 export died in a 21-second gap with ZERO error text)
led through three nested defects, each proven by a planted control:

1. **clone-d1.sh's export** piped wrangler through `grep -v <R2-url>` under
   pipefail. A failing wrangler lost its message, and a SUCCESSFUL export
   whose whole output was the redacted lines made `grep -v` exit 1 and kill
   the step silently. Now capture-first, redact-after, report wrangler's own
   exit code.
2. **check-silent-failure-patterns.sh had never fired since it was written**,
   for two independent reasons: awk's `-v` escape mangling rewrote the
   `\|\|` guard regex into an ERE with EMPTY alternations that matched every
   line (so nothing was ever "unguarded"), and its hand-counted `../..`
   REPO_ROOT resolved to `.ci`, so the find scanned `.ci/.ci/scripts` --
   zero files. Same failure family as issue #549: a green gate nobody had
   ever seen fire. Both fixed (character classes, get_repo_root); a
   two-class planted defect now exits 1 with both lines reported, and the
   clean tree exits 0.
3. **The repaired instrument exposed 28 real unguarded pipelines** across 15
   scripts (grep/find heads whose no-match rc aborts the calling script
   silently). All guarded with `|| true` where the value is validated or
   display-only, one explicit loud empty-check added (build-pkg-repo's GPG
   key id), one in-string false positive whitelisted, and condition-head
   pipelines exempted in the gate itself. shellcheck, shfmt, and every
   touched gate suite re-run green.

## Cross-PR greenlight: skipping a suite on ANY run's job-level green (2026-07-31)

The scope engine asks a lineage-local question: did the delta against THIS
branch's baseline touch the job's surface. So a rebase, or a second PR that
bumps the same submodule pointer, pays for the 90-minute renet suite again
even though the exact same inputs were executed green an hour earlier on
another branch. `.ci/scripts/ci/greenlight.cjs` asks the wider question: has
this exact input closure already been executed green by any run, anywhere.

### Verify-at-read, because a memo is unsound here

The obvious design is a memo store: a run that goes green records "renet at
sha X passed", and later runs look it up. The repo already argued that down
once, at `scope-engine.cjs:177`, and the argument transfers intact. A run that
writes its own trust token mints a claim later readers cannot check, and the
write would have to happen in a PR-triggered job whose code comes from the PR
itself, which is exactly the bypass `.github/actions/app-token/action.yml:13`
exists to remove. `SELF-DECLARATION IS DELETED, NOT BLACKLISTED`.

So nothing is stored. The greenlight is derived fresh at Initialize time from
three facts nobody had to be trusted to record:

- the per-JOB conclusion from the Actions API;
- the candidate's submodule gitlink, read from
  `GET /repos/{repo}/contents/private/renet?ref=<head_sha>`, which returns the
  submodule object and its sha;
- the candidate's console-side closure, read the same way.

All three are properties of a commit or of what the runner actually did. None
is a claim a run made about itself.

### Why the evidence is the JOB conclusion and never the check

Run-level "CI Complete" cannot distinguish an executed job from a skipped one:
`assert-ci-complete.sh` puts TESTS in `SOFT_REQUIRED`, where `skipped` passes
identically to `success`. A fully-scoped-out run and a fully-executed run emit
the same green check. The per-job conclusion does distinguish them, so that is
the only thing read.

This is also why a candidate that was itself a REDUCED run is perfectly good
evidence. The rule asks whether the job RAN, not what the plan intended.
Intent is not outcome; outcome is what gets read. A `skipped` conclusion is
refused precisely so evidence cannot chain: without that rule a reduced run
whose renet job was skipped would greenlight the next PR, which would skip it
too, and the suite would go unrun forever with every check green.

### The closure key

A greenlight is granted only when all three hold, checked in this order so the
expensive lookup is paid last:

1. the job for the key exists, is unique, and concluded `success`;
2. the candidate's submodule gitlink equals ours;
3. the candidate's console-side closure hash equals ours.

The closure is the part that is easy to get wrong. `test-renet` looks
submodule-only and is not: `run-renet.sh:12` sources `.ci/scripts/lib/common.sh`,
and renet's own `run-tests.sh:15-26` sources the CONSOLE-side
`.ci/scripts/infra/ci-env.sh`. The table in `greenlight.cjs` therefore covers
the five `.ci/scripts/private/renet-*.sh` entry points, those two libraries,
and the whole `ct-tests.yml`. Account E2E adds `run-account-e2e.sh`, the
`setup-workspace` and `app-token` composite actions, `install-deps.sh`, the
root `package.json`/`package-lock.json`, and `packages/shared` plus
`packages/provisioning` (the job runs `npm run build:packages`, and
`private/account` depends on `@rediacc/shared` through a `file:` link).

The hash is computed from the LOCAL checkout, so a PR that edits any of those
files differs from every candidate and nothing greenlights, which is correct.
Directories are covered by their tree sha and submodules by their commit sha,
both read out of the same contents listing, which is also why the fetch costs
one call per parent directory rather than one per path.

Over-inclusion in that table is safe (rarer greenlights, more full rounds) and
under-inclusion is not, so when in doubt the path is listed. One deliberate
absence: `build-packages.sh` is NOT an account input, because
`setup-workspace` only runs it when its `build-packages` input is `true` and
`ct-tests.yml` leaves it unset, calling `npm run build:packages` directly.

### Fail-open, and where it was proven

The engine may only ever turn a RUN into a SKIP. It emits `run_<key>=false`
and has no `=true` form at all, so any error, timeout, or absence of a match
emits nothing and changes nothing. `scope-shadow.sh`'s reader is strict for the
same reason: only an exact `run_<key>=false` line paired with an
`evidence_<key>=<digits>` line does anything, so a malformed emit is inert.

The first live run proved both directions at once. `renet` was greenlit by run
30628333340 (gitlink and job conclusion independently confirmed by hand),
while `account_e2e` walked 25 candidates and refused every one, exercising
`job-failed:cancelled`, `job-not-run`, `pointer-differs`, and, when the 60s
budget ran out mid-walk, `jobs-unreadable:budget exhausted`. Budget exhaustion
resolves to no greenlight, which is a full round.

### How it lands in the plan

`apply_greenlight` runs inside the existing scope step, after `plan.json` is
written and before any output is emitted, and only for keys the scope engine
still plans to RUN. It rewrites the key's plan entry to
`{"run": false, "reason": "greenlight:<run-id>"}` rather than emitting a
parallel output, so `plan.json` stays the single object that gates jobs, gets
uploaded, and is audited, and the audit trail names the evidence run. The
reconciler reads `run` and `preexisting_skip` and never `reason`, so the
annotation changes no verdict.

The plan's `mode` flips to `reduced` when anything is greenlit, and that is a
correctness requirement rather than bookkeeping: `attestPlan` refuses a
non-full plan as a future baseline, so leaving `mode` at `full` would let a
LATER run adopt a round that greenlit its way out of a suite as a full
baseline. That is the evidence-chaining failure the scope engine already
refuses, arriving by a different door.

> **Half-corrected on 2026-08-05.** The flip stays; the conclusion drawn from it
> did not survive contact with the traffic. Because these two closures change
> rarely, the flip fired on nearly every console run, so every later walk
> refused its own parent and the engine never reduced a round at all. The
> baseline reader now asks per key whether the work was COVERED rather than
> reading this aggregate label. See "the scope engine had never reduced a
> round" below.

The kill switches need no new wiring. `FULL_CI` and the `full-ci` label
short-circuit `scope-shadow.sh` before any of this runs, and the step is
`pull_request`-only, so the nightly stays full by construction.

Worth knowing: the greenlight needs no git history, so it still fires on a
shallow clone where `--resolve-baseline` answers `baseline:shallow-clone` and
falls open to a full plan. Reducing a fail-open-full plan is legitimate here
because the evidence is independent of the baseline machinery, but it does
mean a round can be shrunk that the scope engine had made full for a stated
reason.

### Cross-branch cache and API trust, which was undocumented anywhere

The discovery pass found no doc in `docs/` or `.ci/` discussing cache scoping,
poisoning, or cross-branch cache trust; the word "poison" in this repo always
means "poisons CI Complete". Since this is the first mechanism to consume
another branch's evidence, the trust model belongs here.

GitHub's Actions cache is scoped to the ref that wrote it, and reads fall back
UP the chain: a PR reads its own scope, then its base branch, then the default
branch. Flow is base to PR, never PR to base, so a PR cannot overwrite or
shadow an entry that main will later read. That is the property that makes the
existing shared `renet-embed-assets` key safe, and `ci-build-renet.yml:78-82`
adds a second layer on top of it: build.sh's content-based receipt makes
`embed_assets` a verified no-op, so a stale or corrupt blob triggers a full
restage rather than passing silently.

The greenlight deliberately consumes NONE of that. It trusts only
reader-derived API facts: job conclusions, and object shas read out of commits.
It reads no cache, downloads no artifact, and writes nothing at all, so it adds
no trust surface to the pipeline. The bound on how far back it can see is the
Actions API's run retention, not the 7-day `ci-skip-plan` artifact retention
that bounds the scope engine's baseline walk.

### Tests

`.ci/scripts/test/gates/test-greenlight.sh`, 44 assertions over nine cases,
every one control-proven. Cases 1 to 5 drive the pure core with injected
fixtures (full match, failed job, skipped job, differing closure, and
fail-open over an empty list plus a throwing fetch at each of the three lazy
stages). Case 6 drives the real CLI offline against a fake `gh` that serves
this repo's actual tree as the candidate's content, so the fixture cannot rot,
then withdraws the greenlight by flipping one job conclusion, then by moving
one closure blob, then by breaking `gh` outright.

Case 7 is the submodule pointer rule, which the operator names as the core
soundness requirement of the feature: a suite may be skipped ONLY when the
submodule points at the exact hash some job-green run already tested, and any
submodule change runs the tests. It asserts the refusal with everything else
held identical, that no evidence run is named, that a one-character difference
is still a difference, that an absent gitlink is not a free pass, and, at CLI
level against the real tree, that a moved `private/renet` pointer emits
nothing at all. Each of those carries the matching control, including an
unperturbed invocation that DOES greenlight, so an empty emit cannot pass for
the right reason by accident.

Two cases beyond the plan. One guards the job-name hazard: a real run carries
`Tests + Infra / Renet` alongside `Build (Renet) / Renet (cached)` and
`Build (Docker Fast) / Renet Docker`, so matching is on the exact leaf name
after the last ` / `, and a substring match would read a cache-hit build job as
proof that a 90-minute test suite passed. The other asserts every declared
closure path still exists in HEAD, because a path that quietly stopped
resolving would be hashed by nobody and noticed by nothing.

PLANTED-DEFECT PROOFS, one per load-bearing rule. Rule 1 was inverted so a
`skipped` conclusion fell through to the success path: case 3 failed with
`FAIL: a skipped job must never greenlight: expected 'false', got 'true'`
while cases 1 and 2 still passed. Rule 2 was then weakened from full hash
equality to a 4-character prefix comparison, which is the shape a "cheap
early-out" would take: case 7 failed on its near-miss assertion with
`FAIL: a pointer differing in one character must refuse: expected 'false', got 'true'`
while cases 1 to 6 ALL still passed, so a weakened pointer rule is invisible
to every other property in the file and visible to that one. The engine was
restored after each and re-verified byte-identical (md5
`8b35c56e7f5ca90c959f90ac7db029b9` before and after both).

## `check:ci-renet-tiers`: the tier-map tests get a local leg (2026-08-04)

New gate id `check:ci-renet-tiers`, script
`.ci/scripts/quality/check-renet-tier-map.sh`, manifest entry beside
`check:ci-renet-types`. It runs the seven Go tests that prove renet's licence
tier map covers the function registry and drives dispatch
(`TestTierMapCoversRegistry`, `TestTierMapHasNoOrphans`, `TestTierMapGateCanFail`,
`TestPendingBacklogIsReported`, `TestTierMapDrivesDispatch`,
`TestOperateTierSurvivesExpiry`, `TestTierProbeMatchesTheMap`).

WHY IT IS WORTH A LOCAL LEG. Those tests already run in CI, inside
`ct-tests.yml` job `test-renet` step "Run renet tests", which is renet's whole
`go test ./...`. But `npm run ci` had no leg for them, so a tier-map regression
was only visible after a push, and it stopped being a renet-only concern this
same session: the CLI now DERIVES which functions are licence-issuance-relevant
from that map, through
`packages/shared/src/renet-contract/data/license-tiers.generated.ts` and the new
accessor in `packages/cli/src/services/renet/renet-license-contract.ts`. A
function registered with no tier is now a console defect as well as a renet one.

`ci` is declared `local-only`, NOT a step pointer at `test-renet`, and that is a
measured decision rather than a shortcut. The parity oracle compares LEAVES:
that step resolves to `.ci/scripts/private/run-renet.sh` and never to this
script, so a `step` pointer fails R3 with "the pointer names a step that runs
something else". That is the oracle working. The BLOCKER names the CI job that
does cover the property. Registered in
`.ci/scripts/test/gates/test-gate-anti-vacuity.sh` as
`|required`, since with `private/renet` absent the gate would otherwise run zero
tests and report that the map is complete.

PROVE-IT-FIRES, three planted defects against a scratch copy of `private/renet`
(the gate takes a `RENET_DIR` override so the real submodule is never touched):

1. Registering `planted_defect_untiered_function` in the copy's command registry
   turned it RED with `1 registered function(s) have no tier decision`, exit 1;
   removing it returned exit 0.
2. Renaming `TestTierProbeMatchesTheMap` turned it RED at the phase-1 instrument
   check ("The tier-map test selection has drifted"). This is the failure mode
   the phase exists for: `go test -run` exits 0 with "no tests to run" when its
   regex matches nothing, so a rename would otherwise have silently retired the
   gate while leaving it green.
3. Planting `t.Skip` in `TestOperateTierSurvivesExpiry` left `go test` exiting 0
   with `ok`, and the gate still went RED at the phase-3 PASS accounting:
   "These tier-map tests never reported PASS". A green exit code is not evidence
   that the tests ran.

## 2026-08-04 -- `check:ci-locale-de-contamination`

`scripts/check-locale-de-contamination.ts`, chained into
`check:ci-i18n-cross-locale` in `package.json` so it inherits that gate's real CI
home (`ci-quality.yml`, job `quality-i18n`, step "i18n cross-locale"). Its
manifest entry declares that same step, and the chained parent's `leaves` now
lists both scripts, which is what the parity oracle's hygiene rule compares
against.

Chaining rather than `local-only` was the point. The defect it catches is live in
the tree right now: 94-95 German values sitting in each of account-web's `ar`,
`ja`, `ru` and `zh`. A gate no CI step invokes would not have stopped the next
batch, and the operator's own review would still be the only instrument.

WHY IT IS A SECOND GATE AND NOT A WIDENED FIRST ONE.
`scripts/check-i18n-cross-locale.ts` identifies a string's LANGUAGE from function
words, which is the right tool for telling French from German but structurally
cannot look at a locale it has no word list for (`if (!STOPWORDS[locale])
continue` -- de/fr/es/it/pt/tr only). Arabic, Japanese, Korean, Russian, Chinese
and Estonian were never scanned by anything: every other i18n check in the repo
compares a locale against ENGLISH, and German is not English. This gate keys on
byte equality with the German value instead, so it reads exactly the locales the
other one skips.

Equality alone is far too loose -- 699 hits, nearly all of them units ("200 GB"),
localised numbers ("2,4 TB") and product names ("Rediacc (btrfs CoW)"). Three
filters, each added because dropping it produced a false positive that is named
in the script's header comment, bring it to 379 findings with none in
`packages/www` or `packages/cli`: the value must hold two real words after
placeholders and markup are stripped; it must not be shared by the crowd (a
citation every locale carries is language-neutral, not a leak); and it must carry
language evidence chosen per script -- for a non-Latin locale, a value with not
one character of that locale's own script IS the evidence, while a Latin-script
locale needs German markers.

BASELINE THAT ONLY SHRINKS. `scripts/data/locale-de-contamination-baseline.json`
holds the 379 known findings so the gate lands green today. A baselined finding
that is no longer contaminated is a hard ERROR telling the caller to re-run
`--write-baseline`, so fixing keys forces the file down and it cannot rot into a
permanent suppression list. The 12-locale naturalization pass drains it.

Registered in `.ci/scripts/test/gates/test-gate-anti-vacuity.sh` as
`|Refusing to run`: with the locale trees absent it would find zero contamination
AND see all 379 baselined findings as fixed, so an unguarded version could fail
for entirely the wrong reason.

PROVE-IT-FIRES, against a scratch copy of the four locale trees so the real files
were never touched:

1. Copying the German `activity.emptyMessage` into `ko/admin.json` and the German
   pricing-FAQ question into `et.json` turned it RED naming both, exit 1. Both
   locales are invisible to the stopword gate, which is the whole reason this one
   exists.
2. Reverting those two and instead FIXING one baselined key (`ar` /
   `admin.json:activity.emptyMessage`) turned it RED with "1 baselined finding(s)
   are already fixed", exit 1. The shrink-only property is enforced, not
   documented.
3. The seven inline self-test cases run on every invocation, not behind a flag.
   Three of them are the false-positive controls (a shared unit, an English
   citation every locale carries, a shared product name) and one pins the flat
   `packages/www` layout, where the German values live in `de.json` rather than in
   a same-named file -- getting that lookup wrong finds nothing while looking
   perfectly healthy.

## 2026-08-04 -- the i18n gates could not see three whole defect classes

The operator asked why pre-existing translation defects were never caught. The
answer was not "no gate covers translations". Four gates did. Each one had a
hole, and every hole had the same shape: a code path that reports NOTHING is
indistinguishable, in the output, from a code path that finds nothing.

### 1. `check-i18n-cross-locale.ts` skipped six of its twelve locales

`if (locale === SOURCE_LOCALE || !STOPWORDS[locale]) continue` walked past every
locale with no function-word list -- `ar`, `ja`, `ko`, `ru`, `zh` and `et`. Those
are precisely where the damage was: 379 German values sat in account-web's `ar`,
`ja`, `ru` and `zh` while this gate printed a checkmark.

MEASURED, not argued. A scratch copy of `private/account/web/src/i18n/locales`
with 1,576 real German values planted into `ar/ja/ru/zh`:

* the gate as it stood at `HEAD`: `No cross-locale contamination across 1 locale
  root(s)`, exit 0;
* the same tree after this change: `236 value(s)`, 59 per locale, exit 1.

A stopword list is a Latin-alphabet instrument and cannot be built for these five,
so they get a second instrument instead: a value holding not one character of its
own writing system is not a translation into it. It is paired with the existing
function-word signal rather than used alone, so a Latin PRODUCT NAME standing by
itself scores zero and is not reported.

There is no `continue` left. A locale directory the gate cannot model by either
instrument is a hard error naming the locale.

### 2. There was no `en` stopword list, so English residue was undetectable

Every other i18n check compares a locale against English, so it can see a value
that IS English. None could see a value that is MOSTLY English -- the ordinary
residue of a half-finished translation pass. Adding `en` (and `et`) closes it:
2,364 real English values planted across `fr/es/it/pt/tr/et` produce 316 findings
in all six locales; the clean tree produces zero.

While adding it, `more` was found sitting in the SPANISH stopword list. It is an
English word, it was that list's only non-Spanish entry, and it scored every
English string one point towards "this is Spanish". Removed.

`packages/www` was measured for inclusion and deliberately left out: 1,060
findings, essentially all of them English CITATIONS that all twelve locales carry
verbatim ("IBM Security, Cost of a Data Breach Report 2024"). Those are
language-neutral content, not contamination, and admitting them would need the
crowd filter from `check-locale-de-contamination.ts`, which already scans that
tree.

### 3. Nothing at all validated renet's locale VALUES

`private/renet/.ci/scripts/quality/i18n.sh` scans Go SOURCE for hardcoded strings.
The catalogs in `pkg/i18n/locales/*.go` were checked for key alignment, exact
identity with English, and format parity -- structure, never content. So this
shipped and stayed green:

    ru  "Zadachi dobavleny v ochered"   for  "Added tasks to queue"

Twenty-six `ru` values are Russian written in LATIN TRANSLITERATION. They are not
English, every key aligns, every format verb matches, so every existing class
passed them, and a Russian user reads romanized gibberish.

`pkg/i18n/locale_quality_test.go` adds three rules, each provable rather than a
judgement call: the value IS English; three CONSECUTIVE English function words
(one is noise and two is arguable, three in a row is a clause); and for
`ar/ja/ko/ru/zh`, prose carrying not one character of its own script. Findings are
held in a shrink-only baseline, and a baselined finding that is no longer detected
FAILS, so a fix forces its removal.

It does NOT reuse `localeHomographs` from `rules.go`. That map was widened until
the advisory fragment rule stopped producing noise, which left entries that are
not homographs at all -- `the` is in both the German and the French lists, and
`is`, `of`, `to`, `at`, `it` and `was` in the German one. Borrowing it would score
"because the socket is" as a run of ONE.

### 4. The renet i18n gate could retire itself in one line

    ./bin/renet i18n extract ... 2>/dev/null || { log_warn "...skipping"; exit 0; }

A crashed extractor produced a WARNING and a GREEN gate -- and because `exit 0`
came before them, it took the locale validation and the hash-manifest check with
it. Proven on a fixture whose `bin/renet` exits 3: the `HEAD` script prints
`i18n extraction failed or not implemented, skipping` and exits 0; the new one
prints the crash and exits 1.

The six `jq ... 2>/dev/null || echo "0"` reads were the same defect one layer
down, because `0` is the value that means clean. With `jq` off `PATH` and
`validate` reporting 99 certain defects over ZERO locales, the `HEAD` script
printed `All 12 locales clean`. They now go through a `read_stat` helper that
refuses to substitute a default, `jq` is a `require_cmd`, and the locale count is
pinned at 12 so a moved catalog directory cannot make every total a vacuous zero.
The two fixed `/tmp/findings.json` and `/tmp/validate.json` paths, which two
concurrent runs shared, are now a per-run `mktemp -d`.

The new Go tests already run in CI's test stage via `go test ./pkg/...`. They are
also invoked from `i18n.sh` using the three-phase pattern of
`check-renet-tier-map.sh` -- confirm `-list` selects exactly the expected names,
run with `-count=1`, then assert each reported `--- PASS` -- so neither a rename
nor a `t.Skip` can retire one silently, the control included.

### Registered

`check-i18n-cross-locale.ts` joins `.ci/scripts/test/gates/test-gate-anti-vacuity.sh`
as `|Refusing to run`. Its three locale-root constants are root pattern 1, and it
was previously unregistered while carrying a second vacuity inside itself. The
harness copies `scripts/` and `.ci/scripts/` only, so renet's `i18n.sh` cannot be
registered there; the submodule-absent case is already pinned through
`.ci/scripts/private/run-renet.sh`.

## 2026-08-04 (later) -- the locale SET becomes derived, and two more hidden classes

Four follow-ups to the section above, three of them defects the first pass did not reach.

### 5. Both locale gates hand-maintained their own implicit locale universe

`check-i18n-cross-locale.ts` decided which locales existed from `readdirSync` plus the
keys of its own `STOPWORDS` map. That is the root of the original hole: the set of
locales the gate KNEW about and the set it could JUDGE were the same object, so a locale
with no detection data was not a gap, it simply was not a locale.

Both gates now derive the universe from `@rediacc/locales`, the same declaration the rest
of the repo builds against, and cross-check the tree against it in both directions:

* a directory that is not a site locale is a hard error naming it;
* a site locale with no directory is a hard error, because comparing it against nothing
  reports no contamination, which is the same checkmark as finding none;
* every non-English site locale must have a function-word list OR a writing system, and
  that is asserted AT MODULE LOAD, before a single file is opened. A fourteenth locale
  added to `packages/locales/index.js` turns both gates red immediately, with no tree
  needed to trigger it;
* every key of the detection data must itself be a site locale, so `NATIVE_SCRIPT.jp`
  fails loudly instead of silently never matching the `ja` directory.

Both selftests now build fixtures with all thirteen locales, and each rule above has a
case that plants the failure and requires the throw.

Found while wiring it: `packages/www/src/i18n/translations` holds
`.naturalized-hashes.json` and `.translation-hashes.json`, 2.2 MB of CRC sidecars that
the de-contamination gate had been reading and flattening as two extra LOCALES on every
run. No finding came from them, but they counted towards `targets`, which is the
denominator of the crowd filter, so its exemption threshold was computed against fourteen
locales where twelve exist. Dot-prefixed entries are now excluded.

### 6. The crowd-exclusion filter was hiding shared CORRUPTION

`check-locale-de-contamination.ts` exempted any value that most other locales also carry,
on the reasoning that a string every locale shares belongs to no language -- a citation, a
product name. Sound for citations, wrong in general, and it hid 59 genuinely corrupted
keys: most of account-web's `team.json` was German across `ar`, `ja`, `ru` and `zh`
IDENTICALLY, which the filter read as language-neutral when it was one bad translation
pass writing the same German into four files.

The two cases are told apart by evidence the gate already computed and simply did not
consult: shared corruption looks German, a citation does not. Crowd-exclusion now applies
only when `looksGerman` is false.

MEASURED against the real tree, with 280 real German values planted identically into seven
locales of account-web's `team.json` (seven, because the exemption needs
`shared * 2 >= targets - 1` and four locales never reached it):

* unconditional filter, everything else identical: `No new German contamination across 4
  locale root(s)`, exit 0;
* conditioned on the German evidence: 147 findings, exit 1.

The English-citation control still passes, which is the whole point of conditioning rather
than deleting.

### 7. A translation pasted over a run of unrelated keys

Found live in `ja.go`: 64 clusters covering 255 keys where DISTINCT English strings had all
been collapsed onto the SAME Japanese value. Larger than every other class combined, and
invisible to every per-value rule -- each value on its own is fluent Japanese, differs from
English, aligns on keys and keeps its format verbs. The defect exists only in the
RELATIONSHIP between keys.

`duplicate-cluster` groups a locale's values and reports any value shared by three or more
keys whose English sources are pairwise DIFFERENT. The one-directional signal is what makes
it precise: locales do legitimately collapse short labels, but when they do the English
side is identical too, so requiring distinct English exempts every legitimate case without
a list to maintain.

Its substance floor is measured in LETTERS, not words. A four-WORD threshold silently
exempted every CJK value, because Japanese writes a whole clause with no spaces in it and
so scores two tokens -- and CJK is the one locale family where the defect was actually
found. Caught by a control that expected four planted keys and got zero, not by reading.

### 8. `localeHomographs` in rules.go listed words that are not words

The map suppresses English function words on the grounds that they are also ordinary words
in the target language. It had been widened until the advisory fragment rule stopped
producing noise, which is a different criterion, and it let through entries that belong to
no language involved: `the`, `is`, `of`, `to`, `at`, `it`, `be`, `are`, `do`, `must`, `has`
and `not` were all listed as GERMAN, and `the`, `in` and `it` as FRENCH.

Each entry is a word the fragment rule can no longer see. Pruned to words a native speaker
would confirm, with `error` ADDED for Spanish (spelled exactly as in English, which is the
only thing that ever justifies an entry). Zero new findings on the current tree, so this is
pure sharpening; `TestHomographListHoldsOnlyRealWords` pins it, and restoring the original
German list makes that test fail on seven words.

NOT fixed, reported instead: `detectWordBlends` skips wholly-ASCII tokens, so an
ASCII-only corruption like `"Listeer available images"` is caught by neither it nor
`detectEnglishFragments` (which only counts KNOWN English words). Making it ASCII-aware
would fire on every legitimate `Starting`/`Running` in twelve locales and needs a
false-positive measurement pass per locale. That is a rework, not a cheap hardening.

### Renet's locale set is already derived, and stays that way

No `@rediacc/locales` change is needed on the renet side and none was made. Renet's
catalogs register themselves through `pkg/i18n/locales/registry.go`, and
`GetAllLocaleFiles` derives the locale list from the generated files rather than from a
hand-written list, which is the same property `@rediacc/locales` provides on the console
side. The Go test asserts that list is exactly 12 non-English catalogs and that each
yields at least 200 keys, so a moved or renamed catalog is a hard failure rather than a
scan over nothing.

## 2026-08-04 -- two dark coverage assets get CI legs: the drills, and suite 24's ACCOUNT tier

Both were written, both passed on an operator's box, and neither had ever executed in CI.
This wires them, with the scope engine's 18th key and one new job script. UNCOMMITTED: the
workflow edits land locally and the operator pushes, so **the first real CI run is the
operator's push** -- everything below was proven locally or is named as unproven.

### `test-drills`, a new ct-tests leaf (scope key `drills`)

Runs `./run.sh drill universe` then `./run.sh drill transfer`. Both drive the real
`./rdc.sh` against a real `./run.sh account dev` gateway and assert on stdout and stderr
SEPARATELY, which is the surface no unit test sees and the surface each drill's header
says it was written to catch defects in.

Proven locally before the wiring, not after: universe 42/42 in 31s, transfer 33/33 in 32s,
both on this checkout with Docker up (transfer needs the RustFS container, so it is a real
prerequisite rather than a nicety). No org secrets are involved -- `account_ensure_env`
generates `private/account/.env` with fresh throwaway ed25519/x25519 keys on first use.

The Go toolchain, the Docker Hub login and the embed-assets cache on this leg all exist
for ONE reason, and it is worth stating because none of them look like a drill's business:
`rdc.sh:188` calls `ensure_renet_built` unconditionally, which runs `build.sh dev` ->
`embed_assets`. With the cache warm the receipt check makes staging a verified no-op; on a
miss it falls back to the Docker extraction, which is what the 30-minute budget covers.
Neither drill touches renet.

**`www` is deliberately NOT in the `drills` surface**, and this is the one judgement call
in the key. `account_dev` starts the Astro dev server from `packages/www` and exits
non-zero if it does not come up, so www is a literal dependency of the harness. It is
still excluded: a www change cannot change what these drills ASSERT, only whether the
harness stands, and carrying www would run a ~15-minute leg on every i18n or marketing PR
-- the most common change shape in this repo. Accepted cost, stated so the next reader does
not think it was an oversight: a www change that breaks `astro dev` while still building
clean surfaces as a red drills leg on the NEXT cli/account PR.

The drills' own source needs no module: `scripts/` hits the `scripts-harness` rule => full
CI, so editing a drill always runs the leg. Same shape as `license_enforcement` under
`.ci/`.

### The 18th key costs five tables, not one

Adding a `JOB_SURFACES` key is not a one-file edit, and every one of these fails CLOSED,
which is why they were found by running rather than by reading:

- `scope-map.cjs` -- `drills: ['cli', 'shared', 'account']`.
- `ci.yml` -- an `initialize` output and a `with:` pass-through. A key missing here is
  silently DROPPED by the outputs block.
- `ct-tests.yml` -- the `run_drills` input plus the leaf's `!= 'false'` clause.
- `skip-plan-reconcile.cjs` -- `EXPECTED_JOB_NAMES` (validateNameTable THROWS AT LOAD on a
  surface key with no name) and `CT_TESTS_LEAF_KEYS` (without it the leaf is not exempted
  under `full_suite`/`pointer_bump_only` and reds every push-to-main).
- three gate fixtures under `.ci/scripts/test/gates/` that carry a second, independent copy
  of the job list on purpose.

Instrument check rather than assertion-reading: `buildPlan` was driven over single-path
deltas and the key discriminates in both directions -- `packages/cli/**` and
`private/account/**` and `packages/shared/**` => `run:true reason:modules:*`,
`packages/www/**` and `private/renet/**` => `run:false reason:out-of-scope`,
`scripts/drills/**` => full.

### Suite 24: the ACCOUNT tier runs, the VM tier is excluded (not skipped)

`.ci/scripts/test/start-account-for-e2e.sh` starts a TEST_MODE node account server with
throwaway keys, seeds a PROFESSIONAL subscription, and mints a token over the COOKIE
session only -- the CLI must be the token's first user, because a token binds to the client
IP on first use and the CLI's E2E tunnel presents a different one (the drill lib paid an
hour for that; violating it answers 403 and the CLI misreports it as a passkey requirement).
`CLUSTER_LICENSING_SUITE=1` on the multinode leg lights project `k8s-multinode-24`.

**The VM tier cannot run here, and the brief's assumption that it could was checked and is
wrong.** Three independent blockers, any one of them sufficient:

1. it adopts an EXISTING cluster named by `E2E_CLUSTER_NAME`; the only cluster this job
   builds is suite 17's `mnprod`, which suite 17's own last test and its `afterAll` tear
   down completely (kube uninstall, datastore detach + delete, ceph pool delete). Project
   `k8s-multinode-24` runs after project `k8s-multinode-17`, so there is nothing left;
2. suite 17 builds that cluster through raw `renet` over the bridge, so no rdc config ever
   holds a `clusters` entry for it -- `cluster fork mnprod` could not resolve it even if it
   still stood;
3. every renet on this fleet is `--nolicense`, so the on-machine licence blobs the tier's
   test 1 asserts on do not exist by construction.

So the tier is removed from the RUN with `--grep-invert "licensing on the fleet"` (its
describe title; suite 17's titles do not contain it), AND `E2E_EXPECT_NO_CLUSTER_VMS` is
declared. The pair is deliberate and the ordering is the whole point: a declared skip is
still a SKIP, and this leg carries `--fail-on-skip`, so declaring alone would red the job.
`--grep-invert` filters at collection so nothing is reported as skipped, while the
declaration keeps the omission loud on stderr and keeps the suite fail-closed if the grep
is ever dropped.

### Four things this touched that were not obviously in scope

- **`account: 'true'` is back on the multinode leg**, reversing part of the eight-job strip
  documented above `test-e2e-workers`. That comment's reason (no E2E suite touches
  private/account) is no longer true for this one job. The cost it names is real and
  accepted: this job's setup cache key now hashes the three account lockfiles.
- **The E2E run line must stay ON ONE LINE.** `check-e2e-coverage`'s registry self-check
  scans workflows line by line and only pairs a `--config` with a `run-e2e.sh` on the SAME
  line. Folding the invocation across lines with `>-` made the gate report
  `'playwright.k8s-multinode.config.ts' is in LIVE_CONFIG_REGISTRY but NO workflow runs
  it`, and silently set `bareDefaultSeen` from a line that is not a bare invocation. Loud
  and fail-closed, so not repaired; noted at the call site so the next folder is not
  puzzled.
- **`CLUSTER_LICENSING_SUITE` in `CI_LEG_ENABLE_FLAGS` over-counts by design and it was
  checked, not assumed.** Config expansion resolves FILES, so the flag counts the whole of
  suite 24 as live while `--grep-invert` runs only half of it. Inert today: the only bridge
  method suite 24 calls is `executeViaBridge`, which dispatches no renet verb and is in the
  method map for none, so the file confers no verb coverage in either tier. The gate's
  expansion moved `playwright.k8s-multinode.config.ts` from 1 file to 2, which is the
  instrument check that the flag does something.
- **`npx` forks, so `$!` is not the server.** The first cut of the start script recorded
  `$!` and used `kill -0` on it as a startup liveness check. Measured: launch pid 1155097,
  tsx 1155113, listener 1155124 -- the recorded pid was already gone while the server was
  healthy, so that check was a false red waiting on scheduling. Readiness is now the PORT
  for the full budget, and the pid is resolved from the listening socket afterwards
  (verified: recorded pid == listener pid, and killing it stops the server).

### What is NOT proven, and cannot be from here

The suite-24 ACCOUNT tier's own assertions were not executed. `subscription login --token`
and `subscription status` were driven against the throwaway server and print the exact
lines the suite parses (`Machine slots: 0/5`, `Monthly repo license issuances: 0/2000`),
and E2E key discovery against a non-production server works when `REDIACC_ACCOUNT_SERVER`
is set -- but `cluster create` is gate class D and `assertCommandPolicy` refuses it inside
an agent session unless the operator exported `REDIACC_ALLOW_CLUSTER_OPS` before the
session started. It refused, verbatim: `Cluster command "cluster create" is blocked in
agent mode`. CI has no agent ancestor so the override is legitimate there, and suite 24's
test 1 detects exactly this case and says so rather than failing obscurely eight tests
later. The pre-flight's refusal text and exit code are therefore first proven on the
operator's push.

## 2026-08-05 -- the scope engine had never reduced a round, in five days live

Reported as "run 30983418337 is running the whole test matrix for a commit that
is documentation and agent tooling". The push `1d172438f..208c8a2d9` carried
four files: `.claude/agents/pr-babysitter.md`, `.claude/commands/pr-babysit.md`,
`.claude/hooks/stop/wl_judge.py`, and a report under `docs/agent/main/`. Every
one classifies to the `docs` module, which appears in no `JOB_SURFACES` entry,
so the table would skip all eighteen keys. It skipped none.

### The measurement, before any hypothesis

The plan artifact is uploaded per run, so the verdict is readable rather than
inferable. Twenty-five recent `pull_request` runs, fourteen of which still had
their `ci-skip-plan` artifact:

```
30983418337  mode=reduced full_reasons=["baseline:merge-base-reached"] skipped=2 out-of-scope=0
30975223299  mode=reduced full_reasons=["baseline:merge-base-reached"] skipped=1 out-of-scope=0
...  (12 more, identical shape)
30944973190  mode=full    full_reasons=["baseline:no-candidates"]      skipped=0 out-of-scope=0
```

Every walk died at the merge parent or found no candidates, and **not one job
in any run was ever skipped with reason `out-of-scope`**. Both skips visible
above came from the cross-PR greenlight, not from scope. The engine went live
on 2026-07-31 (D-1) and had, by its own artifacts, never once reduced a round.

### Why the reduction path was unreachable rather than unlucky

Four properties compose into a closed loop:

1. the walk is fenced at the merge parent, so only the PR's OWN commits are
   candidates. A one-commit PR therefore has none;
2. a candidate must be green, its plan `mode: 'full'`, and its outcome
   reconciled;
3. every superseded push is `cancelled`, which reads as `not-green`, and a
   babysit loop supersedes constantly;
4. the surviving green run had its plan's `mode` flipped to `reduced` by the
   greenlight the moment it skipped a single key -- and `renet` /
   `account_e2e` closures change rarely, so this fired almost every time.

Run 30983418337's own trail says it in one line: 28 candidates `not-green`, and
the one green one (`1d172438f`, run 30975223299) refused as `reduced-baseline`.
That run had executed seventeen of eighteen keys and held greenlight evidence
for the eighteenth.

### Two changes were designed. ONE LANDS; the other is held for a soak

**LANDED -- baseline usability is read per key, not from the mode label**
(`planCoverageIsFull`). A key covers if it was planned to RUN -- the reconciler
then proves it actually ran -- or if it was skipped with a `greenlight:<run-id>`
reason, whose evidence is a different run that executed that job's exact input
closure green. A key skipped as `out-of-scope` covers nothing, so case 1 stands:
scope evidence still cannot chain. This makes `reason` load-bearing where the
reconciler ignores it, which adds no trust: it arrives in the same artifact as
`mode`, `run` and `base_sha`, all already load-bearing. What stays derived
rather than declared is `reconciled`, per `attestPlan`'s doctrine.

This is the change that answers the report, and it answers it alone: run
30975223299 becomes a usable baseline, so run 30983418337 resolves one instead
of walking off the fence. It fixes pushes 2..N of every PR, which is the large
majority of pushes.

**HELD -- no usable baseline classifies the merge-parent delta instead of
forcing full** (`noBaseline`). Designed, implemented and gated, then deliberately
NOT landed on 2026-08-05. Kept here rather than deleted, because the design is
sound and the reason for holding it is about the state of `main`, not about the
mechanism.

The design: `diff(merge-parent, head)` is a SUPERSET of any baseline delta (the
baseline is an ancestor of head and a descendant of the merge parent), and it is
the evidence GitHub's own `paths:` filters run on, so a job whose surface is
disjoint from it would execute byte-identical inputs to the ones main already
carries. `decideBaseMove` already trusts this exact diff for the case-5 fold. It
would be offered ONLY for the "no usable baseline" family -- a shallow clone, a
throwing walk, a throwing diff and an over-cap diff all still force full,
because there the instrument is what is broken and a second reading from it
proves nothing.

Why it is held:

1. **It reduces against a baseline nobody verified was green.** `ci.yml:276` and
   `:327` are both `if: github.event_name == 'pull_request'`, so a main commit
   never uploads a plan. Push #1 of every PR therefore has no baseline BY
   CONSTRUCTION -- not by accident -- and the fallback would reduce that round
   against whatever the merge parent happens to be. Right now that parent is a
   `[skip ci]` commit with no run at all, and main's last four scheduled runs
   are all failure. A docs-only PR would skip all eighteen heavy keys against a
   red main.
2. **It buys the smallest share of the win and carries all of the risk.** The
   landed change already covers pushes 2..N; the fallback only adds push #1.

What it would need before landing: a shadow soak that records what the fallback
WOULD have decided, alongside a main that is green often enough for the
merge-parent to be worth anything as evidence.

### The API-outage boundary, which the existing gates were right to guard

Recorded with the held change, because it is the boundary that change has to
respect and the reasoning does not expire.

`test-scope-gate-outputs.sh` asserts that an engine which cannot reach the API
must not skip a single job, and the fallback would have broken it: git still
works under a `gh` outage, so the delta would classify and the round would
reduce. Two reasons that is wrong, and only the second is decisive. "No green
ancestor" derived from an API that answered nothing is an absence of
measurement, not a finding; and a round that reduces must be RECONCILED against
that same API at the end of the pipeline, so it would trade a full round for a
red required check. The held implementation handled this by marking an
unreadable candidate in `candidateFor` and declining the fallback with the note
`merge-parent-classify-declined:run-history-unreadable` when every candidate was
unreadable. An EMPTY walk is not that case: a one-commit PR legitimately has no
ancestor inside the fence.

### The hardening the landed change needed

`planCoverageIsFull` first asked `run !== false`, which is the wrong polarity
for this predicate. The two verdicts are not symmetric: reading a malformed
entry as coverage reduces a round on evidence nobody checked, while reading it
as a gap costs one full round, and only the second is recoverable. Driven
against the real predicate, `{run absent, reason:"out-of-scope"}`, `{run:"false"}`
and `{run:0}` all answered COVERS. The first is the dangerous one -- a dropped
`run` key beside an out-of-scope skip is precisely the scope-chaining case 1
forbids, wearing a shape that looks benign.

It now asks `run === true` for an executed key and `run === false` plus a
well-formed `greenlight:<digits>` reason for an evidenced one, matching
`skip-plan-reconcile.cjs:408,428` (`planned.run === true`) and the strict
booleans `scope-map.cjs:325-332` always writes. An array `jobs` is refused
explicitly, since `Object.values` would otherwise walk a shape no producer emits.

The hardening costs the fix nothing on real evidence: run 30975223299's
downloaded plan still answers `planCoverageIsFull = true` under the strict form,
its single non-run key being exactly `{"run":false,"reason":"greenlight:30968082228"}`.

### Evidence, both directions

Classification of the real deltas, through the real CLI (`--classify` over
stdin), re-run after the split:

| delta | mode | heavy keys running |
|---|---|---|
| `docs/ci-overhaul/06-progress.md` | reduced | 0 of 18 |
| `packages/cli/src/commands/repo.ts` | reduced | 14 of 18 |
| `.audit-allowlist` | full | 18 (`root-manifest:`) |
| `.ci/lib/common.sh` | full | 18 (`harness:`) |

The last two rows are the honest part of the answer: for PR #551 the full matrix
was CORRECT, because the branch also touches those surfaces. What was wrong is
that the mechanism which should have noticed the last push changed nothing
relevant had never been able to fire.

And the claim that it fires now, checked against the real artifacts rather than
asserted: run 30975223299's plan artifact was downloaded and attested against
that run's real Jobs API payload (96 jobs), and answers
`planCoverageIsFull = true`, `reconciled = true` DERIVED (the artifact carries no
`reconciled` field at all), and `full-green-attested`. So run 30983418337 would
have taken it as its baseline -- with the fallback held and playing no part.

### Gates

`test-scope-engine.sh` gains four cases pinning greenlight-only versus
scope-reduced baselines (including a forged `greenlight:probably-fine` reason
and an empty jobs vector), plus four more for the malformed entries the
hardening refuses. `test-scope-baseline-attest.sh`'s case (i) now mutates a real
skipped key rather than only the label -- a fixture that relabelled alone would
be asserting the thing that no longer decides.

Mutation-proven both directions against a copy of the tree carrying the
pre-hardening predicate: all four malformed entries answered
`full-green-attested` there and `reduced-baseline` here, while five controls
(greenlight skip, scope skip, forged reason, empty jobs, `mode: full`) answer
identically under both, so the hardening refuses exactly the malformed shapes
and nothing else.

### The classification regression table

Added the same day, because everything above tests the engine's decision
MACHINERY and nothing pinned the ANSWER for a representative delta -- which is
the half the operator actually experienced. Seven rows in
`test_representative_deltas_classify_to_pinned_verdicts`, asserted through the
real `--classify` path: docs-only, agent-tooling-only, THE REPORTED PUSH (the
exact four paths behind run 30983418337), cli, renet and account source each
against their named key SET, and docs-plus-one-cli-file, which is the row that
catches an over-eager skip. The three forced-full surfaces
(`.github/workflows/**`, `.audit-allowlist`, `.ci/lib/**`) are asserted
structurally -- mode, every key running, the pinned reason -- rather than as a
literal eighteen-name list, so adding a job key is not an eighteen-line diff in
a file that is not about the key list.

SETS, NEVER COUNTS, and that distinction was proven rather than asserted:
swapping `cli` from the `drills` surface onto `renet` leaves the count at
fourteen, so a count-based assertion still passes, while the set assertion goes
red with `missing: drills | unexpected: renet`. Dropping `cli` from `drills`
alone is caught the same way and by nothing else in the file. The failure
message names the row and the exact symmetric difference, deliberately: a
regression test that is a puzzle to update gets suppressed instead of updated.

The block runs LAST, and that is load-bearing. `test-gate-anti-vacuity.sh`
registers this file with the pattern `closure`, meaning the empty-tree run must
fail saying "closure" -- which is the seventh test, and `log_fail` exits on the
first failure. A table placed ahead of it would fail first with a message
carrying no "closure" and silently retire that registration. Verified by running
the anti-vacuity gate before and after. The block also carries its own inline
vacuity control, since it cannot borrow the file's registered one: a dead engine
answers `ENGINE-PRODUCED-NOTHING` rather than an empty key list, which would
otherwise read as "no keys to run" and pass every zero-key row.

Gate counts after the split and the table: `test-scope-engine.sh` 97 assertion
call sites plus 7 classification rows (counted separately so the table cannot
shrink unnoticed), `test-scope-baseline-attest.sh` 128; both green, as are
`test-scope-gate-outputs.sh`, `test-skip-plan-reconcile.sh` and
`test-gate-anti-vacuity.sh`.
