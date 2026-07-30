# 01. Verified context

Status: **verified 2026-07-27 on branch `main`** (tree clean except `.ci/breakpoint/scripts/start-shell.sh`).

> **RE-VERIFY BANNER.** Every `file:line` below is a hypothesis by the time you read it.
> The tree moves. Re-check any claim before you build on it, and run the real command
> rather than trusting the number written here. Where a claim was measured from a CI
> run, the run id is given so you can re-measure rather than re-believe.

---

## 1. Platform facts (these bound the whole design)

| Fact | Evidence |
|---|---|
| `rediacc/console` is **public**, on a **free** org | `gh api repos/rediacc/console`; `gh api orgs/rediacc --jq .plan.name` = `free` |
| `renet`, `account`, `elite` are **private** on that free org | same probe |
| Those three have **no rulesets at all** | `gh api repos/rediacc/renet/rulesets` returns `403 Upgrade to GitHub Pro or make this repository public` |
| The submodules have **no CI of their own** | `private/renet/.github/workflows/` and `private/account/.github/workflows/` contain only `claude-review.yml`; `private/elite/.github/workflows/` does not exist |
| Exactly **one** required status check exists | ruleset `12344707`, `required_status_checks: [{context: "CI Complete", integration_id: 15368}]` |
| `strict_required_status_checks_policy` is **false** | same ruleset |
| The CI/CD app can **bypass** main branch protection | ruleset bypass_actors includes `{actor_id: 2772000, actor_type: Integration, bypass_mode: "always"}`, and `gh api orgs/rediacc/installations` shows `app_id 2772000` is `rediacc-ci-cd` |
| Actions minutes are **free** (public repo, standard runners) | GitHub billing docs |
| `ubuntu-slim` is a 1-vCPU runner with a **hard, non-overridable 15 min** job cap | GitHub changelog, 2025-10-28 |
| Draft PRs are **free in all repos** since 2025-05-01 | GitHub changelog: "You can now create draft pull requests in any repository, public or private, completely free of charge" |
| Merge queue needs **Enterprise Cloud** for private repos | GA changelog: "available on private and public repos on the GitHub Enterprise Cloud plan and all public repos owned by organizations" |
| Sub-issues work on the **plain repo-scoped token** | `gh api repos/rediacc/console/issues/532/sub_issues` returns `[]`, not 404 |
| Projects v2 needs an **org-scoped credential** | live probe returned `INSUFFICIENT_SCOPES`: `admin:org` + `repo` is not enough; needs `read:project` / `project` |

**Consequence chain worth internalising.** Because only `CI Complete` is required, skipping
jobs cannot break merging. Safety therefore lives entirely inside
`.ci/scripts/ci/assert-ci-complete.sh`, which you control and can test. That is the whole
reason scope-cutting is viable here at all.

---

## 2. Measured CI baseline

Source run: **30122118002** (PR path, full green). Re-measure with
`gh run view <id> --json jobs` rather than trusting these.

- 93 jobs, **72 actually ran**, **73.3 min wall clock**, **498.6 machine-min**
- **Peak concurrency 19** against the free cap of 20, so the pipeline is *not* cap-bound

**Two independent critical paths.**

1. **E2E Workers: stable at 57 to 60 min** across six consecutive runs. This is the real path.
2. **`ops-qemu-provision` on `macos-15-intel`: 4 to 69 min of pure queue wait.** It has no
   `needs:` of its own, becomes eligible at ~11 min, then waits for a runner. Measured start
   offsets across six runs: `68.6, 66.8, 12.0, 64.0, 4.1, 21.4`. It **set the wall clock on
   three of six runs** (73.3, 72.8, 91.6 min). In run 30122118002, minutes 64 to 70 had
   **zero jobs executing**.

**The uncuttable floor is 33.2 min:** `initialize` to `build-renet` to
`build-cli`/`build-docker` to `stage-artifacts` to `validate-install`/`validate-promote`.
`build-cli` and `build-docker` are **hard-required** in `assert-ci-complete.sh` (a `skipped`
there is a hard failure), so nothing cuts this chain.

**`deploy-preview` currently waits for the whole E2E fleet** (`needs: [initialize,
stage-artifacts, tests]`, ci.yml:721-731). It started at minute 60.2, immediately after E2E
ended at 60.1.

