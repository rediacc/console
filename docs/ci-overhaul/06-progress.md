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
