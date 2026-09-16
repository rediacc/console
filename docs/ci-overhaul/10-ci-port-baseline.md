# 10. The `.ci` port baseline (W7 phase 0)

Every later W7 box is measured against this file. It is written under one rule,
taken from [08-driver-contract.md](08-driver-contract.md) section 5: **cite the
COMMAND, not the number.** That section records that four planning drafts
asserted four different figures for the same quantities, and that the manifest
gained two gates between the baseline measurement and the first implementation
branch. So every row below carries the command that produced it, and where a SET
is what matters the set is written out rather than counted.

Measured at `ac817a647322c219763e22d93c970d96beec886f`, branch `tooling-transformation-w0`, in a shared checkout with
289 uncommitted paths from other sessions. Section 4 of the contract applies:
**the tree measured is not necessarily the tree you are editing.** Re-run the
commands before relying on a row.

---

## 1. The quality-gate inventory

### 1a. `check-*.sh` under `.ci/scripts/quality` — 77 files

    git ls-files '.ci/scripts/quality/check-*.sh'

The contract's timing table says "74 `check-*.sh` plus 5 wrappers". The command
answers **77** today, which is the sort of drift that row warns about. The set:

  check-account-portal.sh
  check-account-probes.sh
  check-agent-browser-exit.sh
  check-audit-coverage.sh
  check-autopilot-breakpoint-alignment.sh
  check-autopilot-no-bypass.sh
  check-battery-clean-tree.sh
  check-branch.sh
  check-ci-job-aggregation.sh
  check-ci-scans-tracked-paths.sh
  check-ci-watch-recipe.sh
  check-claude-attribution.sh
  check-cli-contract.sh
  check-cli-doc-coverage.sh
  check-command-tree.sh
  check-commit-identity.sh
  check-compose-env.sh
  check-config-migrations.sh
  check-content-quality.sh
  check-control-vacuity.sh
  check-dead-case-arms.sh
  check-devbox-exec.sh
  check-devcontainer-scripts.sh
  check-drill-verdicts.sh
  check-e2e-coverage.sh
  check-editorconfig.sh
  check-gate-id-convention.sh
  check-git-op-conditionals.sh
  check-go-deps.sh
  check-go-module-sync.sh
  check-go-tool-path.sh
  check-greenlight-closures.sh
  check-hook-integrity.sh
  check-host-toolchain-coverage.sh
  check-label-inventory.sh
  check-label-references.sh
  check-lockfile.sh
  check-mutate-check.sh
  check-no-app-admin-perm.sh
  check-no-otlp-creds.sh
  check-npmrc.sh
  check-peer-deps.sh
  check-pipefail-grep-q.sh
  check-plan-housekeeping.sh
  check-pool-writer-safety.sh
  check-pr-description.sh
  check-probe-parity.sh
  check-profiler-coverage.sh
  check-python-lint.sh
  check-regions-sync.sh
  check-release-bump-skip.sh
  check-release-key-canonical.sh
  check-release-signing-coverage.sh
  check-release-state.sh
  check-renet-tier-map.sh
  check-renet-types.sh
  check-resolved-threads.sh
  check-review-cap-coherence.sh
  check-review-comments.sh
  check-review-report-replies.sh
  check-review-turn-capacity.sh
  check-rubric-calibration.sh
  check-scope-scripts-reachability.sh
  check-script-exec-bit.sh
  check-setup-idempotency.sh
  check-shell-size.sh
  check-silent-failure-patterns.sh
  check-staging-tag-guard.sh
  check-submodule-branches.sh
  check-subscription-schema.sh
  check-swallowed-failures.sh
  check-toolchain-env-dockerfile-sync.sh
  check-toolchain-pins.sh
  check-tracked-sidecars.sh
  check-trap-registry.sh
  check-workflows.sh
  check-www-build-token.sh

### 1b. The non-check wrappers under the same directory — 5 files

    git ls-files '.ci/scripts/quality/*.sh' | grep -v '/check-'

This is the "5 wrappers" the contract names, and here the number does hold:

  announce-gate-skips.sh
  browser-smoke.sh
  page-density.sh
  run-external-gate.sh
  typecheck-workers.sh

### 1c. `check-*.sh` elsewhere under `.ci/scripts` — 9 files

    git ls-files '.ci/scripts/**/check-*.sh' | grep -v '/quality/'