**Per-job durations** (run 30122118002, minutes): E2E Workers opensuse 43.9, fedora 38.6,
ubuntu 34.7, oracle 33.2, debian 27.2; OPS Provision linux-amd64 27.3; K8s Multinode 24.0;
K8s Ceph 21.9; Account E2E 20.3; Ceph Workers 19.2; Ceph 18.1; Renet Go 16.3; K8s 14.9;
Migrate 11.4; Fork Isolation 10.3; everything else under 10.

---

## 3. The scoping measurements (these decided the design)

### 3a. Cumulative scoping is nearly worthless here

Two independent samples agree.

| Sample | Method | Eligible for any cut |
|---|---|---|
| 40 most recent merged PRs | classify by touched module | **5%** (2/40) |
| all 60 merged PRs #427-#535 | same | **~7%**; 51/60 (85%) touch `packages/cli` or `private/renet` |

Under a `merge-base..HEAD` diff, `.ci/` or `.github/` appears in **82.5%** of PRs and
`packages/shared` / `provisioning` / root lockfile in **72.5%**. A maximally refined rule
table (runtime workflow-closure computation, per-subtree `.ci/scripts` map, `.claude/**`
reclassified as docs) still reached only **7.5%**, and **cut the E2E fleet on 0 of 40**.
The misses are legitimate: lockfile and `shared` genuinely touch everything.

### 3b. Incremental scoping is a 6x improvement

Measured over **all 61 commits of PR #531**, classifying each commit by its **own** delta
rather than the PR's cumulative delta:

| Scope basis | Commits eligible for a reduced run |
|---|---|
| `merge-base..HEAD` | 5% |
| `last-green..HEAD` | **30%** (18/61) |

Residual blocker: **17 of 61 commits are 1 to 2 file `.ci/` or `.github/` tweaks** that force
full CI. Subtree histogram of harness touches across that PR: `.github/workflows` 66,
`.ci/scripts/review` 18, `.ci/scripts/test` 14, `.ci/scripts/ci` 10, `.ci/scripts/quality` 5,
`.ci/scripts/security` 5, `.ci/tutorials` 5, everything else at most 1.

So the subtree refinement that measured as worthless in the cumulative frame becomes
valuable in the incremental one: `.ci/scripts/review` cannot affect E2E Workers, and a
runtime workflow-closure computation excludes `claude-*`, `watchdog-monitor`, `breakpoint`
and `cd-deploy-*` from those 66.

**Caveat on my own number:** measured per-commit. A push can bundle several commits, so the
real per-push rate is somewhat lower. Re-measure on live traffic before over-claiming.

**Endogeneity, stated honestly:** the distribution is big-bang-shaped *because the process
demanded big-bangs*. Smart CI's value is coupled to sub-issue decomposition adoption.

---

## 4. Defects found during discovery

D1 and D2 were **already fixed** on PR #535 by a different session. The rest are open.

### D1 (FIXED) The review prompt was never delivered
`claude-review-gate.sh` built the prompt into `$GITHUB_OUTPUT` but
`claude-review-reusable.yml` never passed `prompt:` to the action. `git log -S'gate.outputs.prompt'`
showed exactly two commits: added `7916a03c6`, dropped `ab35241e0`. Live proof from run
30121634850 job 89575482111: `"prompt": ""`, `Auto-detected mode: tag`, `Context prompt: NO
PROMPT`, and it fired only because PR #531's body happened to contain `@claude` once
(`#530` and `#529` bodies contain zero).

### D2 (FIXED) `track_progress` throws on `workflow_run`
The action's `validateTrackProgressEvent` allowlist excludes `workflow_run`.

### D3 Coverage is a dead instrument
`ct-tests.yml:130` runs `run-unit.sh --coverage` every full run; `run-unit.sh:55` is
`npm run test:coverage || log_warn`, so total tooling failure passes; **zero `thresholds` in
any `vitest.config.ts`**; nothing uploads or reads the report. `ct-tests.yml:1373` uploads
`test-renet-coverage-${sha}` with **zero downloaders**. The repo already has
`.ci/scripts/test/gates/test-gate-anti-vacuity.sh` asserting exactly this class.

