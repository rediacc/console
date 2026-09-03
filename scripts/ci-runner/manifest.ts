/**
 * The single gate inventory both halves of the local CI runner consume.
 *
 * scripts/check-ci-parity.ts reads it as the authoritative "what the local run
 * executes" set, and scripts/ci-runner/run.ts schedules it. Before this file
 * existed both facts were encoded in one place: the 93-step `&&` string at
 * package.json `scripts.ci`. Two gates parsed that string as their input, so
 * the moment `scripts.ci` became a runner invocation they would have read an
 * empty chain and gone green over everything -- the exact failure class of
 * rediacc/console#549, at scale. See agent/PLAN-npm-ci-parallel-parity.md
 * section 6.1.
 *
 * Precedent for the shape is .ci/scripts/ci/scope-map.cjs: a hand-verified
 * lookup table plus a pure function, deliberately offline so a unit test can
 * exercise it in milliseconds.
 *
 * MAINTENANCE IS BY RULE, NOT BY HAND. A wrong or stale entry fails
 * check-ci-parity rather than rotting: assertion 5 re-verifies every declared
 * `ci` pointer against the parsed workflow, and assertion 7 compares the
 * `qualityGateTest` set against the on-disk glob run-all.sh itself uses.
 */

import fs from 'node:fs';
import path from 'node:path';

export interface GateSpec {
  /**
   * Skip the per-gate process-tree sampler for this gate. Only for gates that
   * PLANT structural defects on purpose: check:ci-resprofile's selftest spawns an
   * unreaping parent with four zombies, and the sampler caught it on the first
   * default-on run -- a correct finding on a fixture, which would have poisoned
   * the E6 fire rate in any seed. The profiler must not profile its own test.
   */
  noProfile?: boolean;
  /** npm script key, or a synthetic node id like 'build:packages'. */
  id: string;
  /** Exact command to run, and the exact rerun line printed on failure. */
  run: string;
  /**
   * false for prerequisite nodes (build:*) that validate nothing, and for the
   * CI-side aggregate check:ci-quality-gates whose 62 constituents are
   * scheduled individually. A false entry runs only when something that
   * `needs` it is in the selected set, so an aggregate with no dependents
   * never runs locally.
   */
  gate: boolean;
  /** Ordering edges: ids that must succeed first. */
  needs?: string[];
  /** Mutual-exclusion groups: no two gates sharing a group overlap. */
  mutex?: string[];
  /** Scheduler slots. Default 1. */
  weight?: number;
  /** Memory-hungry (>=4 GB heap). Bounded by --heavy-limit. */
  heavy?: boolean;
  /** Repo-relative globs this gate validates; powers --changed. */
  paths?: string[];
  /**
   * Too expensive for the pre-push lane. ABSENT MEANS FAST, deliberately: a
   * new gate is enforced before a push until someone takes it out on purpose,
   * which is the fail-safe direction. Opting out is the one mechanism -- there
   * is no second exemption file -- so the reason lives in a comment beside it.
   *
   * The threshold is measured, not judged: `.ci/cache/gate-durations.json`
   * holds per-gate timings from real runs, and check:ci-gate-manifest's tier
   * oracle asserts this field against them in BOTH directions. (It named a
   * `check:ci-gate-tiers` until 2026-09-02; no such gate has ever existed, so
   * a reader looking for the guard found nothing and could conclude the field
   * was unasserted. The guard is real, it just lives in the manifest gate.) A gate marked slow that is in
   * fact cheap fails just as loudly as the converse, because the cheap-marked-
   * slow direction is the invisible one: the push stays fast and the coverage
   * quietly shrinks.
   */
  slow?: true;
  /** Set on the 62 entries flattened out of .ci/scripts/test/gates/. Their set
   *  must equal the on-disk glob; see assertion 7 in section 6.3. */
  qualityGateTest?: boolean;
  /** Leaf commands this gate ultimately executes. The parity oracle compares
   *  these, not the npm key, because CI frequently invokes the same underlying
   *  script under a different key or by bare path. */
  leaves: string[];
  /** How CI runs this gate. See section 6 for every variant and its rules. */
  ci: CiCoverage;
}

export type CiCoverage =
  /** A workflow step runs it. Verified against the parsed workflow. */
  | { kind: 'step'; workflow: string; job: string; step: string }
  /** A gate test under .ci/scripts/test/gates/ drives its REAL scan against the
   *  REAL tree, and run-all.sh runs in CI. Requires `test` plus a BLOCKER
   *  reason naming the line that proves the real scan runs. Never inferred. */
  | { kind: 'test'; test: string; blocker: string }
  /** Deliberately local-only. Requires a BLOCKER reason. */
  | { kind: 'local-only'; blocker: string };

/**
 * NO `paths` ARE DECLARED YET, and that is the safe state. An entry without
 * `paths` must be treated by `--changed` as always selected: a partial run
 * reporting green is the vacuity failure this whole design exists to prevent,
 * so a half-populated path table would be worse than an empty one.
 *
 * TWO OMISSIONS, both deliberate:
 *   - `lint` (package.json:142) has no entry. check:lint is the same eslint
 *     invocation plus --max-warnings 0 plus a biome lint, so it strictly
 *     subsumes it, and the duplicate cost 120.9s measured (plan finding F1).
 *     The package.json key stays as a developer convenience; it just leaves the
 *     gate set.
 *   - check:ci-chain-parity and check:ci-gate-reachability are gone entirely:
 *     scripts/check-ci-parity.ts subsumes and replaces both (plan section 6.1).
 *
 * FOUR ENTRIES ARE ALSO REACHED THROUGH check:i18n: check:ci-i18n-cli-key-usage,
 * check:ci-i18n-cli-help-render, check:cli-docs and check:ci-i18n-locale-only.
 * They are listed separately anyway, because R1 requires every check:ci-* key to
 * be a manifest id and because check:i18n chains 19 leaves with `&&` so the
 * first failure hides the rest (plan section 2). The cost is that those four run
 * twice in a full local run; all four are seconds-scale.
 */