These are NOT in the 1a set and are easy to forget, because the shape of the
name says "quality gate" and the directory says otherwise. Three of them are
release preconditions and one is a CI helper:

  .ci/scripts/ci/check-rerun-attempt.sh
  .ci/scripts/release/check-edge-manifest.sh
  .ci/scripts/release/check-existing-release.sh
  .ci/scripts/release/check-soak-period.sh
  .ci/scripts/release/check-stable-manifest.sh
  .ci/scripts/security/check-autopilot-workflow-invariants.sh
  .ci/scripts/security/check-ci-workflow-invariants.sh
  .ci/scripts/security/check-commands.sh
  .ci/scripts/security/check-workflow-gates.sh

### 1d. Python gates already in `.ci/scripts/quality` — 41 files

    git ls-files '.ci/scripts/quality/check_*.py'

Named here because they are the CONVENTION the port lands into, not a
competing design: contract section 5d says a gate's entry point lives in
`.ci/scripts/quality/` (or the package, since the 2026-09-06 amendment) so the
binder can see it, "and that is also where the 41 existing `check_*.py` gates
already are".

---

## 2. Which of them declare themselves

    for f in $(git ls-files '.ci/scripts/quality/check-*.sh'); do \
      head -12 "$f" | grep -qF -- '---- gate ----' && echo "$f"; done

**53 declare a `---- gate ----` header. 24 are still hand-registered.**

The contract's row reads "19 tracked, 14 parsing", which was true when it was
written and is badly stale now; the binder is the authority. The undeclared set,
which is what a later box has to drain:

  check-autopilot-breakpoint-alignment.sh
  check-autopilot-no-bypass.sh
  check-branch.sh
  check-ci-job-aggregation.sh
  check-ci-scans-tracked-paths.sh
  check-claude-attribution.sh
  check-cli-doc-coverage.sh
  check-commit-identity.sh
  check-dead-case-arms.sh
  check-editorconfig.sh
  check-label-inventory.sh
  check-label-references.sh
  check-no-otlp-creds.sh
  check-pr-description.sh
  check-profiler-coverage.sh
  check-regions-sync.sh
  check-release-bump-skip.sh
  check-release-state.sh
  check-renet-tier-map.sh
  check-resolved-threads.sh
  check-review-comments.sh
  check-review-report-replies.sh
  check-submodule-branches.sh
  check-swallowed-failures.sh

### 2a. The binder's own count, which is the one to quote

    npx tsx scripts/gate-bind.ts            # read-only; --write is the driver's

    ✓ gate binding: 186 declared gate(s), each matching its package.json script,
      its manifest entry, and a workflow step in a lane that provides its needs

    npx tsx scripts/gate-bind.ts --extract-all --dry-run

    would extract: 16
    refused: 394
         186  already declares a header
         171  outside .ci/scripts and scripts
          19  shares a step with other gates (sub-gate of an aggregate)
          18  other

The `171 outside .ci/scripts and scripts` row is the measurement behind contract
section 5d's "a gate's ENTRY POINT lives where the binder can see it". A header
in any of those 171 files is INERT, and nothing reports the silence.

A NAIVE GREP OVERCOUNTS AND SHOULD NOT BE USED. `git ls-files | xargs grep -l
'---- gate ----'` answers 195, because `docs/ci-overhaul/06-progress.md`,
`docs/ci-overhaul/08-driver-contract.md` and `.github/workflows/ci-quality.yml`
all QUOTE the marker. Ask the binder.

---

## 3. The gate-test inventory

    git ls-files '.ci/scripts/test/gates/*.sh'      -> 144
    git ls-files '.ci/scripts/test/*.sh' '.ci/scripts/test/*.ts'  -> 167