### D4 `ops down` destroys the wrong fleet (live data loss)
`ops_down.go:61-67` iterates `cfg.GetCluster(false)` and calls `driver.Destroy(vmID)`, which
resolves the target by **libvirt domain name only** (`kvm/driver.go:372-385` to
`opsconfig/config.go:644-649`). `VM_NET_BASE` has **zero** influence on the destroy target,
and `rdc ops` never sets `VM_GROUP`. So `VM_NET_BASE=192.168.112 rdc ops down` destroys
`rediacc1/11/12/21/22/23`, the other fleet. It also fires on **create**: `kvm/driver.go:73-79`
force-destroys a name match before provisioning, so `ops up` on a second octet silently
deletes the first fleet's running VMs.
Related: `VMMACAddress` (`kvm/osquirks.go:61-68`) derives from `netOffset` **only**, so two
fleets on different octets get identical MACs; `ops_down.go:78-80` never destroys the
network; `CleanupStoragePool` early-returns for ungrouped fleets.
**The machinery already exists and `rdc ops` is the one caller that never opted in:**
`buildGroupEnv()` (`packages/provisioning/src/factories.ts:79-96`) emits the full per-group
map, two-group behavior is already tested (`OpsManager.group-env.test.ts:147-149`), and
the cluster-declaration path (`buildKvmConfig` in
`packages/cli/src/commands/cluster/declare.ts:69-75`, reached through
`rdc cluster create --provider kvm`, or `--declare-only` to stop after declaring) *requires*
it, throwing with an explicit reference to collision with the ops fleet.

> Corrected 2026-07-27 by `npm run ci`: an earlier draft of this line named a
> `cluster`-level subcommand that does not exist. `declare.ts` is a module exporting
> `buildClusterConfig`, consumed by `cluster create`; the CLI has no such subcommand. Caught by
> `check:cli-docs` the first time this suite was committed, which is the gate doing exactly its
> job.

### D5 Docker cache never hits
`generate-tag.sh:118` implements `--self` as `git rev-parse --short HEAD`, so `WEB_TAG`
changes on every console commit and `web_exists`/`rdc_exists` are always false. Worse,
`initialize.sh:143` is `RDC_TAG="$WEB_TAG"`, so **one tag serves two images** and a www-only
change also invalidates the rdc image. Contrast `RENET_TAG` (`generate-tag.sh:84-112`), a
real content hash over six build-config files.
**This is the only change that lowers the 33.2 min floor** (estimated to ~28 min).

### D6 The draft-PR hook enforces an obsolete premise
`.claude/hooks/pre-bash/block-nondraft-pr-create.sh:46-51` blocks `--draft` on
`renet|account|elite` because "private, free plan, drafts don't exist". That has been false
since 2025-05-01. `pr-babysitter.md` codifies the same split.
**Watch out:** `block-premature-ready.sh` gates `gh pr ready` on console's `CI Complete`, and
the submodule repos have no such check, so making their PRs drafts would make them
unflippable without a decision. See decision D-6.

### D7 `/handoff` step 6 silently no-ops
`programs/` did not exist in `~/.claude/projects/-home-muhammed-monorepo-console/` before
this handoff created it. What exists instead is a **flat** layout at silo root, established
by a 2026-07-11 reboot recovery whose own note says "GOING FORWARD: all program state
(MANIFEST, reports, checkpoints) lives in
`~/.claude/projects/-home-muhammed-monorepo-console/`". The convention beat the spec.
**Contract conflict:** `handoff.md:68` says `programs/<slug>/reports/`, while
`pr-babysit.md:81` and `pr-babysitter.md:144` say silo-root `reports/`. That directory is two
contracts interleaved by filename prefix: 53 `p3*`, 9 `p4*`, 8 `pr-babysit-*`, 5 `w4*`,
4 `w2*`, 3 `p5*`, 3 `b1*`, 2 `b2*`. `MANIFEST.md` is **single-tenant**, titled "Datastore-Centric
Redesign Program". **Zero `docs/*/PROMPT.md` existed** though step 8 mandates one.
The docs half is healthy: `docs/config-universe-follow-up/` has `01-verified-context.md`
through `05-execution-guide.md` plus all mandated README sections.

