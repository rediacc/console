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

---

## 2026-08-05 -- the `no-cancel-failure` label is deleted, engine and all

Operator instruction, and the reason is the whole point: the label made CI
iterations slower. It suppressed the watchdog's force-cancel so a red run ran to
completion and reported every failure at once, which on this pipeline means
waiting out the 44-minute E2E and OPS legs before the round ends. On a branch
being driven to green that cost is paid every round.

**What it gated, both halves, because deleting one and leaving the other is how a
flag removal goes wrong.** `skipCancellationOnFailure` was consumed in exactly
two places: branch 2 of the failure handler (`core.setFailed` and keep
monitoring, instead of cancelling), and one term of `evaluateNoRetryCancel`,
where it suppressed the Quality/no-retry force-cancel. Both are gone; the
no-retry decision is now `isFailure && matchesNoRetry`, with no suppression
argument at all, and the branch chain renumbers 3/4/5 to 2/3/4.

The third thing keyed off the label was `LABEL_IMMUNE_PATTERNS`, and it does NOT
die with it -- it had a second job. `['Review Gate']` is also the set excluded
from the sibling drain (`pendingNoRetryJobs`) and the set whose force-cancel
fires instantly rather than waiting, so deleting it would have silently made a
Review Gate failure wait on every `Quality / *` lane. It survives, renamed
`NO_DRAIN_PATTERNS` after what it actually does, with `labelImmune` on the
verdict renamed `noDrain`.

The schedule/dispatch cancel exemption (`evaluateCancelExemption`) is untouched:
it never read the label, only cited it in prose to explain why the nightly could
not use one. Those paragraphs now say the same thing without naming a dead label.

**What replaces the label's purpose.** Nothing needed to: the Quality drain
landed after it and covers the deterministic half properly. A no-retry failure
holds its cancel until every sibling no-retry lane is terminal (90s cap), and
`forceCancel` re-fetches the job list so the annotation names every job that had
failed by then. What the label added on top was holding the run open for the
EXPENSIVE legs, which is precisely the cost being removed. A long job that keeps
being cancelled before it reports is verified by running its gate locally
(`npx tsx scripts/ci-runner/run.ts --only '<gate-id>'`), not by keeping a red run
alive.

**Gate.** `test-watchdog-cancel-label.sh` was not deleted: seven of its twelve
cases test the branch ordering and the drain, which outlived the label. It is
reduced and renamed `test-watchdog-no-retry-cancel.sh` (manifest id
`gate-test:watchdog-no-retry-cancel`), keeping the anti-vacuity read of the real
`WATCHDOG_NO_RETRY_PATTERNS`, and gains a case asserting that passing the old
suppression flag changes nothing -- so a half-reverted removal cannot pass
silently. Twelve assertions, green, and proven able to fire: four mutants run
against a mirrored copy (drop the cancel, re-introduce the suppression term,
empty `NO_DRAIN_PATTERNS`, treat a cancellation as a failure) each turn it red on
a different named case, with the unmutated copy green as the control.

## External drift leaves the nightly's verdict: `external_quality` (2026-08-05)

Five of the eight nightlies before 2026-08-04 were red on nothing but external
drift (a new rclone release, freshly published npm advisories, a new action
version): main's head had not changed for three of those nights. The
`no-external-quality` label could never help, because the nightly fires on
`schedule` where no PR label is readable, and push-to-main skips quality
entirely, so the one suite that validates main was the one place the escape
hatch could not reach. Worse, the guard existed in three spellings across five
sites, one gate (`check:ci-embed-asset-freshness`, the one that actually
reddened 3 consecutive nightlies) had NO guard at all, and `quality-security`'s
guard was job-level, silently skipping four fully offline gates alongside the
one external step it aimed at.

**The shape that landed.** ONE three-state initialize output,
`external_quality` (`hard` normal PR / `skip` labelled PR / `soft`
schedule+dispatch), passed to ci-quality.yml as a `workflow_call` input and
consumed by every external step the same way: `inputs.external_quality !=
'skip'` in the `if:`, command routed through
`.ci/scripts/quality/run-external-gate.sh` with `EXTERNAL_QUALITY_MODE`. In
soft mode the wrapper downgrades a failure to `::warning::` + step summary +
exit 0, which is exactly what the nightly-red machinery needs: it judges the
whole-run conclusion, so #544 stops crying wolf and closes on the first green
nightly. `audit.sh` deliberately keeps only the skip half (operator decision:
a new advisory against an unchanged lockfile is a real signal about main).
`check:deps` gains schedule execution it never had (its old guard was
positive-form PR-only).

**Why a wrapper and not `continue-on-error`:** check-workflows.sh BANS
continue-on-error repo-wide, and the repo's precedent for non-blocking is the
script-internal soft-fail (check-embed-asset-freshness.ts). The wrapper is that
precedent factored out once. It fails closed: unset mode is hard, an unknown
mode refuses (exit 2) even around a passing command.

**Proofs run, not reasoned.** test-external-gate-wrapper.sh pins all four
directions (soft-fail green + warning, hard-fail keeps the child's exit code,
unset->hard, unknown->refuse) plus the step-summary write. check-ci-parity
initially reported all six converted pointers as "runs something else" -- the
resolver read the wrapper as the leaf -- so resolveLeaves gained wrapper
transparency, pinned by two new cases: the wrapped gate counts as covered
(planted-defect proven: removing transparency fails exactly that case), and an
UNKNOWN wrapper does NOT count (the transparency cannot leak into generic
indirection). check-workflow-gates CHECK 2 held the input/with pair together;
actionlint, check-workflows, shellcheck, shfmt all green.

## Labels: four kill switches existed only in code (2026-08-05)

The sweep behind the external_quality work found that `.github/labels.yml` had
ZERO consumers (nothing created labels from it, nothing checked drift), and
four labels referenced by running code did not exist on the repo at all:
`full-ci` (the scope engine's documented kill switch, which
scope-reconcile-shadow.sh literally tells the operator to apply), `autopilot`
and `autopilot-blocked` (hard-required by autopilot-gate.sh), and `rollback` --
the nastiest, because promote-stable.yml's `label:rollback` search returns
zero PRs for a nonexistent label, so the rollback promotion-block was silently
FAIL-OPEN.

All four are now created live and declared in labels.yml, alongside
declarations for `nightly-red`, `bug` and `automated` (consumed by
report-nightly-status.cjs; nightly-red stays self-creating on first fire, the
declaration is inventory). The mechanism that stops the fifth unreachable
label: `check:ci-label-refs` (.ci/scripts/quality/check-label-references.sh)
sweeps `.github` and `.ci` with ten curated extraction patterns (one per
consumption shape in the tree: workflow contains(), gh api labels[]=, search
filters, cjs includes()/consts/arrays, jq --arg, the AUTOPILOT_LABEL defaults
in both yml and sh spellings, and detect-bump-type's grep -qx) and fails on
any reference labels.yml does not declare. Every extractor self-tests against
a planted sample BEFORE the sweep, and a distinct-labels floor refuses a dead
sweep outright -- the check-silent-failure-patterns lesson (a green gate that
scanned zero files for weeks) designed in from the start. The gate's own test
drives all ten shapes through fixtures, proves the fail direction names label
AND site, proves declared-but-unreferenced stays legal, and runs the real gate
seam-free so the sweep provably executes in CI.

## Autopilot: dispatch-campaign arming, model plumbing, hold-open debug (2026-08-05)

**Arming is no longer label-only.** `gh workflow run Autopilot -f pr_number=N`
is now itself the arming act: round 1 runs off the dispatch, and that round's
state-comment write records a CAMPAIGN on the metadata line, which gained three
fields (`campaign: open|closed|none | model: <id> | rounds_max: N`). Later
`workflow_run` rounds re-arm from the campaign while it is open and rounds
remain, so the loop no longer depends on a label existing. The label path is
untouched and still works; `autopilot-blocked` is checked before all three
paths and beats all three. Stop story, three scopes: cancel the run kills one
round, `autopilot-blocked` kills the loop, `AUTOPILOT_ENABLED` kills everything.

The carry-over parser in state-comment.sh deliberately drops unknown content
(anti-tamper), so the new fields ride the metadata line, which is re-rendered
from validated values every round rather than copied forward. Every value is
normalized on read AND on write: campaign is one of three literals, model
matches a tight identifier shape, rounds_max is a small integer, and anything
else collapses to its sentinel. The gate does not re-parse that line -- it calls
the new `state-comment.sh fields` subcommand, so the format has exactly one
reader and one writer, and a round-trip case (render -> classify) is what would
go red if they ever diverged. The 400-char line cap and 55 KB compaction are
untouched.

**Campaign termination is real, not aspirational.** The model job only runs for
fix and review-response, so it can never observe mode `done`; a campaign closed
only there would stay open forever and re-arm on every later CI completion. The
finish job therefore got a `Close the campaign` step (same `AUTOPILOT_ALLOW_STATE`
flag, same render call, `--campaign closed`). The round cap is the second
terminator: the campaign path will not re-arm once `ROUNDS_DONE >= MAX_ROUNDS`.

**Model and effort plumbing.** The model job's `claude_args` no longer hardcodes
`--model claude-sonnet-5`. The gate resolves the effective model as dispatch
input > campaign field > `claude-sonnet-5`, validates it against a two-entry
allowlist (an unknown value is a typo, not an instruction: it falls back rather
than failing the round after paying for the runner), and emits it as a decision
output. Round caps resolve the same way with `AUTOPILOT_MAX_ROUNDS` as the third
fallback and 25 as the fourth. The argument list is assembled in one env-routed
step output, so there is a single copy of it.

**The `effort` input is wired, and the forwarding was verified rather than
assumed.** Evidence, at the pinned action SHA `fa7e2f0a` (v1.0.180): the action
leaves every unrecognised `claude_args` flag in `extraArgs`
(`base-action/src/parse-sdk-options.ts` extracts only model, add-dir,
allowed/disallowed-tools, mcp-config and setting-sources, and passes the rest
through); `@anthropic-ai/claude-agent-sdk` (dependency `^0.3.217`, current
0.3.222) emits every `extraArgs` entry to the CLI verbatim as `--<key> <value>`
(`sdk.mjs`: `for (let [W, Se] of Object.entries(Zt)) ... $w(H, W, Se)`, with the
intervening filter a pass-through that only touches sandbox/settings); and the
CLI accepts `--effort <level>` -- the SDK emits exactly that flag for its own
`effort` option (`if (this.options.effort) H.push("--effort", this.options.effort)`),
its types declare `'low'|'medium'|'high'|'xhigh'|'max'|number`, and the local
CLI 2.1.222 `--help` lists it. So the lever is live, not decorative. It is
dispatch-ONLY on purpose: unlike model and max_rounds it is not recorded in the
campaign, because raising effort is a decision about one hard failure rather
than a property of the whole run.

**Hold-open debug session, and why it sits where it sits.** A dispatch may now
carry `debug-shell` and hold the runner open behind a quick Cloudflare tunnel
with a tmate shell, driven by the vendored `.ci/breakpoint/scripts/`. The steps
sit strictly BETWEEN "Assert the model left HEAD alone" and "Mint post-model app
token", and that placement is the whole security argument: it is the only window
where the workspace holds the round's entire result and no write credential
exists anywhere on the runner. Two steps later `Wire push authentication` writes
the app token into `.git/config`, and a human on the box after that line holds a
repo-write bearer token. Three conditions gate every step: the input, the event
being `workflow_dispatch` (an autonomous round must never hold a runner open),
and the gate's new `dispatch_trusted` output. That third one is not redundant --
a round can be armed by the LABEL, whose trust check is the label applier, so
without it anyone with dispatch rights could get a shell on a runner holding the
repo source by dispatching an already-armed PR.

Three further calls, each deliberate: a credential SCRUB with an assertion runs
before the tunnel (a scrub whose result is never checked is a claim, not a
control); the breakpoint scripts are invoked from `$RUNNER_TEMP/harness`, the
trusted copy staged before the PR head landed, because running `.ci/breakpoint`
out of the workspace would execute PR-authored shell; and the Cloudflare token
is deliberately NOT in any of these steps' env. Quick mode never reads it
(`start-tunnel.sh` requires it only in `start_named`) and `stop-breakpoint.sh`
skips its whole account-side block without it, so passing a tunnel-edit +
`rediacc.io` DNS-edit token into the one step sequence whose purpose is to put a
human on the runner would hand that human the token for nothing. This is a
deliberate deviation from a literal reading of the brief, called out here rather
than buried. The tunnel URL is not a step output and appears in no `env:` block,
for the reason breakpoint learned in run 30254567365. The job timeout is
`350 || 30` by expression -- 350 rather than 360 for breakpoint's reason, and a
choice between two constants because Actions expressions have no arithmetic.

**New gate: `check:ci-autopilot-bp-align`.** breakpoint.yml is frozen in
MANIFEST.sha256 and GitHub has no include mechanism for workflow inputs, so the
three debug inputs are hand-copied -- and hand-copied shapes drift silently. The
gate extracts breakpoint's `duration` option list and the two booleans'
type+default and compares them to autopilot's copies (breakpoint is canonical;
the gate never asks anyone to edit the frozen file). Descriptions are
deliberately not compared: breakpoint's duration text is about named-mode Access
logins, which the quick-tunnel autopilot does not have. Anti-vacuity is the
point of most of its code: a missing file, a missing input block, a missing
field, or an options list under five entries all exit 1, because
empty-equals-empty is this gate's only real failure mode. Its test proves the
real tree, unmutated copies through the env seams, a removed duration option, a
flipped `send-email` default, both missing-file directions, a renamed input
block, and the short-list floor.

