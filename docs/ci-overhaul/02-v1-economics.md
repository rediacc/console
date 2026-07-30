# 02. v1, CI economics and correctness

Status: **RECOMMENDED design, not yet built.** Every claim traces to
[01-verified-context.md](01-verified-context.md); re-verify before building on it.

v1 is two merges. **PR-A must merge and be proven green before PR-B's cuts are honest**,
because PR-B's entire safety argument rests on the nightly being a real backstop.

---

## PR-A: resurrect the nightly (~400 lines)

Nothing else in this program is trustworthy until this lands. The nightly executes **main's**
code, so these fixes only take effect after merge. That is why this is its own PR.

### A1. Fix the three nightly failures

**Stage Artifacts (07-27).** `.ci/scripts/release/validate-stage-artifacts.sh:106-113`
asserts APT/RPM metadata unconditionally, but on `schedule` the channel is `''` and the
metadata-producing step self-gates on a non-empty channel.

*Preferred fix:* make metadata **generation** channel-independent (always generate locally,
gate only the R2 **upload** on `channel != ''`), so the nightly keeps validating the real
path rather than skipping it.
*Fallback if generation and upload are inseparable:* give the validator a `--channel` flag
and skip exactly those two assertions when empty, loudly, with a step-summary line saying so.

**Quality/Workflows (07-26, 07-24).** The actions-freshness gate is **right**. Do the
upgrade: `docker/login-action` is pinned at `abd2ef45` (v4.5.1); bump every site to current.
No blocklist entry. Verify with `scripts/check-actions.ts` locally, expecting zero pending.

**Quality/Security (07-25).** Run the audit gate and act on what it says. It may have
self-healed via the documented sub-24h auto-defer. If a real vulnerability persists, fix it
or add a `BLOCKER:` allowlist entry per `docs/agent/suppressions.md`. **The fix is running
the instrument, not guessing at it.**

### A2. Fix the reporting defect that hid all three

This is the more important half. A gate fails, the watchdog force-cancels the run, and the
conclusion becomes `cancelled` rather than `failure`.

- The watchdog must **never force-cancel a `schedule` run**. A failed nightly must read as
  failed.
- `watchdog-monitor.yml` gains: on `workflow_run` where `run.event == 'schedule'` and
  `conclusion != 'success'`, upsert a dated `nightly-red` issue (labels `bug` + `automated`,
  body listing the failed jobs) and auto-close it on the next green. `housekeeping.yml`
  already runs daily with an app token if you prefer that home.

A red nightly becomes impossible to ignore, with no new notification infrastructure.

### A3. #537, the watchdog classifier (same subsystem, same PR)

The classifier returned HTTP 402, so every failure was labelled `transient` with
**confidence 0** and retried blind. Doing this in a separate PR would mean touching the
watchdog twice and shipping a half-repaired judgment layer.

**RESOLVED 2026-07-30, and the root cause was not a broken subscription.** The 402 came from
using a partner-served model (`deepseek/deepseek-v4-pro`) through
`/ai/v1/chat/completions`, which bills from a prepaid AI Gateway balance that was never
funded, rather than from Workers Paid. Probed live on the same credentials: the partner route
returns 402 while `/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast` returns 200. The tier now
calls the native route and answers on real traffic.

Two follow-ups came out of watching it work, both recorded in `06-progress.md`: the tier-1
log label was hardcoded to the old model name and had to be derived from `AI_MODEL`, and the
classifier can answer with HIGH confidence on a SHALLOW reading, which is what prompted the
retry-policy change below.

1. **Capture the failed-step log before re-running.** Highest value-per-line item in the
   whole program. Attempt-1 logs become `BlobNotFound` once a retry starts, so a blind retry
   currently destroys the evidence needed to tell a real break from a flake.
2. **Conservative fallback when the classifier is unavailable:** retry only jobs on a
   hardcoded known-flaky allowlist (the VM-provisioning E2E and OPS legs); fail everything
   else immediately. Today's retry-everything is defensible only while somebody reads the
   log, and nobody does.
3. **Make the outage visible at PR level** with a `::warning::`, and make `confidence 0`
   distinguishable downstream from `confidence 0.8`.
4. **Do not chase the provider question first.** Once absence is safe and loud, the classifier
   is advisory. Decide on Workers AI credit separately.

### A4. The rehearsal path (this is what makes A provable)

`ci.yml` deliberately has no `workflow_dispatch` (comment at ci.yml:10 explains manual
triggers do not satisfy PR checks). Re-add it as an explicit **nightly rehearsal**, guarded
to `main`, with a comment superseding the old removal note (the old reason was about PR
retriggering and does not apply to a main-ref rehearsal).