The contract's timing table says "Gate test files 131". The command says **144**
under `gates/` plus **167** at the top level of `.ci/scripts/test`:

  assert-r2-sentinel.sh
  collect-drill-diagnostics.sh
  fixture-suite.sh
  git-fixture.sh
  mutate-check.sh
  probe-receipt-stability.sh
  profiler-control.sh
  run-account-e2e.sh
  run-all.sh
  run-e2e.sh
  run-unit.sh
  seed-smoke-test.sh
  smoke-test-preview.ts
  start-account-for-e2e.sh
  test-actions-release-age.sh
  test-age-check.sh
  test-assert-edge-tag-exists.sh
  test-autopilot-breakpoint-alignment.sh
  test-autopilot-guide-comment.sh
  test-autopilot-harness.sh
  test-autopilot-no-bypass.sh
  test-autopilot-workflow-invariants.sh
  test-backfill-commit-resolve.sh
  test-blocker-golden-corpus.sh
  test-blocker-validator.sh
  test-breakpoint-drift.sh
  test-breakpoint-mode-selection.sh
  test-breakpoint-naming.sh
  test-breakpoint-pins.sh
  test-breakpoint-portability.sh
  test-breakpoint-secret-exposure.sh
  test-breakpoint-teardown.sh
  test-bws-env.sh
  test-bws-map.sh
  test-channel-for-event.sh
  test-ci-compat-prose.sh
  test-ci-complete-tiers.sh
  test-ci-job-aggregation.sh
  test-ci-parity.sh
  test-ci-runner.sh
  test-ci-trace-branch.sh
  test-ci-workflow-invariants.sh
  test-claude-hooks.sh
  test-client-bundle-budget.sh
  test-commit-identity.sh
  test-dead-bash.sh
  test-dead-case-arms.sh
  test-detect-bump-type.sh
  test-devbox-probes.sh
  test-devbox-slug.sh
  test-devcontainer-pin-freshness.sh
  test-dispatch-release.sh
  test-docs-gen.sh
  test-e2e-coverage.sh
  test-edge-verify-retries.sh
  test-embed-arch-parity.sh
  test-embed-asset-freshness.sh
  test-embed-credits.sh
  test-emit-advisory.sh
  test-external-gate-wrapper.sh
  test-fetch-depth-safety.sh
  test-form-validation.sh
  test-gate-anti-vacuity.sh
  test-gate-header.sh
  test-gate-lanes.sh
  test-gate-paths-exist.sh
  test-gate-skip-announcer.sh
  test-generate-tag-inputs.sh
  test-go-deps-probe-failure.sh
  test-go-module-sync.sh
  test-greenlight-closure-trace.sh
  test-greenlight.sh
  test-helpers.sh
  test-housekeeping-phases.sh
  test-hydration-clean.sh
  test-install-methods.sh
  test-install-script.sh
  test-install-sh-config.sh
  test-installmethods-args.sh
  test-installmethods-container-version.sh
  test-installmethods-linuxpkg-idiom.sh
  test-installmethods-manifest.sh
  test-knip-blockers.sh
  test-label-guide-comment.sh
  test-label-inventory.sh
  test-label-references.sh
  test-layout-overflow.sh
  test-linux-packages.sh
  test-mark-production.sh
  test-media-args.sh
  test-media-bridge.sh
  test-media-cuda.sh
  test-media-entry.sh
  test-media-helpers.sh
  test-media-pool.sh
  test-media-r2.sh
  test-media-venv.sh
  test-nightly-retry-filters.sh
  test-nightly-status-report.sh
  test-overrides-reasons.sh
  test-plan-housekeeping.sh
  test-policy-liveness-floors.sh
  test-policy-path.sh
  test-positional-detector.sh
  test-preview-readiness.sh
  test-preview-worker-reaping.sh
  test-profiler-coverage.sh
  test-profiler-report.sh
  test-rdc-sh-env.sh
  test-rdc-update.sh
  test-rebase-resolve.sh
  test-regions-sync.sh
  test-release-state-consistency.sh
  test-releaseversion-attestation.sh
  test-releaseversion-build-version.sh
  test-releaseversion-cd-retry-assert.sh
  test-releaseversion-closure-untagged.sh
  test-releaseversion-inject-env.sh
  test-releaseversion-tag-fetch.sh
  test-renet-deadcode.sh
  test-resprofile.sh
  test-review-labels.sh
  test-review-status.sh
  test-run-all-parallel.sh
  test-run-sh.sh
  test-runner-advice.sh
  test-schema-coverage.sh
  test-scope-baseline-attest.sh
  test-scope-engine.sh
  test-scope-gate-outputs.sh
  test-scrub-sentinel-empty.sh
  test-shadow-gate.sh
  test-shell-counter-increment.sh
  test-shrink-only-composition.sh
  test-simulate-promotion-serverside.sh
  test-skip-plan-reconcile.sh
  test-skip-release-channel-pointer.sh
  test-slim-timeout.sh
  test-stage-artifacts-channel.sh
  test-stop-hook-stdin.sh
  test-suppression-liveness.sh
  test-swallowed-failures.sh
  test-toolchain.sh
  test-trap-registry.sh
  test-tutorial-render-queue.sh
  test-untagged-commit-branch.sh
  test-unverified-downloads.sh
  test-vacuity-floors.sh
  test-verify-version.sh
  test-watchdog-binary-exec-guard.sh
  test-watchdog-classifier-chain.sh
  test-watchdog-designed-failure.sh
  test-watchdog-log-capture.sh
  test-watchdog-monitor-ordering.sh
  test-watchdog-no-retry-cancel.sh
  test-watchdog-observer-exclusion.sh
  test-watchdog-retry-allowlist.sh
  test-watchdog-schedule-exemption.sh
  test-watchdog-supersession.sh
  test-workflow-contracts.sh
  test-workflow-env-shell-vars.sh
  test-workflow-inline.sh
  test-workflow-pr-environment.sh
  test-worklist-hooks.sh
  test-worktree-devbox-teardown.sh
  test-write-once-guard.sh
  workflow-rule.sh

