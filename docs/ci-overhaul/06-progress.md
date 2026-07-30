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

**S-2 is UNPROVEN and was wrongly marked done.** S-1 is genuinely resolved
(issue #539: the haiku label was a `jq 'keys | first'` alphabetical artifact, not
an ignored `--model` flag; fix live at `claude-review-gate.sh:280-300`). But no
live `--max-budget-usd 0.01` run is recorded anywhere: not in these docs, the
commit messages, PR #543, issue #539, or the worklist. **So no dollar stop is
known to exist**, `03-v2-autonomy.md:359-360` stands unchanged, and Wave C's cost
floor is structural instead: zero model cost on every no-go, dedup, superseded,
ready-flip, review-rerun and done path, plus per-round `--max-turns`, a 30-minute
job timeout, and the round cap. Run the spike during the S4 canary and record the
answer either way.

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

- README: "Nothing in it has been built" is stale. Wave A merged, Wave B built.
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