**Also fixed while in here.** `Build event fixture` used to end in a bare
`jq -e '.workflow_run.id'`, so a dispatch aimed at a head whose CI had not
finished died with exit 1 and nothing on stdout explaining it. It now sets a
`ready` output, emits a `::notice::` naming the head and telling the operator to
dispatch again after CI completes, and the two downstream steps that need the
event fixture are gated on it -- a no-go with a reason instead of a red step.

**claude-review model input.** `claude-review-reusable.yml` gained an optional
`model` workflow_call input (default `claude-sonnet-5`) consumed at BOTH
hardcode sites through ONE job-level `REVIEW_MODEL` env var: the real
`claude_args` and the `CLAUDE_ARGS_SENT` log echo were two independent copies of
the same string, which is a log that can lie about the run it describes. The
console caller gained a matching `workflow_dispatch` choice input; submodule
callers are untouched and get the default.

**Gates run:** test-autopilot-harness (216 assertions), test-autopilot-workflow-invariants
(30, still "4 jobs scanned" -- no new job), test-autopilot-breakpoint-alignment (23),
test-gate-paths-exist, test-gate-anti-vacuity, test-ci-parity, plus
check:ci-autopilot-workflow, check:ci-autopilot-bp-align, check:ci-parity,
check:ci-workflows, check:ci-actionlint, check:ci-shell-lint, check:ci-label-refs
and `shfmt -i 4 -ci -d` on every touched script. Two planted defects, not
reasoned: removing one `duration` option from a fixture copy fires the alignment
gate with its pinned diagnostic, and disabling the gate's dispatch-arming branch
fails exactly the dispatch case in the harness test (restored md5-identical,
green again afterwards).

---

## 2026-08-05 -- review-gate blind spots, a review-budget undercount, and a durable agent report inbox