**Exactly one gate test carries a `---- gate ----` header**, and it is not a
registration:

  .ci/scripts/test/gates/test-gate-header.sh

`gate-bind.ts`'s own selftest states why -- "a gate-test is out of scope: its
header is fixture data and it owns no step". A later box must not read that one
hit as "the drain has begun".

---

## 4. Which bash libraries each surface sources

This is the dependency map W7 phases 2 and 3 have to unpick, and the interesting
result is how LOPSIDED it is. Counted with

    grep -lE "source .*(lib|config)/<lib>" $(git ls-files '.ci/scripts/quality/*.sh') | wc -l

over the 82 shell files under `.ci/scripts/quality`:

| library | sourced by |
|---|---|
| `.ci/scripts/lib/common.sh` | 45 |
| `.ci/scripts/lib/blocker-validator.sh` | 4 |
| `.ci/scripts/lib/age-check.sh` | 1 |
| `.ci/scripts/lib/release-state-validator.sh` | 1 |
| `.ci/scripts/lib/toolchain.sh` | 1 |
| `.ci/scripts/lib/gate-controls.sh` | 1 |
| `.ci/scripts/lib/release-age.sh` | 1 |
| `.ci/scripts/lib/emit-advisory.sh` | 0 (reached transitively, through `age-check.sh`) |
| `.ci/lib/local-common.sh` | 0 |
| `.ci/lib/find-port.sh` | 0 |

and over the 144 files in `.ci/scripts/test/gates`:

| library | sourced by |
|---|---|
| `.ci/scripts/test/lib/test-helpers.sh` | 137 of 144 |
| `.ci/scripts/lib/common.sh` | 4 |
| `.ci/scripts/lib/blocker-validator.sh` | 2 |
| `.ci/scripts/lib/emit-advisory.sh` | 1 |
| `.ci/scripts/lib/age-check.sh` | 1 |
| `.ci/scripts/lib/release-state-validator.sh` | 1 |

**The consequence for sequencing.** `common.sh` (742 lines) and `test-helpers.sh`
are the only two libraries a port cannot approach incrementally: one of them is
under 45 gates and the other under 137 gate tests. Everything else has a
single-digit blast radius, which is why phase 1 took two of the single-digit ones.

### 4a. The full library set, with size

    git ls-files '.ci/lib/*.sh' '.ci/scripts/lib/*.sh' | xargs wc -l

  .ci/lib/account.sh
  .ci/lib/bws-env.sh
  .ci/lib/devbox.sh
  .ci/lib/find-port.sh
  .ci/lib/local-common.sh
  .ci/lib/service.sh
  .ci/lib/setup.sh
  .ci/scripts/lib/age-check.sh
  .ci/scripts/lib/blocker-validator.sh
  .ci/scripts/lib/common.sh
  .ci/scripts/lib/emit-advisory.sh
  .ci/scripts/lib/gate-controls.sh
  .ci/scripts/lib/release-age.sh
  .ci/scripts/lib/release-state-validator.sh
  .ci/scripts/lib/toolchain.sh