### D8 The nightly has been red for four consecutive nights, invisibly
Scheduled `ci.yml` runs `30237524399` (07-27), `30187728271` (07-26), `30143522525` (07-25),
`30066214924` (07-24) are all `conclusion=cancelled`. **Three different root causes:**
- 07-27 `Stage Artifacts`: `No APT metadata files found` / `No RPM metadata files found`.
  `.ci/scripts/release/validate-stage-artifacts.sh:106-113` asserts this metadata
  unconditionally, but on `schedule` the channel is `''` and the metadata-producing step
  self-gates on a non-empty channel.
- 07-26 and 07-24 `Quality/Workflows`: the actions-freshness gate wants `docker/login-action`
  upgraded or blocklisted with a `BLOCKER:` reason.
- 07-25 `Quality/Security`: the audit gate doing exactly its job (vulnerability state moves
  with time, not with your diff).

**The mechanism that hides all three:** a gate fails, the watchdog force-cancels the run, and
the run's conclusion becomes `cancelled` rather than `failure`, which reads as "superseded,
ignore". The babysitter's own rule "cancelled is never green" is not being applied to the
nightly.

**Why this blocks everything:** the smart-CI safety argument is "the nightly bypasses all
filtering; it is the net that catches whatever the filter got wrong". That net does not
currently exist.

### D9 The pointer-bump fast path has never fired
`detect-pointer-bump.sh:62` gates the script to `pull_request` events **only**. On a
`pull_request`, `actions/checkout` with no `ref:` checks out `refs/pull/N/merge`, which is
**always a 2-parent synthetic merge commit**. Line 72 sets `current=$(git rev-parse HEAD)`
and lines 75-76 abort if `${current}^2` exists. It therefore aborts on iteration one, every
time, on the only event type it is permitted to run on.

**Live proof.** Commit `2ae83d874187f291eace80b15e4e85e4b1aee06a` on PR #540 is a textbook
pointer bump: one file, the `private/account` gitlink, with a commit message recording a
verified-empty `git diff --stat`. Run `30284618294` emitted
`pointer_bump_only=false -- merge commit fd7610b in the walk`, and `fd7610b` is literally
`Merge 2ae83d87 into 42ab7f55`, the synthetic PR merge ref.

**Empirical.** The `Initialize` log of 12 consecutive recent PR runs (`30284618294`,
`30274958157`, `30270471731`, `30264725898`, `30260786173`, `30232911377`, `30229784201`,
`30219918379`, `30219775359`, `30212049655`, `30210460333`, `30122118002`) reports
`pointer_bump_only=false` in **12 of 12**.

**Consequence:** `/pr-merge` step 3 waits for "the pointer-bump fast-path run (minutes)" that
has never happened. Every pointer bump has paid a full 60 to 90 minute round.

---

## 5. Structural findings

### F10 Push-to-main runs no tests, and the nightly is its only backstop
`ci.yml:59` is `full_suite: ${{ github.event_name != 'push' }}`, documented as "skip
expensive jobs on push-to-main since PR already validated". Verified live on run
`30249144168`: **35 skipped jobs**, including `OPS Tests` and `Tests + Infra / E2E Ceph
Workers`. Defensible at queue depth 1 on its own; combined with D8 it means main's combined
state has had **zero test validation for four days**.

### F11 The invisible cell (sharpest technical finding of the discovery)
The all-skipped-to-caller-skipped trap (proven on push run `29887422351`, where caller job
"Tests + Infra" reported `skipped`) is the **visible** failure mode. The invisible one: if
scope filters are passed **into** a reusable workflow as inputs (the existing `full_suite`
pattern, ci.yml:554-562), an inner test job self-skips while sibling jobs succeed, so the
**caller reports `success`** and `assert-ci-complete.sh` cannot see the skip at all. Any
caller-level assertion is structurally blind to it.

**Mandatory mitigation:** `initialize` writes an attested skip-plan (job to `run|skip`,
reason, the base and head SHAs it diffed, and the changed-file list). `ci-complete`
reconciles that plan against **actual per-job results** from `gh api`, at job level, never
caller level. Changed files intersecting a module's ownership globs while that module's jobs
skipped is a **hard fail**.