It is **schedule-equivalent by construction**: `full_suite` is `event != 'push'`, true for
dispatch; and the channel step yields `''` for anything that is not push or pull_request
(ci.yml:116-120), the same path as schedule.

**Harden the guard while you are there.** `assert-channel-for-event.sh` ends in a `*)` arm
that logs a warning and accepts any channel for an unknown event. Adding `workflow_dispatch`
without an explicit arm would land the new path **unasserted**, and that guard exists
specifically to stop orphan R2 bytes. Add a `workflow_dispatch)` arm asserting an empty
channel.

### A5. Acceptance gate for unblocking PR-B

Both of these, not one:
1. one green rehearsal dispatch on `main`; **and**
2. the next real scheduled run green
   (`gh run list --workflow ci.yml --event schedule -L 1 --json conclusion` is `success`).

The rehearsal also becomes the permanent tool for proving any future nightly-affecting change
without waiting a day.

---

## PR-B: the engine, the cuts, and the defect sweep (~2.6 to 3.2K lines)

### B1. THE KEYSTONE: one baseline-and-net-delta engine

D9 and incremental scoping are **the same mechanism**. Do not build a fresh
`detect-changed-modules.sh` alongside a broken `detect-pointer-bump.sh`. Build **one engine
with two consumers**:

- delta is gitlink-only  ->  the pointer fast path (today's `pointer_bump_only`)
- delta touches modules M ->  incremental scoping (the new `run_*` vector)

**Baseline discovery, replacing the walk that never works:**

1. Resolve the head as `github.event.pull_request.head.sha`, **not** `git rev-parse HEAD`.
   That single change fixes D9: HEAD on a `pull_request` is always the 2-parent
   `refs/pull/N/merge` commit, which the current walk aborts on.
2. Find the baseline as **the nearest ancestor carrying a green `CI Complete` that ran a full
   suite**. Requiring a *full* baseline avoids a chain of inference across successive reduced
   runs: evidence always traces to one full run.
3. Prove on the **net** diff `baseline..head`, never by walking intermediate commits. Merge
   commits then stop being fatal.
4. **The subtlety that must not be skipped:** CI validates the *merge* commit, so the proof
   must also require the base SHA to be unchanged since the baseline, or fold main's delta
   into the proof. If main moved, degrade to full.

**Why this self-corrects:** because the delta is always measured from the last **full** green
baseline, it grows monotonically as a PR evolves, so jobs naturally re-enter scope. The
mechanism is bounded rather than drifting.

**Fail-open, everywhere.** Any git failure, any API error, `compare` status `diverged`
(force-push or rebase inside a submodule), the 300-file `compare` truncation cap, a shallow
superproject, an unknown path: **all degrade to full CI.** Copy `initialize.sh:131-133`'s
fail-open wrapper exactly.

**Submodule content diffing** (nothing does this today):
```
git diff-tree -r --raw <baseline> <head> | grep '^:160000 160000 '
gh api repos/rediacc/<sm>/compare/<old>...<new> --jq '.files[].filename'
```
The `-r` is load-bearing. Use the **API**, not a local `git -C private/<sm> diff`:
`ci-build-renet.yml:251` inits renet at `--depth=1`, and `ci-quality.yml:652` and
`ct-tests.yml:97` init only `private/account`. The `readonly` app-token preset already spans
all four submodule repos.

**Classification, fail-closed.** An unmatched path yields full CI with reason
`unclassified:<path>`, so a new subtree can never silently skip. Two refinements that matter
in the incremental frame (they were worthless in the cumulative one):
- compute the workflow **closure at runtime** by iterating `uses: ./.github/workflows/`,
  never a hand-list and never a name pattern. `ci.yml:530` calls `cd-stage.yml`, so a `cd-*`
  pattern would have wrongly excluded a workflow inside the CI closure.
- a **per-subtree `.ci/scripts` map** with `unknown subtree -> harness`, cross-checked by a
  quality gate that fails when a row claims "none" while a workflow literally references that
  subtree. That makes it gate-enforced rather than freeform divergence.
- `.claude/**` can never affect CI and is restored from `origin/main` by the action anyway;
  classify it as docs.

### B2. F11's mitigation is mandatory, not optional

`initialize` writes an **attested skip-plan** artifact: job to `run|skip`, the reason, the
base and head SHAs it diffed, and the changed-file list. `ci-complete` reconciles that plan
against **actual per-job results** fetched with `gh api`, at **job level, never caller
level**. Changed files intersecting a module's ownership globs while that module's jobs
skipped is a **hard fail**.

Without this, an inner job that self-skips inside a reusable workflow makes the caller report
`success`, and `assert-ci-complete.sh` is structurally blind to it.

### B3. Policy cuts, which apply to 100% of PRs

| Cut | Effect | Note |
|---|---|---|
| **D5 tag split** | floor 33.2 -> ~28 min on **every** run | Split `WEB_TAG` and `RDC_TAG` so a www-only change stops rebuilding rdc. **Enumerate what the images actually COPY before hashing**; under-inclusion causes stale image reuse, which is the dangerous direction |
| **macOS demotion** | up to 28 min on the bad half of runs | Rides here, **behind A5's acceptance gate**. Demoting onto a dead nightly is moving coverage to `/dev/null` |
| **deploy-preview decouple** | ~13 min off the good-run wall | Drop `tests` from `needs`. Behaviour change to flag: previews then exist for red PRs, which is cosmetic |

**Explicitly cut from v1: the E2E Workers 5-to-2 matrix reduction.** It is **wall-neutral**
(the legs run in parallel), machine-minutes are free on a public repo, and its safety leans
entirely on the nightly. Revisit only if concurrency ever actually binds; measured peak was
19 of 20, not 20 of 20.

### B4. Defect sweep

- **D3:** delete coverage, do not revive it. Remove the `--coverage` invocation
  (`ct-tests.yml:130`), the swallowed-failure block (`run-unit.sh:52-56`), and the dead
  `test-renet-coverage` artifact upload (`ct-tests.yml:1373`). Keep `npm run test:coverage`
  as a local developer tool. **Do not keep it as decoration:** a green instrument that
  measures nothing is worse than no instrument.
- **D4:** the ops instance descriptor. A single `--instance N` deriving `VM_GROUP`, `VM_NET`,
  `VM_NET_BASE`, `VM_NET_OFFSET` **in lockstep**, because neither knob alone is sufficient
  and nothing currently enforces the pairing. Also fold group or netBase into
  `VMMACAddress`, enable `DestroyNetwork`, and fix `CleanupStoragePool`'s ungrouped
  early-return. Reuse `buildGroupEnv()`; `rdc ops` is the one caller that never opted in.
  Unfreeze `packages/shared/src/config/network.ts` (which also hardcodes
  `VM_USER: 'muhammed'`) and widen the two `block-ssh-*` hook regexes.
- **D6:** all four repos draft-until-green. **Requires decision D-6** for
  `block-premature-ready` on submodules.
- **D7:** resolve the report-root contract conflict and add an **assertion step** to
  `handoff.md` that `ls`-es every artifact it claims to have produced. Requires decision D-2.

### B5. The five issues

- **#538** eval sweep plus an enforcement gate in the `quality-static` (L1) lane. The caller
  audit is mandatory: `printf -v` is not behaviour-equivalent to `eval`. Register in
  `test-gate-anti-vacuity.sh`, give it a both-ways fixture test, and remember
  `check-ci-chain-parity.ts` (a gate wired into a workflow must also be in `npm run ci`).
- **#534** fix the rule **and** allowlist the survivors: ignore comment-only mentions, then
  BLOCKER-allowlist whatever legitimately remains. The issue's smallest option (allowlist
  only) leaves the detector broken. Note `ci-start.sh` is **no longer** a candidate.