---

## 5. The JavaScript under `.ci` — 23 files

    git ls-files '.ci/**/*.js' '.ci/**/*.cjs' '.ci/**/*.mjs' '.ci/**/*.ts'

  .ci/scripts/autopilot/exfil-tripwire.cjs
  .ci/scripts/autopilot/validate-handoff.cjs
  .ci/scripts/build/sea-inject/cli.mjs
  .ci/scripts/build/sea-inject/common.mjs
  .ci/scripts/build/sea-inject/elf.mjs
  .ci/scripts/build/sea-inject/index.mjs
  .ci/scripts/build/sea-inject/macho.mjs
  .ci/scripts/build/sea-inject/pe.mjs
  .ci/scripts/build/sea-inject/verify.mjs
  .ci/scripts/ci/autopilot-guide-comment.cjs
  .ci/scripts/ci/greenlight.cjs
  .ci/scripts/ci/label-guide-comment.cjs
  .ci/scripts/ci/report-nightly-status.cjs
  .ci/scripts/ci/scope-engine.cjs
  .ci/scripts/ci/scope-map.cjs
  .ci/scripts/ci/skip-plan-reconcile.cjs
  .ci/scripts/ci/validate-pr.cjs
  .ci/scripts/ci/watchdog-monitor.cjs
  .ci/scripts/docs/compress-cast-idle.mjs
  .ci/scripts/docs/process-cast-markers.mjs
  .ci/scripts/quality/lint-rule-liveness.mjs
  .ci/scripts/test/smoke-test-preview.ts
  .ci/tutorials/apps/heartbeat/app/heartbeat.mjs

which matches contract section 5d's "W7 phase 1 relocates 23 JS and TS files out
of `.ci`" exactly. See section 7 for why that relocation did NOT happen in phase
1, and what has to land first.

---

## 6. The comment-archaeology baseline

Contract section 5c makes the comment-byte ratio a port acceptance criterion,
with a floor of 0.90, and requires that every original line naming a date, a run
id, a sha or an issue number is shown to survive. The counter used is

    scratchpad/archaeology.py   (bash: `#` comment bodies, quote-aware so that
                                `sed 's/#x/y/'` is not counted as prose;
                                python: `tokenize` COMMENT tokens plus every
                                module/class/function docstring)

| original | its comment bytes | the port | port bytes | ratio |
|---|---|---|---|---|
| `.ci/lib/find-port.sh` @ ac817a647 | 2,587 | `.ci/rediacc_ci/core/ports.py` | 9,389 | **3.63** |
| `.ci/scripts/lib/age-check.sh` @ ac817a647 | 3,650 | `.ci/rediacc_ci/core/age.py` | 7,394 | **2.03** |

A ratio far above 1.0 is not padding: contract section 5c explicitly permits the
prose to change, and both ports absorbed reasoning that used to live in the
CALLER (why `check-setup-idempotency.sh` sources the file standalone, why the
probe is `ss` and not a socket bind) rather than in the file.

**Archaeology tokens in the originals, and where each survives.** `find-port.sh`
carries no date, sha or issue number; it carries three file-and-line anchors,
listed with them because the ratio cannot see those either.

| token | in the original | in the port |
|---|---|---|
| `2026-09-03` (the truncated-history measurement) | age-check.sh:13 | core/age.py, twice |
| `195 days` / `2026-02-20` (full clone) | age-check.sh:18 | core/age.py |
| `2 days` / `2026-09-01` (truncated clone) | age-check.sh:19 | core/age.py |
| `github.com/docker/docker` (the entry measured) | age-check.sh:16 | core/age.py |
| `.go-deps-upgrade-blocklist` (the file it lives in) | age-check.sh:16 | core/age.py |
| `check-plan-housekeeping.sh` (the sibling defect) | age-check.sh:24,48 | core/age.py, twice |
| `check-setup-idempotency.sh:129-130` (the standalone sourcer) | find-port.sh:94 | core/ports.py |
| `check-account-probes.sh` (the gate the comment WRONGLY named) | find-port.sh:95 | core/ports.py, twice |
| `local-common.sh` (the dependency it must not take) | find-port.sh:92 | core/ports.py |
| `_sha256sum_portable` (the function the port deletes) | find-port.sh:97 | core/ports.py, twice |