Landed on branch `0804-1` (console PR #551). Everything below touches `.ci/`,
`.github/` or `.claude/`, which is why it belongs in this log rather than only in
the wave's own plan file.

### Both review gates were blind to the larger half of a review

`check-review-comments.sh` read only `pulls/{PR}/comments`, so the reviewer's
TOP-LEVEL verdict -- the comment carrying the severity-ordered defects, the nits
and the coverage map -- could go unanswered with CI green. Only the top findings
are ever mirrored inline (capped at 20, and any whose line is outside the diff is
dropped), so the summary is strictly the larger surface. It now also reads
`issues/{PR}/comments`.

`check-review-report-replies.sh` had the same class of defect for a different
reason: its selector AND-ed the report header with `json:review-findings` OR
`### Review`, a guess about the report's WORDING that no producer emits.
`--post-report` wraps whatever the model's closing text happened to be, which on
this PR carried neither marker, so the gate found no report and passed
vacuously. It now keys on the `**Claude finished` header alone.

The rule both fixes follow: **key on what the producer actually writes, never on
a description of it.** The header and the findings fence are constants the
pipeline emits verbatim, so a rename breaks posting in the same commit instead of
silently blinding a gate.

The two gates are complementary rather than duplicate -- different producer
constants, different comments from the same pass -- so their reply thresholds are
asserted equal, and `test_one_reply_clears_both_gates` proves one reply satisfies
both. That property has since held twice on live data.

**Gate self-demonstration:** the new gate went red on this very PR, on its own
author, for an unanswered verdict that would have passed silently a day earlier.

### The review budget was undercounting, and the cap could never be reached

`review_report_count()` carried the same defective qualifier in its two remaining
call sites. Measured against live PRs before the change, counted versus actually
posted: **#551 0 of 1**, #550 5 of 7, #546 3 of 7, #543 1 of 9. So a completed,
marked review registered as never having happened, the cap never advanced, and
every subsequent green push paid for another full review -- the exact
"pays again forever" failure the spent-attempt path exists to prevent.

The function also existed as two identical copies. It now lives in
`.ci/scripts/lib/common.sh` beside `review_cap_for()`, so numerator and
denominator come from one place. Counts after: 1, 7, 7, 9.

### A typecheck target that had never run

`scripts/tsconfig.json` had covered 70 files since January with nothing invoking
it, and `.ci/scripts/**/*.ts` had no tsconfig at all -- a config that read as
coverage and provided none. Corrected and extended, it reports 0 errors across 71
files (512 as written, ~99% of it noise from settings nobody had executed). It
surfaced two real bugs: a fifth argument passed to a four-parameter function, so
a "cloud-only context detection" silently did nothing (deleted, not implemented --
the cloud adapter was removed deliberately), and a `snippet` field set on a type
that has no such field and requires `command`, so that reporter printed
`in: undefined`.

Wiring it into `check:types` needs `package.json` and is left as a one-line
operator decision against a provably green target.

### Preview readiness required a streak, and previews stopped lying about themselves

`wait-for-preview-worker.sh` declared ready on a SINGLE successful probe. Two
prior fixes had changed WHICH endpoint was probed; neither changed how many
times, so the failure returned a third time. The deploy flaps by construction --
the per-PR D1 database is recreated on every push and `server-info` is the first
endpoint touching it. Readiness now requires 3 consecutive successes, control-
proven both directions (a flapping stub passes at streak 1 and fails at streak 3).

Separately, preview workers self-identified as **production**: `envSchema`
defaults `ENVIRONMENT` to `production` and `wrangler.preview.toml` never set it,
so a preview served `updateChannel` `stable` while the `install.sh` it served
baked in channel `pr-N`. Fixed in the preview heredoc only; production deploys
unchanged.

### Durable sub-agent report inbox and a push-based waiter

Sub-agent reports reached the lead session only as a message in its context, so a
compaction lost them and an agent that reported substantively was
indistinguishable from one that went idle silently. Investigation inverted the
premise: reports are ALREADY durable -- every sub-agent writes a transcript --
so the gap was discovery, addressing and unread-ness, and the `SubagentStop`
hook that would capture them had never been wired.

`.claude/settings.json` now wires `SubagentStop` plus a second `SessionStart` and
`PostCompact` group (two groups on one event both deliver their context --
probed, not assumed). New `wl_report.py` captures and surfaces; new `wl_wait.py`
blocks until something new arrives and exits, so its EXIT is the notification and
a waiting session costs zero turns. A `--scan` back-filled 132 previously
unrecoverable reports.

Four findings worth carrying:

- **`last_assistant_message` is the SIGN-OFF, not the report.** A teammate
  delivers by SendMessage and then says "Released. Task complete." Measured on one
  agent: 24 characters handed over against payloads of 8,646 and 6,331. Building
  to spec would have marked that agent `silent`, inverting the one distinction
  the feature exists to draw. Bodies are harvested from the payloads instead.
- **A waiter EXITS every time it fires**, so "no waiter running right now" is true
  exactly when a session is behaving correctly. A force-a-waiter check keyed on
  that broke 16 harness cases. It is now a grace count over unacted `PostToolUse`
  nudges, resetting the moment a waiter appears.
- **`PostToolUse` carries no `background_tasks`**, so the nudge cannot see the task
  table; it uses a heartbeat the waiter re-touches, since a marker written once at
  launch becomes a lie the moment the process dies.
- **Phantom captures.** 44 of 181 records had neither an agent type nor a
  resolving transcript -- not sub-agent reports at all. The store partitioned
  exactly, with no mixed case, and 1885 sidecars confirmed no real agent kind
  lacks a type. Discarded only when BOTH fail (AND-on-reject is more permissive
  than either predicate alone; the OR form drops real reports and turns seven
  assertions red). The 44 were retired by APPENDING retire events, preserving the
  append-only property the lock-free design rests on.

### Gates run

`test-worklist-v5.sh` 432 -> 460, new `test-report-inbox.sh` 113,
`test-claude-hooks.sh` 541, `test-review-status.sh` 26 -> 44,
`test-gate-paths-exist.sh` 4, `test-swallowed-failures.sh` 22, plus
`check:ci-parity`, `check:ci-suppression-liveness` (82 entries, 0 findings),
`check:ci-external-links`, `check:ci-shell-lint`, `check:ci-shell-format` and
`shfmt -i 4 -ci -d` on every touched script.

`gate-test:worklist-hooks` now runs BOTH stop-hook harnesses, parsing each one's
own summary -- the wrapper previously used `tail -1`, which would have read only
the second. No `manifest.ts` change was needed for that (the gate is already
registered); `test-preview-readiness.sh` DID need one, correcting a claim from the
preceding commit that glob discovery made an entry unnecessary: `run-all.sh`
globs for CI, but `npm run ci` schedules from the manifest, so a glob-only gate
runs on one side and `check-ci-parity` catches it.

Mutations, not reasoning: nine against the report inbox, six against the gate
wrapper, three against the phantom filter, and one per review-gate assertion.
Two tests were found passing for the WRONG reason and fixed rather than accepted --
one asserted an outer layer while appearing to assert an inner one, and one read
the real report store because an unset env var is not neutral.

## 2026-08-05 — identity, latching, and three gates that could not fail

Eleven commits touched `.ci`, `.github` and `.claude` after the entry above. What
a new session needs from them:

**The stop hook now validates WHO is calling it.** Every `<me>` was previously
accepted on SHAPE alone, so a session that copied a sub-agent's namespace token
out of a tool result used the wrong identity for 26 hours: 219 calls under it,
20 under the right one, from one process. Every call SUCCEEDED — writes and reads
key off the same unvalidated string, so one typo splits a session into two
internally-consistent halves and nothing downstream can tell. A peer's message
sat unread for 34 hours while it auto-escalated. `wl_core.py::check_me` compares
`<me>` against `CLAUDE_CODE_SESSION_ID` (that name is verified against a live
child's environment; `CLAUDE_SESSION_ID` DOES NOT EXIST and would resolve to ""
forever, which every caller treats as pass). Three layers: refusal, a phantom
backstop that names orphaned identities, and `--reassign` that moves open work
without rewriting history. `WORKLIST_SESSION_ID` is the declared override, an
identity ASSERTION rather than a suppression flag.

Its own control landed by accident and is the clearest evidence in the file:
`--list --open <session>` answered "no actionable items" while that session held
22 open items and a request.

**A gate keyed on a description of what a producer emits, rather than the
constant the producer writes, cannot fail.** Six instances this day, across
review-comment checks, the sidecar gate, and a suite harness reading only the
last of two summaries. The sidecar gate shipped WITH the defect it was written to
prevent (it swallowed `git ls-files`'s exit status, so an unreadable tree read as
a clean one), caught by `test-swallowed-failures.sh`. Standing lesson: derive the
gate from the constant, and prove it fires by planting the defect.

**Latched, never silenced.** The SUBMODULE POINTER MOVED warning re-fired every
stop until push, including after a deliberate decision to keep a pointer local —
which is how a real warning becomes wallpaper. It is now latched per
(path, target sha) for `SUBMODULE_LATCH_MIN` (15). TIME-BOXED on purpose: a
permanent acknowledgement would go silent on a pointer somebody forgot, and
silence there is indistinguishable from correctness.

**Housekeeping Phase 6 is dead by design, and now says so.** Deleting a pr-*
environment OBJECT needs Administration:write, which `check-no-app-admin-perm.sh`
deliberately forbids the App so a leaked token cannot delete edge/stable. The
comment used to read as a pending upgrade. The real mechanism is a periodic
manual `gh` sweep by an owner-token human.

Gate: `.ci/scripts/test/gates/test-worklist-hooks.sh` runs BOTH stop-hook
harnesses (569 + 115 = 684). It previously parsed only the last summary, so the
first harness could fail unnoticed.

## 2026-08-06 — the scope map stops running ceph for an attribution string

**The scripts/ harness rule was too coarse, and it fired for real.** Commit
`bcc4f1ee1` changed one file — an Apache-2.0 attribution-URL check — and the
resolved plan recorded `"full_reasons": ["harness:scripts/check-embed-credits.ts"]`,
running the whole E2E/ceph/k8s/OPS matrix. Measured across three runs, dropping
the infra matrix saves **19-43 min wallclock (28-47%)**, and the new tail is
`Validate Promotion` at ~47-52 min in all three, so it also converts a 66-93 min
variable pipeline into a predictable ~50 min one.

**The old comment gave the WRONG reason, and that is the more useful finding.**
It said quality lanes "must stay immune to scoping by construction" and concluded
`full`. Gate immunity is real but the engine guarantees it independently:
`ci-quality.yml` contains **zero** `run_` references, so no quality lane is among
the 18 keys the engine can switch off. A `scripts/` rule cannot scope out a gate
because gates are not scopeable at all. A conservative rule defended by a wrong
reason is one that gets removed for bad reasons later.

**Two subsets stay full**, found by tracing execution rather than reading names:
`scripts/drills/` (ct-tests.yml:1730 → run.sh:1987) and
`generate-third-party-licenses.ts`, which runs inside the SEA build and whose
output SHIPS in the CLI binary — a silently-wrong credits file is caught only by
gated jobs. Everything else is a zero-job `gates` module.

**Honest expected value: ~1.28% of commits** (29 of 2263). 75% of
`scripts/`-touching commits also drag `package.json`/`.ci/`/`.github/`, which
force full independently. The reason to land it is not the minutes; it is that
"an attribution-string check ran a ceph fork test" makes the engine look
untrustworthy even when it is working correctly. Full analysis:
`docs/agent/0804-1/PLAN-scope-gates-split.md`.

**A CI wait is no longer a legitimate stop.** Operator ruling: a session watching
a run is idle, not blocked, because the run needs nothing from it. The stop-gate
judge now earns "stop" from a named CI wait only when no tracked item can be
advanced locally. Unpushed work cannot disturb a run in flight, so "wait for the
PR to land" almost never justifies not writing the code.

**Mutation discipline, unchanged and still earning its keep.** Four mutations on
the scope rules; M4 (swap `modules: ['gates']` for `['cli']`) is the one that
matters — it still reports `reduced` while dragging the matrix back, so without
that assertion a future edit giving `gates` a job surface would silently undo the
change while every test row still read `reduced`.

## 2026-08-06 — the 12 CI-only stop-suite failures: not reproducible, not diagnosed

**Left here rather than in a worklist item, because the worklist item had no
executable action left and a blocked item that nobody can advance is worse than a
record somebody can read.**

`test-worklist-v5.sh` reported **563 passed / 12 failed** in CI run
`31055389610` (`Quality / Security`) while giving **575/0** locally. It has not
recurred in **six** subsequent executions of the battery (`31065302651`,
`31069411195`, `31073312222`, `31075240744`, `31077151139`, `31078369416`).

**The twelve were never NAMED.** `2f509ccf8` fixed the reporter that hid them —
it used `tail -20`, and in a 575-case suite the last twenty lines are PASS lines
plus the summary, so every FAIL line scrolled past. That fix has never had a red
to fire on. If this returns, the next red names the cases, and that is the single
most valuable thing to read.

**Seven hypotheses falsified**, so a recurrence starts narrower:
1. `HOME` — an empty one still gives 575/0.
2. Sibling fixtures from the `wl_liveness` session-scoping — case 163v is the
   only v5 case creating `subagents` dirs.
3. Wall-clock sensitivity — only 3 time deps exist, all in 163v, bounded by 10
   hours or set-to-now, nothing crosses a threshold.
4. Shared-store collision — the harness pins `TMPDIR=$BASE/tmp` under
   `mktemp -d`, so concurrent runs cannot collide in `/tmp/claude-worklist`.
5. Blind `proc_table` — 569/8, not 12.
6. Blind `harness_ancestors` — 571/6, not 12.
7. **Their union — 569/8, IDENTICAL to (5) alone**, because `harness_ancestors`
   consumes `proc_table`. That puts a **ceiling of 8** on the entire
   OS-visibility family, which therefore cannot explain 12. This killed the
   leading theory, and it is the most useful of the seven.

**The measurement error worth not repeating** is recorded in
`docs/agent/TRAPS.md`: three rounds were initially counted as "did not recur"
when the battery had never executed, because the run was cancelled by an earlier
gate. Not-executed is a third state.

**Honest status: not reproducible in six executions, cause unknown.** That is a
characterisation, not a mechanism.

## 2026-08-06 — the reachability gate, and its own first defect

`check:ci-scope-scripts-reachability` exists because the scope split's two
carve-outs (`scripts/drills/`, `generate-third-party-licenses.ts`) were traced BY
HAND at one commit. Nothing stopped the next file becoming reachable from a gated
job and being narrowed silently — a job skipped on the very delta that changed
its dependency, which reads as a faster green rather than a gap.

**It shipped with the defect it exists to catch, and review found it.** The scan
read run.sh's drill arm with `grep -A 12`. One line short: run.sh dispatches
THREE drills and `scripts/drills/license.sh` at :1995 fell outside the window, so
`check_path` was never invoked for it. The gate reported "every reachable path
forces full" having never looked at one. Inert only because `scripts/drills/`
carries an independent full-prefix rule — the stated invariant was already
narrower than its claim.

**Two wrong fixes, both worth recording:**
- A bigger window. `-A 16` passes today and breaks on the fourth drill.
- Reading each arm to its closing `;;`. run.sh NESTS case statements and
  terminates arms inline (`stop) account_stop ;;`), so the block scan ran past
  `account)` and mis-attributed `scripts/dev/worktree.sh` to it. One silent miss
  became one loud false positive.

The fix attributes each dispatch to its nearest preceding TOP-LEVEL case label,
which needs no model of arm termination at all.

**A near-miss worth naming**: the first rewrite used `sub` as an awk variable.
That is a gawk BUILTIN, and the scan returned nothing. It failed loudly, which is
the only reason it was caught — silently it would have been another green that
checked zero paths.

**Method note.** Both the original gate and the fix were verified by planting a
real invocation of a narrowed path in `.ci/scripts/build` and observing rc=1,
then removing it for rc=0. The proof was RE-RUN after the rewrite rather than
assumed to survive it.


## 2026-08-06 — Python was ungated, and the first thing the gate caught was ours

Operator ask: "we have too much linting and tidy-up thingy for js/ts but we don't
have for python! Especially for hook program."

The premise held exactly. `package.json` carried **91** `check:ci-*` gates
covering TypeScript, shell and Go and **zero** covering Python, while 13 of the
15 tracked `.py` files are the Stop-hook program that gates every agent turn.
There was no `ruff.toml`, `pyproject.toml`, `setup.cfg`, `.flake8` or `mypy.ini`
anywhere — yet the hook modules already carried `# noqa: BLE001` and
`# noqa: PLC0415`. Someone had run ruff against them once, by hand, and nothing
had enforced it since: **suppressions with no gate behind them**, which is worse
than neither, because the annotations read as evidence that something checks.

### `check:ci-python-lint`

`.ci/scripts/quality/check-python-lint.sh` + `ruff.toml`, `select = ["ALL"]` with
every exclusion stated in config rather than sprinkled as per-line noqa, so new
ruff rules opt IN automatically. Wired at all four points, three of which are
silent when missing: the package.json key, the `manifest.ts` GateSpec, the
`ci-quality.yml` step it names, and a pinned+verified ruff install step beside
the shfmt one. `check-ci-parity.ts` green in both directions.

**Control-first, because there are two ways this gate could be green while
proving nothing.** (1) `ruff check` with no paths exits 0, so a broken glob or a
run outside a work tree reads exactly like a clean repo — the file list is
counted against a floor, and that check runs BEFORE ruff is resolved, so an
empty-tree failure is about vacuity rather than a missing binary. (2) A wrong
config path or a dropped rule also looks like a clean tree — so a synthetic
`F821` is planted in a scratch dir outside the repo and ruff must report it.
`F821` specifically, because that is the rule that caught the real bug: if a
future config change disables it, the gate fails loudly instead of going quietly
blind to the defect it was built for. Registered in `test-gate-anti-vacuity.sh`
and observed rejecting an empty tree.

### mypy was measured and rejected

Default mode finds exactly **2** things, both the deliberate sibling-import shim
`worklist.py` documents as an invariant. `--strict` finds **1061**, of which
96.7% is `no-untyped-def`/`no-untyped-call` annotation churn, for 5 real
findings. It does not earn a gate. That is a measurement, not a preference.

### 97 findings → 0, five of them real

- **`F821` in `wl_checks.guided_slice`** — a `NameError` introduced by this same
  session's root-anchoring sweep an hour earlier. Both hook suites (584 and 118
  assertions) passed straight over it, because reaching the branch needs
  `root=None` AND a plan-subagent triage at once. It then failed **soft** into a
  bare `except` that replaced the operator's whole worklist guide with an
  apology. The gate caught it before it had landed.