### F12 CD writes submodule pointers to main automatically
10 of the last 40 main commits are CD auto-pushes, five of them
`chore(release): update homebrew-tap submodule pointer [skip ci]`. Releases land roughly
every two days (45 tags in 90 days). This is why a merge queue interacts badly with
submodules here, and why `pr-babysitter.md` insists pointer decisions are made by **which
commit is newer, not whose work it is**.

---

## 6. The five tracked issues

| Issue | Core claim | Status |
|---|---|---|
| **#539** review cost line | The marker comment is upserted, so per-pass cost is overwritten; and the model label uses `modelUsage \| keys \| first`, which is **alphabetical**, so haiku is reported when sonnet was requested | Open. **The unresolved sub-question matters most:** whether `--model claude-sonnet-5` is honoured at all. If `modelUsage` contains only haiku, this is a review-quality bug, not a label bug. Could not settle it: the latest Claude Review run concluded `skipped`, so no fresh `claude-execution-output.json`. Haiku legitimately appears for the action's internal sub-steps, so its presence alone proves nothing |
| **#538** eval in `parse_args` | `.ci/scripts/lib/common.sh:287,295,298` assign with `eval`; proven exploitable with `` --access-emails 'a@b.com`touch PWNED`' `` | Open, but **much lower risk than the issue implies**. Verified 2026-07-27: **152 files** source the lib (not 147), and a sweep of all 46 `parse_args` call sites found **zero callers depending on eval's expansion**. `.ci/breakpoint/lib/breakpoint-common.sh:116-146` is an **already-shipped, already-tested `printf -v` twin**, and `test-breakpoint-mode-selection.sh` pins its three preserved quirks. The sweep is a port of working code, not a novel change |
| **#537** watchdog classifier down | Cloudflare Workers AI returns HTTP 402, so every failure is labelled `transient` with **confidence 0** and retried blind | Open. Corrected citations: the AI call is `watchdog-monitor.cjs:328,343` in `callClassifierModel()` (**not** `:276-291`, which is `fetchJobLogs()`); config at `:258-265` (`AI_MODEL = 'deepseek/deepseek-v4-pro'`, threshold 0.8); the fallback literal is at `:396`. Since `:791` requires `confidence >= 0.8` to suppress a retry, a confidence-0 transient **always** retries. Backstop `check-rerun-attempt.sh` caps at `MAX_ATTEMPTS=2`. **The issue's `BlobNotFound` claim is REFUTED**: a live probe of run `30274958157` fetched attempt-1 job `90008782906` logs in full. Do not enshrine it |
| **#534** `check-dead-bash` | `scripts/check-dead-bash.ts:212-224` treats any textual mention as a reference, so **documenting a script exempts it** from the orphan check; `.ci/README.md` contains a directory tree that immunises every script it names | Open. **The 9-item list is stale in both directions.** Honest 2026-07-27 split: **4 true orphans** (`.ci/scripts/docker/build-image.sh`, `.ci/scripts/infra/docker-pull-ghcr.sh`, `.ci/scripts/version/inject-env.sh`, `scripts/docker/build-server.sh`); **4 documented manual entrypoints** with real runbooks, which is the allowlist's own `manual:` category (`packages/json/templates/databases/postgresql/postgres.sh`, `scripts/dev/migrate-stripe-to-envs.sh`, `scripts/dev/reset-bench.sh`, `scripts/dev/backup-d1.sh`); and `ci-start.sh`, see below |
| **#533** three `web` compose stacks | Asks whether stack 1 (`.ci/docker/ci/` + `ci-start.sh`) is a leftover | **Partly expired, and I got this wrong first time.** `.ci/docker/ci/` genuinely has five live consumers (`constants.sh:32`, `ci-stop.sh:19`, `check-compose-env.sh:18`, `ci-env.sh:122`, `ci-start-account.sh:22`). But **`ci-start.sh` itself has ZERO execution sites**: every reference is a comment, plus one log-error string at `pull-service-images.sh:56`. The breakpoint work *documents and works around* it (`pull-service-images.sh` pre-pulls "the images ci-start.sh expects") and `start-origin.sh:12` says outright *"The fix is not 'call ci-start.sh somewhere'."* So the compose directory lives; its entrypoint is still an orphan, and the breakpoint author **deliberately declined to adopt it** |

---