The `check-account-probes.sh` row is the one worth a reviewer's eye. It is a
correction: the original comment named the wrong gate, a later edit fixed it IN
PLACE and said so, and the port carries the correction AND the fact that it was
one. A summary would have kept only the right answer and thrown away the record
that somebody got it wrong.

---

## 7. Why phase 1 relocated no JavaScript, measured

The plan's P1(a) is "JS relocation out of `.ci`". It did not happen, and this is
the evidence rather than a judgement call. Three independent blockers, each with
the command that shows it.

### 7a. Every move DOWNGRADES CI scope, and that is a safety regression

`.ci/scripts/ci/scope-map.cjs` classifies `.ci/` as `full` (reason `harness`) and
everything under `scripts/` that is not specifically carved out as
`reduced` with the zero-job module `gates`. Run the real classifier:

    node -e 'const m=require("./.ci/scripts/ci/scope-map.cjs");
             console.log(JSON.stringify(m.classify(["scripts/build/sea-inject/cli.mjs"])))'

    .ci/scripts/build/sea-inject/cli.mjs           | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/build/sea-inject/common.mjs        | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/build/sea-inject/elf.mjs           | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/build/sea-inject/index.mjs         | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/build/sea-inject/macho.mjs         | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/build/sea-inject/pe.mjs            | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/build/sea-inject/verify.mjs        | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/docs/compress-cast-idle.mjs        | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/docs/process-cast-markers.mjs      | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/quality/lint-rule-liveness.mjs     | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/autopilot/exfil-tripwire.cjs       | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/autopilot/validate-handoff.cjs     | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/ci/greenlight.cjs                  | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/ci/scope-map.cjs                   | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/ci/scope-engine.cjs                | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/ci/skip-plan-reconcile.cjs         | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/ci/validate-pr.cjs                 | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/ci/watchdog-monitor.cjs            | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/ci/label-guide-comment.cjs         | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/ci/autopilot-guide-comment.cjs     | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/ci/report-nightly-status.cjs       | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/scripts/test/smoke-test-preview.ts         | full (harness)       -> reduced [gates]        <== DOWNGRADE
    .ci/tutorials/apps/heartbeat/app/heartbeat.mjs | reduced [tutorials]  -> reduced [gates]      

    DOWNGRADES: 22 of 23

So relocating the SEA injector -- the program that produces the release binary --
would stop a change to it from running the build. `check-scope-scripts-
reachability.sh` catches part of this class (its `GATED_DIRS` are
`.github/workflows`, `.ci/scripts/build`, `.ci/scripts/deploy`,
`.ci/scripts/setup`, `.ci/scripts/private`, `.ci/scripts/housekeeping`), so
sea-inject would go red; the `.ci/scripts/docs` and `.ci/scripts/quality` movers
are referenced only from `.ci/tutorials` and `.ci/scripts/quality` and would move
SILENTLY.

### 7b. The compensating rule cannot be written by this workstream right now

The fix is a scope-map rule per relocated family. Contract section 3 puts
`.ci/scripts/ci/scope-map.cjs` under "one writer at a time; every mover states
where its rule sits", and

    git status --porcelain .ci/scripts/ci/scope-map.cjs
     M .ci/scripts/ci/scope-map.cjs

says a writer already holds it (W4, adding five root allow/block lists to
`ROOT_MANIFESTS`). A second concurrent edit to a file whose rule ORDER is
semantics is exactly what that lock exists to prevent.

### 7c. `scripts/domains.json` does not exist yet, and it is the declared precondition

Contract section 5d: "W9 publishes `scripts/domains.json` FIRST, with a declared
home for each relocated family ...; W7 then relocates into those declared homes".

    ls scripts/domains.json
    ls: cannot access 'scripts/domains.json': No such file or directory

### 7d. Eleven of the 23 have readers this workstream may not edit

Measured by basename across the tree, excluding `agent/` and `docs/`:

| file | reader outside W7's write access |
|---|---|
| `ci/autopilot-guide-comment.cjs` | `.github/workflows/ci.yml` |
| `ci/label-guide-comment.cjs` | `.github/workflows/ci.yml` |
| `ci/validate-pr.cjs` | `.github/workflows/ci.yml` |
| `ci/report-nightly-status.cjs` | `.github/workflows/nightly-status.yml` |
| `ci/watchdog-monitor.cjs` | `.github/workflows/watchdog-monitor.yml` |
| `ci/scope-map.cjs` | `scripts/ci-runner/manifest.ts`, `.ci/policy/README.md`, `.gitignore` |
| `test/smoke-test-preview.ts` | `.github/workflows/ci.yml` |
| `autopilot/exfil-tripwire.cjs`, `autopilot/validate-handoff.cjs` | reached as `"$RUNNER_TEMP/harness/.ci/scripts/autopilot/autopilot-push.sh"` from `.github/workflows/autopilot.yml:743` |

Four workflows also take `sparse-checkout: .ci/scripts` (`review-status.yml`,
`ct-install-methods.yml`, `nightly-status.yml`, `profiler-probe.yml`), so a file
moved out of that prefix is simply ABSENT in those jobs.

### 7e. One of the 23 must never move at all

`.ci/tutorials/apps/heartbeat/app/heartbeat.mjs` is not tooling. It is the demo
application a tutorial deploys, twinned with
`packages/json/templates/monitoring/heartbeat/`, and it is the only one of the 23
that classifies as `reduced [tutorials]` rather than `full`. Moving it into
`scripts/` would reclassify it to `gates` and stop the tutorial job running on a
change to it. The contract's "23 JS and TS files" is a correct file count and a
misleading work item: the relocation set is 22.

### 7f. What phase 1 hands the driver instead

The homes, so W9 can adopt them into `domains.json` rather than inventing a
second partition, and the scope-map rule each one needs. Exact text is in the
W7 registry proposal handed to the driver.

| family | proposed home | scope-map rule needed |
|---|---|---|
| `sea-inject/*.mjs` (7) | `scripts/build/sea-inject/` | `matchPrefix('scripts/build/')` -> `full: 'harness'` |
| `docs/*.mjs` (2) | `scripts/docs/` | `matchPrefix('scripts/docs/')` -> `modules: ['tutorials']` |
| `quality/lint-rule-liveness.mjs` (1) | `scripts/` (with the other gate helpers) | none; `scripts-gates` is correct for it |
| `autopilot/*.cjs` (2) | `scripts/autopilot/` | `matchPrefix('scripts/autopilot/')` -> `full: 'harness'` |
| `ci/*.cjs` (9) | `scripts/ci/` | `matchPrefix('scripts/ci/')` -> `full: 'harness'` |
| `test/smoke-test-preview.ts` (1) | `scripts/test/` | `matchPrefix('scripts/test/')` -> `full: 'harness'` |
| `tutorials/.../heartbeat.mjs` (1) | STAYS. It is content. | n/a |

Each rule must sit ABOVE the blanket `{ name: 'scripts-gates', match:
matchPrefix('scripts/'), modules: ['gates'] }` at scope-map.cjs:267, because
first match wins.

---

## 8. What phase 1 did land

Two libraries ported into `rediacc_ci.core` behind delegating shims. The bash
files keep their paths, their function names, their stdout and their exit codes;
their bodies are one call into the package. Neither twin is deleted -- contract
section 3 names the conditions for that and none of them is "the Python works".

| bash entry point | implementation | proved by |
|---|---|---|
| `.ci/lib/find-port.sh` | `.ci/rediacc_ci/core/ports.py` | `.ci/scripts/quality/check-setup-idempotency.sh` (control C), 52 pytest cases |
| `.ci/scripts/lib/age-check.sh` | `.ci/rediacc_ci/core/age.py` | `.ci/scripts/test/gates/test-age-check.sh` UNCHANGED, `.ci/scripts/quality/check-go-deps.sh`, `.ci/scripts/security/audit.sh`, 17 pytest cases |

Both shims FAIL CLOSED. There is deliberately no bash fallback: a fallback is a
second implementation, and what would drift is the value deciding which port a
bookmarked devbox URL resolves to, and whether a year-old suppression is
expired. With no interpreter or no package, `source` returns non-zero having
defined nothing, so the caller gets `derive_slot: command not found`.

`REDIACC_CI_ROOT` -- the package's single environment override, from
`.ci/rediacc_ci/paths.py` -- is honoured by both shims, which is what lets a
planted-defect control point one at a MUTATED COPY of the package and prove the
delegation is real rather than decorative.