- A leaked SES response-body handle (`SIM115`): the `finally` unlinked the temp
  file and never closed the reader. CPython refcounting hid it.
- `ci_queue_state` unpacked the `gh` error and dropped it, so a **failed API call
  and a genuinely quiet queue both surfaced as a bare "unknown"** — the exact
  blindness `worklist.py`'s own invariants forbid.
- `worker_facts` took a `session_id` parameter, ignored it, and re-read the same
  value from the event.
- `app.run(debug=True)` in a Flask **template** whose purpose is to be copied.

**Nothing was baselined and no rule was disabled to reach zero.** Where a
finding was genuinely deliberate it is annotated AT THE SITE with its reason
(4 lazy sibling imports, 2 urlopen calls behind a runtime https guard, one
blanket except whose 11-line comment already explained itself). The other 3
`PLC0415` were lazy for no reason and were hoisted, so those findings are gone
rather than documented.

**The 6 `B023` are false positives and were fixed anyway**: `fire_once` is only
called inside the iteration that defines it. Binding the loop variables as
default args is free and provably equivalent, and it keeps `B023` ENABLED for
sites where it would be real. Disabling a rule to clear six known-safe uses is
how the next genuine late-binding bug ships unnoticed.

### A trap that nearly cost 50 deliberate suppressions

`ruff check --select RUF100` **replaces** the rule set. `BLE001` switches off,
and every one of the 50 deliberate `# noqa: BLE001` in the tree reports as an
unused directive — all marked `[*] fixable`. Auto-fixing that would have
stripped the suppressions guarding the fail-closed exception handlers, whose
whole job is to stop a crashing hook from reading as ALLOW. **Only the
full-config run is authoritative**; under it there is no `RUF100` at all. Never
judge noqa health from a narrowed `--select`.

### `check_inline_python.py` — the blind spot the ruff gate leaves

A `.py` gate lints tracked `.py` files. Python inside a JS/TS string literal is
invisible to it, and that is not hypothetical:
`packages/cli/src/remote/vscode/bootstrap.ts` held a **130-line, 4871-character
Python program** in a template literal, executed on a remote host over SSH. Four
of its six interpolations were unescaped, and `ast.parse` says what that means —
a `universalUser` of `'; import os; os.system('id'); x='` **parses cleanly** and
turns the middle into executable Python, under `sudo -u` on the user-switch
path. Escaping fixed separately; the program itself still needs to move.

The detector is narrow on purpose. Of 999 tracked JS/TS files, four match
`/python3?/` and **three are innocent** — an interpreter binary name, the word
"python" in a word list, and the string `"check:ci-python-lint"`. A rule that
flagged those would be switched off within a week. So it flags only a quoted
region carrying two or more Python STATEMENT shapes at line starts, or a
`python -c` handed source assembled in the same file. Controls run in both
directions before any real file is read, and a control failure aborts without a
verdict.

Written in Python so the ruff gate polices it — it had 10 findings on its first
run. Committed **unwired**: the tree cannot pass it until `bootstrap.ts` is
migrated, and wiring a gate the tree fails is landing a red gate, not a fix.

## `validate-promote` timed out and blocked a release (2026-08-07)

The 0804-1 merge landed on `main` and then **did not release**. Console CI run
`31143504009` ended `cancelled`, and the chain is worth stating exactly, because
none of it was a code failure:

`Validate Promotion` hit its `timeout-minutes: 30` at 30m13s -> its conclusion
became `cancelled` -> `assert-ci-complete.sh` forgives `skipped` but **not**
`cancelled`, so `CI Complete` failed -> `Pipeline Sentinel` failed on
"Check finalize-release-sentinel conclusion" -> the finalize step never
dispatched `cd-v2.yml`, so **no Release run was ever created**. The job's own
cleanup step did run, so no R2 bytes were orphaned.

### It was not transient, and the PR could not have caught it

The standard triage question — *did this job run and pass on the PR run?* —
answers **yes**, in 7m19s, and that answer is misleading here. Durations of the
same job on `main` pushes, oldest first:

| run | duration |
|---|---|
| 30249144168 | 21m57s |
| 30289599104 | 27m20s |
| 30324286856 | **CANCELLED 31m03s** (2026-07-28) |
| 30528112416 | 28m35s |
| 30596539903 | 24m09s |
| 30621380078 | 24m56s |
| 30692838860 | 24m01s |
| 31143504009 | **CANCELLED 30m51s** (2026-08-07) |

It had been running within minutes of its own ceiling for weeks and had already
blown through it once, eleven days earlier, with nobody acting on it. The PR is
fast because it promotes the tiny per-PR channel; `main` promotes the full
`edge` channel, and that channel grows with every release. So this is the
**"runs differently on main"** case, not the transient case: a PR check here
goes green while proving nothing about the path that actually breaks. That is
what licensed a direct-to-`main` fix (`afe143d9a`, `timeout-minutes: 30 -> 60`,
measurements recorded at the site).

### 60 is headroom, not a fix

Promotion validation re-copies the whole channel every run, so its cost is
O(channel size) and the trend is upward — 21m57s on 2026-07-27 to over 30m on
2026-08-07. **If it creeps past 60, make the copy incremental rather than
raising the number again.** Raising it a second time would be treating the
symptom twice.

### The generalisable trap

A soft-required job that distinguishes `skipped` from `cancelled` turns a
*timeout* into a *release blocker* with no error message anywhere naming the
timeout. The failing job says only "The operation was canceled." Worth checking
whether any other job in `ci.yml` sits close enough to its ceiling to do the
same; the measurement is
`gh api "repos/rediacc/console/actions/runs/<id>/jobs?per_page=100"` and
comparing `started_at`/`completed_at` against each job's `timeout-minutes`
(note `per_page`: the default of 30 silently truncates a 94-job run).

## The version-check family that could not fail (2026-08-07)

A release published CLI binaries built as **1.2.16** under the label **1.2.17**.
Nothing user-facing broke — `tag-and-release` needs `validate-install-published`
and so was skipped, and the channel pointers never advanced — but the incident
exposed a family of guards that were *incapable of failing*. Thirteen in total.
They are recorded here because the shared shape matters more than any one fix.

### The shape

Every one of them reported success while examining nothing:

| guard | how it could not fail |
|---|---|
| `assert-artifact-version.sh` | downloaded an artifact named `cli-manifest` that **nothing has ever produced**; took its not-found → warn → `exit 0` branch on every release since it was written |
| `verify_version()` | `grep -q "$expected"` passes on an empty expectation, on empty output, and on a **substring** — `1.2.1` "verified" against `1.2.16` |
| Windows install validation | ran `--version` and **discarded the output** |
| 7 of 11 install methods | never referenced `$VERSION` at all; the assertion was "the binary exits 0" |
| the test script itself | `exit 0` after running **zero tests** — a typo'd `--method` was swallowed |
| retry-mode releases | skipped the artifact assertion, justified by a comment claiming the artifacts "match by definition". They do not |
| the build's own smoke test | asserted non-empty and not-`null`, never compared, and **clobbered** the variable it should have compared against |
| `inject-env.sh --strict` | the only `0.0.0-dev` guard, with **zero callers** |
| attestation verification | no failing exit path, and `find` over two absent directories exited 0 having verified nothing |
| `compareVersions` | returned `0` — "equal" — for malformed versions (NaN segments, *not* the empty case: `Number("")` is `0`) |
| the tag fetch | `2>/dev/null \|\| true` four lines before the version is computed |
| the image closure key | an empty version collapsed it, so a cached image built at an older version could be promoted |
| `check:ci-secret-reachability` | **the new gate itself**, on day one — see below |

### The rule that came out of it

> **Always have a version. Skip or fail — never a silent pass.**

Every path must end VERIFIED, in an explicit VISIBLE skip, or in a FAILURE. A
path that cannot determine a version and returns success *is* the defect. A skip
that prints its reason and is counted satisfies the rule; a zero-total run does
not, because it says nothing at all.

### Three recurring traps, each of which bit more than once

**A guard callers cannot reach is a guard that cannot be used.** `isValidVersion`
existed but was never re-exported; `--strict` existed with zero callers;
`assert-artifact-version.sh` looked for an artifact nobody produced. One disease,
three costumes.

**A green you have never watched go red proves nothing.** Every fix in this wave
ships with a planted-defect control, and several of those controls were
themselves wrong first — one fake `gh` read the wrong argument and made the
all-good case pass vacuously, caught only because the one-bad case also went
green.

**A partial scan reads exactly like a clean one.** The new secret-reachability
gate scanned console alone in CI, because `actions/checkout` defaults to
`submodules: false`; it cleared its own vacuity floor on console's 42 references
and reported green while never seeing the two repos the defect lived in. It now
*refuses a verdict* when a recorded repo is unscannable, and `quality-static`
checks out submodules. Measured before the fix:
`40 secret reference(s) across 1 repo(s) are all reachable`, exit 0.