export const GATES: readonly GateSpec[] = [
  {
    id: 'check:version',
    run: 'npm run check:version',
    gate: true,
    leaves: ['scripts/check-workspace-versions.ts', 'syncpack'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Versions',
    },
  },
  {
    id: 'check:deps',
    run: 'npm run check:deps',
    slow: true, // 17.8s measured
    gate: true,
    leaves: ['scripts/check-deps.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'External dependency freshness',
    },
  },
  {
    id: 'check:lint',
    run: 'npm run check:lint',
    slow: true, // 244.9s measured
    gate: true,
    weight: 2,
    heavy: true,
    // eslint no longer runs directly: check:lint calls scripts/eslint-heap.sh,
    // which clamps the heap downward only when the host cannot honour the
    // requested size (never raises -- CI keeps its full request) and then
    // execs eslint itself. The leaf is the wrapper, not the tool it wraps.
    leaves: ['scripts/eslint-heap.sh', 'biome'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Lint',
    },
  },
  {
    id: 'lint:unused',
    run: 'npm run lint:unused',
    slow: true, // 13.4s measured
    gate: true,
    heavy: true,
    mutex: ['www-src-probe'], // see check:i18n
    leaves: ['.ci/scripts/quality/typecheck-workers.sh', 'knip'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Unused exports (knip)',
    },
  },
  {
    id: 'check:ci-knip-blockers',
    run: 'npm run check:ci-knip-blockers',
    gate: true,
    leaves: ['scripts/check-knip-blockers.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'knip BLOCKER reasons',
    },
  },
  {
    id: 'check:format',
    run: 'npm run check:format',
    gate: true,
    leaves: ['biome'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Format',
    },
  },
  {
    id: 'check:i18n',
    run: 'npm run check:i18n',
    slow: true, // 76.3s measured
    gate: true,
    // check-translation-key-usage.control.ts writes __control_probe__.tsx INTO
    // packages/www/src for the length of its run. knip (lint:unused) scanning at
    // the same moment reported it as an unused file (seen 2026-09-02 in a full
    // run). knip refuses an ignore entry for a file that is not on disk, so the
    // two are kept apart here instead.
    mutex: ['www-src-probe'],
    leaves: [
      'scripts/check-translation-hashes.ts',
      'scripts/check-translation-completeness.ts',
      'scripts/check-translation-key-usage.ts',
      'scripts/__tests__/check-translation-key-usage.control.ts',
      'scripts/__tests__/check-docs-render-parity.control.ts',
      'scripts/__tests__/check-page-locale-imports.control.ts',
      'scripts/check-cli-i18n-key-usage.ts',
      'packages/cli/scripts/check-cli-i18n-help-render.ts',
      'scripts/check-docs-inline-translations.ts',
      'scripts/check-docs-untranslated-text.ts',
      'scripts/check-account-email-templates.ts',
      'packages/www/scripts/validate-cli-docs.js',
      'packages/www/scripts/validate-docs-cli-usage.js',
      'packages/www/scripts/validate-landing-cli-usage.js',
      'packages/www/scripts/validate-translation-freshness.js',
      'packages/www/scripts/validate-content.js',
      'packages/www/scripts/validate-content-accuracy.js',
      'packages/www/scripts/validate-comparison-refs.js',
      'scripts/check-component-hardcoded-strings.ts',
      'scripts/check-cli-docs.ts',
      'scripts/check-i18n-naturalization.ts',
      'scripts/check-locale-only-edits.ts',
      'scripts/check-i18n-ledger-growth.ts',
      'scripts/check-dead-translation-keys.ts',
      'scripts/check-em-dash-surfaces.ts',
      'packages/www/scripts/check-client-i18n-freshness.ts',
      'scripts/check-locale-currency-integrity.ts',
      'scripts/__tests__/check-locale-currency-integrity.control.ts',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-cli-key-usage',
    run: 'npm run check:ci-i18n-cli-key-usage',
    gate: true,
    leaves: ['scripts/check-cli-i18n-key-usage.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-cli-help-render',
    run: 'npm run check:ci-i18n-cli-help-render',
    gate: true,
    leaves: ['packages/cli/scripts/check-cli-i18n-help-render.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:cli-docs',
    run: 'npm run check:cli-docs',
    gate: true,
    leaves: ['scripts/check-cli-docs.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-locale-currency',
    run: 'npm run check:ci-locale-currency',
    gate: true,
    leaves: [
      'scripts/check-locale-currency-integrity.ts',
      'scripts/__tests__/check-locale-currency-integrity.control.ts',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-locale-only',
    run: 'npm run check:ci-i18n-locale-only',
    gate: true,
    leaves: ['scripts/check-locale-only-edits.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-ledger-growth',
    run: 'npm run check:ci-i18n-ledger-growth',
    gate: true,
    leaves: ['scripts/check-i18n-ledger-growth.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // Split out of check:i18n so a CI label can skip exactly the tutorial-media
  // validators without skipping the rest of the i18n surface. Deliberately NOT
  // chained back into check:i18n -- chaining it would undo the split -- so this
  // manifest entry is the only thing that keeps it reachable from `npm run ci`.
  // The comment sits ABOVE the brace on purpose: wl_reggate.py's
  // _manifest_gate_ids matches /\{\s*id:/, so a comment INSIDE the brace makes the
  // entry invisible to check:ci-gate-reachability-coverage.
  {
    id: 'check:ci-i18n-media',
    run: 'npm run check:ci-i18n-media',
    gate: true,
    leaves: [
      'packages/www/scripts/validate-tutorial-transcripts.js',
      'packages/www/scripts/validate-tutorial-audio.js',
      'packages/www/scripts/validate-tutorial-cast-output.js',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Tutorial media',
    },
  },
  {
    id: 'check:ci-rubric-calibration',
    run: 'npm run check:ci-rubric-calibration',
    gate: true,
    leaves: ['.ci/scripts/quality/check-rubric-calibration.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Rubric calibration',
    },
  },
  {
    id: 'check:ci-www-build-token',
    run: 'npm run check:ci-www-build-token',
    gate: true,
    leaves: ['.ci/scripts/quality/check-www-build-token.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'www build token',
    },
  },
  {
    id: 'check:ci-shape-duplication',
    run: 'npm run check:ci-shape-duplication',
    // 1.9s measured on a quiet machine, five samples. The 21.4s this entry used
    // to claim was a contended sample; the tier oracle judges the floor of
    // `recent` for exactly that reason.
    gate: true,
    leaves: ['scripts/check-shape-duplication.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Shape duplication',
    },
  },
  {
    id: 'check:ci-fetch-retry',
    run: 'npm run check:ci-fetch-retry',
    gate: true,
    leaves: ['.ci/scripts/quality/check_fetch_retry.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Fetch retry',
    },
  },
  {
    id: 'check:ci-judged-rule-wiring',
    run: 'npm run check:ci-judged-rule-wiring',
    gate: true,
    leaves: ['.ci/scripts/quality/check_judged_rule_wiring.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Judged rule wiring',
    },
  },
  {
    id: 'check:ci-review-prompt-render',
    run: 'npm run check:ci-review-prompt-render',
    gate: true,
    leaves: ['.ci/scripts/quality/check_review_prompt_render.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Review prompt render',
    },
  },
  {
    id: 'check:ci-git-history-depth',
    run: 'npm run check:ci-git-history-depth',
    gate: true,
    leaves: ['.ci/scripts/quality/check_git_history_depth.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Git history depth',
    },
  },
  {
    id: 'check:ci-typecheck-scope-coverage',
    run: 'npm run check:ci-typecheck-scope-coverage',
    slow: true, // 17.7s: `tsc --showConfig` on all 13 projects, twice (selftest + real run)
    gate: true,
    leaves: ['scripts/check-typecheck-scope-coverage.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Typecheck scope coverage',
    },
  },
  {
    id: 'check:types',
    run: 'npm run check:types',
    slow: true, // 51.4s contended (tsc over every workspace)
    gate: true,
    mutex: ['build-artifacts'],
    heavy: true,
    leaves: ['tsc', '.ci/scripts/quality/typecheck-workers.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'TypeScript',
    },
  },
  {
    id: 'check:ci-tutorial-healthcheck-headroom',
    run: 'npm run check:ci-tutorial-healthcheck-headroom',
    gate: true,
    leaves: ['.ci/scripts/quality/check_tutorial_healthcheck_headroom.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Tutorial healthcheck headroom',
    },
  },
  {
    id: 'check:ci-guard-mutations',
    run: 'npm run check:ci-guard-mutations',
    slow: true, // 25.4s measured
    gate: true,
    weight: 2,
    heavy: true,
    leaves: ['scripts/check-guard-mutations.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Guard mutations',
    },
  },
  {
    id: 'check:test-cli',
    run: 'npm run check:test-cli',
    slow: true, // 38.3s measured
    gate: true,
    weight: 2,
    heavy: true,
    leaves: ['vitest'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Run CLI unit tests',
    },
  },
  // `Run shared package tests` has run in CI for a long time with NO manifest
  // entry, so `npm run ci` never ran packages/shared's tests locally: CI caught
  // them, a pre-push run did not. The parity gate could not see the hole
  // because R2 only matches `.ci/scripts/**` leaves and a bare vitest is not
  // one. Both entries below close that, and are `check:test-*` rather than
  // `check:ci-*` because R1 only demands manifest membership for the latter.
  {
    id: 'check:test-shared',
    run: 'npm run check:test-shared',
    gate: true,
    weight: 2,
    heavy: true,
    leaves: ['vitest'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Run shared package tests',
    },
  },
  {
    id: 'check:test-www',
    run: 'npm run check:test-www',
    gate: true,
    leaves: ['vitest'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Run www unit tests',
    },
  },
  {
    // Was defined in package.json but referenced nowhere: never ran in CI, and
    // failed locally against its own 60s dev-server-boot timeout the first
    // time it was actually invoked (a cold `astro dev` measured 84s). Fixed
    // the timeout (packages/www/scripts/test-tutorial-player-release-gate.js)
    // alongside wiring this in.
    id: 'check:test:tutorial-player',
    run: 'npm run check:test:tutorial-player',
    slow: true, // spins up a real astro dev server; measured ~90s+ cold
    gate: true,
    leaves: ['packages/www/scripts/test-tutorial-player-release-gate.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Tutorial player release gate',
    },
  },
  // A FOURTH www-dist consumer, which the plan's F5 list did not have.
  // workers/www/src/__tests__/redirect-aliases.test.ts:3 statically imports
  // packages/www/dist/route-manifest.json. `astro build` empties dist before
  // repopulating it, so under parallelism this read the emptied directory and
  // died with "Cannot find module ../../../../packages/www/dist/route-manifest.json".
  // It passed at --jobs 1 only because dist happened to be left populated by an
  // earlier build, so the missing edge was latent in the serial world too. The
  // `ci` pointer below already recorded the truth: CI runs it in the lane that
  // builds www first.
  {
    id: 'check:test-workers',
    run: 'npm run check:test-workers',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    needs: ['build:www'],
    leaves: ['vitest'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Worker unit tests (workers/www)',
    },
  },
  {
    id: 'check:ci-install-sh-config',
    run: 'npm run check:ci-install-sh-config',
    gate: true,
    leaves: ['.ci/scripts/test/test-install-sh-config.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'install.sh config tests',
    },
  },
  {
    id: 'check:ci-rdc-sh-env',
    run: 'npm run check:ci-rdc-sh-env',
    gate: true,
    leaves: ['.ci/scripts/test/test-rdc-sh-env.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'rdc.sh env tests',
    },
  },
  {
    id: 'check:ci-probe-parity',
    run: 'npm run check:ci-probe-parity',
    gate: true,
    leaves: ['.ci/scripts/quality/check-probe-parity.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Capability-probe parity',
    },
  },
  {
    id: 'check:ci-drill-verdicts',
    run: 'npm run check:ci-drill-verdicts',
    gate: true,
    leaves: ['.ci/scripts/quality/check-drill-verdicts.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Drill verdict logic',
    },
  },
  {
    id: 'check:ci-account-probes',
    run: 'npm run check:ci-account-probes',
    gate: true,
    leaves: ['.ci/scripts/quality/check-account-probes.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Dev-stack liveness probes',
    },
  },
  {
    id: 'check:ci-npmrc',
    run: 'npm run check:ci-npmrc',
    gate: true,
    leaves: ['.ci/scripts/quality/check-npmrc.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Block legacy-peer-deps workarounds',
    },
  },
  {
    id: 'check:ci-setup-idempotency',
    run: 'npm run check:ci-setup-idempotency',
    gate: true,
    paths: ['.ci/lib/**', 'run.sh', '.ci/scripts/quality/check-setup-idempotency.sh'],
    leaves: ['.ci/scripts/quality/check-setup-idempotency.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Setup path idempotency',
    },
  },
  {
    // The other half of check:ci-npmrc: that gate keeps ignore-scripts=true set,
    // this one keeps every root-workspace installer pairing it with a rebuild.
    id: 'check:ci-native-rebuild',
    run: 'npm run check:ci-native-rebuild',
    gate: true,
    leaves: ['scripts/check-native-rebuild.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Native modules rebuilt after every root install',
    },
  },
  {
    // Guards the ONE module allowed to drive a force push. It reaches git via
    // subprocess, which the pre-bash guards structurally cannot see, so this
    // static check is the only thing watching it.
    id: 'check:ci-git-tool-safety',
    run: 'npm run check:ci-git-tool-safety',
    gate: true,
    leaves: ['scripts/check-git-tool-safety.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Mediated git tool stays lease-only and dry-run by default',
    },
  },
  {
    // ./run.sh setup is run repeatedly, so a second run must do no work. This
    // asserts every bootstrap entry point installs through ensure_deps' hash
    // stamp rather than shelling out to npm itself.
    id: 'check:ci-bootstrap-idempotency',
    run: 'npm run check:ci-bootstrap-idempotency',
    gate: true,
    leaves: ['scripts/check-bootstrap-idempotency.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Bootstrap paths install through the dependency stamp',
    },
  },
  {
    // Every commit must name the epic it belongs to, because the review selects
    // an epic's commits by trailer. An untagged commit is reviewed by nobody.
    id: 'check:ci-pr-task-trailers',
    run: 'npm run check:ci-pr-task-trailers',
    gate: true,
    leaves: ['scripts/check-pr-task-trailers.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Every commit names its epic',
    },
  },
  {
    // A guard's refusal message is the last thing a session reads before
    // changing course. It must not prescribe a merge method the platform
    // rejects: allow_squash_merge is false on all five repos.
    id: 'check:ci-merge-method-prose',
    run: 'npm run check:ci-merge-method-prose',
    gate: true,
    leaves: ['scripts/check-merge-method-prose.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Instruction files do not prescribe a rejected merge method',
    },
  },
  {
    // A .ci script must declare the non-baseline binaries it runs. An
    // undeclared one exits 127 with no message under `set -euo pipefail`, and
    // reads as working code on any host that happens to have it.
    id: 'check:ci-shell-declared-commands',
    run: 'npm run check:ci-shell-declared-commands',
    gate: true,
    leaves: ['scripts/check-shell-declared-commands.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'CI scripts declare the binaries they execute',
    },
  },
  {
    // The PR body carries a generated epic block; this asserts it matches the
    // published snapshot, since a generated section nobody checks drifts while
    // still looking authoritative.
    id: 'check:ci-pr-epic-block',
    run: 'npm run check:ci-pr-epic-block',
    gate: true,
    leaves: ['scripts/check-pr-epic-block.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'PR epic block matches the published worklist',
    },
  },
  {
    id: 'check:ci-control-vacuity',
    run: 'npm run check:ci-control-vacuity',
    gate: true,
    paths: ['.ci/scripts/quality/**'],
    leaves: ['.ci/scripts/quality/check-control-vacuity.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Control-first gates prove their plant landed',
    },
  },
  {
    id: 'check:ci-devcontainer-scripts',
    run: 'npm run check:ci-devcontainer-scripts',
    gate: true,
    paths: ['.devcontainer/**', '.ci/scripts/quality/check-devcontainer-scripts.sh'],
    leaves: ['.ci/scripts/quality/check-devcontainer-scripts.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Devcontainer script stderr visibility',
    },
  },
  {
    id: 'check:ci-shell-size',
    run: 'npm run check:ci-shell-size',
    gate: true,
    // Any shell file anywhere can grow into the linter-killing range, so this
    // one is deliberately not path-narrowed.
    paths: ['**/*.sh'],
    leaves: ['.ci/scripts/quality/check-shell-size.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Shell file size',
    },
  },
  {
    id: 'check:ci-devbox-exec',
    run: 'npm run check:ci-devbox-exec',
    gate: true,
    // The lane library and anything that could add a call site to it. Narrow on
    // purpose: this gate reasons about devbox.sh's own invocations, and a wider
    // path filter would imply a coverage it does not have.
    paths: ['.ci/lib/devbox.sh', '.ci/scripts/quality/check-devbox-exec.sh'],
    leaves: ['.ci/scripts/quality/check-devbox-exec.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Devbox exec invocation',
    },
  },
  {
    id: 'check:ci-toolchain-pins',
    run: 'npm run check:ci-toolchain-pins',
    slow: true, // 26.7s measured
    gate: true,
    // Triggers on every surface that could restate a pin or acquire a tool
    // unpinned, so a version added back into a workflow or the Dockerfile
    // cannot slip past on an unrelated path filter.
    paths: [
      '.devcontainer/**',
      '.github/workflows/**',
      '.ci/scripts/**',
      '.ci/config/constants.sh',
      'run.sh',
    ],
    leaves: ['.ci/scripts/quality/check-toolchain-pins.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Toolchain pins',
    },
  },
  {
    // check-toolchain-pins.sh's A1 deliberately EXEMPTS GO_VERSION/NODE_VERSION
    // from its single-source check (they legitimately appear elsewhere: go.mod,
    // third-party action inputs) -- which also removes any check that the TWO
    // files meant to carry the identical value on purpose (toolchain.env and the
    // Dockerfile's matching ARG) actually do. This is that narrower check.
    id: 'check:ci-toolchain-env-dockerfile-sync',
    run: 'npm run check:ci-toolchain-env-dockerfile-sync',
    gate: true,
    paths: [
      '.devcontainer/toolchain.env',
      '.devcontainer/Dockerfile',
      '.ci/scripts/quality/check-toolchain-env-dockerfile-sync.sh',
    ],
    leaves: ['.ci/scripts/quality/check-toolchain-env-dockerfile-sync.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Toolchain env/Dockerfile sync',
    },
  },
  {
    id: 'check:ci-host-toolchain-coverage',
    run: 'npm run check:ci-host-toolchain-coverage',
    gate: true,
    // The pinned-tools DEFINITION (check-toolchain-pins.sh's GATED_TOOLS) and the
    // host-toolchain runtime GUARD's call sites (block-host-toolchain-run.sh's
    // NPX_TOOLS/BARE_TOOLS) are two independently maintained lists. Either
    // surface changing is when they can drift.
    paths: [
      '.ci/scripts/quality/check-toolchain-pins.sh',
      '.claude/hooks/pre-bash/block-host-toolchain-run.sh',
      '.ci/scripts/quality/check-host-toolchain-coverage.sh',
    ],
    leaves: ['.ci/scripts/quality/check-host-toolchain-coverage.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Host toolchain runtime coverage',
    },
  },
  {
    id: 'check:ci-git-op-conditionals',
    run: 'npm run check:ci-git-op-conditionals',
    gate: true,
    // Scoped to .claude/hooks and .ci/scripts/quality, where the two real
    // defects lived (a git identity capture guarded against empty but not
    // against rev-parse --abbrev-ref HEAD's misleading literal "HEAD" on a
    // detached checkout, in both an assignment and a bare-statement shape).
    paths: ['.claude/hooks/**/*.sh', '.ci/scripts/quality/*.sh'],
    leaves: ['.ci/scripts/quality/check-git-op-conditionals.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Git-op conditional guards',
    },
  },
  {
    // Console's own scripts already use the right shape -- toolchain.sh installs
    // with GOBIN and invokes by absolute path, which is why check:ci-shell-format
    // passes on a host with no shfmt on PATH. This gate exists so that stays
    // true: the defect it names cost four instances in the renet submodule on
    // 2026-08-27, each one a `go install` followed by a bare invocation, and CI
    // could not see any of them because actions/setup-go masks it.
    id: 'check:ci-go-tool-path',
    run: 'npm run check:ci-go-tool-path',
    gate: true,
    paths: ['.ci/**', 'scripts/**'],
    leaves: ['.ci/scripts/quality/check-go-tool-path.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Go tool PATH',
    },
  },
  {
    // The gap check:ci-parity leaves open: it proves a gate is WIRED into a
    // workflow, never that the job it landed in can RUN it. Two tsx gates were
    // added to a job that does checkout and nothing else, and run 33125687081
    // died on `tsx: not found` and took seven cancelled siblings with it.
    // Verified against the pre-fix workflow: this reports exactly those two.
    id: 'check:ci-gate-prerequisites',
    run: 'npm run check:ci-gate-prerequisites',
    gate: true,
    // packages/*/package.json and workers/*/package.json joined 2026-08-30:
    // the resolver now follows `npm run <key> -w <workspace>` into that
    // workspace's OWN scripts (needed to find check:test:tutorial-player's
    // real agent-browser dependency, two hops past root's package.json).
    paths: [
      '.github/workflows/**',
      'package.json',
      'packages/*/package.json',
      'workers/*/package.json',
      '.ci/scripts/quality/**',
    ],
    leaves: ['.ci/scripts/quality/check_ci_gate_prerequisites.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Gate prerequisites',
    },
  },
  {
    // Found by hand three times in one session (2026-08-28: 891ff49db,
    // 946e0e6da, 74114a26b) before this existed: a script preferring
    // PR_HEAD_REF, invoked by a workflow step that never set it. On this
    // repo's workflow_call chain the runner's default GITHUB_HEAD_REF does
    // not reliably materialise, so the gap is silent -- a skipped check or a
    // degraded one, never a crash.
    id: 'check:ci-pr-head-ref-completeness',
    run: 'npm run check:ci-pr-head-ref-completeness',
    gate: true,
    paths: ['.github/workflows/**', 'package.json', '.ci/scripts/**', 'scripts/**'],
    leaves: ['.ci/scripts/quality/check_pr_head_ref_completeness.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'PR_HEAD_REF completeness',
    },
  },
  {
    // A guard that refuses PROSE is a guard nobody can write a doc line about.
    // The class recurred FOUR times on 2026-08-28 and every instance was fixed
    // by hand, including one reintroduced within the hour by the session doing
    // the fixing -- which is the i18n lesson exactly. This probes each guard
    // with a sentence built from its OWN pattern, so it cannot go stale as
    // guards are added.
    id: 'check:ci-guard-mention-anchoring',
    run: 'npm run check:ci-guard-mention-anchoring',
    gate: true,
    // The script scans all 3 chains (pre-bash, pre-edit, pre-ask) since the
    // peer's extension on 2026-08-28; this list had stayed pre-bash-only, the
    // exact "half-populated path table" anti-pattern gate-author.md warns
    // against -- a guard added under pre-edit/pre-ask would not have
    // re-selected this gate on --changed.
    paths: [
      '.claude/hooks/pre-bash/**',
      '.claude/hooks/pre-edit/**',
      '.claude/hooks/pre-ask/**',
      '.ci/scripts/quality/check_guard_mention_anchoring.py',
    ],
    leaves: ['.ci/scripts/quality/check_guard_mention_anchoring.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Guard mention anchoring',
    },
  },
  {
    // The manifest is the pre-push lane's only source of truth about which
    // gates are cheap and which files select them, and nothing re-reads it.
    // Three oracles, each with both directions in --selftest: a `slow` claim
    // must agree with the measured cache BOTH ways (a cheap gate marked slow
    // is the invisible direction -- the push stays fast while coverage
    // shrinks); a gate declaring paths must include its own leaves, or editing
    // the gate does not select the gate; and a declared glob must match at
    // least one tracked file. Found eight live leaf violations and one
    // mis-tiered gate on its first run.
    id: 'check:ci-gate-manifest',
    run: 'npm run check:ci-gate-manifest',
    gate: true,
    paths: ['scripts/ci-runner/**', 'scripts/check-gate-manifest.ts'],
    leaves: ['scripts/check-gate-manifest.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Gate manifest self-consistency',
    },
  },
  {
    // TRAPS.md is a REGISTRY, not prose: every `## ` entry names the instrument
    // that enforces it, and the gate proves that pointer RESOLVES and is LIVE.
    // Presence alone would be worse than nothing -- the cheapest thing to name
    // under a coverage gate is a check that cannot fire -- so a gate: pointer
    // must be scheduled by `npm run ci`, a hook: rule must have both a firing
    // and a silent case, and a file: pointer must be reachable from something
    // that runs it. No `paths`, deliberately: pointers resolve against the
    // manifest, package.json, the dispatcher, the hook suite and settings.json,
    // so almost any change can dangle one, and a half-populated path table
    // would drop the gate from --changed exactly when it was needed.
    id: 'check:ci-trap-registry',
    run: 'npm run check:ci-trap-registry',
    gate: true,
    leaves: ['.ci/scripts/quality/check-trap-registry.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Trap registry dispositions',
    },
  },
  {
    // The runner's 21 assertions were its ONLY controls and ran on ONE side:
    // `npm run ci` executes them on a developer machine and nothing in CI did,
    // which is the "a gate that runs on one side only" case check:ci-parity
    // exists to name. They pin the pre-push lane's correctness -- glob
    // semantics (a `**` glob must match a root-level run.sh), gitlink widening (a
    // changed submodule is one diff entry, not a file list), and that --list
    // reflects the SELECTION rather than every spec -- each with its converse.
    id: 'check:ci-runner-selftest',
    run: 'npm run check:ci-runner-selftest',
    gate: true,
    // The leaf must be inside the paths, or editing the runner does not select
    // the gate that checks the runner (check:ci-gate-manifest asserts this).
    paths: ['scripts/ci-runner/**'],
    leaves: ['scripts/ci-runner/run.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'CI runner selftest',
    },
  },
  {
    id: 'check:ci-hook-integrity',
    run: 'npm run check:ci-hook-integrity',
    gate: true,
    // Triggers on the enforcement layer itself and on the coverage it is
    // judged by, so weakening a guard and dropping its cases in one commit
    // cannot slip through on an unrelated path filter.
    paths: [
      '.claude/hooks/**',
      'scripts/data/hook-inventory-baseline.json',
      'scripts/data/hook-coverage-baseline.json',
      '.ci/scripts/quality/check-hook-integrity.sh',
    ],
    leaves: ['.ci/scripts/quality/check-hook-integrity.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Hook integrity',
    },
  },
  {
    // A detector built as `producer | grep -q` under pipefail cannot reliably
    // fail: grep -q exits at its first match, SIGPIPEs the producer, and
    // pipefail makes that 141 the verdict. check-ci-watch-recipe.sh shipped
    // exactly that in both detectors and certified 124 files clean over a real
    // offender for as long as it existed.
    id: 'check:ci-pipefail-grep-q',
    run: 'npm run check:ci-pipefail-grep-q',
    slow: true, // 13.5s standalone / 37.0s contended: it greps every shell file twice
    gate: true,
    paths: ['.ci/scripts/**', 'scripts/**', '.claude/hooks/**'],
    leaves: ['.ci/scripts/quality/check-pipefail-grep-q.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'No racing pipefail/grep -q detectors',
    },
  },
  {
    id: 'check:ci-watch-recipe',
    run: 'npm run check:ci-watch-recipe',
    gate: true,
    // The defect lives in PROSE agents copy, so the trigger set is the prose,
    // not the code: every instruction surface that has ever carried the loop.
    paths: [
      '.claude/skills/ci-watch/**',
      '.claude/commands/**',
      '.claude/agents/**',
      '.claude/hooks/**',
      'docs/agent-reference/**',
      '.ci/scripts/quality/check-ci-watch-recipe.sh',
    ],
    leaves: ['.ci/scripts/quality/check-ci-watch-recipe.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'CI-watch recipe has one source',
    },
  },
  {
    id: 'check:ci-cli-doc-coverage',
    run: 'npm run check:ci-cli-doc-coverage',
    gate: true,
    // The pairs it checks: ci-trace.py against its skill, run.ts against
    // ci-gates.md. Trigger on either script or either doc changing.
    paths: [
      '.ci/scripts/ci/ci-trace.py',
      '.claude/skills/ci-watch/**',
      'scripts/ci-runner/run.ts',
      'docs/agent-reference/ci-gates.md',
      '.ci/scripts/quality/check-cli-doc-coverage.sh',
    ],
    leaves: ['.ci/scripts/quality/check-cli-doc-coverage.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: "CLI docs stay in sync with their scripts' real flags",
    },
  },
  {
    id: 'check:ci-ceph-image-pin',
    run: 'npm run check:ci-ceph-image-pin',
    gate: true,
    leaves: ['scripts/check-ceph-image-pin.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Ceph image pin freshness',
    },
  },
  {
    id: 'check:ci-naturalization-model-policy',
    run: 'npm run check:ci-naturalization-model-policy',
    gate: true,
    leaves: ['scripts/check-naturalization-model-policy.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Naturalization model policy',
    },
  },
  {
    id: 'check:ci-script-exec-bit',
    run: 'npm run check:ci-script-exec-bit',
    slow: true, // 22.1s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check-script-exec-bit.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Block non-executable invoked scripts',
    },
  },
  {
    id: 'check:ci-lockfile',
    run: 'npm run check:ci-lockfile',
    slow: true, // 52.3s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check-lockfile.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Lockfile',
    },
  },
  {
    id: 'check:ci-peer-deps',
    run: 'npm run check:ci-peer-deps',
    gate: true,
    leaves: ['.ci/scripts/quality/check-peer-deps.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Verify no peer dependency conflicts',
    },
  },
  {
    id: 'check:ci-security-audit',
    run: 'npm run check:ci-security-audit',
    slow: true, // 60.9s measured
    gate: true,
    leaves: ['.ci/scripts/security/audit.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Audit',
    },
  },
  {
    id: 'check:ci-scope-scripts-reachability',
    run: 'npm run check:ci-scope-scripts-reachability',
    slow: true, // 24.3s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check-scope-scripts-reachability.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Scope map — reachable scripts/ paths force full CI',
    },
  },
  {
    id: 'check:ci-mutate-check',
    run: 'npm run check:ci-mutate-check',
    gate: true,
    leaves: ['.ci/scripts/quality/check-mutate-check.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Mutation runner self-test',
    },
  },
  // The 675-assertion suite behind the stop hook. check:ci-mutate-check does
  // NOT cover this: it drives a miniature fixture-suite.sh to prove the
  // MUTATION RUNNER still reports four verdicts, and never runs the real suite.
  // So until this entry the hook logic was gated by nothing, and a hand fix to
  // it could regress silently -- which is exactly how the dead i18n rules
  // survived. `heavy` because it is minutes, not seconds.
  {
    id: 'check:ci-hook-worklist-suite',
    run: 'npm run check:ci-hook-worklist-suite',
    slow: true, // 460.3s measured
    gate: true,
    weight: 2,
    heavy: true,
    leaves: ['.claude/hooks/stop/test-worklist-v5.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Stop-hook worklist suite',
    },
  },
  {
    id: 'check:ci-shell-lint',
    run: 'npm run check:ci-shell-lint',
    slow: true, // 124.0s measured
    gate: true,
    leaves: ['.ci/scripts/security/shellcheck.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Shell lint',
    },
  },
  {
    id: 'check:ci-shell-format',
    run: 'npm run check:ci-shell-format',
    gate: true,
    leaves: ['.ci/scripts/security/shfmt.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Shell format',
    },
  },
  {
    id: 'check:ci-python-lint',
    run: 'npm run check:ci-python-lint',
    gate: true,
    leaves: ['.ci/scripts/quality/check-python-lint.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Python lint + format (ruff)',
    },
  },
  {
    id: 'check:ci-bws-map',
    run: 'npm run check:ci-bws-map',
    gate: true,
    leaves: ['.ci/scripts/quality/check_bws_map.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Bitwarden secret map',
    },
  },
  // Offline by construction: it compares .ci/config/actions-allowlist.json, a
  // committed copy of repository settings, against every `uses:` line. The network
  // lives only in --refresh, for the same reason check_secret_reachability splits
  // them -- a gate that needs a token degrades to "passed" where the token is absent.
  {
    id: 'check:ci-actions-allowlist',
    run: 'npm run check:ci-actions-allowlist',
    gate: true,
    paths: [
      '.github/workflows/*.yml',
      '.github/actions/**/action.yml',
      '.ci/breakpoint/workflow/*.yml',
      '.ci/config/actions-allowlist.json',
      '.ci/scripts/quality/check_actions_allowlist.py',
    ],
    leaves: ['.ci/scripts/quality/check_actions_allowlist.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Actions allowlist',
    },
  },
  // quality-i18n is the ONLY lane with fetch-depth 0 that also runs on the
  // nightly, and this gate needs both: shallow makes it vacuous (see its header),
  // and a clock-driven gate that never runs on a schedule first surfaces by
  // ambushing an unrelated PR. It is a TENANT of that lane, not an i18n gate.
  {
    id: 'check:ci-plan-housekeeping',
    run: 'npm run check:ci-plan-housekeeping',
    gate: true,
    paths: [
      'agent/PLAN-*.md',
      '.ci/config/plan-lifecycle.json',
      '.plan-housekeeping-allowlist',
      '.ci/scripts/quality/check-plan-housekeeping.sh',
    ],
    leaves: ['.ci/scripts/quality/check-plan-housekeeping.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Plan file housekeeping',
    },
  },
  // The comment sits ABOVE the brace deliberately: wl_reggate._manifest_gate_ids
  // matches /\{\s*id:/, so a comment INSIDE the brace makes the entry invisible to
  // check:ci-gate-reachability-coverage (manifest.ts:322 records that trap).
  // Lane: quality-branch. A1-A5 compare the merge-base ledger against HEAD, and
  // that is the only lane with BOTH fetch-depth 0 and the PR head ref. It is
  // pull_request-only, so A1-A5 do not run on push -- the gate says so rather
  // than letting a skip read as a clean result.
  {
    id: 'check:ci-resprofile',
    noProfile: true,
    run: 'npm run check:ci-resprofile',
    // Judges the PREVIOUS run's process-tree captures (rotated by this runner at
    // start), so it never reads a torn file. Pristine until the baseline is seeded.
    gate: true,
    leaves: ['.ci/scripts/quality/check_resprofile.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-branch',
      step: "Resource profile (previous run's captures)",
    },
  },
  {
    id: 'check:ci-plan-boxes',
    run: 'npm run check:ci-plan-boxes',
    gate: true,
    paths: [
      'agent/PLAN-*.md',
      '.ci/config/plan-boxes.json',
      '.ci/scripts/quality/check_plan_boxes.py',
    ],
    leaves: ['.ci/scripts/quality/check_plan_boxes.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-branch',
      step: 'Plan checkbox ledger',
    },
  },
  {
    id: 'check:ci-syncpack-sources',
    run: 'npm run check:ci-syncpack-sources',
    gate: true,
    paths: [
      '.syncpackrc.json',
      '.ci/config/syncpack-source-exclusions.json',
      '.ci/scripts/quality/check_syncpack_sources.py',
      '**/package.json',
    ],
    leaves: ['.ci/scripts/quality/check_syncpack_sources.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'syncpack source coverage',
    },
  },
  {
    id: 'check:ci-secret-reachability',
    run: 'npm run check:ci-secret-reachability',
    gate: true,
    leaves: ['.ci/scripts/quality/check_secret_reachability.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Secret reachability',
    },
  },
  {
    id: 'check:ci-scope-completeness',
    run: 'npm run check:ci-scope-completeness',
    gate: true,
    leaves: ['.ci/scripts/quality/check_scope_completeness.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Scope completeness',
    },
  },
  {
    id: 'check:ci-hooks-resolvable',
    run: 'npm run check:ci-hooks-resolvable',
    gate: true,
    leaves: ['.ci/scripts/quality/check_hooks_resolvable.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Hooks resolvable',
    },
  },
  {
    id: 'check:ci-guard-feature-completeness',
    run: 'npm run check:ci-guard-feature-completeness',
    gate: true,
    paths: ['.claude/hooks/**', '.ci/scripts/quality/check_guard_feature_completeness.py'],
    leaves: ['.ci/scripts/quality/check_guard_feature_completeness.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Guard feature completeness',
    },
  },
  {
    // An apt source rewritten to ONE mirror must carry a fallback to another.
    // Born 2026-08-19, when azure.archive.ubuntu.com refused connections for
    // ninety minutes and took down four consecutive CI attempts: every apt
    // source had been rewritten to that single host, so the surrounding
    // five-attempt retry loop hammered the same dead mirror five times.
    // Existing checks counted retry ATTEMPTS and never asked whether the
    // attempts could reach a different SOURCE, which is why nothing caught it.
    id: 'check:ci-dockerfile-mirror-resilience',
    run: 'npm run check:ci-dockerfile-mirror-resilience',
    gate: true,
    leaves: ['.ci/scripts/quality/check_dockerfile_mirror_resilience.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Dockerfile mirror resilience',
    },
  },
  {
    id: 'check:ci-workflow-submodule-deps',
    run: 'npm run check:ci-workflow-submodule-deps',
    gate: true,
    leaves: ['.ci/scripts/quality/check_workflow_submodule_deps.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Workflow submodule deps',
    },
  },
  {
    id: 'check:ci-python-gate-deps',
    run: 'npm run check:ci-python-gate-deps',
    gate: true,
    leaves: ['.ci/scripts/quality/check_python_gate_deps.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Python gate deps',
    },
  },
  {
    id: 'check:ci-tutorial-cli-validity',
    run: 'npm run check:ci-tutorial-cli-validity',
    gate: true,
    leaves: ['.ci/scripts/quality/check_tutorial_cli_validity.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Tutorial CLI validity',
    },
  },
  {
    id: 'check:ci-e2e-case-blind',
    run: 'npm run check:ci-e2e-case-blind',
    gate: true,
    leaves: ['.ci/scripts/quality/check_e2e_case_blind_assertions.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'E2E case-blind assertions',
    },
  },
  {
    id: 'check:ci-tutorial-no-skips',
    run: 'npm run check:ci-tutorial-no-skips',
    gate: true,
    leaves: ['.ci/scripts/quality/check_tutorial_no_skips.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Tutorials cannot skip themselves',
    },
  },
  {
    id: 'check:ci-dead-service-methods',
    run: 'npm run check:ci-dead-service-methods',
    gate: true,
    leaves: ['scripts/check-dead-service-methods.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Dead service methods',
    },
  },
  {
    id: 'check:ci-retired-commands',
    run: 'npm run check:ci-retired-commands',
    gate: true,
    leaves: ['scripts/check-retired-commands-in-docs.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Retired commands in docs',
    },
  },
  {
    id: 'check:ci-timeout-headroom',
    run: 'npm run check:ci-timeout-headroom',
    gate: true,
    leaves: ['.ci/scripts/quality/check_job_timeout_headroom.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'CI job timeout headroom',
    },
  },
  {
    id: 'check:ci-runner-advice',
    run: 'npm run check:ci-runner-advice',
    gate: true,
    leaves: ['.ci/scripts/quality/check_runner_advice.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Runner sizing advice',
    },
  },
  {
    id: 'check:ci-no-inline-python',
    run: 'npm run check:ci-no-inline-python',
    gate: true,
    leaves: ['.ci/scripts/quality/check_inline_python.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'No inline Python in JS/TS',
    },
  },
  {
    id: 'check:ci-i18n-value-types',
    run: 'npm run check:ci-i18n-value-types',
    gate: true,
    leaves: ['.ci/scripts/quality/check_i18n_value_types.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'i18n value types match English',
    },
  },
  {
    id: 'check:ci-lint-rule-liveness',
    run: 'npm run check:ci-lint-rule-liveness',
    slow: true, // 30.6s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check_lint_rule_liveness.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Enabled lint rules can actually fire',
    },
  },
  {
    id: 'check:ci-agent-hint-liveness',
    run: 'npm run check:ci-agent-hint-liveness',
    gate: true,
    leaves: ['.ci/scripts/quality/check_agent_hint_liveness.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Agent hints can actually fire',
    },
  },
  // Answers the question the other two wiring gates cannot: not "is what we
  // declared wired up?" but "did we forget to declare something?". A test file
  // absent from the manifest is absent from BOTH sides of ci-parity, so parity
  // agrees and reports success; gate-reachability can only ask about entries
  // that registered. test-teammate-idle.py was committed with 20 controls and
  // ran nowhere, and this gate then found four more orphans of the same shape.
  // Gate 1 of the sentence-wrapping pair. Source-level and sub-second, so it runs on
  // every PR; the browser half (check:ci-sentence-lines) measures real line boxes and
  // needs a build. Neither subsumes the other. Shrink-only baseline, seeded at 51 because
  // the <Sentences> mechanism does not exist yet -- that is what lets wave B land it
  // incrementally without this gate being either useless or blocking.
  // The half of www-round5's gate 3 the content schema does NOT cover. Per-doc
  // subcategory legality moved into content/config.ts (z.enum + superRefine), where it
  // cannot be bypassed; what is left is thumbnail coverage. The thumbnails are
  // hand-authored and their generator was deleted, so a new doc without one ships a
  // blank browse card in all 13 locales silently -- one file serves every translation,
  // resolved by base slug.
  // Plyr's quality pane cannot host the language picker: it snaps every click to
  // min(options), so the video plays a language nobody chose. Re-adding it is the
  // regression that looks like it works.
  {
    id: 'check:ci-video-player-invariants',
    run: 'npm run check:ci-video-player-invariants',
    gate: true,
    leaves: ['scripts/check-video-player-invariants.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Video player invariants',
    },
  },
  // A skill an agent may edit gets longer every pass, because appending beats
  // rewriting. The cap is what forces the editing pass; skills opt in through
  // `self-improving: true` in their own frontmatter rather than a list here.
  {
    id: 'check:ci-skill-size',
    run: 'npm run check:ci-skill-size',
    gate: true,
    leaves: ['scripts/check-skill-size.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Self-improving skill size',
    },
  },
  // The mechanisms three /en/docs fixes rest on: the tally is announced not shown, the
  // two headings are styled by one shared rule, and the category group is decided before
  // first paint. Structural, not visual -- the interactive gate is wave D gate 2.
  {
    id: 'check:ci-docs-browse-invariants',
    run: 'npm run check:ci-docs-browse-invariants',
    gate: true,
    leaves: ['scripts/check-docs-browse-invariants.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Docs browse invariants',
    },
  },
  // A copy button on a bare `}` or on a YAML key is a control that hands the reader
  // something they cannot paste anywhere. The classifier is lifted out of DocsLayout.astro
  // and run over the real corpus, so this gate exercises the shipped script rather than a
  // second copy of its rules.
  {
    id: 'check:ci-docs-copy-units',
    run: 'npm run check:ci-docs-copy-units',
    gate: true,
    leaves: ['scripts/check-docs-copy-units.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Docs code-block copy units',
    },
  },
  {
    id: 'check:ci-docs-thumb-coverage',
    run: 'npm run check:ci-docs-thumb-coverage',
    gate: true,
    leaves: ['scripts/check-docs-thumb-coverage.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Docs thumbnail coverage',
    },
  },
  {
    id: 'check:ci-sentence-wrapping',
    run: 'npm run check:ci-sentence-wrapping',
    gate: true,
    leaves: ['scripts/check-sentence-wrapping.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Sentence wrapping',
    },
  },
  {
    id: 'check:ci-test-file-orphans',
    run: 'npm run check:ci-test-file-orphans',
    gate: true,
    leaves: ['.ci/scripts/quality/check_test_file_orphans.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Test-file orphan check',
    },
  },
  {
    id: 'check:ci-lint-scope-coverage',
    run: 'npm run check:ci-lint-scope-coverage',
    slow: true, // 163.0s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check_lint_scope_coverage.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Every source file reaches a linter',
    },
  },
  {
    id: 'check:ci-format-scope',
    // A formatter command may not narrow its own config's scope. Sibling of
    // lint-scope-coverage: that one proves FILES reach a linter, this proves the
    // COMMAND does not shrink what biome.json declares.
    run: 'npm run check:ci-format-scope',
    slow: true, // 21.6s contended: three full biome passes over 2426 files (11.2s idle)
    gate: true,
    leaves: ['.ci/scripts/quality/check_format_scope.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: "Format command covers its config's scope",
    },
  },
  {
    id: 'check:ci-battery-clean-tree',
    // run-all.sh's tree snapshot must not abort on a clean checkout. It extracts the
    // REAL tree_state() rather than copying it, and refuses if that function is gone.
    run: 'npm run check:ci-battery-clean-tree',
    gate: true,
    leaves: ['.ci/scripts/quality/check-battery-clean-tree.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Battery clean-tree guard',
    },
  },
  {
    id: 'check:ci-workflow-env-provision',
    // A job may not use a shell variable nothing in that job provides. bash
    // expands an unset name to the empty string, so the failure always surfaces
    // downstream wearing somebody else's name.
    run: 'npm run check:ci-workflow-env-provision',
    gate: true,
    leaves: ['.ci/scripts/quality/check_workflow_env_provision.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Workflow env provision',
    },
  },
  {
    id: 'check:ci-shell-commands',
    run: 'npm run check:ci-shell-commands',
    gate: true,
    leaves: ['.ci/scripts/security/check-commands.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Shell commands exist on the runner image',
    },
  },
  {
    id: 'check:ci-gate-id-convention',
    run: 'npm run check:ci-gate-id-convention',
    gate: true,
    leaves: ['.ci/scripts/quality/check-gate-id-convention.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Gate registration follows the gates/ convention',
    },
  },
  {
    id: 'check:ci-pool-writer-safety',
    run: 'npm run check:ci-pool-writer-safety',
    gate: true,
    leaves: ['.ci/scripts/quality/check-pool-writer-safety.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Pool-registered tests do not write the real tree',
    },
  },
  {
    id: 'gate-test:edge-verify-retries',
    run: '.ci/scripts/test/gates/test-edge-verify-retries.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-edge-verify-retries.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'check:ci-review-turn-capacity',
    run: 'npm run check:ci-review-turn-capacity',
    gate: true,
    leaves: ['.ci/scripts/quality/check-review-turn-capacity.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Review turn budget cannot starve a routed review',
    },
  },
  {
    id: 'check:ci-review-cap-coherence',
    run: 'npm run check:ci-review-cap-coherence',
    gate: true,
    leaves: ['.ci/scripts/quality/check-review-cap-coherence.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Review cap is measured coherently',
    },
  },
  {
    id: 'check:ci-gate-reachability-coverage',
    run: 'npm run check:ci-gate-reachability-coverage',
    gate: true,
    leaves: ['.ci/scripts/quality/check_gate_reachability_coverage.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Gate-reachability probe agrees with registrations',
    },
  },
  {
    id: 'check:ci-workflows',
    run: 'npm run check:ci-workflows',
    slow: true, // 12.0s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check-workflows.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Workflow banned patterns',
    },
  },
  {
    id: 'check:ci-greenlight-closures',
    run: 'npm run check:ci-greenlight-closures',
    gate: true,
    leaves: ['.ci/scripts/quality/check-greenlight-closures.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Greenlight closure paths',
    },
  },
  {
    id: 'check:ci-workflow-gates',
    run: 'npm run check:ci-workflow-gates',
    gate: true,
    leaves: ['.ci/scripts/security/check-workflow-gates.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Workflow structural gates',
    },
  },
  {
    id: 'check:ci-actionlint',
    run: 'npm run check:ci-actionlint',
    gate: true,
    leaves: ['.ci/scripts/security/actionlint.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Workflow lint (actionlint)',
    },
  },
  {
    id: 'check:ci-breakpoint-drift',
    run: 'npm run check:ci-breakpoint-drift',
    gate: true,
    leaves: ['.ci/breakpoint/scripts/check-breakpoint-drift.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Breakpoint drift',
    },
  },
  {
    id: 'check:ci-app-admin-perm',
    run: 'npm run check:ci-app-admin-perm',
    gate: true,
    leaves: ['.ci/scripts/quality/check-no-app-admin-perm.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'App admin permission',
    },
  },
  {
    id: 'check:ci-tracked-sidecars',
    run: 'npm run check:ci-tracked-sidecars',
    gate: true,
    leaves: ['.ci/scripts/quality/check-tracked-sidecars.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Tracked runtime sidecars',
    },
  },
  {
    id: 'check:ci-scans-tracked-paths',
    run: 'npm run check:ci-scans-tracked-paths',
    gate: true,
    leaves: ['.ci/scripts/quality/check-ci-scans-tracked-paths.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'CI executes only tracked paths',
    },
  },
  {
    id: 'check:ci-agent-browser-exit',
    run: 'npm run check:ci-agent-browser-exit',
    // 20.8s measured serially on an idle machine, so this is the gate's own cost
    // and not the 17x parallel load the pre-push lane runs under. The oracle
    // judges the FLOOR of recent samples for exactly that reason, and the floor
    // is over the line too.
    slow: true,
    gate: true,
    leaves: ['.ci/scripts/quality/check-agent-browser-exit.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'agent-browser exit status',
    },
  },
  {
    id: 'check:ci-silent-failures',
    run: 'npm run check:ci-silent-failures',
    gate: true,
    leaves: ['.ci/scripts/quality/check-silent-failure-patterns.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Silent-failure patterns',
    },
  },
  {
    id: 'check:ci-compose-env',
    run: 'npm run check:ci-compose-env',
    gate: true,
    leaves: ['.ci/scripts/quality/check-compose-env.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Compose env',
    },
  },
  {
    id: 'check:ci-e2e-coverage',
    run: 'npm run check:ci-e2e-coverage',
    gate: true,
    leaves: ['.ci/scripts/quality/check-e2e-coverage.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Check E2E test coverage for all renet functions',
    },
  },
  {
    id: 'check:ci-e2e-skip-hygiene',
    run: 'npm run check:ci-e2e-skip-hygiene',
    gate: true,
    leaves: ['scripts/check-e2e-skip-hygiene.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Check E2E skip hygiene (no collected-then-skipped suites)',
    },
  },
  {
    id: 'check:ci-audit-coverage',
    run: 'npm run check:ci-audit-coverage',
    gate: true,
    leaves: ['.ci/scripts/quality/check-audit-coverage.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Check audit logging coverage for CLI operations',
    },
  },
  {
    id: 'check:ci-cli-contract',
    run: 'npm run check:ci-cli-contract',
    slow: true, // 12.7s measured
    gate: true,
    needs: ['build:packages'],
    mutex: ['build-artifacts'],
    leaves: ['.ci/scripts/quality/check-cli-contract.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'CLI contract',
    },
  },
  {
    id: 'check:ci-command-tree',
    run: 'npm run check:ci-command-tree',
    slow: true, // 10.7s measured
    gate: true,
    needs: ['build:packages'],
    mutex: ['build-artifacts'],
    leaves: ['.ci/scripts/quality/check-command-tree.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Command tree',
    },
  },
  {
    id: 'check:ci-command-planes',
    run: 'npm run check:ci-command-planes',
    gate: true,
    leaves: ['packages/cli/scripts/check-command-planes.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Command planes',
    },
  },
  {
    id: 'check:ci-design-tree',
    run: 'npm run check:ci-design-tree',
    gate: true,
    leaves: ['scripts/check-design-tree.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Design tree',
    },
  },
  {
    id: 'check:ci-i18n-placeholders',
    run: 'npm run check:ci-i18n-placeholders',
    gate: true,
    leaves: ['scripts/check-i18n-placeholders.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n placeholders',
    },
  },
  {
    id: 'check:ci-i18n-untranslated',
    run: 'npm run check:ci-i18n-untranslated',
    gate: true,
    leaves: ['scripts/check-i18n-untranslated.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n untranslated',
    },
  },
  {
    id: 'check:ci-i18n-cross-locale',
    run: 'npm run check:ci-i18n-cross-locale',
    gate: true,
    leaves: [
      'scripts/check-i18n-cross-locale.ts',
      'scripts/check-locale-de-contamination.ts',
      'scripts/check-locale-config-divergence.ts',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n cross-locale',
    },
  },
  {
    id: 'check:ci-docs-structure-parity',
    run: 'npm run check:ci-docs-structure-parity',
    gate: true,
    leaves: ['scripts/check-docs-structure-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Docs structure parity',
    },
  },
  // Chained into check:ci-i18n-cross-locale rather than given a workflow step of its
  // own, so it inherits a REAL CI home instead of a 'local-only' BLOCKER. The two are
  // the same defect class read by two instruments: the stopword detector identifies a
  // language and can only look at the six locales it has function words for, while
  // this one keys on byte equality with the German value and is the only thing that
  // can see contamination in ar/ja/ko/ru/zh/et.
  {
    id: 'check:ci-locale-de-contamination',
    run: 'npm run check:ci-locale-de-contamination',
    gate: true,
    leaves: ['scripts/check-locale-de-contamination.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n cross-locale',
    },
  },
  {
    id: 'check:ci-locale-sources',
    run: 'npm run check:ci-locale-sources',
    gate: true,
    leaves: ['scripts/check-locale-sources.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Locale sources',
    },
  },
  {
    id: 'check:ci-i18n-command-parity',
    run: 'npm run check:ci-i18n-command-parity',
    gate: true,
    leaves: ['scripts/check-cli-docs.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n command parity',
    },
  },
  {
    id: 'check:ci-config-migrations',
    run: 'npm run check:ci-config-migrations',
    gate: true,
    leaves: ['.ci/scripts/quality/check-config-migrations.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Check config-migration runner + fixtures',
    },
  },
  {
    id: 'check:ci-schema-coverage',
    run: 'npm run check:ci-schema-coverage',
    gate: true,
    leaves: ['scripts/check-schema-coverage.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Schema coverage',
    },
  },
  {
    id: 'check:ci-shared-constant-duplication',
    run: 'npm run check:ci-shared-constant-duplication',
    gate: true,
    leaves: ['scripts/check-shared-constant-duplication.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Shared constant duplication',
    },
  },
  {
    id: 'check:ci-shared-esm-resolvable',
    run: 'npm run check:ci-shared-esm-resolvable',
    gate: true,
    leaves: ['scripts/check-shared-esm-resolvable.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Shared ESM resolvable',
    },
  },
  {
    id: 'check:ci-runtime-imports-are-deps',
    run: 'npm run check:ci-runtime-imports-are-deps',
    gate: true,
    leaves: ['scripts/check-runtime-imports-are-deps.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Runtime imports are dependencies',
    },
  },
  {
    id: 'check:ci-backup-manifest-shape-parity',
    run: 'npm run check:ci-backup-manifest-shape-parity',
    gate: true,
    leaves: ['scripts/check-backup-manifest-shape-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Backup manifest shape parity',
    },
  },
  {
    id: 'check:ci-fetch-integrity',
    run: 'npm run check:ci-fetch-integrity',
    gate: true,
    leaves: ['scripts/check-ci-fetch-integrity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'CI fetch integrity',
    },
  },
  {
    id: 'check:ci-aws-credential-bridge',
    run: 'npm run check:ci-aws-credential-bridge',
    gate: true,
    leaves: ['scripts/check-aws-credential-bridge.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'AWS credential bridge',
    },
  },
  {
    id: 'check:ci-worker-secret-names',
    run: 'npm run check:ci-worker-secret-names',
    gate: true,
    leaves: ['scripts/check-worker-secret-names.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Worker secret names',
    },
  },
  {
    id: 'check:ci-builder-env-contract',
    run: 'npm run check:ci-builder-env-contract',
    gate: true,
    leaves: ['scripts/check-builder-env-contract.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Builder env contract',
    },
  },
  {
    id: 'check:ci-backup-bucket-conformance',
    run: 'npm run check:ci-backup-bucket-conformance',
    gate: true,
    leaves: ['scripts/check-backup-bucket-conformance.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Backup bucket conformance',
    },
  },
  {
    id: 'check:ci-backup-protocol-conformance',
    run: 'npm run check:ci-backup-protocol-conformance',
    gate: true,
    leaves: ['scripts/check-backup-protocol-conformance.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Backup protocol conformance',
    },
  },
  // Covers the CLASS the conformance gate above cannot see: that gate pins
  // the key fields EXIST on both sides of the wire, this one pins that the
  // client never COMPOSES a key when one is missing. The composing fallback
  // was introduced twice, and the second time it was duplicated into the
  // read path, because each path's tests passed in isolation.
  {
    id: 'check:ci-no-client-key-composition',
    run: 'npm run check:ci-no-client-key-composition',
    gate: true,
    leaves: ['scripts/check-no-client-key-composition.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'No client-side key composition',
    },
  },
  // The knobs are spelled in FOUR places (shared schema, account DTO, the
  // sweep that enforces them, the CLI flags). A knob present in three and
  // absent from the sweep is a rule that silently does nothing, and each
  // layer's own tests pass because each layer is internally consistent.
  {
    id: 'check:ci-retention-knob-parity',
    run: 'npm run check:ci-retention-knob-parity',
    gate: true,
    leaves: ['scripts/check-retention-knob-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Retention knob parity',
    },
  },
  // The CLASS behind four separate findings this program hit: an unrun test
  // suite reads exactly like a passing one. private/account/web ran 1 of 34
  // files, packages/www ran none, packages/shared ran in CI but never
  // locally, and packages/json runs nowhere. This gate makes a suite
  // impossible to be invisible to BOTH CI and the omissions record.
  {
    id: 'check:ci-test-scripts-reachable',
    run: 'npm run check:ci-test-scripts-reachable',
    gate: true,
    leaves: ['scripts/check-test-scripts-reachable.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Test suites are CI-reachable',
    },
  },
  {
    id: 'check:ci-editorconfig',
    run: 'npm run check:ci-editorconfig',
    slow: true, // 12.9s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check-editorconfig.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'EditorConfig',
    },
  },
  {
    id: 'check:ci-account-portal',
    run: 'npm run check:ci-account-portal',
    slow: true, // 53.7s measured
    gate: true,
    heavy: true,
    leaves: ['.ci/scripts/quality/check-account-portal.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Check account portal (typecheck + build)',
    },
  },
  {
    id: 'check:ci-account-server',
    run: 'npm run check:ci-account-server',
    slow: true, // 41.5s contended (submodule vitest suite)
    gate: true,
    mutex: ['account-vitest'],
    weight: 2,
    heavy: true,
    leaves: ['.ci/scripts/private/run-account.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Run account integration tests',
    },
  },
  {
    id: 'check:ci-account-layer-isolation',
    run: 'npm run check:ci-account-layer-isolation',
    slow: true, // 10.8s measured
    gate: true,
    heavy: true,
    leaves: ['eslint'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Check account route layer isolation',
    },
  },
  {
    id: 'check:ci-account-config-auth',
    run: 'npm run check:ci-account-config-auth',
    gate: true,
    leaves: ['node'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check config token auth requires org membership',
    },
  },
  {
    id: 'check:ci-account-no-node-env-routes',
    run: 'npm run check:ci-account-no-node-env-routes',
    gate: true,
    leaves: ['grep', 'echo'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Assert no NODE_ENV branching in account routes',
    },
  },
  {
    id: 'check:ci-account-no-admin-role',
    run: 'npm run check:ci-account-no-admin-role',
    gate: true,
    leaves: ['grep', 'echo'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check no admin user role (must be root)',
    },
  },
  {
    id: 'check:ci-account-scope-audit',
    run: 'npm run check:ci-account-scope-audit',
    gate: true,
    mutex: ['account-vitest'],
    weight: 2,
    heavy: true,
    leaves: ['vitest'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check scope registry audit',
    },
  },
  // Runs the WHOLE private/account/web tree, not just the contract-coverage
  // file it used to name. That one file was 1 of 34; the other 33 (config key
  // slots, the config session provider, useJobStream, executor-session, all of
  // src/lib) could go red while CI stayed green. Renamed rather than quietly
  // widened, because the step name is the only thing a reader of a red log
  // sees and "Console contract coverage" would then be lying about 33 files.
  {
    id: 'check:ci-test-account-web',
    run: 'npm run check:ci-test-account-web',
    slow: true, // 32.6s measured
    gate: true,
    mutex: ['account-vitest'],
    weight: 2,
    heavy: true,
    leaves: ['vitest'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Account portal unit tests',
    },
  },
  {
    id: 'check:ci-renet',
    run: 'npm run check:ci-renet',
    gate: true,
    // 40.4s measured 2026-08-27, and only now: it used to die at exit 127 in
    // format.sh (goimports installed to $(go env GOPATH)/bin, which was on no
    // PATH) about a second in, so its old "fast" tier was the cost of crashing
    // early rather than of running. With that fixed it does the real work --
    // gofmt, goimports, golangci-lint and govulncheck over the whole module.
    slow: true,
    mutex: ['renet-bin'],
    leaves: ['.ci/scripts/private/run-renet.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Run renet quality',
    },
  },
  {
    id: 'check:ci-go-deps',
    run: 'npm run check:ci-go-deps',
    gate: true,
    leaves: ['.ci/scripts/quality/check-go-deps.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check Go dependency freshness',
    },
  },
  {
    id: 'check:ci-renet-types',
    run: 'npm run check:ci-renet-types',
    // 1.4s measured. It shells out to `go build`, so a COLD Go build cache
    // costs more than this -- but that is a once-per-tree cost, not the
    // steady-state one the lane is sized against.
    gate: true,
    mutex: ['renet-bin'],
    leaves: ['.ci/scripts/quality/check-renet-types.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check renet types freshness',
    },
  },
  // No `renet-bin` mutex, deliberately: that group guards the shared WRITE of
  // private/renet/bin/renet (check-renet-types.sh:26, and the renet quality
  // battery that rebuilds it). This gate only runs `go test`, which writes
  // nothing into bin/ and whose build cache is concurrency-safe, so serialising
  // it behind the two binary writers would buy nothing.
  //
  // `local-only` is measured, not assumed. The tier-map tests DO run in CI, but
  // through ct-tests.yml job test-renet step "Run renet tests", which resolves
  // to the leaf .ci/scripts/private/run-renet.sh (renet's whole `go test ./...`
  // suite) and never to this script. Declaring that as a `step` pointer fails
  // R3 with "the pointer names a step that runs something else", which is the
  // oracle working correctly: a manifest pointer asserts CI runs THIS leaf.
  {
    id: 'check:ci-renet-tiers',
    run: 'npm run check:ci-renet-tiers',
    gate: true,
    leaves: ['.ci/scripts/quality/check-renet-tier-map.sh'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: no CI step invokes this script; the seven tier-map tests it drives already run in CI inside .ci/scripts/private/run-renet.sh test (ct-tests.yml job test-renet, step "Run renet tests"), which resolves to that leaf and not this one, so a step pointer would claim CI runs a script it never invokes',
    },
  },
  {
    id: 'check:ci-embed-credits',
    run: 'npm run check:ci-embed-credits',
    gate: true,
    leaves: ['scripts/check-embed-credits.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check embed credits consistency',
    },
  },
  {
    id: 'check:ci-embed-arch-parity',
    run: 'npm run check:ci-embed-arch-parity',
    gate: true,
    leaves: ['scripts/check-embed-arch-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check embed arch parity',
    },
  },
  {
    id: 'check:ci-embed-asset-freshness',
    run: 'npm run check:ci-embed-asset-freshness',
    gate: true,
    leaves: ['scripts/check-embed-asset-freshness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check embed-asset upstream freshness',
    },
  },
  {
    id: 'check:ci-unverified-downloads',
    run: 'npm run check:ci-unverified-downloads',
    gate: true,
    leaves: ['scripts/check-unverified-downloads.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Check every Dockerfile download is cryptographically verified',
    },
  },
  {
    id: 'check:ci-devcontainer-pins',
    run: 'npm run check:ci-devcontainer-pins',
    gate: true,
    leaves: ['scripts/check-devcontainer-pin-freshness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check devcontainer pin upstream freshness',
    },
  },
  {
    id: 'check:ci-embed-asset-versions',
    run: 'npm run check:ci-embed-asset-versions',
    gate: true,
    // 46s by the FLOOR of its last five measurements (46.4, 47.1, 47.9, 48.9,
    // 51.7) -- not load noise, which is what the floor rule filters out. It
    // unpacks and hashes embedded assets, so the cost is real work.
    slow: true,
    leaves: ['scripts/check-embed-asset-versions.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check embedded asset versions match their pins',
    },
  },
  {
    id: 'check:ci-recovery-context',
    run: 'npm run check:ci-recovery-context',
    gate: true,
    leaves: ['scripts/check-recovery-context.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check recovery functions get an uncancellable context',
    },
  },
  {
    id: 'check:ci-no-otlp-creds',
    run: 'npm run check:ci-no-otlp-creds',
    slow: true, // 21.2s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check-no-otlp-creds.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-build-renet.yml',
      job: 'build-renet',
      step: 'Assert no OTLP credentials baked into the built binaries',
    },
  },
  {
    id: 'check:ci-subscription-schema',
    run: 'npm run check:ci-subscription-schema',
    gate: true,
    leaves: ['.ci/scripts/quality/check-subscription-schema.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check subscription schema consistency',
    },
  },
  {
    id: 'check:ci-pricing-consistency',
    run: 'npm run check:ci-pricing-consistency',
    gate: true,
    leaves: ['scripts/check-pricing-consistency.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Pricing consistency',
    },
  },
  {
    id: 'check:ci-seo',
    run: 'npm run check:ci-seo',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/check-seo.ts', 'scripts/check-client-bundle-budget.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'SEO',
    },
  },
  // The only gate that reads BUILT HTML against the source it was rendered from, so it
  // is the only one that can see a page rendering another locale's document. `needs`
  // build:www is not an optimisation: without dist it REFUSES rather than self-skipping,
  // which is the difference between this and check:ci-seo's built-HTML scan sitting
  // vacuous on a laptop for its whole life.
  {
    id: 'check:ci-docs-render-parity',
    run: 'npm run check:ci-docs-render-parity',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/check-docs-render-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Docs render parity',
    },
  },
  // Its cheap source-level complement: no build, so it lives in the i18n lane. It is a
  // proxy (an inline English string is invisible to it) and cannot replace the gate above.
  {
    id: 'check:ci-page-locale-imports',
    run: 'npm run check:ci-page-locale-imports',
    gate: true,
    leaves: ['scripts/check-page-locale-imports.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Page locale imports',
    },
  },
  {
    id: 'check:ci-external-links',
    run: 'npm run check:ci-external-links',
    slow: true, // 17.2s measured
    gate: true,
    leaves: ['scripts/check-external-links.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'External links',
    },
  },
  {
    id: 'check:ci-dkim-notify',
    run: 'npm run check:ci-dkim-notify',
    gate: true,
    leaves: ['scripts/check-dkim-notify.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'DKIM notify DNS',
    },
  },
  {
    id: 'check:ci-css-dom-refs',
    run: 'npm run check:ci-css-dom-refs',
    gate: true,
    leaves: ['scripts/check-css-dom-refs.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'CSS DOM references',
    },
  },
  {
    id: 'check:ci-svg-theme-reach',
    run: 'npm run check:ci-svg-theme-reach',
    gate: true,
    leaves: ['scripts/check-svg-theme-reach.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'SVG theme reach',
    },
  },
  {
    id: 'check:ci-dead-css',
    run: 'npm run check:ci-dead-css',
    gate: true,
    leaves: ['scripts/check-dead-css.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Dead CSS',
    },
  },
  {
    id: 'check:ci-viewport-unit-mixing',
    run: 'npm run check:ci-viewport-unit-mixing',
    gate: true,
    leaves: ['scripts/check-viewport-unit-mixing.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Dead CSS',
    },
  },
  {
    id: 'check:ci-illustration-contract',
    run: 'npm run check:ci-illustration-contract',
    gate: true,
    leaves: ['scripts/check-illustration-contract.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Dead CSS',
    },
  },
  {
    id: 'check:ci-redirects',
    run: 'npm run check:ci-redirects',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/check-redirect-integrity.ts', 'scripts/check-anchor-integrity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Redirects',
    },
  },
  {
    id: 'check:ci-browser-smoke',
    run: 'npm run check:ci-browser-smoke',
    slow: true, // 20.4s measured
    gate: true,
    leaves: ['.ci/scripts/quality/browser-smoke.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Browser smoke',
    },
  },
  {
    id: 'check:ci-captcha-recovery',
    run: 'npm run check:ci-captcha-recovery',
    gate: true,
    leaves: ['scripts/check-captcha-recovery.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Captcha recovery',
    },
  },
  {
    id: 'check:ci-page-density',
    run: 'npm run check:ci-page-density',
    slow: true, // drives 3 routes x 4 viewports in a container
    gate: true,
    leaves: ['.ci/scripts/quality/page-density.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Page density',
    },
  },
  {
    id: 'check:ci-landmarks',
    run: 'npm run check:ci-landmarks',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    // Reads packages/www/dist, so this is NOT an optimisation: without dist the
    // gate REFUSES ("zero built pages found") rather than self-skipping, and the
    // runner recorded that refusal as a FAILURE on every local lane. Seven
    // sibling gates that read dist already declare this; these two never did.
    needs: ['build:www'],
    leaves: ['scripts/check-landmarks.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Landmarks',
    },
  },
  {
    id: 'check:ci-ssr-locale',
    run: 'npm run check:ci-ssr-locale',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    // Same as check:ci-landmarks above: without dist it refuses with "zero
    // probes were comparable", which is correct anti-vacuity behaviour and was
    // being classified as a failure.
    needs: ['build:www'],
    leaves: ['scripts/check-ssr-locale.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'SSR locale',
    },
  },
  {
    id: 'check:ci-docker-image-freshness',
    run: 'npm run check:ci-docker-image-freshness',
    gate: true,
    leaves: ['scripts/check-docker-image-freshness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Docker image freshness',
    },
  },
  {
    id: 'check:ci-baseline-key-semantics',
    run: 'npm run check:ci-baseline-key-semantics',
    gate: true,
    // `leaves` is what package.json's run command actually resolves to (the real
    // source file check:ci-parity cross-checks); the 13 baseline JSON files this
    // script reads at runtime belong in `paths` (change-detection selection), not
    // here -- conflating the two is what check:ci-parity caught on this entry's
    // first real run.
    paths: [
      'scripts/check-baseline-key-semantics.ts',
      'scripts/data/dead-translation-keys-baseline.json',
      'scripts/data/dead-css-baseline.json',
      'scripts/data/sentence-wrapping-baseline.json',
      'scripts/data/em-dash-surfaces-baseline.json',
      'scripts/data/locale-de-contamination-baseline.json',
      'scripts/data/docker-image-freshness-baseline.json',
      'scripts/data/shell-declared-commands-baseline.json',
      'scripts/data/static-nowrap-baseline.json',
      'scripts/data/hook-coverage-baseline.json',
      'scripts/data/css-dom-refs-baseline.json',
      'scripts/data/hook-inventory-baseline.json',
      '.ci/scripts/quality/job-timeout-baseline.json',
      '.ci/scripts/quality/runner-sizing-baseline.json',
    ],
    leaves: ['scripts/check-baseline-key-semantics.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Baseline key semantics',
    },
  },
  {
    // check:test:tutorial-player sat in package.json for three months with no
    // manifest.ts entry and no workflow step -- found by hand this session,
    // not by any gate. This is the gate: every check:test* key must resolve
    // to a real manifest.ts entry wired to ci-quality.yml.
    id: 'check:ci-test-gate-wiring',
    run: 'npm run check:ci-test-gate-wiring',
    gate: true,
    paths: ['package.json', 'scripts/ci-runner/manifest.ts', 'scripts/check-test-gate-wiring.ts'],
    leaves: ['scripts/check-test-gate-wiring.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Test-gate wiring',
    },
  },
  {
    id: 'check:ci-search-index',
    run: 'npm run check:ci-search-index',
    gate: true,
    leaves: ['scripts/check-search-index-freshness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Search index',
    },
  },
  {
    id: 'check:ci-cta-bolt',
    run: 'npm run check:ci-cta-bolt',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    needs: ['build:www'],
    leaves: ['packages/www/scripts/check-cta-bolt-uniqueness.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'CTA bolt',
    },
  },
  {
    id: 'check:ci-content-quality',
    run: 'npm run check:ci-content-quality',
    slow: true, // 17.3s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check-content-quality.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Check content for AI slop patterns',
    },
  },
  {
    id: 'check:ci-nis2-quotes',
    run: 'npm run check:ci-nis2-quotes',
    gate: true,
    leaves: ['scripts/check-directive-quotes.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Verify NIS2 directive quotations match the official source',
    },
  },
  {
    id: 'check:cli-examples',
    run: 'npm run check:cli-examples',
    slow: true, // 22.7s measured
    gate: true,
    leaves: ['scripts/validate-cli-examples.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'CLI examples',
    },
  },
  {
    id: 'check:ci-tutorial-commands',
    run: 'npm run check:ci-tutorial-commands',
    gate: true,
    leaves: ['scripts/check-tutorial-commands.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate tutorial storyboard commands against the live CLI',
    },
  },
  {
    id: 'check:ci-tutorial-noninteractive',
    run: 'npm run check:ci-tutorial-noninteractive',
    gate: true,
    leaves: ['scripts/check-tutorial-noninteractive.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate tutorial commands are non-interactive',
    },
  },
  {
    id: 'check:ci-tutorial-parity',
    run: 'npm run check:ci-tutorial-parity',
    gate: true,
    leaves: ['packages/www/scripts/check-tutorial-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate tutorial cast/storyboard/transcript/mdx parity',
    },
  },
  {
    id: 'check:ci-tutorial-casts',
    run: 'npm run check:ci-tutorial-casts',
    gate: true,
    leaves: ['packages/www/scripts/validate-tutorial-cast-output.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Block fallback hacks and error output in tutorial recordings',
    },
  },
  {
    id: 'check:ci-tutorial-render-queue',
    run: 'npm run check:ci-tutorial-render-queue',
    gate: true,
    leaves: ['packages/www/scripts/list-tutorial-render-pairs.js'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-tutorial-render-queue.sh',
      blocker:
        'BLOCKER: the predicate needs the render ledger and media manifest that only the tutorial pipeline writes, and test-tutorial-render-queue.sh:79 runs `node "$PREDICATE" --selftest` against the real tree inside run-all.sh, so the real scan does execute in CI (ci-quality.yml quality-security, "Quality-gate unit tests")',
    },
  },
  {
    id: 'check:ci-locale-tutorial-assets',
    run: 'npm run check:ci-locale-tutorial-assets',
    gate: true,
    leaves: ['packages/www/scripts/check-locale-tutorial-assets.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate per-locale tutorial video assets exist',
    },
  },
  {
    // The sibling gate to locale-tutorial-assets: that one proves the five
    // files EXIST, this one proves the text inside them is drawable. Both were
    // green while eighteen Arabic tutorials shipped with detached letters.
    id: 'check:ci-tutorial-card-fonts',
    run: 'npm run check:ci-tutorial-card-fonts',
    gate: true,
    // Leaves are the scripts the npm key RUNS, not everything it imports.
    // card-fonts.ts is a module this gate reads; listing it here made
    // check:ci-parity red on a leaves-vs-package.json mismatch.
    leaves: ['packages/www/scripts/check-tutorial-card-fonts.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate tutorial card fonts cover every locale',
    },
  },
  {
    id: 'check:ci-solution-videos',
    run: 'npm run check:ci-solution-videos',
    gate: true,
    leaves: ['packages/www/scripts/check-solution-videos.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate localized solution videos exist',
    },
  },
  {
    id: 'check:ci-solution-video-engine',
    run: 'npm run check:ci-solution-video-engine',
    gate: true,
    leaves: ['packages/www/scripts/check-solution-video-engine.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate solution narration engine is current',
    },
  },
  {
    id: 'check:ci-tutorial-caption-sync',
    run: 'npm run check:ci-tutorial-caption-sync',
    gate: true,
    leaves: ['packages/www/scripts/check-tutorial-caption-sync.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate published tutorial word-timing sync (real ASR alignment, not estimated)',
    },
  },
  {
    id: 'check:ci-account-onboarding',
    run: 'npm run check:ci-account-onboarding',
    gate: true,
    leaves: ['scripts/check-account-onboarding.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate account onboarding splash against canonical tutorials',
    },
  },
  {
    id: 'check:ci-overrides-reasons',
    run: 'npm run check:ci-overrides-reasons',
    gate: true,
    leaves: ['scripts/check-overrides-reasons.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'BLOCKER validator — package.json overrides',
    },
  },
  {
    id: 'check:ci-syncpack-reasons',
    run: 'npm run check:ci-syncpack-reasons',
    gate: true,
    leaves: ['scripts/check-syncpack-reasons.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'BLOCKER validator — syncpack versionGroups',
    },
  },
  {
    id: 'check:ci-suppression-liveness',
    run: 'npm run check:ci-suppression-liveness',
    gate: true,
    leaves: ['scripts/check-suppression-liveness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Suppression liveness — are our allowlist entries still needed?',
    },
  },
  {
    id: 'check:ci-dead-bash',
    run: 'npm run check:ci-dead-bash',
    slow: true, // 141.7s measured
    gate: true,
    leaves: ['scripts/check-dead-bash.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Dead bash',
    },
  },
  {
    id: 'check:actions',
    run: 'npm run check:actions',
    gate: true,
    leaves: ['scripts/check-actions.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Action freshness',
    },
  },
  {
    id: 'check:ci-jq-boolean-default',
    run: 'npm run check:ci-jq-boolean-default',
    gate: true,
    leaves: ['scripts/check-jq-boolean-default.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'jq boolean defaults',
    },
  },
  {
    id: 'check:ci-dead-case-arms',
    run: 'npm run check:ci-dead-case-arms',
    gate: true,
    leaves: ['.ci/scripts/quality/check-dead-case-arms.sh'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-dead-case-arms.sh',
      blocker:
        'BLOCKER: the gate is CONTROL-FIRST -- it plants a dead case arm with a runtime-generated key and refuses to report on the real tree unless its scanner catches that arm, so a green IS the fire proof; test-dead-case-arms.sh:14 runs it seam-free against the real tree inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests")',
    },
  },
  {
    id: 'check:ci-label-refs',
    run: 'npm run check:ci-label-refs',
    gate: true,
    leaves: ['.ci/scripts/quality/check-label-references.sh'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-label-references.sh',
      blocker:
        'BLOCKER: test-label-references.sh:116 runs the gate seam-free against the real tree inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests"), so the real sweep over .github/.ci executes every CI run; the fixture cases around it prove both fire directions',
    },
  },
  {
    id: 'check:ci-label-inventory',
    run: 'npm run check:ci-label-inventory',
    gate: true,
    leaves: ['.ci/scripts/quality/check-label-inventory.sh'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-label-inventory.sh',
      blocker:
        'BLOCKER: test-label-inventory.sh:191 runs the gate seam-free over the REAL .github/labels.yml inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests") with the live list injected, so the real parse, the declared floor and the create-on-demand allowlist verification execute every CI run, and the two controls beside it drop a real label and add an undeclared one to prove both fire directions; the live GitHub read is the one part that cannot run in that lane because it holds no label-read token, and it runs on the local npm invocation',
    },
  },
  {
    id: 'check:ci-profiler-coverage',
    run: 'npm run check:ci-profiler-coverage',
    gate: true,
    leaves: ['.ci/scripts/quality/check-profiler-coverage.sh'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-profiler-coverage.sh',
      blocker:
        'BLOCKER: test-profiler-coverage.sh:584 runs the gate seam-free against the real tree inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests") -- real .github/workflows, real .profiler-coverage-allowlist, real .github/actions/profiler/action.yml, real floors -- so the full 121-job parse and both relations execute every CI run; the 22 fixture cases around it prove every fire direction, including the anti-vacuity refusals (empty dir, missing dir, zero jobs, three floors, missing action.yml) that a real-tree-only case can never exercise',
    },
  },
  {
    id: 'check:ci-autopilot-workflow',
    run: 'npm run check:ci-autopilot-workflow',
    gate: true,
    leaves: ['.ci/scripts/security/check-autopilot-workflow-invariants.sh'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-autopilot-workflow-invariants.sh',
      blocker:
        'BLOCKER: no quality lane can run this against the live ruleset, but test-autopilot-workflow-invariants.sh:23-24 points both GATE and REAL at the real .github/workflows/autopilot.yml, so run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests") executes the real scan over the real tree every CI run',
    },
  },
  {
    id: 'check:ci-go-module-sync',
    run: 'npm run check:ci-go-module-sync',
    gate: true,
    leaves: ['.ci/scripts/quality/check-go-module-sync.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check Go module sync against the renet worktree',
    },
  },
  {
    id: 'check:ci-workflow-invariants',
    run: 'npm run check:ci-workflow-invariants',
    gate: true,
    leaves: ['.ci/scripts/security/check-ci-workflow-invariants.sh'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-ci-workflow-invariants.sh',
      blocker:
        'BLOCKER: no quality lane runs this against the live workflow, but test-ci-workflow-invariants.sh points both GATE and REAL at the real .github/workflows/ci.yml, so run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests") executes the real scan over the real tree every CI run',
    },
  },
  {
    id: 'check:ci-autopilot-bp-align',
    run: 'npm run check:ci-autopilot-bp-align',
    gate: true,
    leaves: ['.ci/scripts/quality/check-autopilot-breakpoint-alignment.sh'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh',
      blocker:
        'BLOCKER: test-autopilot-breakpoint-alignment.sh:59 runs the gate seam-free against the real .ci/breakpoint/workflow/breakpoint.yml and .github/workflows/autopilot.yml inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests"), so the real comparison executes every CI run; the mutated-copy cases around it prove both fire directions',
    },
  },

  // ---------------------------------------------------------------------------
  // WAVE 0 OF THE www-simplification PROGRAM: eight gates for defect classes that
  // nothing in this repo could see. Seven of the eight are RED on the tree they
  // landed on, DELIBERATELY -- they encode bugs a later wave fixes, and a gate
  // introduced green over a live defect is a gate that ratifies it.
  //
  // FIVE OF THEM RIDE AN EXISTING WORKFLOW STEP rather than adding one, by being
  // chained into that step's npm key. The precedent is check:ci-locale-de-contamination
  // (see its comment above), and the pairings are by SUBJECT, not by convenience:
  //   em-dash-surfaces        -> "i18n"; 2,401 of its 2,451 findings are locale VALUES, and
  //                              check-content-quality.sh keeps the markdown half of the
  //                              same ban. It was first pointed at the AI-slop step, which
  //                              is the better SUBJECT match, and check-ci-parity refused
  //                              it: that step invokes the script by path, not through npm,
  //                              so the chain would never have reached CI. The pairing has
  //                              to follow what the step RUNS, not what it is called.
  //   locale-config-divergence-> "i18n cross-locale"; catalog-versus-catalog integrity,
  //                              beside de-contamination. Its true subject twin,
  //                              check_i18n_value_types.py, compares the TYPE of every
  //                              non-string leaf where this compares the VALUE -- but that
  //                              step is a bare script path too, so it cannot host a chain.
  //   dead-translation-keys   -> "i18n"; check-translation-key-usage.ts in the same chain
  //                              walks source->catalog, and this walks catalog->source.
  //   anchor-integrity        -> "Redirects"; both assert that a link in the BUILT output
  //                              resolves to something.
  //   client-bundle-budget    -> "SEO"; page weight is read from the same built HTML, and
  //                              the step already sits behind build:www.
  // The remaining three have no honest step to ride and are covered by a gate test that
  // drives their REAL scan against the REAL tree inside run-all.sh.
  // WAVE 1's gate, registered here because w2-i18n correctly did not touch the root
  // package.json or this file. Without it a STALE CLIENT CATALOG SHIPS SILENTLY: wave 1
  // replaced the thirteen static locale imports with generated per-locale bundles under
  // packages/www/src/i18n/{client,client-route}/, and those bundles are committed
  // artifacts of packages/www/src/i18n/translations/. Nothing else compares the two, and
  // the TypeScript build that used to be the backstop for "a locale file went missing" is
  // exactly what wave 1 removed (01-verified-context.md flagged this as the hazard of the
  // wave). The npm key runs --selftest FIRST, so its five cases -- clean tree, stale,
  // deleted, stray non-site-locale, wiped bundle -- gate the real comparison on every
  // invocation rather than sitting behind a flag nobody passes.
  {
    id: 'check:ci-client-i18n',
    run: 'npm run check:ci-client-i18n',
    gate: true,
    leaves: ['packages/www/scripts/check-client-i18n-freshness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-em-dash-surfaces',
    run: 'npm run check:ci-em-dash-surfaces',
    gate: true,
    leaves: ['scripts/check-em-dash-surfaces.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-locale-config-divergence',
    run: 'npm run check:ci-locale-config-divergence',
    gate: true,
    leaves: ['scripts/check-locale-config-divergence.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n cross-locale',
    },
  },
  {
    id: 'check:ci-dead-translation-keys',
    run: 'npm run check:ci-dead-translation-keys',
    gate: true,
    leaves: ['scripts/check-dead-translation-keys.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // Both of these read packages/www/dist, so `needs: ['build:www']` is not an optimisation:
  // without it they would be scheduled before the build and REFUSE, which is correct but
  // useless. Same reasoning as check:ci-docs-render-parity above.
  {
    id: 'check:ci-anchor-integrity',
    run: 'npm run check:ci-anchor-integrity',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/check-anchor-integrity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Redirects',
    },
  },
  {
    id: 'check:ci-player-css-scope',
    run: 'npm run check:ci-player-css-scope',
    slow: true, // reads the built dist; needs build:www like its neighbour
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/check-player-css-scope.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Player CSS scope',
    },
  },
  {
    id: 'check:ci-client-bundle-budget',
    run: 'npm run check:ci-client-bundle-budget',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/check-client-bundle-budget.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'SEO',
    },
  },
  {
    id: 'check:ci-layout-overflow',
    run: 'npm run check:ci-layout-overflow',
    gate: true,
    leaves: ['scripts/check-layout-overflow.ts'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-layout-overflow.sh',
      blocker:
        'BLOCKER: no quality lane owns CSS overflow, and the two shapes this gate detects are invisible to a browser scan because querySelectorAll returns no pseudo-elements; test-layout-overflow.sh:66 runs the gate seam-free against the real stylesheets inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests"), so the real parse of every declaration block executes every CI run, and the mutant case beside it strips the nowrap detector and requires the gate\'s own controls to go red',
    },
  },
  {
    id: 'check:ci-hydration-clean',
    run: 'npm run check:ci-hydration-clean',
    gate: true,
    leaves: ['scripts/check-hydration-clean.ts'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-hydration-clean.sh',
      blocker:
        'BLOCKER: no quality lane reads React state initializers, and the defect is decidable only from the source pair (server render, client render); test-hydration-clean.sh:60 runs the gate seam-free against the real packages/www components inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests"), so the real scan executes every CI run, and the mutant case beside it blinds the one-hop lookup and requires the indirect control to go red',
    },
  },
  {
    id: 'check:ci-form-validation',
    run: 'npm run check:ci-form-validation',
    gate: true,
    leaves: ['scripts/check-form-validation.ts'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-form-validation.sh',
      blocker:
        'BLOCKER: no quality lane inspects form submit handlers, and the defect is a MISSING guard rather than a present one, so nothing else can express it; test-form-validation.sh:59 runs the gate seam-free against the real components inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests"), so the real scan of all six forms executes every CI run, and the mutant case beside it accepts a captcha guard as validation and requires the control to go red',
    },
  },

  // The parity gate itself. It replaces the two it deleted, and it inherits
  // their workflow step (ci-quality.yml quality-content) rather than adding a
  // new one, so the surface keeps exactly one parity step.
  {
    id: 'check:ci-parity',
    run: 'npm run check:ci-parity',
    gate: true,
    leaves: ['scripts/check-ci-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate parity between the local gate set and the CI quality surface',
    },
  },

  // F3: two Quality/Static steps that ran in CI and nowhere else. The forward
  // gate could not see them because its BARE_GATE pattern only covered
  // .ci/scripts/{quality,security}/check-*.sh; these live in .ci/scripts/test/
  // and start with test-. They are invoked by path, not by an npm key, because
  // the Static lane is a bare checkout with no node_modules -- the same reason
  // ci-quality.yml:166-171 already gives for its sibling test-install-sh-config.sh.
  {
    id: 'test:write-once-guard',
    run: '.ci/scripts/test/test-write-once-guard.sh',
    gate: true,
    leaves: ['.ci/scripts/test/test-write-once-guard.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Write-once guard tests',
    },
  },
  {
    id: 'test:install-script',
    run: '.ci/scripts/test/test-install-script.sh',
    gate: true,
    leaves: ['.ci/scripts/test/test-install-script.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Install-script tests',
    },
  },

  // Prerequisite nodes. They validate nothing, so gate:false; they run only
  // when something that needs them is selected.
  //
  // build:www is what closes F5. check:ci-seo's built-HTML link scan self-skips
  // without packages/www/dist (ci-quality.yml:738-740) and the old `&&` chain
  // never built www, so that scan has been vacuous locally for its whole life.
  {
    id: 'build:packages',
    run: 'npm run build:packages',
    gate: false,
    mutex: ['build-artifacts'],
    heavy: true,
    leaves: ['tsc'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: a prerequisite, not a validation; CI gets the same artifacts from the per-lane build steps (ci-quality.yml quality-code TypeScript, quality-packages CLI contract) and has no single step that corresponds to this node',
    },
  },
  {
    id: 'build:www',
    run: 'npm run build:www',
    slow: true, // 131.9s measured
    gate: false,
    mutex: ['www-dist'],
    heavy: true,
    leaves: ['astro'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Build www (produces dist/route-manifest.json)',
    },
  },

  // The CI-side aggregate. gate:false because its 62 constituents are scheduled
  // individually below: scheduling this as one unit too would run the whole
  // 443s battery twice, and 443s is 43% of the measured serial total (plan
  // section 2). The npm key stays because CI wants one step for it.
  {
    id: 'check:ci-quality-gates',
    run: 'npm run check:ci-quality-gates',
    gate: false,
    leaves: ['.ci/scripts/test/run-all.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },

  // ---------------------------------------------------------------------------
  // The battery, flattened. run-all.sh runs these 57 serially behind one opaque
  // npm key; scheduling them individually is what lifts the parallel ceiling
  // from 2.4x to roughly 7x and what makes the summary name the failing test.
  //
  // Assertion 7 pins this set against the on-disk glob run-all.sh:26,46 uses, so
  // a newly added test cannot be silently omitted here -- without that rule this
  // flattening would recreate #549 fifty-seven times over.
  //
  // ISOLATION IS A HYPOTHESIS, NOT A GIVEN. test-claude-hooks.sh failed once
  // Since 2026-08-08 run-all.sh enforces this in-step: the two writers run as
  // an exclusive serial chain and the real-tree scanners are held until it
  // finishes. See its header.
  // inside the SERIAL battery and could not be reproduced standalone (plan
  // finding F8). Any red that appears only under parallelism gets a named mutex
  // group, never a retry.
  //
  // A HAZARD OF THIS CLASS, ONE INSTANCE FIXED AND TWO OPEN. Three gates write a
  // file into the REAL working tree for the duration of their run, and a
  // tree-scanning gate running concurrently trips over it. Observed live
  // on 2026-07-31:
  //   FIXED  .ci/scripts/test/gates/test-gate-paths-exist.sh
  //     wrote scripts/.gate-paths-exist{,-noise}-fixture.ts and broke check:lint
  //     with `ENOENT ... open '.../scripts/.gate-paths-exist-fixture.ts'`, exit 2
  //     (eslint enumerated the file, then the control deleted it). Its fixtures
  //     now go to .ci/scripts, which that gate's own scan_targets() walks and no
  //     linter does. Re-run green with both controls firing and zero dotfiles
  //     observed in scripts/ for the whole 142s run.
  //   OPEN   .ci/scripts/quality/check-config-migrations.sh:68
  //     -> packages/cli/.config-migrations-check.tmp.ts, which broke check:format.
  //     Cannot use the same fix: biome covers packages/**/*.ts, and the script
  //     must stay under packages/cli for node to resolve @rediacc/shared.
  //   OPEN   .ci/scripts/test/gates/test-gate-anti-vacuity.sh:255
  //     -> scripts/.gate-anti-vacuity-fixture.ts, same shape, no victim observed.
  //     Cannot use the same fix either: run_against_empty_tree() builds its
  //     fixture tree with `cp -r "$REPO_ROOT/scripts"`, so the file has to exist
  //     under the real scripts/ at copy time to reach the harness at all.
  // The hazard PREDATES the runner: `npm run check:lint` in one terminal while
  // `npm run check:ci-quality-gates` runs in another hits the same ENOENT, and
  // that is how it was first seen here, not through the pool.
  //
  // `mktemp` is NOT the fix, which is the trap: test-gate-paths-exist.sh's
  // scan_targets() (:62-64) hardcodes `cd $REPO_ROOT` and `find scripts`, so a
  // fixture outside the real tree stops being scanned and its control at
  // :178-192 silently stops firing; and check-config-migrations.sh's generated
  // script must sit under packages/cli for node to resolve @rediacc/shared and
  // its relative fixtures dir. Both files have to stay in the tree.
  //
  // PREFER AN IGNORE RULE OVER A MUTEX, on measured cost. The insertion points
  // exist: eslint.config.js's global `ignores` array and biome.json's
  // `files.includes`, which already takes negated patterns. Both lists are
  // "this is not source" exclusions (dist, node_modules, generated .d.ts), and
  // a fixture that lives for milliseconds and is never committed belongs there.
  // Cost: zero scheduling time, and it stands on its own merits whether or not
  // the runner exists.
  //
  // USE THE FOUR EXACT PATHS, NOT A GLOB. `scripts/.gate-*-fixture.ts` would
  // silently exempt any future file matching it; four literals cannot, because
  // they name exactly the files that exist. The failure mode also inverts the
  // right way: a fifth writer added later is NOT covered, so it trips the
  // scanner loudly the first time it races instead of being silently absorbed.
  // That matches how the rest of this repo's suppressions work, enumerated
  // rather than pattern-matched.
  //
  // Both halves were PROVEN on a throwaway tree, each with a control that fires
  // (2026-07-31), rather than reasoned from the tools' documented semantics.
  // Both probes ran against the WORKSPACE tools, eslint 9 and biome 2.5.6,
  // reached by linking the real node_modules into the scratch dir:
  //   eslint  no ignore entry -> exit 1 on a planted parse error;
  //           exact-path `ignores` entry -> exit 0.
  //   biome   no negation -> "Checked 2 files", flags the temp file, exit 1;
  //           exact-path `!` negation -> "Checked 1 file", exit 0.
  // That biome run, and only that one, is what establishes that biome DOES walk
  // dotfiles, which is why check:format was a victim at all. An earlier attempt
  // without the node_modules link exited 0 in silence on a deliberately
  // misformatted file; `npx` had resolved something other than the workspace
  // biome, so that run is evidence about npx resolution and about nothing else.
  // Do not read it as biome skipping dotfiles: a tool that never ran produces a
  // green indistinguishable from a passing one, which is this whole file's
  // subject.
  //
  // A mutex group binding the three writers against check:lint / check:format /
  // lint:unused is the fallback, and it is expensive. It would serialise 511.7s
  // of work against an observed 264.2s wall, a 1.94x regression that drops the
  // run from about 9x to about 4.7x. It also binds the two LONGEST gates in the
  // set to each other, because one of the writers is the critical path:
  // test-gate-paths-exist.sh measured 142.6s standalone on an idle tree and
  // 264.1s under parallel load, against check:lint at 194.8s under the same
  // load. (The plan's 116.7s for check:lint is stale; do not cost this from it.)
  // No mutex is declared here, deliberately, because that trade wants an
  // explicit decision rather than a silent default.
  {
    // The composition guard shared by every shrink-only baseline here. Registered as a
    // gate-test rather than a `check:ci-*` npm alias because it RUNS a gates/ script
    // directly, which is the convention check-gate-id-convention.sh enforces.
    id: 'gate-test:shrink-only-composition',
    run: '.ci/scripts/test/gates/test-shrink-only-composition.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-shrink-only-composition.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:actions-release-age',
    run: '.ci/scripts/test/gates/test-actions-release-age.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-actions-release-age.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:age-check',
    run: '.ci/scripts/test/gates/test-age-check.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-age-check.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:autopilot-breakpoint-alignment',
    run: '.ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:autopilot-harness',
    run: '.ci/scripts/test/gates/test-autopilot-harness.sh',
    slow: true, // 59.8s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-autopilot-harness.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:autopilot-no-bypass',
    run: '.ci/scripts/test/gates/test-autopilot-no-bypass.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-autopilot-no-bypass.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:go-module-sync',
    run: '.ci/scripts/test/gates/test-go-module-sync.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-go-module-sync.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:simulate-promotion-serverside',
    run: '.ci/scripts/test/gates/test-simulate-promotion-serverside.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-simulate-promotion-serverside.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:ci-workflow-invariants',
    run: '.ci/scripts/test/gates/test-ci-workflow-invariants.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-ci-workflow-invariants.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:autopilot-workflow-invariants',
    run: '.ci/scripts/test/gates/test-autopilot-workflow-invariants.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-autopilot-workflow-invariants.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:form-validation',
    run: '.ci/scripts/test/gates/test-form-validation.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-form-validation.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:hydration-clean',
    run: '.ci/scripts/test/gates/test-hydration-clean.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-hydration-clean.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:layout-overflow',
    run: '.ci/scripts/test/gates/test-layout-overflow.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-layout-overflow.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:backfill-commit-resolve',
    run: '.ci/scripts/test/gates/test-backfill-commit-resolve.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-backfill-commit-resolve.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:blocker-validator',
    run: '.ci/scripts/test/gates/test-blocker-validator.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-blocker-validator.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:breakpoint-drift',
    run: '.ci/scripts/test/gates/test-breakpoint-drift.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-breakpoint-drift.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:breakpoint-mode-selection',
    run: '.ci/scripts/test/gates/test-breakpoint-mode-selection.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-breakpoint-mode-selection.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:breakpoint-naming',
    run: '.ci/scripts/test/gates/test-breakpoint-naming.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-breakpoint-naming.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:ci-compat-prose',
    run: '.ci/scripts/test/gates/test-ci-compat-prose.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-ci-compat-prose.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:watchdog-designed-failure',
    run: '.ci/scripts/test/gates/test-watchdog-designed-failure.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-watchdog-designed-failure.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:nightly-retry-filters',
    run: '.ci/scripts/test/gates/test-nightly-retry-filters.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-nightly-retry-filters.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:preview-worker-reaping',
    run: '.ci/scripts/test/gates/test-preview-worker-reaping.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-preview-worker-reaping.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:ci-trace-branch',
    run: '.ci/scripts/test/gates/test-ci-trace-branch.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-ci-trace-branch.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:run-sh',
    run: '.ci/scripts/test/gates/test-run-sh.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-run-sh.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:devbox-probes',
    run: '.ci/scripts/test/gates/test-devbox-probes.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-devbox-probes.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'check:ci-release-bump-skip',
    run: 'npm run check:ci-release-bump-skip',
    gate: true,
    leaves: ['.ci/scripts/quality/check-release-bump-skip.sh'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/quality/check-release-bump-skip.sh',
      blocker:
        'BLOCKER: the gate IS the test -- it drives the real dispatch-release.sh decide branch with a shimmed gh through all five paths, so ci-quality.yml quality-security runs the real decision every CI run; it exists because a bump-none merge and a broken decision both produce "no release" and only the emitted signal distinguishes them, which no release gate could see',
    },
  },
  {
    id: 'check:ci-regions-sync',
    run: 'npm run check:ci-regions-sync',
    gate: true,
    leaves: ['.ci/scripts/quality/check-regions-sync.sh'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-regions-sync.sh',
      blocker:
        'BLOCKER: test-regions-sync.sh drives the REAL gate over the REAL regions.json and packages/shared/src/regions/data.json inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests"), and its controls plant a divergence, an empty file and invalid JSON to prove all three refusals fire; the two files are held together by hand (no build step syncs them, despite what index.ts used to claim) and data.json is the ONLY region list users get because ${SITE_URL}/regions.json returns 404, so silent drift would ship to every install',
    },
  },
  {
    id: 'gate-test:worktree-devbox-teardown',
    run: '.ci/scripts/test/gates/test-worktree-devbox-teardown.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-worktree-devbox-teardown.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:mark-production',
    run: '.ci/scripts/test/gates/test-mark-production.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-mark-production.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:skip-release-channel-pointer',
    run: '.ci/scripts/test/gates/test-skip-release-channel-pointer.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-skip-release-channel-pointer.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:assert-edge-tag-exists',
    run: '.ci/scripts/test/gates/test-assert-edge-tag-exists.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-assert-edge-tag-exists.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:devbox-hostname',
    run: '.ci/scripts/test/gates/test-devbox-slug.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-devbox-slug.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:toolchain',
    run: '.ci/scripts/test/gates/test-toolchain.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-toolchain.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:breakpoint-pins',
    run: '.ci/scripts/test/gates/test-breakpoint-pins.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-breakpoint-pins.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:breakpoint-portability',
    run: '.ci/scripts/test/gates/test-breakpoint-portability.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-breakpoint-portability.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:breakpoint-secret-exposure',
    run: '.ci/scripts/test/gates/test-breakpoint-secret-exposure.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-breakpoint-secret-exposure.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:breakpoint-teardown',
    run: '.ci/scripts/test/gates/test-breakpoint-teardown.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-breakpoint-teardown.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:channel-for-event',
    run: '.ci/scripts/test/gates/test-channel-for-event.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-channel-for-event.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:ci-complete-tiers',
    run: '.ci/scripts/test/gates/test-ci-complete-tiers.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-ci-complete-tiers.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:ci-job-aggregation',
    run: '.ci/scripts/test/gates/test-ci-job-aggregation.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-ci-job-aggregation.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:ci-parity',
    run: '.ci/scripts/test/gates/test-ci-parity.sh',
    slow: true, // 42.3s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-ci-parity.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:ci-runner',
    run: '.ci/scripts/test/gates/test-ci-runner.sh',
    slow: true, // 16.9s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-ci-runner.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:claude-hooks',
    run: '.ci/scripts/test/gates/test-claude-hooks.sh',
    slow: true, // 537.4s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-claude-hooks.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:installmethods-args',
    run: '.ci/scripts/test/gates/test-installmethods-args.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-installmethods-args.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:installmethods-container-version',
    run: '.ci/scripts/test/gates/test-installmethods-container-version.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-installmethods-container-version.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:installmethods-linuxpkg-idiom',
    run: '.ci/scripts/test/gates/test-installmethods-linuxpkg-idiom.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-installmethods-linuxpkg-idiom.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:installmethods-manifest',
    run: '.ci/scripts/test/gates/test-installmethods-manifest.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-installmethods-manifest.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:releaseversion-attestation',
    run: '.ci/scripts/test/gates/test-releaseversion-attestation.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-releaseversion-attestation.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:releaseversion-build-version',
    run: '.ci/scripts/test/gates/test-releaseversion-build-version.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-releaseversion-build-version.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:releaseversion-cd-retry-assert',
    run: '.ci/scripts/test/gates/test-releaseversion-cd-retry-assert.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-releaseversion-cd-retry-assert.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:releaseversion-closure-untagged',
    run: '.ci/scripts/test/gates/test-releaseversion-closure-untagged.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-releaseversion-closure-untagged.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:releaseversion-inject-env',
    run: '.ci/scripts/test/gates/test-releaseversion-inject-env.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-releaseversion-inject-env.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:releaseversion-tag-fetch',
    run: '.ci/scripts/test/gates/test-releaseversion-tag-fetch.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-releaseversion-tag-fetch.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:stop-hook-stdin',
    run: '.ci/scripts/test/gates/test-stop-hook-stdin.sh',
    slow: true, // 12.9s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-stop-hook-stdin.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:verify-version',
    run: '.ci/scripts/test/gates/test-verify-version.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-verify-version.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:worklist-hooks',
    run: '.ci/scripts/test/gates/test-worklist-hooks.sh',
    slow: true, // 454.2s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-worklist-hooks.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:dead-bash',
    run: '.ci/scripts/test/gates/test-dead-bash.sh',
    slow: true, // 199.8s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-dead-bash.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:dispatch-release',
    run: '.ci/scripts/test/gates/test-dispatch-release.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-dispatch-release.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:detect-bump-type',
    run: '.ci/scripts/test/gates/test-detect-bump-type.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-detect-bump-type.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:e2e-coverage',
    run: '.ci/scripts/test/gates/test-e2e-coverage.sh',
    slow: true, // 13.0s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-e2e-coverage.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:embed-arch-parity',
    run: '.ci/scripts/test/gates/test-embed-arch-parity.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-embed-arch-parity.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:embed-asset-freshness',
    run: '.ci/scripts/test/gates/test-embed-asset-freshness.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-embed-asset-freshness.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:unverified-downloads',
    run: '.ci/scripts/test/gates/test-unverified-downloads.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-unverified-downloads.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:devcontainer-pin-freshness',
    run: '.ci/scripts/test/gates/test-devcontainer-pin-freshness.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-devcontainer-pin-freshness.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:embed-credits',
    run: '.ci/scripts/test/gates/test-embed-credits.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-embed-credits.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:emit-advisory',
    run: '.ci/scripts/test/gates/test-emit-advisory.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-emit-advisory.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:external-gate-wrapper',
    run: '.ci/scripts/test/gates/test-external-gate-wrapper.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-external-gate-wrapper.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:gate-anti-vacuity',
    run: '.ci/scripts/test/gates/test-gate-anti-vacuity.sh',
    slow: true, // 72.0s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-gate-anti-vacuity.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:gate-paths-exist',
    run: '.ci/scripts/test/gates/test-gate-paths-exist.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-gate-paths-exist.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:gate-skip-announcer',
    run: '.ci/scripts/test/gates/test-gate-skip-announcer.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-gate-skip-announcer.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:generate-tag-inputs',
    run: '.ci/scripts/test/gates/test-generate-tag-inputs.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-generate-tag-inputs.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:go-deps-probe-failure',
    run: '.ci/scripts/test/gates/test-go-deps-probe-failure.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-go-deps-probe-failure.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:greenlight',
    run: '.ci/scripts/test/gates/test-greenlight.sh',
    slow: true, // 14.8s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-greenlight.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:greenlight-closure-trace',
    run: '.ci/scripts/test/gates/test-greenlight-closure-trace.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-greenlight-closure-trace.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:housekeeping-phases',
    run: '.ci/scripts/test/gates/test-housekeeping-phases.sh',
    slow: true, // 26.3s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-housekeeping-phases.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:knip-blockers',
    run: '.ci/scripts/test/gates/test-knip-blockers.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-knip-blockers.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:autopilot-guide-comment',
    run: '.ci/scripts/test/gates/test-autopilot-guide-comment.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-autopilot-guide-comment.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:label-guide-comment',
    run: '.ci/scripts/test/gates/test-label-guide-comment.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-label-guide-comment.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:regions-sync',
    run: '.ci/scripts/test/gates/test-regions-sync.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-regions-sync.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:label-inventory',
    run: '.ci/scripts/test/gates/test-label-inventory.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-label-inventory.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:dead-case-arms',
    run: '.ci/scripts/test/gates/test-dead-case-arms.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-dead-case-arms.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:label-references',
    run: '.ci/scripts/test/gates/test-label-references.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-label-references.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:nightly-status-report',
    run: '.ci/scripts/test/gates/test-nightly-status-report.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-nightly-status-report.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:overrides-reasons',
    run: '.ci/scripts/test/gates/test-overrides-reasons.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-overrides-reasons.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:positional-detector',
    run: '.ci/scripts/test/gates/test-positional-detector.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-positional-detector.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:preview-readiness',
    run: '.ci/scripts/test/gates/test-preview-readiness.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-preview-readiness.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    // The `rebase-resolve` verb, driven against REAL halted rebases rather than
    // hand-written stage tables. wl_git.py's own selftest covers the classifier
    // and the union as pure functions; this covers the half that only a real
    // halt can reach -- what git writes into .git/rebase-merge and the index.
    // The first wiring passed (sha, mode) tuples to an oracle wanting bare
    // shas; a pure-function test could not have seen it.
    id: 'gate-test:rebase-resolve',
    run: '.ci/scripts/test/gates/test-rebase-resolve.sh',
    gate: true,
    qualityGateTest: true,
    leaves: [
      '.ci/scripts/test/gates/test-rebase-resolve.sh',
      '.ci/scripts/test/lib/git-fixture.sh',
    ],
    paths: [
      '.claude/hooks/stop/wl_git.py',
      '.ci/scripts/test/gates/test-rebase-resolve.sh',
      '.ci/scripts/test/lib/git-fixture.sh',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    // Which BRANCH the trailer guard is judging, in four HEAD states. Not in
    // test-hooks.sh because every case needs a real repo detached, or halted
    // mid-rebase, and that suite's `check` helper drives the guard against the
    // live tree with no env or cwd control. The defect it pins was invisible on
    // a developer machine and unconditional in CI: `rev-parse --abbrev-ref HEAD`
    // prints the string "HEAD" when detached, so the guard looked for
    // agent/pr/HEAD.md and had no epic set to catch a typo'd id against.
    id: 'gate-test:untagged-commit-branch',
    run: '.ci/scripts/test/gates/test-untagged-commit-branch.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-untagged-commit-branch.sh'],
    paths: [
      '.claude/hooks/pre-bash/block-untagged-commit.sh',
      '.ci/scripts/test/gates/test-untagged-commit-branch.sh',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:profiler-coverage',
    run: '.ci/scripts/test/gates/test-profiler-coverage.sh',
    slow: true, // 21.5s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-profiler-coverage.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:profiler-report',
    run: '.ci/scripts/test/gates/test-profiler-report.sh',
    slow: true, // 16.6s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-profiler-report.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:runner-advice',
    run: '.ci/scripts/test/gates/test-runner-advice.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-runner-advice.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:release-state-consistency',
    run: '.ci/scripts/test/gates/test-release-state-consistency.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-release-state-consistency.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:renet-deadcode',
    run: '.ci/scripts/test/gates/test-renet-deadcode.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-renet-deadcode.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:review-labels',
    run: '.ci/scripts/test/gates/test-review-labels.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-review-labels.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:review-status',
    run: '.ci/scripts/test/gates/test-review-status.sh',
    slow: true, // 86.1s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-review-status.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:run-all-parallel',
    run: '.ci/scripts/test/gates/test-run-all-parallel.sh',
    slow: true, // 10.9s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-run-all-parallel.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:schema-coverage',
    run: '.ci/scripts/test/gates/test-schema-coverage.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-schema-coverage.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:scope-baseline-attest',
    run: '.ci/scripts/test/gates/test-scope-baseline-attest.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-scope-baseline-attest.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:scope-engine',
    run: '.ci/scripts/test/gates/test-scope-engine.sh',
    slow: true, // 13.2s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-scope-engine.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:scope-gate-outputs',
    run: '.ci/scripts/test/gates/test-scope-gate-outputs.sh',
    slow: true, // 11.5s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-scope-gate-outputs.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:scrub-sentinel-empty',
    run: '.ci/scripts/test/gates/test-scrub-sentinel-empty.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-scrub-sentinel-empty.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:shell-counter-increment',
    run: '.ci/scripts/test/gates/test-shell-counter-increment.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-shell-counter-increment.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:skip-plan-reconcile',
    run: '.ci/scripts/test/gates/test-skip-plan-reconcile.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-skip-plan-reconcile.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:slim-timeout',
    run: '.ci/scripts/test/gates/test-slim-timeout.sh',
    gate: true,
    // 23.7s by the floor of its last five (23.7 24.3 24.7 24.9 27.1). It parses
    // every workflow and walks each ubuntu-slim job's timeout, several times over
    // fixture trees. Swept with two siblings on 2026-09-02; a scan of the whole
    // duration cache says these three were the only unmarked gates over budget.
    slow: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-slim-timeout.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:stage-artifacts-channel',
    run: '.ci/scripts/test/gates/test-stage-artifacts-channel.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-stage-artifacts-channel.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:suppression-liveness',
    run: '.ci/scripts/test/gates/test-suppression-liveness.sh',
    slow: true, // 18.3s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-suppression-liveness.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:swallowed-failures',
    run: '.ci/scripts/test/gates/test-swallowed-failures.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-swallowed-failures.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:trap-registry',
    run: '.ci/scripts/test/gates/test-trap-registry.sh',
    slow: true, // 10.2s measured, five samples (reads corpus, manifest, dispatcher, suite, settings)
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-trap-registry.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:tutorial-render-queue',
    run: '.ci/scripts/test/gates/test-tutorial-render-queue.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-tutorial-render-queue.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:watchdog-binary-exec-guard',
    run: '.ci/scripts/test/gates/test-watchdog-binary-exec-guard.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-watchdog-binary-exec-guard.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:watchdog-classifier-chain',
    run: '.ci/scripts/test/gates/test-watchdog-classifier-chain.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-watchdog-classifier-chain.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:watchdog-log-capture',
    run: '.ci/scripts/test/gates/test-watchdog-log-capture.sh',
    slow: true, // 60.9s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-watchdog-log-capture.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:watchdog-no-retry-cancel',
    run: '.ci/scripts/test/gates/test-watchdog-no-retry-cancel.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-watchdog-no-retry-cancel.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:watchdog-retry-allowlist',
    run: '.ci/scripts/test/gates/test-watchdog-retry-allowlist.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-watchdog-retry-allowlist.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:watchdog-schedule-exemption',
    run: '.ci/scripts/test/gates/test-watchdog-schedule-exemption.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-watchdog-schedule-exemption.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:watchdog-supersession',
    run: '.ci/scripts/test/gates/test-watchdog-supersession.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-watchdog-supersession.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:watchdog-observer-exclusion',
    run: '.ci/scripts/test/gates/test-watchdog-observer-exclusion.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-watchdog-observer-exclusion.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:plan-housekeeping',
    run: '.ci/scripts/test/gates/test-plan-housekeeping.sh',
    // 7.6s alone, ~20s in the pre-push lane, and the lane is what the tier is
    // about. It drives the REAL gate against 13 fixture git repositories, so its
    // cost is 13 process trees rather than anything it computes -- exactly the
    // shape that stretches under 20x contention. It was already borderline
    // (samples 19.9-23.0s) and a 13th case tipped it.
    slow: true,
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-plan-housekeeping.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:fetch-depth-safety',
    run: '.ci/scripts/test/gates/test-fetch-depth-safety.sh',
    // 7.9s alone, and the same shape as plan-housekeeping above: three fixture
    // repositories of 60 commits each, so the cost is process trees rather than
    // computation and it stretches under the lane's 20x contention.
    slow: true,
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-fetch-depth-safety.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:commit-identity',
    run: '.ci/scripts/test/gates/test-commit-identity.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-commit-identity.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:client-bundle-budget',
    run: '.ci/scripts/test/gates/test-client-bundle-budget.sh',
    // 8.3s alone, ~20s in the pre-push lane. Two `npx tsx` starts (the gate's selftest
    // and a mutant of it), which is process cost rather than computation and is exactly
    // what stretches under 20x contention.
    slow: true,
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-client-bundle-budget.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:resprofile',
    noProfile: true,
    // Pristine warns, seeded enforces a planted E6, seeding refuses a silent shrink,
    // and a mutant with wall scaling removed reds the gate's own control.
    run: '.ci/scripts/test/gates/test-resprofile.sh',
    slow: true,
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-resprofile.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:shadow-compare',
    run: '.ci/scripts/test/gates/test-shadow-compare.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-shadow-compare.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:bws-map',
    run: '.ci/scripts/test/gates/test-bws-map.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-bws-map.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:bws-env',
    run: '.ci/scripts/test/gates/test-bws-env.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-bws-env.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:workflow-contracts',
    run: '.ci/scripts/test/gates/test-workflow-contracts.sh',
    gate: true,
    // 22s by the floor of its last five (22.4, 55.7, 56.2, 56.6, 59.3). It
    // drives the real check-workflow-gates.sh against several fixture trees,
    // and that script parses every workflow with PyYAML five times over.
    slow: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-workflow-contracts.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:workflow-pr-environment',
    run: '.ci/scripts/test/gates/test-workflow-pr-environment.sh',
    // Sibling of workflow-env-shell-vars: the rule lives inside
    // check:ci-workflows, this drives it against fixtures in both directions.
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-workflow-pr-environment.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:workflow-env-shell-vars',
    run: '.ci/scripts/test/gates/test-workflow-env-shell-vars.sh',
    slow: true, // 17.8s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-workflow-env-shell-vars.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:workflow-inline',
    run: '.ci/scripts/test/gates/test-workflow-inline.sh',
    slow: true, // 30.6s measured
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-workflow-inline.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
];

/** The root workflow every CI run enters through. */
const ENTRY_WORKFLOW = '.github/workflows/ci.yml';
/** Jobs of ENTRY_WORKFLOW that are themselves part of the quality surface. */
const ENTRY_JOBS = ['quality', 'review-gate'];

/**
 * Workflows outside this set are not part of the parity surface.
 *
 * COMPUTED, NEVER HAND-LISTED. Direction B produced 14 release/CD/E2E scripts
 * that are correctly out of scope; listing them as exemptions would be 14
 * permanent lies in a suppression file. So scope is structural: the transitive
 * closure of `uses: ./.github/workflows/*` reachable from ci.yml's `quality`
 * job, plus the `review-gate` job's own steps. Iterating `uses:` rather than
 * matching names is what stops a new lane workflow escaping the gate, and is
 * the same technique test-scope-engine.sh is registered in the anti-vacuity
 * harness for.
 *
 * An entry is a repo-relative workflow path, optionally suffixed `#<jobId>` to
 * scope the surface to a single job of that file. review-gate is job-scoped
 * because the rest of ci.yml (build, release, E2E) is out of scope.
 *
 * AN ENTRY JOB THAT IS NOT THERE COLLAPSES THE SURFACE, ON PURPOSE. If `quality`
 * were renamed, a version of this that quietly emitted a job-scoped stub would
 * hand the caller a non-empty surface containing nothing, and the reverse
 * direction would go silent over the entire quality tier while still reporting
 * a clean run. That is the vacuity failure this file exists to prevent, so a
 * missing entry job returns the empty surface and the caller's preflight
 * refuses to run.
 */
export function paritySurface(repoRoot: string): string[] {
  const entryPath = path.join(repoRoot, ENTRY_WORKFLOW);
  if (!fs.existsSync(entryPath)) return [];

  const out: string[] = [];
  const seen = new Set<string>();
  const queue: string[] = [];

  // job id -> reusable workflow it calls (or '' when it has its own steps), for
  // the jobs of ci.yml only.
  const calls = new Map<string, string>();
  let job = '';
  for (const raw of fs.readFileSync(entryPath, 'utf-8').split('\n')) {
    const jobMatch = raw.match(/^ {2}([\w-]+):\s*$/);
    if (jobMatch) {
      job = jobMatch[1];
      calls.set(job, '');
      continue;
    }
    const uses = raw.match(/^ {4}uses:\s*(\.\/\.github\/workflows\/[\w.-]+)\s*$/);
    if (uses && job) calls.set(job, uses[1].replace(/^\.\//, ''));
  }

  for (const j of ENTRY_JOBS) {
    const called = calls.get(j);
    if (called === undefined) return [];
    if (called) queue.push(called);
    else out.push(`${ENTRY_WORKFLOW}#${j}`);
  }

  while (queue.length > 0) {
    const file = queue.shift();
    if (file === undefined || seen.has(file)) continue;
    seen.add(file);
    const abs = path.join(repoRoot, file);
    if (!fs.existsSync(abs)) continue;
    out.push(file);
    for (const m of fs
      .readFileSync(abs, 'utf-8')
      .matchAll(/^ {4}uses:\s*(\.\/\.github\/workflows\/[\w.-]+)\s*$/gm)) {
      queue.push(m[1].replace(/^\.\//, ''));
    }
  }
  return out;
}