## 7. Existing machinery you must extend rather than duplicate

- **`detect-pointer-bump.sh`** is the ethos to copy, quoted from its own header: *"the proof
  is content identity, not trust. Any doubt on any test degrades to full CI."* Its `-r` on
  `git diff-tree` is load-bearing (without it a nested gitlink reports as its parent tree and
  never matches `160000`, documented at `:80-81`).
- **Every expensive job already gates on one boolean**, `if: inputs.full_suite == 'true'`
  (ct-tests.yml:122, 134, 312, 446, 589, 725, 867, 1010, 1174, 1335, 1428) or
  `if: inputs.pointer_bump_only != 'true'` (ct-tests.yml:78). Scoping is a **vector
  replacement, not a rewrite**.
- **`initialize` already emits `full_suite` and `pointer_bump_only`** (ci.yml:56-63) with a
  default-then-overwrite output pattern (initialize.sh:83-85) and a fail-open wrapper
  (initialize.sh:131-133) you should copy exactly.
- **Zero `paths:` / `paths-ignore:` filters exist.** Do not add them: that skips the whole
  workflow, `CI Complete` is never reported, and that is the one way to actually hit the
  required-check trap.
- **`ci.yml:6-7` is `pull_request: types: [opened, synchronize]`.** `labeled` is absent, so a
  `full-ci` label cannot retrigger CI. Label gating on `synchronize` does work:
  `no-external-quality` is the precedent (ci-quality.yml:777 and steps 540/544/553/893).
- **Static gates constraining your YAML:** `check-workflows.sh` caps inline `run:` logic at
  `INLINE_MAX_LOGIC=8` lines, so detector logic goes in `.ci/scripts/ci/`.
  `.ci/scripts/security/check-workflow-gates.sh` CHECK 1 requires any job-level `if:`
  referencing `needs.*.result` to be prefixed with `always()`/`!cancelled()`/`failure()`/
  `success()`; CHECK 3 requires `ubuntu-slim` jobs to declare `timeout-minutes <= 14`.
- **`migration-test` is unconditional on PRs** (ct-tests.yml:74-78), which is what keeps the
  "Tests + Infra" caller out of the all-skipped trap for free. Preserve that and say so in a
  comment.
- **Four structural coverage gates** are the pattern to extend: `check:ci-e2e-coverage`,
  `check:ci-schema-coverage` (which **proves the instrument on a control schema every run**),
  `check:ci-audit-coverage`, `check:ci-e2e-skip-hygiene`.
- **`.ci/scripts/ci/validate-pr.cjs`** already computes the changed-file list and already
  warns "PR does not reference any issues", with nothing acting on it.
- **`.github/actions/app-token`** presets: `readonly`, `pr-read`, `push` (contents:write),
  `cd`, `housekeeping`. A catch-all `ci` preset was deliberately deleted.

---

## 8. Label inventory, by actual consumption

**Dead, zero consumers in code:** `release` (yet 28 PRs carried it; CD is `workflow_dispatch`
dispatched unconditionally from `finalize-release-sentinel`, ci.yml:1023), `description-current`
(the PR-description gate reads `lastEditedAt`), `codex`, and six unused GitHub defaults
(`good first issue`, `help wanted`, `wontfix`, `duplicate`, `invalid`, `question`).

**Alive, machine-read:** `no-external-quality` (5 workflow references), `no-cancel-push`,
`no-cancel-failure`, `no-auto-retry`, `bump-minor`, `bump-major`, `automated`, `dependencies`,
`github-actions`.

**Alive, triage:** `enhancement` (29), `bug` (23), `translation` (13), `documentation` (1).

**All 13 open issues carry zero labels.** 109 of 124 issues live in `console`.

---

## 8b. Late verification findings (2026-07-27, three read-only sweeps)

These arrived after the first draft and **correct it**. Trust these over anything earlier.