- **#539** append one row per review pass with a recomputed total, preserving both body-format
  constraints (marker stays the first line; no second 40-char SHA anywhere in the body). Report
  the model by **usage share**, not alphabetical order. **And settle the open sub-question:**
  read a real `claude-execution-output.json` and determine whether `--model claude-sonnet-5`
  is honoured at all.
- **#537** is in PR-A, see A3.
- **#533** is a decision, not an implementation. See decision D-3.

### B6. The testing pillar (ask 9)

**Structural registries as the only blocking gate, plus a mandatory `## Testing` section in
the PR description as the judgment channel.**

Rejected alternatives, with reasons, so this is not relitigated:
- *Diff-coverage thresholds:* would require reviving a dead instrument across three
  heterogeneous stacks, needs a baseline store that does not exist, measures execution rather
  than verification, and is **dishonest under smart CI** because skipped modules produce no
  data.
- *"Changed source implies changed test" heuristic:* high false-positive rate on this repo's
  wave-shaped PRs, and every false positive demands a suppression. `docs/agent/suppressions.md`
  requires a `BLOCKER:` reason **plus a liveness proof**, and a judgment call ("no test needed
  here") structurally cannot carry one. Blocking heuristics here converge on rot or blanket
  suppression.

Registries assert mechanical truth, so false positives are near zero by construction. The
known false negative (arbitrary logic changes escape) is exactly what the `## Testing` section
plus the Claude reviewer covers. New registries worth adding: an account API-route-to-test
map (209 tests exist; the gate is what is missing), and an elite compose-service-to-healthcheck
map.

**Interaction with smart CI, which is subtle and must be got right.** Registry gates are
static cross-references, cheap, and live in Quality, so **they must never be path-filtered**.
That makes the pillar immune to scoping by construction. The honest claim ladder for a
filtered green is: registries complete; touched-module tests pass; untouched modules are
vouched for by the filter; the filter itself is under anti-vacuity test; the nightly audits
the residue. **One correction to make:** `check:ci-e2e-coverage`'s header says "a suite CI
actually runs", which under scoping weakens to "a suite full CI runs". Rewrite the header or
the gate's claim becomes quietly false.

**`private/elite` does not have zero tests.** ci.yml:605-665 boots the compose stack and
healthchecks it. Do not build a test framework for a compose repo. Note that
`ci-start-elite.sh:53` always overlays `docker-compose.standalone.yml`, so the non-standalone
variant is never exercised: either test both or document the overlay as the only supported
shape.

### B7. Labels, metadata, milestones

**Delete** (zero consumers): `release`, `description-current`, `codex`, and the six unused
GitHub defaults.
**Create:** `no-release` (gates `finalize-release-sentinel`), `full-ci`, and an `area:*`
namespace.

**`no-release` must be a step-level gate inside `finalize-release-sentinel`, never a job-level
`if:`.** `pipeline-sentinel` (ci.yml:1143-1156) asserts finalize's conclusion on release
channels, so a **skipped** finalize job trips it. Fail-open: an API failure must not eat a
release.

**Metadata split by determinism.** Path-derived facts (area labels, `no-release` when the diff
is entirely non-shipping, assignee) go in `validate-pr.cjs`, which already computes the file
list and already warns about missing issue links. Judgment (does this close #537, or only
partly address #518) stays with the Claude reviewer.

**Linking issues:** there is **no API mutation** to link a PR to an issue.
`closingIssuesReferences` is query-only, and closing keywords in the PR body are the only
path. The babysitter already refreshes the body every push, so this is one line in an
existing contract.

**Milestones are program milestones** (see 01 section 9), one per `/handoff` slug, with
sub-issues as the waves. Sub-issues work on the plain repo-scoped token: 100 children,
8 nesting levels, one parent per issue.

### B8. Also flip one ruleset setting

`strict_required_status_checks_policy: true`. It closes the window between a PR's last green
run and its merge, which is the main thing a merge queue would have bought. One line. The
tradeoff is a re-run whenever main moves under an open PR, which is rare at depth 1 and is
exactly why this is the right call *now* and worth revisiting if concurrency changes.

---

## Gate strategy, so none of this rots

Follow the repo's own doctrine: **a validator that passes when given nothing is broken by
definition.**

- `gates/test-detect-changed-modules.sh`, table-driven over a pure `--classify` mode. Every
  table needs a **control** (can it fire) and a **shape check** (can it see). Minimum cases:
  empty input yields full; docs-only yields reduced with every `run_*` false; a
  submodule-prefixed path classifies correctly; an unknown path yields full with the
  diagnostic **pinned**; a `.ci/` path yields full; a `full-ci` label fixture yields full; a
  tutorial-doc path yields `run_ops=true`; and a harvest fixture with a PATH-shimmed `gh`
  returning a canned `compare` payload plus a `diverged` case that must yield full.
- `check-scope-coverage.sh`, in the `check:ci-e2e-coverage` mould: every emitted key must have
  at least one `if:` consumer, and every `full_suite`-gated job must reference a scope key or
  sit on an explicit allowlist with a reason. Kills both rot directions.
- Register both in `test-gate-anti-vacuity.sh` with pinned diagnostic substrings.
- **Live proof on throwaway PRs**, because the v1 PR's own diff forces full CI and therefore
  cannot demonstrate a reduced run: one draft PR with a one-line `docs/` change (expect
  reduced, gated jobs `skipped`, `CI Complete` green), and one with a one-line comment change
  inside `private/account` (expect reduced with `run_account_e2e=true` and workers skipped,
  proving the submodule-content leg). Close both unmerged.

## Rollback

Every wave has a kill switch that does not need a revert:
- the detector call in `initialize.sh` can be deleted, and the pre-written `run_*` defaults
  resurrect all-true;
- `ct-tests.yml` inputs default to `'true'`, so even un-reverted YAML fails open;
- macOS demotion, the preview decouple, and D5 are each a small independent revert;
- `apply-pr-metadata` must **not** be in `ci-complete`'s `needs`: label reconciliation must
  never block a merge.

**The worst-case failure mode of the whole feature is a false skip letting a PR merge without
a suite that mattered.** It is bounded by: fail-closed classification, fail-open harvesting,
the attested skip-plan reconciliation, the nightly, the `full-ci` label, and the throwaway-PR
proofs.