### New gates

- `check:ci-timeout-headroom` — every baselined job keeps ≥1.5x headroom under
  its `timeout-minutes`. Offline; network only in `--refresh`. Found that
  `Stage Artifacts`, the R2 upload on the release path, had **no ceiling at all**
  in either the caller or the reusable workflow.
- `check:ci-secret-reachability` — a workflow may not reference a secret its
  repository cannot read. Found that `Claude Review` had **never once succeeded**
  in `account` or `renet` (org secret scoped to `console` alone; see
  rediacc/account#76, waivers expire 2026-09-07), and that
  `secrets.AUTOPILOT_APP_ID` was a **namespace mismatch** — it is an org
  *variable*, so `client-id` resolved empty at three app-token call sites.

Both follow the same pattern as the older gates here: a committed baseline, a
`--refresh` that carries the only network access, a vacuity floor, and controls
that fire in both directions before any real read.

## A required check that could not pass, and a guard that could not fire (2026-08-07)

Two defects of the same shape, found hours apart, both in the machinery that
decides whether a PR may merge. Neither was a missed bug: both were checks
producing confident WRONG answers, which is more expensive, because the work they
create looks legitimate.

### 1. The review deadlock: two numerators, one cap

PR #553 reached green CI, ready, zero unresolved threads -- and became
PERMANENTLY UNMERGEABLE. Its required `Review Complete` was red and no action
could clear it.

`review-status.sh` has an explicit DEADLOCK GUARD for exactly that state: once
the review cap is reached the reviewed-SHA marker can never advance, so failing
would strand the PR "through no fault of its author". It passes loudly instead.

It never fired, because the two scripts measured different numerators against the
same denominator:

| script | numerator | #553 |
|---|---|---|
| `claude-review-gate.sh:449` | posted reports + spent attempts | **3/3** -> refuses to review |
| `review-status.sh:296` | posted reports only | **0/3** -> guard mute |

The gate stopped reviewing because the budget was gone; review-status could not
see the cap as reached and demanded a review that could never happen.

`.ci/scripts/lib/common.sh` exists precisely to stop this drift, and it
half-worked: it shared `review_cap_for()` (the DENOMINATOR) while the NUMERATOR
stayed split across two files, one of which did not know spent attempts existed.
**Sharing a file is not sharing the computation.** Both callers now use
`review_spend_total()` from that file; the gate's local counter is deleted rather
than left as a second copy.

**This fix could not be validated on the PR that made it.** `review-status.yml`
checks out `.ci/scripts` from the DEFAULT BRANCH -- deliberately, so a PR cannot
edit the logic judging it -- so the fix is inert until it is on `main`. Breaking
the circularity needed a separate tiny branch (0807-3, PR #554). Any future
session touching review-cap logic must expect the same: **your fix will not act
on your own PR.**

### 2. The turn budget, and why a green retry proves nothing

The same PR starved its entire review budget first: three passes, all
`error_max_turns`, zero findings posted. Sonnet twice, then opus-5 -- the model
was never the constraint.

Measured, same day, same reviewer, both in the old 50-turn tier:

| PR | diff | outcome |
|---|---|---|
| #552 | 2270 lines / 39 files | completed, full report (22.0 turns/KLOC) |
| #553 | 2802 lines / 36 files | starved, nothing posted (17.8 turns/KLOC) |

File count does not discriminate (39 passed where 36 failed); lines do. The
50-turn tier stretched to 5000 lines, so a 4999-line diff got 10 turns/KLOC.

The first fix -- moving the rung from 5000 to 2000 -- was WRONG, and the new
`check-review-turn-capacity.sh` gate caught it immediately: it left a
2000..29999 tier whose top edge got 2.6 turns/KLOC, the same hole fifteen times
wider. **Rungs starve at their top by construction.** The budget is now
continuous (25 turns/KLOC, floor 50, ceiling 140).

### The generalisable trap

A starved review is the EXPENSIVE outcome, not the cheap one: it burns its whole
budget, posts nothing, and still spends an attempt against a finite per-PR cap.
Three attempts at a budget that cannot finish leaves a PR unreviewable forever.
`REVIEW_CAP_TIERS` and the turn budget are still tuned independently -- nothing
forbids granting N attempts at a budget guaranteed to starve. That coupling is
the next thing worth gating.

### The gates that close this, and where they live

**NOT on this branch.** `check:ci-review-turn-capacity`,
`check:ci-review-cap-coherence` and `check:ci-gate-reachability-coverage` were
built on `0807-2` and land with it. Naming them here as shipped would be exactly
the drift this directory exists to prevent -- a reader grepping for them on this
branch finds nothing.

What THIS branch carries is the numerator fix alone, plus the gate-test case that
reproduces the #553 shape,
`test-review-status.sh::test_cap_reached_by_spent_attempts_alone`. That case is
mutation-proven against the scripts as they exist on main, where it reports the
live incident verbatim: `expected 'success', got 'failure'`. Its sibling case --
which reaches the cap with three POSTED reports -- passes under either numerator,
which is why 46 existing assertions never caught this.

When 0807-2 lands, those three gates cover the turn budget (monotonic, total,
density-where-achievable, ceiling-beyond), the cap coherence (one numerator, one
denominator, and the deadlock guard reachable AT the cap), and the Stop hook's own
reachability probe -- which returned False for all 191 registered gates because it
walked `npm run` edges from `ci`, and `ci` is `tsx scripts/ci-runner/run.ts` with
zero such edges.

## The release path's own version holes, closed (2026-08-07, branch 0807-2)

Companion to *"The version-check family that could not fail"* (branch 0807-1),
which records the incident -- **v1.2.16 published under the tag v1.2.17** -- and
the shape it kept taking. This section records what was actually closed on the
**release path**, because that half landed on a different branch and a reader of
one section will otherwise think the other half does not exist.

The operator's rule, verbatim, governs every fix below:
**always have a version; skip or fail; never a silent pass.**

### Seven of eleven install methods never compared a version

`apt`, `dnf`, `apk`, `pacman`, `npm`, `linuxbrew` and `quick` each ended their
container heredoc with a bare `${PKG_BINARY_NAME} --version` whose output was
never captured. `$VERSION` did not appear once inside those functions, even
though `ci.yml` and `ct-install-methods.yml` pass `--version` into every one of
them. The assertion was *"the binary exits 0"*. **The mislabelled artifact would
have passed all seven.**

The fix is a **container-side version fence**, not a host-side grep, and that
distinction is the entire point: `apt-get`, `npm` and `brew` each PRINT the
expected version while installing, so matching the transcript would accept

```
Setting up rediacc-cli (1.2.17) ...      <- from the installer's own chatter
  version reported by the binary: 1.2.16 <- what the artifact actually is
```

That is a check that cannot fail, rebuilt in a new place. The container now
fences its own output between markers and the host compares only what is inside;
the gate asserts **both** directions -- the fenced check refuses the noise case,
the unfenced grep accepts it.

Three smaller vacuity floors in the same script:

- **A zero-total run exited 0.** `*) shift ;;` swallowed a typo'd `--method`,
  nothing matched, and "success" meant *nothing failed* rather than *something
  was verified*. Arguments are now validated with the valid list named, and a
  zero-total run is fatal. **All-skipped stays acceptable** -- a skip prints its
  reason and is counted, which is the visible half of skip-or-fail; a zero-total
  says nothing at all.
- **`--dry-run` counted as PASS.** It installs nothing and compares no version,
  so `3 passed, 0 failed` was indistinguishable from three real verifications.
  It is a SKIP now.
- **`test_update_check`** printed the manifest version and never compared it, and
  its structural guard passed on `"binaries": {}` because an empty object is
  truthy in `jq`.

### Six ways a wrong version could still ship

| # | Hole | Why it never fired |
|---|---|---|
| 1 | **Retry mode published with the assertion off** | `cd-v2.yml` excluded `retry_mode` from *Assert artifact version matches promotion target*, on a comment claiming retry's artifacts "already match by definition". False: retry takes its **version** from `resolve-version.sh --current` and its **artifacts** from `resolve-ci-run.sh`, which picks the latest green CI on `main` with nothing tying it to the tag |
| 2 | **The build's own smoke test compared nothing** | `build-cli-executables.sh` read a version out of the freshly built binary, asserted only that it was non-empty and not `null`, and clobbered the variable holding what it had been *told* to build. It is the **only** point in the pipeline that reads a version out of real bytes, and it declined to compare |
| 3 | **The only `0.0.0-dev` guard had zero callers** | `inject-env.sh --strict` was referenced by a comment and by itself (see `01-verified-context.md` #534). An explicitly-empty `--version` fell through and picked up the **already published** current tag |
| 4 | **Attestation verification could not fail** | Every failure became a warning and the script had no failing exit path at all; its `find` over two absent directories exited 0 having verified **zero** artifacts |
| 5 | **A swallowed tag fetch could silently regress the version** | `2>/dev/null \|\| true` four lines before the version is computed: a failed fetch left stale tags and nothing downstream could tell |
| 6 | **An empty version collapsed the image closure key** | One shared key let an image built at an older version be promoted |

Hole 6 was judged **deliberately not a failure** -- that script legitimately runs
where no tag is reachable -- so the fallback is now *distinguishing*
(`untagged-<sha>`, with a warning) rather than fatal. Skip-or-fail does not mean
everything fails; it means nothing passes **silently**.

Hole 5's fetch now retries three times then hard-fails, with git's stderr
**redacted rather than suppressed**, because the fetch URL embeds a token. Zero
tags after a *successful* fetch is its own explicit failure.

### `compareVersions` called malformed versions equal

`packages/shared/src/utils/version.ts` returned `0` -- meaning **equal** -- for
`1.2.x` against `1.2.16`, and for `x.y.z` against anything.

Worth pinning precisely, because the obvious guess is wrong: **it is not the
empty-string case.** `Number("")` is `0`, so `compareVersions("1.2.16", "")`
correctly returns `1`. The silent-equal case is **non-numeric segments** ->
`NaN` -> both `>` and `<` comparisons false -> the loop falls through and reports
equality. It throws now, and exports `isValidVersion` so callers can branch
instead of catching.

### Eleven gate tests, registered

Eleven new control gates (six for the release-version holes, four for the
install-method rebuild, one for `verify_version`) are registered in
`scripts/ci-runner/manifest.ts` as `qualityGateTest: true` entries pinned to
`ci-quality.yml` -> `quality-security` -> *Quality-gate unit tests*. Without that
registration `check-ci-parity.ts` fails, and -- more to the point -- a gate that
`npm run ci` does not run is a gate nobody will notice going stale.

**Every one was mutation-proven**: a planted defect watched to make the gate
**pass**, then the fix watched to make it **fail**. The release-version set
replays the incident's own `1.2.17`-versus-`1.2.16` through the extracted
comparison block; the install-method set includes a copy-mutation reproducing the
exact zero-total signature, plus a real-docker end-to-end run against alpine.
37 assertions across the six release-version gates.

The same commit deleted a comment on `assert-artifact-version.sh` that still said
its `exit 0` branches should *"be hardened to a hard fail"* -- they already had
been, hours earlier, and a stale TODO pointing at finished work reads as an
invitation to undo it.

### Two non-version fixes that rode along

- **Two pipelines would abort silently under `pipefail`.** `grep` exits 1 when a
  field is absent, and under `set -eo pipefail` that killed the script *before*
  the emptiness check that reports **which** field was missing. Both now end
  `|| true` with a comment naming the intended failure path, so the explicit
  `log_fail` is reachable. This is the pattern's sharp edge: `pipefail` turns a
  deliberate empty result into an abort, and the abort is quieter than the error
  it pre-empted.
- **`wrangler d1 export` had no retry.** It stages through R2, and on 2026-08-07
  two *different* R2 operations failed on two *different* databases on
  consecutive attempts of the same run (`Could not create a presigned URL to R2`
  on `account-db-us`; `completeMultipartUpload ... does not exist (10024)` on
  `account-db-eu`). One unlucky sample failed the whole migration job and took
  **15 sibling jobs** with it via fail-fast. Now 3 attempts / 10s. A database
  that genuinely cannot be exported still fails, three times over, and the final
  message carries the attempt count and wrangler's own output.

  **Both of those R2 failures were one platform incident**, confirmed after the
  fact: `cloudflarestatus.com` reported a Minor Service Outage opened
  `16:04:27Z`, and every red in that window sat on a Cloudflare surface (R2
  twice, a Workers preview 400, a quick-tunnel origin route). The retry is still
  right -- a single unretried sample of an eventually-consistent service is a
  defect regardless of what made it flake -- but the **diagnosis should have
  started at the platform**, not at the fourth job. When several unrelated jobs
  redden inside one window, check the provider's status page before reading a
  single log.

## Four gates that a human reviewer had to find first (2026-08-08)

The version-hole wave shipped, and the review pipeline itself turned out to hold
the same defect class the wave was built to remove: checks that could not fail,
and one that could not pass. Recorded because every one of them was invisible to
the gates already in place, and three were caught by a REVIEWER rather than by CI.

### The review cap deadlocked a PR that was perfectly fine

`review-status.sh` carries an explicit DEADLOCK GUARD: when the review cap is
reached the reviewed-SHA marker can never advance, so failing would strand the PR
"through no fault of its author". It passes loudly instead.

It never fired, because the two scripts measured different numerators against the
same denominator:

| script | numerator | PR #553 read |
|---|---|---|
| `claude-review-gate.sh` | posted reports + spent attempts | **3/3** -> refuses to review |
| `review-status.sh` | posted reports only | **0/3** -> guard mute |

`lib/common.sh` exists to stop exactly this drift and half-worked: it shared the
DENOMINATOR while the NUMERATOR stayed split across two files, one of which did
not know spent attempts existed. **Sharing a file is not sharing the
computation.** Both callers now use `review_spend_total()`.

**The fix could not be validated on the PR that made it.** `review-status.yml`
checks out `.ci/scripts` from the DEFAULT BRANCH -- deliberately, so a PR cannot
edit the logic judging it -- so it was inert until it reached `main`. Breaking the
circularity needed a separate tiny branch. Anyone touching review-cap logic must
expect the same: **your fix will not act on your own PR.**

### The turn budget starved a review three times, and the model was not the cause

Same day, same reviewer, both in the old 50-turn tier: #552 at 2270 lines
completed; #553 at 2802 lines produced `error_max_turns` and posted nothing.
Sonnet twice, then opus-5 -- **the model was never the constraint.**

The first fix was WRONG and the new capacity gate caught it on its first run:
moving the rung from 5000 to 2000 left a 2000..29999 tier whose TOP edge got 2.6
turns/KLOC, the same hole fifteen times wider. **Rungs starve at their top by
construction**, so the budget is now continuous (25 turns/KLOC, floor 50, ceiling
140).

A starved review is the EXPENSIVE outcome: it burns its whole budget, posts
nothing, and still spends an attempt against a finite per-PR cap.

### The Stop hook's reachability probe could not pass

`gate_reachable()` walked `npm run X` edges from the `ci` script -- but `ci` is
`tsx scripts/ci-runner/run.ts`, whose body has ZERO such edges, because the runner
schedules from `manifest.ts`. It returned False for **all 191 registered gates**,
including `check:ci-shell-commands` and `check:ci-dead-bash`.

The cost was not a missed defect but a MANUFACTURED one: it told two consecutive
sessions their correctly-wired gates were "defined but never run". **A probe that
cannot pass is the same class as a check that cannot fail, and more expensive --
it spends real work denying something true.**

### The edge smoke test could be failed by one unlucky sample

Release run 31234422166 deployed edge successfully and then failed
`edge.rediacc.com footer does not render v1.2.19` -- while edge was ALREADY
serving v1.2.19. One `curl` against an eventually-consistent CDN, no retry; the
script had TWELVE such reads. The cascade skipped `Tag & GitHub Release`, so a
good release shipped with no tag and no GitHub Release.

**The reasoning that nearly left this ungated is worth more than the fix.**
`verify-edge-endpoints.sh` runs only from `cd-v2.yml` (dispatch-only, main-only),
so the DEPLOY genuinely cannot be exercised on a PR -- and the first conclusion
was therefore "main-only, not PR-testable". Wrong. The defect was never "edge
served the wrong version"; it was "the assertion samples once", which is a
property of a shell script and can be driven against a fake predicate on any PR.

> Before calling something un-testable on a PR, separate the ENVIRONMENT you
> cannot reproduce from the LOGIC you can.

### New gates from this wave

| key | guards |
|---|---|
| `check:ci-review-turn-capacity` | monotonic, total, density-where-achievable, ceiling-beyond, plus the measured regression point |
| `check:ci-review-cap-coherence` | one numerator, one denominator, and the deadlock guard REACHABLE at the cap |
| `check:ci-gate-reachability-coverage` | the Stop hook's own probe agrees with how gates are registered |
| `gate-test:edge-verify-retries` | stale-then-correct ACCEPTED, never-correct still REJECTED |
| `check:ci-gate-id-convention` | 57 gate scripts share a registration convention nothing enforced |

Every one is control-first: a planted defect watched to make it PASS before the
fix makes it FAIL. Two of them found real defects in the very change that
introduced them -- the capacity gate rejected its author's first tier fix, and CI
caught a `pipefail` silent-abort inside the gate written to catch silent aborts.

### The trap this wave paid for most

**Resolving inline review threads is not answering the review.** A top-level
summary has NO thread, so nothing about resolving threads addresses it, and
`review-findings: []` does not exempt it. Missed four times here, costing three
force-cancelled runs and fourteen killed E2E jobs. The fix is not another note: it
is treating resolve-threads and answer-summary as ONE indivisible step.

## The 0808-2 big-bang: labels that do something, and E2E that skips honestly

Two features landed together on #557 with the pointer bump and the waiter hook,
implemented by two parallel agents with disjoint file ownership; the shared
files (this one and manifest.ts) were integrated by the orchestrating session.

### Auto-labels from the existing AI review pass

The bump labels were dead. `detect-bump-type.sh` resolved the merged PR by
grepping `(#N)` out of the HEAD commit title, which only a squash merge
produces; this repo went rebase-merge on 2026-07-30 and 0 of the next 60
commits on main carried that shape. Every release since took the "no PR
numbers found" fallback and shipped patch, whatever anyone labelled. Nothing
said so, because patch is also the right answer most of the time. It now
resolves `<latest tag>..HEAD` through `commits/<sha>/pulls`, which follows
rebased commits, and takes the highest-priority label across the union.

The labels themselves ride the review that already runs. A second fenced block,
`json:pr-labels`, is appended to the same report the model already writes, so
the carrier costs zero extra invocations and zero extra turns. A mechanical
floor read off the changed paths lands even when the review starved and posted
nothing. A hard whitelist stands between the model and the API, because adding
an unknown label CREATES it and would fail the inventory gate repo-wide; a
`major` verdict is recommendation-only and `bump-major` is absent from that
whitelist by construction.

Reconciliation is ledger-based, never a blind sync: one `<!-- claude-labels: -->`
comment records what the applier applied, and only names in that record are ever
removed, so a hand-applied `full-ci` or `rollback` survives any verdict.

Inert until main. Review scripts execute from console@main by design, so the arm
does not exist for the PR that introduces it; the workflow step carries a
`grep -q -- '--apply-labels'` guard that makes it a logged no-op meanwhile. The
two gate tests are the whole pre-merge evidence, which is why they are
control-first and mutation-proven.

### Cross-PR greenlight: the expensive keys are enrolled

Enrollment is a CLOSURES entry and nothing else. `apply_greenlight` derives its
key list from `Object.keys(CLOSURES)`, every key already has a fail-open
`!= 'false'` consumer, and all 18 are in `JOB_SURFACES`, so no workflow changed.
The table went from 2 keys to 18, 409 declared entries.

The eight VM/E2E legs share ONE closure. They check out the same four gitlinks,
run the same setup-workspace plus build-cli plus build-renet chain, and differ
only in env and playwright config that live inside ct-tests.yml and
packages/e2e-tests, both of which are in the closure. Sharing it also makes the
walk cheap: one cached directory listing answers all eight keys.

The walk budget went 60 to 90 seconds, inside `bounded`'s 120s ceiling. A live
18-key walk over 24 candidates measured 16.6s, so the headroom is real.

package.json and package-lock.json are carried WHOLE by every closure that runs
npm. The consequence is stated rather than hidden: a PR adding an npm script
alias greenlights nothing npm-shaped. A normalized subset hash would need
candidate-side content fetches plus a scripts-graph closure, and a wrong
normalization is a silent wrong skip. The trail data to revisit this is free.

Wrong skips have two layers of defense. `gate-test:greenlight` proves the engine
obeys its rules and that every declared path still exists in HEAD.
`gate-test:greenlight-closure-trace` derives, per key, the paths its defining
workflow job block references and asserts the closure covers each one, so a
workflow that gains a step turns a silent wrong skip into a red gate. It carries
its own control: it re-runs the identical checker over a mutated table with one
required entry deleted and asserts red. The trace gate paid for itself before it
ever ran in CI: on its first run against the real table it found the live
`renet` closure missing `.github/actions/app-token`, an edit to which would not
have withdrawn a renet greenlight.

### Quality-gate unit tests: parallelized inside the step (W/S/T)

The battery ran its 87 tests serially behind one `run-all.sh` loop, costing about
18 minutes of the Security job's 20-minute budget. The step was one slow test
away from a timeout, not one slow test away from a slow run.

A flat worker pool is unsafe here, and the reason is specific. Two tests write
into the real tree because the code they exercise hardcodes it: test-gate-paths-exist.sh
plants fixtures in .ci/scripts, test-gate-anti-vacuity.sh plants one in scripts/.
About nineteen others recursively enumerate those same directories. A file that
appears or vanishes mid-enumeration is a hard error under set -euo pipefail, which
passes on the next serial re-run. That is the flake shape observed locally, and
lowering the worker count makes it rarer rather than absent.

So the runner schedules three sets instead of pooling flat. W is the two writers,
run as one serial chain from t=0. T is the 68 temp-isolated tests, filling the
remaining slots while W runs. S is the 19 real-tree readers, released only once the
W chain has published its done-marker. Workers never print; each writes a log and
atomically publishes an exit code, and main prints the blocks in ascending glob
order, so the transcript is the serial transcript.

Measured on the 20-core dev box over the whole battery: 956s serial versus 304s
parallel, 3.14x, identical failure sets and identical assertion totals (87 passed,
955 assertions, both). CI runs 4 workers rather than 8.

test-run-all-parallel.sh pins four properties, each with its own control: the pool
overlaps (with a jobs=1 run that must be slow, so the stopwatch can fail); jobs=1
and jobs=4 agree byte for byte; output blocks never interleave under --verbose;
and the W/S hold-back holds, proven by a sentinel writer plus a scanner that reds
on contact, with a flat-pool control that must collide. A missing result counts as
a failure, never a skip, so a scheduling bug shows up as red rather than as a
shorter green run.

The wave also fixed two strays it walked past: log_info and log_error were called
by test-shell-counter-increment.sh but never defined anywhere (silent only because
that file runs without -e; its finding report would have printed "command not
found" instead of the finding), and the Stop hook's task-queue blindness described
in the session records rode the same branch.

## Phase 2 of the post-merge wave: probe answers wired in (2026-08-08)

Phase 1 (read-only validation, this session, evidence on worklist tick
#9b7741bb) dispatched `Profiler Probe` run 31252148469 and a
schedule-equivalent Console CI run 31252149485, and settled every question
the 2026-08-05 wave had left open. Phase 2 then landed the consequences,
all uncommitted:

**The probe's two answers, and what each changed.** (1) A JS action's
`post:` hook FIRES when the action is invoked through a composite wrapper,
on both ubuntu-slim and ubuntu-latest. So the profiler rollout is ONE step
in `.github/actions/setup-workspace` (:72) plus that composite becoming the
coverage gate's built-in wrapper default, not 26 per-job edits: coverage
went 1/97 -> 26/97 in one change and 25 ledger lines burned (96 -> 71).
The `runner-label` input is deliberately NOT threaded through the wrapper:
on a cgroup tier the enforced quota substitutes for the label, and the
label's only job (arming HOST_LEAK) does not survive a composite that
cannot know `runs-on`. (2) GitHub's real slim container is cgroup V1 -- the
local docker proof was v2, so the sampler's v1 fallback path is the one
production exercises, and the probe watched it resolve cpu+memory
correctly. Host views are container-scoped on slim (nproc=1,
MemTotal~4.8GiB), awk AND node exist there, and a sample costs ~742us
against the ~1ms estimate.

**The nightly's last red was OUR TEST, not the release pipeline -- and the
first fix for it was wrong, caught by a gate within the hour.** Both the
nightly and the fresh dispatch failed only Validate Install Methods, always
as `curl: (22) ... 404`: with the nightly's deliberately EMPTY channel the
apt and quick-install tests fetched root urls (/apt/gpg.key,
/cli/install.sh) that the <dir>/<channel>/ layout has never published,
while promote-r2-to-stable.sh had published every stable file (verified
200 live across apt/rpm/cli/apk/archlinux). Fix #1 -- default REPO_CHANNEL
to "stable" -- made the urls resolve and BROKE the design:
test-installmethods-args.sh failed on "an all-skipped run is a success",
because test_binary_download:462 already documents why empty must stay
empty (a nightly downloading stable turns MAIN's nightly red when a past
RELEASE breaks; the two signals must not be conflated). The real defect
was that six package-family tests (apt, dnf, apk, pacman, npm, quick)
LACKED the channel-less `return 77` skip guard their siblings
(binary/update/verify/promotion) have carried all along. Fix #2, the one
that stands: the same guard on all six, placed after each DRY_RUN block so
dry-run output is unchanged. A channel-less apt run now reports "0 passed,
0 failed, 3 skipped" with the reason named. Two lessons, both old ones: a
404 names the fetcher's url, not the publisher's tree; and a fix that
makes a red go green is not right until the gates that encode the DESIGN
agree -- the args gate paid for itself completely here.

**The 2026-08-05 cold case is closed.** test-gate-paths-exist.sh planted
FIXED-filename fixtures in tracked .ci/scripts, so two concurrent battery
runs deleted each other's fixtures -- exactly the "control came back empty
only during a full run" signature chased across a four-shape bisect at the
time. The fixtures now carry the pid (FIXTURE_PID_SUFFIX), the scan scopes
itself with a cross-pid glob, and the fix is proven by the failing scenario
itself: two fully concurrent instances, both 7/7 green, re-run
independently by the session lead. The SCAN_FLOOR guard stays as the
loudness backstop. Credit: val-local's read-only sweep spotted the fixed
filenames.

**Autopilot loose ends.** AUTOPILOT_MODEL is renamed AUTOPILOT_ALLOW_MODEL
(the S4 boolean was named like a model VALUE; `AUTOPILOT_MODEL=claude-opus-5`
read as false and silently disarmed the model job -- no error anywhere).
The old name survives only in 03-v2-autonomy.md's dated rename note. The
identity comment at autopilot.yml:52-58 now states the split precisely:
AUTOPILOT_APP_ID is an org VARIABLE (gh secret set on it appears to succeed
while vars. stays empty -- the exact defect the operator fixed once
already); only AUTOPILOT_PRIVATE_KEY and CLAUDE_CODE_OAUTH_TOKEN are
secrets. FOUND, REPORTED, NOT FIXED: the sweeper enumerates only
LABEL-armed PRs (gh pr list --label), so a campaign-armed PR that misses a
workflow_run event stalls silently; reaching those means scanning state
comments for `campaign: open` -- an S6-era decision, its comment corrected
meanwhile.

**Second live data point for external_quality.** The dispatch ran with
EXTERNAL_QUALITY_MODE: soft in both wrapped Quality/Go steps and all ten
Quality lanes green, matching the nightly. Still true and still stated
plainly: no upstream drift existed on either data point, so the downgrade
branch (warn + exit 0 on a REAL external failure) remains test-proven only
until the world moves.

## First fleet-wide live profiler run, and the review-actor facts around it (2026-08-09)

PR #560 (branch 0808-5) carried the wiring into a real `pull_request` run,
31279251398, and the profiler's first fleet-wide outing on genuine jobs:

- All 26 setup-workspace jobs ran the profiler main ("sampling every 10s
  into $RUNNER_TEMP/profiler-<job>-<pid>.tsv") and every post hook concluded
  success (~148ms each on warm jobs).
- **Panels are proven by construction, not by page-scrape.** The run page's
  server-rendered HTML shows annotations but lazy-loads job summaries, so an
  unauthenticated fetch "sees" no panels. The chain that actually proves
  them: panel.sh exits non-zero on any of its own failures and index.js
  refuses to swallow that (`process.exitCode = res.status`); all 26 posts
  were green; and a local drive of panel.sh with exit 0 always appends a
  `## Runner Profile:` section to GITHUB_STEP_SUMMARY, even in the
  degenerate no-samples case. Eyeball the run page for the rendered panels.
- **The sample-floor guard fired in production on its first day**: one 41s
  job got 3 samples against the 4 expected and the run carries the exact
  annotation designed for it ("the sampler was starved or died early") —
  a warning, not a hard fail, because strict mode is off fleet-wide.
- The same run's deprecation banner surfaced that the action declared
  `node20` while GitHub already force-runs it on Node 24; it now declares
  `node24` (the repo's only JS action, so the class is one file).

Two external-links facts from the same wave, for the record: the hard-mode
PR gate caught gnupg.org answering 000 (down from two networks; the
docs.appimage.org outage from earlier the same day had meanwhile recovered)
— external flap, absorbed with the designed `no-external-quality` label. A
label applied mid-PR needs a real push to take effect: `external_quality`
is computed from the EVENT payload's label snapshot (ci.yml:129) and
`pull_request` triggers only on [opened, synchronize], so a bare rerun
re-reads the unlabeled payload.

## Handoff checklist gate: /handoff <-> Stop hook (2026-08-09)

`/handoff` produced prose and nothing else. Its scope waves lived in a README
paragraph, its deliverables lived in the command's own step list, and the only
thing that ever asked the consuming session to seed the worklist was an
instruction sentence inside PROMPT.md. The Stop hook, 13k lines across 13
modules, had zero grep hits for "handoff": nothing verified that a producing
session actually wrote every deliverable, and nothing verified that the
consuming session claimed or finished a single wave. An ignored PROMPT.md, or
one compacted out of context, silently dropped program work with no red
anywhere. `docs/<slug>/CHECKLIST.md` is now the artifact both sides are held
to, and the hook reads it.

The grammar, deliberately small enough to write from memory:

```
# Handoff checklist: <slug>
Status: producing            <- first 10 lines; producing|executing|done|superseded
Owner: 99ccf057              <- 8-char session prefix, required while producing

## Deliverables
- [ ] d1 file:docs/<slug>/README.md
- [ ] d2 file:docs/<slug>/PROMPT.md
- [ ] d3 file:~/.claude/projects/-home-muhammed-monorepo-console/programs/<slug>/MANIFEST.md

## Waves
- [ ] w1 Wave A: <one-line title>
```

Ids are section-scoped (`d` under Deliverables, `w` under Waves), only ` ` and
`x` are legal box states, and every deliverable carries a `file:` token.
Deliverables are file-verified, period: the path must exist and be non-empty,
`~` expands, relative paths resolve against the repo root, and the tick is
bookkeeping while the file is the truth. A ticked-but-missing deliverable is
called out loudly rather than believed. Waves are tick-on-trust with store
linkage: a wave is settled by `[x]` or covered by any worklist store item whose
text contains the literal token `cl:<slug>/<wN>`, seeded with
`worklist.py --add <me> 'cl:<slug>/<wN> <title>'`. Evidence discipline rides
the existing `--tick` gate, so no new evidence machinery was invented.

Four check keys. `cl-shape` is ALWAYS-tier when the parser itself crashed (the
V_CI_UNREADABLE precedent, fail closed rather than unknown-and-pass) and
rotated for ordinary grammar violations: bad Status, missing Owner while
producing, malformed item line, duplicate id, deliverable without a `file:`.
`cl-producing` is rotated and blocks the OWNER only, on unmet deliverables or,
once they all verify, on the missing flip. `cl-flip` is rotated and fires when
Status is executing or done but a deliverable file is missing or empty, or done
carries unticked waves. `cl-waves` is rotated, one body per slug, and blocks
ANY stopping session on an uncovered `[ ]` wave, on a done-but-unticked box,
and on an all-settled checklist that has not been set to `Status: done`.

Blocking everyone on `cl-waves` is the deliberate part. An uncovered wave is
unclaimed work, exactly the semantics an untagged worklist item already has:
the moment any session adds the `cl:` item the wave has an owner and stops
blocking everybody else. Worst case is one redundant simultaneous block, and it
self-resolves on the next stop because every violation has a single-turn solo
exit (add the item, tick the box, or flip the status). A foreign producing
checklist never blocks: it emits the advisory `cl-foreign`, change-latched, and
after the owner's transcript has been idle 24h the advisory gains an adoption
hint (edit `Owner:`, or supersede the program).

Cost is bounded on both paths. The full Stop battery reads checklists because
that is the enforcement point: zero checklists costs one glob, live ones get a
header read, and only producing/executing files are parsed in full (typically
0-2 small files). The poll fast path stays read-free by contract: `clsig` is a
sha1 over sorted `(relpath, mtime_ns, size)`, stat-only so a chmod-000
checklist cannot make it raise, and both `clsig` and `cl_live` are banked in
the pollbase. A poll forfeits the fast path when the signature moved, when
banked `cl_live > 0`, or when the keys are absent from an older baseline. In
plain terms: a live checklist means polls pay the battery, and done or
superseded checklists cost polls nothing. SessionStart and PostCompact inject a
LIVE HANDOFF CHECKLISTS listing, one line per live checklist with status,
owner, and the verified/settled counts.

Lifecycle is `producing` -> `executing` -> `done` or `superseded`. The owner
cannot stop while producing until every file verifies and the status is
flipped; `done` is gated on all-verified plus all-ticked, so it cannot be used
as an escape; `superseded` is the terminal exit for an abandoned program. An
update-mode `/handoff` re-verifies every `file:`, appends new waves with fresh
monotonic ids, never renumbers or un-ticks, and flips `done` back to
`executing` when it adds waves. The hook never writes the checklist, and the md
file is the single source of truth, with no checklist events in the JSONL store
to reconcile against.

Two accepted residuals, stated rather than solved. A session that skips writing
a checklist at all is invisible to the hook; the mitigation is social, making
the checklist the FIRST file write plus a named line in the command's Report
and Constraints sections. And the 45/90/120 liveness ladder does not apply to
checklist items: once a wave is claimed it rides the worklist store item, whose
existing ladder and lease machinery already cover it, so nothing new ages
checklist rows.

Findings are keyed PER CHECKLIST, `<check-class>:<slug>`, built by
`wl_checklist._ckey`. This is the design rather than a detail because two
things downstream read the key as an identity and neither degrades gracefully
when it is shared: the focused block's rotation ties-breaks on
`order = {v[0]: i for ...}`, a dict comp in which duplicate keys collapse, so
two violations under one key get identical sort tuples and `min` returns the
first one on every stop; and `outq_add` finds a non-sticky entry by key alone,
so a second advisory's body overwrites the first's rather than queueing beside
it. A shared key therefore starved the second concurrent handoff permanently,
not for a stop or two, leaving it visible only inside the "N more outstanding"
count. Scoping costs nothing: the rotation already prunes keys that stop being
outstanding, so a settled checklist's key leaves `served` on the next stop. The
prefixes are preserved verbatim (`cl-shape`, `cl-flip`, `cl-producing`,
`cl-waves`, `cl-foreign`) so a grep on the check class still matches. One key
stays unscoped, the glob-level fail-closed backstop in `checklist_findings`:
the glob itself failed, so no slug exists, and that path returns immediately,
which means at most one such finding can exist per stop. The per-FILE
fail-closed wrapper beside it is scoped, reading its slug off the path rather
than out of the parse that just threw.

Drift under a foreign owner gets its OWN message, `N_CL_FOREIGN_DRIFT`, and
does not reuse `V_CL_FLIP`. Both statuses that can drift (`done` and
`executing`) used to build one body and route it either to a blocking violation
or to the `cl-foreign` advisory, which meant a session that does not own the
handoff was handed the owner's imperative, ending "in this turn". Acting on it
means editing another session's `Owner:`/`Status:` header or its files; a
peer's shared `STATE.md` was destroyed here by a session obeying an instruction
addressed to whoever happened to read it. The advisory now states the same
facts (checklist, status, owner, the same drift rows), says the repair belongs
to the owning session, warns that editing it from here would overwrite live
work, and closes with `Reported, never blocked on.` matching `N_CL_FOREIGN`.
`V_CL_FLIP` keeps its imperative unchanged, because on that path the reader is
the owner.

Both were found by the automated review on PR #563, and neither is an accepted
residual: they are fixed, with the per-slug keying making the "one body per
slug" claim above true rather than aspirational.

Enforced in `.claude/hooks/stop/wl_checklist.py` (parse, verify, sig, findings)
wired into `run_stop`, `poll_fast_path`, `bank_pollbase`, `handle_session_start`
and `handle_post_compact` in `wl_checks.py`, with the nine message constants in
`worklist_messages.py` (V_CL_SHAPE, V_CL_UNREADABLE, V_CL_PRODUCING,
V_CL_PRODUCING_DONE, V_CL_FLIP, V_CL_WAVES, N_CL_FOREIGN, N_CL_FOREIGN_DRIFT,
CTX_CHECKLISTS; the wave-token format constant is spelled CL_LINK_FMT because
ruff S105 fires on names containing TOKEN). Suite coverage lands in
`.claude/hooks/stop/test-worklist-v5.sh` cases 193 onward, house style
throughout: every blocking case paired with a clean-fixture control, including
a zero-checklist control that must produce no checklist output at all and a
stat-only unit call against an unreadable file. Cases 204-206 cover the two
review findings, each verified to FAIL against the unfixed code first: two
uncovered waves served across two stops, two foreign advisories surviving one
drain, and the foreign drift wording paired with the same fixture under its
owner. Case 205 keeps a separate fixture per leg deliberately, because draining
an advisory latches it in the queue's `shown` ledger and a second checklist
planted beside an already-shown one is suppressed by the refresh window, which
looks exactly like the overwrite bug.

## STATE.md session isolation, and traps as instruments (2026-08-09/10)

Two programs, one root cause: this repo runs several sessions in ONE shared
checkout, and both the compact-recovery document and the trap corpus were built
as if a branch had one session.

### STATE.md is one owned section per session (PR #565)

`.agent/<branch>/STATE.md` is keyed per BRANCH. The Stop hook told a session the
document was stale, it obeyed, and it destroyed a peer's entire state section:
a live canary campaign's notes, recovered only because the single-slot `.prev`
backup was read before the next write clobbered that too. It was then hand-merged
three more times in one afternoon, which is the workaround that proved the defect.

The staleness gate DROVE the collision. It nags every session on the branch, on a
15-minute limit, to rewrite one shared file, so more sessions meant more
overwrites. The format was already half-present (`AGENT_STATE_SESSION_RE`,
`agent_state_blocks`) and only scaled a character cap by heading count: headings
existed, ownership and merge did not, which is exactly why the tooling could not
see the collision.

Now `--state` takes one session's body and merges it under a lock, leaving every
other section byte-identical and writing the heading itself. Staleness is judged
per section, so one session's write cannot silence another's obligation, nor can
a stale section hide behind a fresh peer. Dead sections are archived before being
dropped, reusing `owner_age_hours` rather than inventing a second liveness notion.
A legacy single-section document is adopted; a malformed one is never silently
replaced.

**The doors are shut mechanically, which is the whole point.** A prose rule
protects only a session that reads it, so the pre-edit guard DENIES a whole-file
`Write` to STATE.md and `--state` REFUSES a body carrying a `## SESSION` heading.
Both messages name the incident and print the correct command.

Two defects only the live document exposed, no fixture would have: a peer heading
stamped 71 minutes in the FUTURE (local time written with `Z`), which makes a
section permanently fresh and is strictly worse than no stamp, now clamped to a
300s skew; and the confirmation line reporting the writer's OWN section's old age
after a fresh write, because the replace branch never updated `ts`. The document
was always right and only the tool's report about itself lied.

### Traps become instruments (PRs #566, #567)

Operator ruling: "reading the trap file could be skipped with an agent." A trap in
markdown protects only a session that reads it, remembers it, and applies it at
the right second. This repo had already proved that in its own record:
`REPORT-licensing-bigbang-2026-08-04.md:234` is titled "WHY KNOWING ABOUT IT DOES
NOT PREVENT IT" and reports eight instances in one night, three by the author who
had just written the entry. `pr-babysit-0804-1.md:114` adds the design principle:
"not one was caught by its author re-reading it. Each was caught by a DIFFERENT
instrument."

Plan at `docs/agent/main/PLAN-trap-enforcement.md`, which absorbs and supersedes
`PLAN-unify-trap-corpus.md`. Instruments are matched to failure SHAPE, not topic:
forbidden action and guaranteed-failing action (PreToolUse block), misread outcome
(PostToolUse injection on `tool_response`), unproven claim (control-first gate).
Of 23 traps roughly 14 are mechanizable now and about 2.5 are judgment-only, and
the judgment-only ones sit at the top of the cost curve.

Landed: `block-blanket-git-add.sh`, and `trapguard/dispatch.py` carrying
`cancelled-run-not-passed` and `phantom-deletion-diff`.

**`tool_response` was probed before anything depended on it**, because the only
evidence it arrives was a docstring recording a captured payload, which is a
ruling from an artifact and itself a trap here. The probe recorded key names,
lengths and booleans only, never values, and corrected that docstring twice:
`isImage` and `noOutputExpected` are undocumented, and `agent_id`/`agent_type` are
ABSENT on main-loop calls, appearing only for subagents, so a rule keyed on them
would have silently never matched. The probe was retired in the same commit that
shipped the rules.

**Three defects in the new instruments, none found by re-reading them.** Review
found the guard bypassable by `git add -A > /dev/null`, `2>&1` and a bare `--`,
since redirection was not a terminator and git treats an empty pathspec list as no
restriction; a present-but-bypassable guard is worse than none because it
manufactures confidence. `phantom-deletion-diff` false-positived within the hour on
an ordinary deletions-only diff of a TRACKED file, so existence narrows and
tracked-ness decides. And three fixtures in a row tested the author's belief rather
than the behaviour, each time with the code right and the test wrong.

Both rules have fired in production on real commands, including on the exact
`git diff` output that misled the session that built them.