### D10 (new) Nothing binds `ci.yml`'s job list to `assert-ci-complete.sh`
`ci-complete`'s `needs` (ci.yml:1026) lists 18 jobs and all 18 have a `RESULT_` var
(ci.yml:1039-1056), but that consistency is **maintained by hand, not by construction**.
`test-ci-complete-tiers.sh` tests the tier logic against a hardcoded baseline and never parses
`ci.yml`. So **a new job forgotten in `ci-complete` is silently unverified, and worse, is not
even waited on**, so `ci-complete` can go green while it is still running or already red. The
script's header claim that "a renamed job must break loudly here" holds only for renames of
jobs already listed, not for additions. Cheap fix: a gate parsing `ci.yml`'s top-level `jobs:`
keys, subtracting a small BLOCKER-annotated exempt set, asserting the rest appear in both
`needs` and the `env:` block.

### Exact tiers (quote these, do not paraphrase)
```
HARD_REQUIRED=(INITIALIZE BUILD_DOCKER BUILD_DOCKER_FAST BUILD_CLI)            # :24
SOFT_REQUIRED=(QUALITY REVIEW_GATE STRIPE_SANDBOX PACKAGE_TESTS STAGE_ARTIFACTS
    VALIDATE_INSTALL VALIDATE_PROMOTE TESTS ELITE_RUN_TEST OPS_TESTS
    UPDATE_FLOW_TEST DEPLOY_PREVIEW SMOKE_TEST_PREVIEW BREAKPOINT_LIFECYCLE)   # :32-36
# POINTER_BUMP_ONLY demotion, :43-46: HARD becomes (INITIALIZE); the three builds move to SOFT
```

### Module map corrections (the earlier map was under-specified)
- **The 8 VM/E2E jobs share a byte-identical step spine.** They check out
  `submodules: true`, meaning **all four** submodules, and run `setup-workspace` with
  `account: 'true'` and `build-packages: 'true'`. So their surface **must include
  `packages/shared`, `packages/provisioning`, `package-lock.json`, and every submodule
  pointer**. A scope rule that omits `packages/shared` will skip E2E on a shared change and
  be wrong.
- **`test-renet` "needs only private/renet" is REFUTED.** It checks out all submodules, and
  five of its seven test steps are console-side scripts under `.ci/scripts/private/`
  (`run-renet.sh`, `renet-ebpf-e2e.sh`, `renet-root-tests.sh`, `renet-csi-sanity.sh`,
  `renet-integration.sh`). Correct scope: `private/renet` plus
  `.ci/scripts/private/renet-*` plus `run-renet.sh` plus `.ci/scripts/lib`. It is still true
  that it has **no npm or setup-workspace step at all**.
- **`test-unit` also runs `packages/e2e-tests` unit tests**, so an e2e-tests-only change must
  still trigger it.
- **OPS doc exposure is tighter than feared, and this is good.** `run-sequence.sh:31,37,40`
  reads `packages/www/src/content/docs/en/tutorial-*.mdx` and greps `^order:`. It is the only
  reader. **Prose edits inside a tutorial `.mdx` are safe**; adding, renaming or removing one,
  or changing its `order:`, is not. Non-`en` locales and non-`tutorial-*` docs are safe.
- Job id is **`ops-vm-provision`**, not `ops-provision`. `ops-qemu-provision` and
  `ops-platform-check` check out **no submodules** and reach renet only via the
  `renet-binaries-${sha}` artifact.
- Reusable-workflow closure confirmed **exactly** and depth is **1**: none of the nine called
  workflows calls another.

### D5's real input surface, and its one big trap
`initialize.sh:141-144`; `--self` is `generate-tag.sh:114-116`.
**The trap: both images embed `private/renet` binaries, but both tags derive from the console
HEAD.** That is accidentally safe today because a renet bump *is* a console commit. Under a
content hash it stops being safe unless the **renet submodule pointer is explicitly
included**, or `RENET_TAG` is folded into both hashes. Omit it and a renet-only bump reuses a
server image carrying the **old** renet binaries. This is the most likely stale-reuse bug.
Also: `VITE_APP_VERSION=${WEB_TAG}` is self-referential and baked into the served version
string; `ACCOUNT_ED25519_PUBLIC_KEY` is a secret build arg and not hashable; `.ci/scripts` is
`.dockerignore`d yet several of those scripts shape the artifacts fed into the context, so
hashing the build context is **not** sufficient.

### `deploy-preview` is safe to decouple, and has two dead steps
It downloads only `preview-pages-${sha}` (produced by `stage-artifacts`), so it consumes
**nothing** from `tests`. Removing `tests` from `needs` requires dropping the
`needs.tests.result` clause in the same edit. **Found, not fixed:** `ci.yml:807` and `:813`
inject `e2e-videos-${sha}` and `tutorial-recordings-${sha}`, and **no workflow produces
either**. Both are `|| true`, so they have silently done nothing.

### Action facts, verified at the pinned SHA
`fa7e2f0a` is tag `v1.0.180`, and a diff of pin against `main` for every relevant source file
is **empty**, so no pin-versus-main caveat applies.
- **`restoreConfigFromBase` never fires on `workflow_run`** (gated on `isEntityContext`).
  See [03](03-v2-autonomy.md) wall 4. Trusted checkout becomes a hard invariant.
- **Agent mode inlines nothing.** No comments, titles, bodies or review text. The prompt is
  exactly `context.inputs.prompt`.
- **An installation token CAN write workflows if the app holds `workflows:write`.**
  `rediacc-ci-cd` does not; the `claude` app **does**. No `app-token` preset requests it.
- `ssh_signing_key` takes precedence over `use_commit_signing` and **does** call
  `configureGitAuth`, so it is the one path that preserves identity control while signing.
- `--max-budget-usd` is **not in the action** (no such input in `action.yml` at the pin), which
  is why it has to ride in through `claude_args`. The "do not claim it binds" warning that
  stood here is **superseded**: spike S-2 ran the live `--max-budget-usd 0.01` test on
  2026-07-30 and **it binds under OAuth**. It is a post-hoc stop rather than a ceiling
  (measured cap $0.01, actual spend $0.2340351, halted between turns), so a dollar stop exists
  and a hard cap does not. See `spike-s1-s2.md` and the cost section of `03-v2-autonomy.md`.
  The CLI-print-mode caveat reconciles with the action never passing `--print`: print mode is
  simply "not interactive", and a spawned child with piped stdin qualifies.
- `--model claude-sonnet-5` **is honoured**; spike S-1 settled #539 as a cosmetic label bug,
  not a review-quality one. Every finding received so far came from the requested model. The
  two haiku sightings both predate `f95533298` (2026-07-28), which replaced `keys | first`
  with a join across every `modelUsage` key.

### The submodule review pipeline is doubly broken
- `CLAUDE_CODE_OAUTH_TOKEN` is an org secret scoped to **`rediacc/console` only**. Neither
  `renet` nor `account` has it. The outstanding operator action is **confirmed still
  outstanding**.
- **Second, separate bug:** account's two `claude-review` runs both failed at
  *"Bootstrap review scripts"* with
  `bash: .ci/scripts/review/bootstrap-review-scripts.sh: No such file or directory` (exit
  127), before ever reaching the action. The reusable assumes that script exists in the
  **caller's** checkout, which is true in console and false in the submodules. **Fixing the
  token alone will not make submodule reviews work.**

### Two efficiency findings, not fixed
- All 8 VM/E2E jobs pass `account: 'true'` to `setup-workspace`, installing three
  `private/account` npm trees that the e2e suites never reference. Pure setup cost, and it
  drags account lockfile changes into the E2E invalidation surface for no test value.
- `generate-tag.sh:92-97` hashes `.ci/scripts/build/build-renet.sh`, but `ct-tests.yml` and
  `ci-ops-test.yml` build renet with the **different** `.ci/scripts/infra/build-renet.sh`.
  Not a live bug for the release-path tag, but do not copy that list as exhaustive.

---

## 9. Milestones must be program milestones, not release milestones

Evidence, all measured:
- **45 tags in 90 days**, one release roughly every two days, four on 2026-07-04 alone.
- The version **does not exist until merge**: `CLAUDE.md` states "Version source of truth:
  git tags. No version bump commits", and the bump size is decided by a **label on the PR**
  read at merge time.
- **Zero of 109 console issues has ever been version-scoped.** The only issues mentioning a
  version reference other software (Docker v29, glibc/musl) or are a bug *about* versioning.
- Every multi-item issue is a campaign tracker: #523 "P5 backlog ... P4 cluster/datastore
  wave", #518 "Ceph + Kubernetes campaign", #519 "Funnel follow-ups".

So a milestone maps one-to-one onto a **`/handoff` slug**, and its sub-issues are the waves.
