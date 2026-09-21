/**
 * The single gate inventory both halves of the local CI runner consume.
 *
 * scripts/gates/check-ci-parity.ts reads it as the authoritative "what the local run
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
 * `qualityGateTest` set against the on-disk glob the battery itself uses.
 */

// RE-EXPORTED, not redefined: every existing importer of GateSpec/CiCoverage/ paritySurface keeps working unchanged, which is what makes this split non-behavioural and safe to land on its own.
export { paritySurface } from './surface.js';
export type { CiCoverage, GateSpec } from './gate-spec.js';

import type { GateSpec } from './gate-spec.js';

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
 *     scripts/gates/check-ci-parity.ts subsumes and replaces both (plan section 6.1).
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
    leaves: ['scripts/gates/check-workspace-versions.ts', 'syncpack'],
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
    leaves: ['scripts/gates/check-deps.ts'],
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
    // gate:false since 2026-09-06. One eslint process over every root measured 166.5s and
    // pinned one scheduler slot for the whole of it, so this is now the AGGREGATE of four sharded scripts, each scheduled on its own below. Measured the same day: the four run concurrently in 87.5s wall, about 1.90x -- NOT the 3.0x a per-root serial sum predicts,
    // because four eslint processes contend and each costs 30-40% more concurrently than
    // alone. The identical baseline re-measured 225.6s forty minutes later, so the ratio is a range and never a threshold. The body and `leaves` stay BYTE-IDENTICAL so the 'Lint' step still resolves to both leaves for every shard (R3), and CI keeps one step. WHAT HOLDS THE SHARDS HONEST: .ci/scripts/quality/check_lint_scope_coverage.py follows the `npm run` links out of this key
    // and unions the roots it finds, so deleting a shard, or a root from a shard, reds on the files that stopped being linted. It deliberately does not hard-code the shard names, because a hard-coded list of four would silently stop counting a fifth.
    gate: false,
    weight: 2,
    heavy: true,
    // eslint no longer runs directly: check:lint calls scripts/eslint-heap.sh,
    // which clamps the heap downward only when the host cannot honour the requested size (never raises -- CI keeps its full request) and then
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
    id: 'check:lint:cli',
    run: 'npm run check:lint:cli',
    slow: true, // 65.1s alone / 87.5s in the concurrent four
    gate: true,
    weight: 2,
    heavy: true,
    leaves: ['scripts/eslint-heap.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Lint',
    },
  },
  {
    id: 'check:lint:web',
    run: 'npm run check:lint:web',
    slow: true, // 60.8s alone / 83.2s in the concurrent four
    gate: true,
    weight: 2,
    heavy: true,
    leaves: ['scripts/eslint-heap.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Lint',
    },
  },
  {
    id: 'check:lint:tooling',
    run: 'npm run check:lint:tooling',
    slow: true, // measured in the concurrent four; retier from the reference worktree
    gate: true,
    weight: 2,
    heavy: true,
    leaves: ['scripts/eslint-heap.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Lint',
    },
  },
  {
    id: 'check:lint:account',
    run: 'npm run check:lint:account',
    slow: true, // measured in the concurrent four; retier from the reference worktree
    gate: true,
    weight: 2,
    heavy: true,
    // TWO leaves, not one: this shard alone chains `biome lint private/account/` after
    // eslint. Landing it with the other three shards' single leaf reddened
    // check:ci-parity hygiene immediately, which is the split-turns-hygiene-red case the proposal warned about and the reason leaves are derived with resolveLeaves rather than copied between sibling entries.
    leaves: ['biome', 'scripts/eslint-heap.sh'],
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
    leaves: ['.ci/rediacc_ci/quality/typecheck_workers.py', 'knip'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Unused exports (knip)',
    },
  },
  // >>> gen-manifest: region 1
  {
    id: 'check:ci-knip-blockers',
    run: 'npm run check:ci-knip-blockers',
    gate: true,
    leaves: ['scripts/gates/check-knip-blockers.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'knip BLOCKER reasons',
    },
  },
  // <<< gen-manifest: region 1
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
    // gate:false since 2026-09-06. Its 18 constituents are scheduled individually below;
    // NINE of them were already separate gates and therefore ran TWICE per full local run. The body and `leaves` stay byte-identical so the workflow's 'i18n' step still resolves to every child's leaf (R3, check-ci-parity.ts), CI keeps one step, and
    // package.json's check:i18n key needs no edit at all.
    // ACCEPTANCE IS A SET, not a timing: the union of the children's leaves equals this entry's 28 declared leaves exactly. Shrink the children and that equality breaks. `mutex: ['www-src-probe']` MOVED to check:i18n:key-usage. A mutex on an entry the scheduler never runs protects nothing, and it is that child, not this aggregate, that writes packages/www/src/__control_probe__.tsx
    // while knip scans.
    gate: false,
    leaves: [
      'scripts/gates/check-translation-hashes.ts',
      'scripts/gates/check-translation-completeness.ts',
      'scripts/gates/check-translation-key-usage.ts',
      'scripts/__tests__/check-translation-key-usage.control.ts',
      'scripts/__tests__/check-docs-render-parity.control.ts',
      'scripts/__tests__/check-page-locale-imports.control.ts',
      'scripts/gates/check-cli-i18n-key-usage.ts',
      'packages/cli/scripts/check-cli-i18n-help-render.ts',
      'scripts/gates/check-docs-inline-translations.ts',
      'scripts/gates/check-docs-untranslated-text.ts',
      'scripts/gates/check-account-email-templates.ts',
      'packages/www/scripts/validate-cli-docs.js',
      'packages/www/scripts/validate-docs-cli-usage.js',
      'packages/www/scripts/validate-landing-cli-usage.js',
      'packages/www/scripts/validate-translation-freshness.js',
      'packages/www/scripts/validate-content.js',
      'packages/www/scripts/validate-content-accuracy.js',
      'packages/www/scripts/validate-comparison-refs.js',
      'scripts/gates/check-component-hardcoded-strings.ts',
      'scripts/gates/check-cli-docs.ts',
      'scripts/gates/check-i18n-naturalization.ts',
      'scripts/gates/check-locale-only-edits.ts',
      'scripts/gates/check-i18n-ledger-growth.ts',
      'scripts/gates/check-dead-translation-keys.ts',
      'scripts/gates/check-em-dash-surfaces.ts',
      'packages/www/scripts/check-client-i18n-freshness.ts',
      'scripts/gates/check-locale-currency-integrity.ts',
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
    id: 'check:i18n:key-usage',
    // 30.6s FLOOR over 5 runs (median 31.6s): it walks every translation key against every source reference, so its cost is the key count times the corpus and grows with both. The oracle judges the floor rather than the average, so contention cannot manufacture this.
    slow: true,
    run: 'npm run check:i18n:key-usage',
    gate: true,
    // check-translation-key-usage.control.ts writes __control_probe__.tsx INTO packages/www/src for the length of its run. knip (lint:unused) scanning at the same moment reported it as an unused file (seen 2026-09-02 in a full run). knip refuses an ignore entry for a file that is not on disk, so the two are kept apart here instead. The mutex moved down from check:i18n when that
    // entry became a gate:false aggregate: it is this child, not the aggregate, that plants the probe.
    mutex: ['www-src-probe'],
    leaves: [
      'scripts/__tests__/check-translation-key-usage.control.ts',
      'scripts/gates/check-translation-key-usage.ts',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // >>> gen-manifest: region 2
  {
    id: 'check:ci-i18n-hashes',
    run: 'npm run check:ci-i18n-hashes',
    gate: true,
    leaves: ['scripts/gates/check-translation-hashes.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-completeness',
    run: 'npm run check:ci-i18n-completeness',
    gate: true,
    leaves: ['scripts/gates/check-translation-completeness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // <<< gen-manifest: region 2
  {
    id: 'check:ci-i18n-docs-render-parity',
    run: 'npm run check:ci-i18n-docs-render-parity',
    gate: true,
    leaves: ['scripts/__tests__/check-docs-render-parity.control.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-page-locale-imports',
    // 21.9s FLOOR over 5 runs (median 22.9s): it parses every page in every locale, so its cost is pages times locales. The oracle judges the floor rather than the average, so contention cannot manufacture this.
    slow: true,
    run: 'npm run check:ci-i18n-page-locale-imports',
    gate: true,
    leaves: ['scripts/__tests__/check-page-locale-imports.control.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // >>> gen-manifest: region 3
  {
    id: 'check:ci-i18n-docs-inline',
    run: 'npm run check:ci-i18n-docs-inline',
    gate: true,
    leaves: ['scripts/gates/check-docs-inline-translations.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-docs-untranslated',
    run: 'npm run check:ci-i18n-docs-untranslated',
    gate: true,
    leaves: ['scripts/gates/check-docs-untranslated-text.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-account-email-templates',
    run: 'npm run check:ci-i18n-account-email-templates',
    gate: true,
    leaves: ['scripts/gates/check-account-email-templates.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-hardcoded-strings',
    run: 'npm run check:ci-i18n-hardcoded-strings',
    gate: true,
    leaves: ['scripts/gates/check-component-hardcoded-strings.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-naturalization',
    run: 'npm run check:ci-i18n-naturalization',
    gate: true,
    leaves: ['scripts/gates/check-i18n-naturalization.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // <<< gen-manifest: region 3
  {
    id: 'check:ci-i18n-www-cli-docs',
    run: 'npm run check:ci-i18n-www-cli-docs',
    gate: true,
    leaves: ['packages/www/scripts/validate-cli-docs.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-www-docs-cli-usage',
    run: 'npm run check:ci-i18n-www-docs-cli-usage',
    gate: true,
    leaves: ['packages/www/scripts/validate-docs-cli-usage.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-www-landing-cli-usage',
    run: 'npm run check:ci-i18n-www-landing-cli-usage',
    gate: true,
    leaves: ['packages/www/scripts/validate-landing-cli-usage.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-www-translation-freshness',
    run: 'npm run check:ci-i18n-www-translation-freshness',
    gate: true,
    leaves: ['packages/www/scripts/validate-translation-freshness.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-www-content',
    run: 'npm run check:ci-i18n-www-content',
    gate: true,
    leaves: ['packages/www/scripts/validate-content.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-www-content-accuracy',
    run: 'npm run check:ci-i18n-www-content-accuracy',
    gate: true,
    leaves: ['packages/www/scripts/validate-content-accuracy.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  {
    id: 'check:ci-i18n-www-comparison-refs',
    run: 'npm run check:ci-i18n-www-comparison-refs',
    gate: true,
    leaves: ['packages/www/scripts/validate-comparison-refs.js'],
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
    leaves: ['scripts/gates/check-cli-i18n-key-usage.ts'],
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
    leaves: ['scripts/gates/check-cli-docs.ts'],
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
      'scripts/gates/check-locale-currency-integrity.ts',
      'scripts/__tests__/check-locale-currency-integrity.control.ts',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // >>> gen-manifest: region 4
  {
    id: 'check:ci-i18n-locale-only',
    run: 'npm run check:ci-i18n-locale-only',
    gate: true,
    leaves: ['scripts/gates/check-locale-only-edits.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // <<< gen-manifest: region 4
  {
    id: 'check:ci-i18n-ledger-growth',
    run: 'npm run check:ci-i18n-ledger-growth',
    gate: true,
    leaves: ['scripts/gates/check-i18n-ledger-growth.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // Split out of check:i18n so a CI label can skip exactly the tutorial-media validators without skipping the rest of the i18n surface. Deliberately NOT chained back into check:i18n -- chaining it would undo the split -- so this manifest entry is the only thing that keeps it reachable from `npm run ci`. The comment sits ABOVE the brace on purpose: wl_reggate.py's
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
  // >>> gen-manifest: region 5
  {
    id: 'check:ci-rubric-calibration',
    run: 'npm run check:ci-rubric-calibration',
    gate: true,
    leaves: ['.ci/scripts/quality/check_rubric_calibration.py'],
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
    leaves: ['.ci/scripts/quality/check_www_build_token.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'www build token',
    },
  },
  // <<< gen-manifest: region 5
  {
    id: 'check:ci-shape-duplication',
    run: 'npm run check:ci-shape-duplication',
    // 1.9s measured on a quiet machine, five samples. The 21.4s this entry used to claim was a contended sample; the tier oracle judges the floor of `recent` for exactly that reason.
    gate: true,
    leaves: ['scripts/gates/check-shape-duplication.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Shape duplication',
    },
  },
  // >>> gen-manifest: region 6
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
      job: 'quality-static',
      step: 'Git history depth',
    },
  },
  // <<< gen-manifest: region 6
  {
    id: 'check:ci-typecheck-scope-coverage',
    run: 'npm run check:ci-typecheck-scope-coverage',
    slow: true, // 17.7s: `tsc --showConfig` on all 13 projects, twice (selftest + real run)
    gate: true,
    leaves: ['scripts/gates/check-typecheck-scope-coverage.ts'],
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
    // `astro` ADDED 2026-09-06, and its absence was not an oversight in this entry -- it was invisible. check-ci-parity.ts resolved `--workspace` only as a package NAME, so `npm run typecheck --workspace packages/www` fell through to the ROOT manifest and the astro leaf never reached the parity surface. Fixing the resolver surfaced it on the first run.
    leaves: ['tsc', 'astro', '.ci/rediacc_ci/quality/typecheck_workers.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'TypeScript',
    },
  },
  // >>> gen-manifest: region 7
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
  // <<< gen-manifest: region 7
  {
    id: 'check:ci-guard-mutations',
    run: 'npm run check:ci-guard-mutations',
    slow: true, // 25.4s measured
    gate: true,
    weight: 2,
    heavy: true,
    leaves: ['scripts/gates/check-guard-mutations.ts'],
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
  // `Run shared package tests` has run in CI for a long time with NO manifest entry, so `npm run ci` never ran packages/shared's tests locally: CI caught them, a pre-push run did not. The parity gate could not see the hole because R2 only matches `.ci/scripts/**` leaves and a bare vitest is not one. Both entries below close that, and are `check:test-*` rather than `check:ci-*`
  // because R1 only demands manifest membership for the latter.
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
    // Was defined in package.json but referenced nowhere: never ran in CI, and failed locally against its own 60s dev-server-boot timeout the first time it was actually invoked (a cold `astro dev` measured 84s). Fixed the timeout (packages/www/scripts/test-tutorial-player-release-gate.js) alongside wiring this in.
    id: 'check:test:tutorial-player',
    env: {
      PUBLIC_VIDEO_CDN_BASE_URL: 'https://media.rediacc.com',
    },
    run: 'npm run check:test:tutorial-player',
    slow: true, // spins up a real astro dev server; measured ~90s+ cold
    gate: true,
    // It boots the real www dev server and asserts on rendered DOM, so the whole astro graph is in scope: the remark plugins, the i18n catalogs, and the two workspaces www depends on. Narrowing to the content and the player component is the mistake to avoid.
    paths: ['packages/www/**', 'packages/shared/**', 'packages/locales/**', 'package.json'],
    pathsOrigin: 'declared',
    leaves: ['packages/www/scripts/test-tutorial-player-release-gate.js'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Tutorial player release gate',
    },
  },
  // A FOURTH www-dist consumer, which the plan's F5 list did not have. workers/www/src/__tests__/redirect-aliases.test.ts:3 statically imports packages/www/dist/route-manifest.json. `astro build` empties dist before repopulating it, so under parallelism this read the emptied directory and died with "Cannot find module ../../../../packages/www/dist/route-manifest.json". It passed
  // at --jobs 1 only because dist happened to be left populated by an earlier build, so the missing edge was latent in the serial world too. The `ci` pointer below already recorded the truth: CI runs it in the lane that builds www first.
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
  // >>> gen-manifest: region 8
  {
    id: 'check:ci-install-sh-config',
    run: 'npm run check:ci-install-sh-config',
    gate: true,
    leaves: ['.ci/rediacc_ci/release/install_sh_config_check.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'install.sh config tests',
    },
  },
  // <<< gen-manifest: region 8
  {
    id: 'check:ci-rdc-sh-env',
    run: 'npm run check:ci-rdc-sh-env',
    gate: true,
    leaves: ['.ci/rediacc_ci/security/rdc_sh_env_check.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'rdc.sh env tests',
    },
  },
  {
    // FIRST REGISTRATION, not a cutover. `check-ci-job-aggregation.sh` was invoked by nothing at all -- no key, no entry, no workflow line -- so CI ran its gate test and never the gate. Added 2026-09-08 with the port, through its header and one `gate:bind --write`.
    id: 'check:ci-job-aggregation',
    run: 'npm run check:ci-job-aggregation',
    gate: true,
    leaves: ['.ci/scripts/quality/check_ci_job_aggregation.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'CI job aggregation',
    },
  },
  {
    // FIRST REGISTRATION, same story: the scanner for probes whose failure is indistinguishable from an empty result was itself unrun.
    id: 'check:ci-swallowed-failures',
    run: 'npm run check:ci-swallowed-failures',
    gate: true,
    leaves: ['.ci/scripts/quality/check_swallowed_failures.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Swallowed failures',
    },
  },
  // >>> gen-manifest: region 9
  {
    id: 'check:ci-probe-parity',
    run: 'npm run check:ci-probe-parity',
    gate: true,
    leaves: ['.ci/scripts/quality/check_probe_parity.py'],
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
    leaves: ['.ci/scripts/quality/check_drill_verdicts.py'],
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
    leaves: ['.ci/scripts/quality/check_account_probes.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Dev-stack liveness probes',
    },
  },
  // <<< gen-manifest: region 9
  {
    id: 'check:ci-npmrc',
    run: 'npm run check:ci-npmrc',
    gate: true,
    // W7 P4 PILOT, 2026-09-07: the FIRST port cut over from bash to Python. The leaf is the Python entry point now, not check-npmrc.sh. The twin is NOT deleted (invariant 5 forbids that in the porting change; deletion is W7 P5) -- what changed is only which of the two the registry invokes. Condition for cutting over is the one the sibling entry points name in their own docstrings:
    // the differential ledger says the port kept its verdict. `shadow-gate --pair w7p2-npmrc --assert --k 5` reports equivalence over 5 distinct trees, and driven again on this tree both sides exit 0 with byte-identical stdout AND stderr.
    leaves: ['.ci/scripts/quality/check_npmrc.py'],
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
    paths: [
      '.ci/lib/**',
      'run.sh',
      // The verb bodies, and setup() with them, moved here in the 2026-09-06 router split. Without this an edit to the file the gate READS does not select it.
      '.ci/legacy/**',
      '.ci/scripts/quality/check_setup_idempotency.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_setup_idempotency.py'],
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
    leaves: ['scripts/gates/check-native-rebuild.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Native modules rebuilt after every root install',
    },
  },
  {
    // Guards the ONE module allowed to drive a force push. It reaches git via subprocess, which the pre-bash guards structurally cannot see, so this static check is the only thing watching it.
    id: 'check:ci-git-tool-safety',
    run: 'npm run check:ci-git-tool-safety',
    gate: true,
    leaves: ['scripts/gates/check-git-tool-safety.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Mediated git tool stays lease-only and dry-run by default',
    },
  },
  {
    // ./run.sh setup is run repeatedly, so a second run must do no work. This asserts every bootstrap entry point installs through ensure_deps' hash stamp rather than shelling out to npm itself.
    id: 'check:ci-bootstrap-idempotency',
    run: 'npm run check:ci-bootstrap-idempotency',
    gate: true,
    leaves: ['scripts/gates/check-bootstrap-idempotency.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Bootstrap paths install through the dependency stamp',
    },
  },
  {
    // Every commit must name the epic it belongs to, because the review selects an epic's commits by trailer. An untagged commit is reviewed by nobody.
    id: 'check:ci-pr-task-trailers',
    env: {
      PR_BASE_REF: 'origin/${{ github.event.pull_request.base.ref }}',
      PR_HEAD_REF: '${{ github.event.pull_request.head.ref || github.ref_name }}',
    },
    run: 'npm run check:ci-pr-task-trailers',
    gate: true,
    leaves: ['scripts/gates/check-pr-task-trailers.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Every commit names its epic',
    },
  },
  {
    // A guard's refusal message is the last thing a session reads before changing course. It must not prescribe a merge method the platform rejects: allow_squash_merge is false on all five repos.
    id: 'check:ci-merge-method-prose',
    run: 'npm run check:ci-merge-method-prose',
    gate: true,
    leaves: ['scripts/gates/check-merge-method-prose.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Instruction files do not prescribe a rejected merge method',
    },
  },
  {
    // A .ci script must declare the non-baseline binaries it runs. An undeclared one exits 127 with no message under `set -euo pipefail`, and reads as working code on any host that happens to have it.
    id: 'check:ci-shell-declared-commands',
    run: 'npm run check:ci-shell-declared-commands',
    gate: true,
    leaves: ['scripts/gates/check-shell-declared-commands.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'CI scripts declare the binaries they execute',
    },
  },
  {
    // The PR body carries a generated epic block; this asserts it matches the published snapshot, since a generated section nobody checks drifts while still looking authoritative.
    id: 'check:ci-pr-epic-block',
    env: {
      GH_TOKEN: '${{ secrets.GITHUB_TOKEN }}',
      PR_HEAD_REF: '${{ github.event.pull_request.head.ref || github.ref_name }}',
      PR_NUMBER: '${{ github.event.pull_request.number }}',
    },
    run: 'npm run check:ci-pr-epic-block',
    gate: true,
    leaves: ['scripts/gates/check-pr-epic-block.ts'],
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
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_control_vacuity.py'],
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
    paths: ['.devcontainer/**', '.ci/scripts/quality/check_devcontainer_scripts.py'],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_devcontainer_scripts.py'],
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
    // Any shell file anywhere can grow into the linter-killing range, so this one is deliberately not path-narrowed.
    //
    // THE LEAF IS LISTED EXPLICITLY, and it has to be. `**/*.sh` used to cover the gate's own file for free, because the gate WAS a `.sh`. The W7 P4 cutover made the leaf a `.py`, the glob stopped matching it, and `check:ci-gate-manifest` caught the consequence by name: "declares paths but not its own leaf -- editing the gate does not select the gate". Any cutover of a gate whose
    // `paths` glob is extension-shaped inherits this.
    paths: ['**/*.sh', '.ci/scripts/quality/check_shell_size.py'],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_shell_size.py'],
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
    // The lane library and anything that could add a call site to it. Narrow on purpose: this gate reasons about devbox.sh's own invocations, and a wider path filter would imply a coverage it does not have.
    paths: ['.ci/lib/devbox.sh', '.ci/scripts/quality/check_devbox_exec.py'],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_devbox_exec.py'],
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
    // Triggers on every surface that could restate a pin or acquire a tool unpinned, so a version added back into a workflow or the Dockerfile cannot slip past on an unrelated path filter.
    paths: [
      '.devcontainer/**',
      '.github/workflows/**',
      '.ci/scripts/**',
      // The gate's own corpus is `git ls-files '.ci/*.sh'`, and under default (non-glob) pathspec matching `*` CROSSES `/`, so it already scans .ci/legacy/run-legacy.sh. This selector does not: `.ci/scripts/**` misses `.ci/legacy/`. Verified, not assumed -- the two matchers have different semantics and that gap is exactly how a gate keeps reading a file that no longer selects it.
      '.ci/legacy/**',
      '.ci/config/constants.sh',
      'run.sh',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_toolchain_pins.py'],
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
    // third-party action inputs) -- which also removes any check that the TWO files meant to carry the identical value on purpose (toolchain.env and the Dockerfile's matching ARG) actually do. This is that narrower check.
    id: 'check:ci-toolchain-env-dockerfile-sync',
    run: 'npm run check:ci-toolchain-env-dockerfile-sync',
    gate: true,
    paths: [
      '.devcontainer/toolchain.env',
      '.devcontainer/Dockerfile',
      '.ci/scripts/quality/check_toolchain_env_dockerfile_sync.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_toolchain_env_dockerfile_sync.py'],
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
    // The pinned-tools DEFINITION (check-toolchain-pins.sh's GATED_TOOLS) and the host-toolchain runtime GUARD's call sites (block-host-toolchain-run.sh's NPX_TOOLS/BARE_TOOLS) are two independently maintained lists. Either surface changing is when they can drift.
    paths: [
      '.ci/rediacc_ci/quality/toolchain_pins.py',
      '.claude/rediacc_hooks/guards/block_host_toolchain_run.py',
      '.ci/scripts/quality/check_host_toolchain_coverage.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_host_toolchain_coverage.py'],
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
    // Scoped to .claude/hooks and .ci/scripts/quality, where the two real defects lived (a git identity capture guarded against empty but not against rev-parse --abbrev-ref HEAD's misleading literal "HEAD" on a detached checkout, in both an assignment and a bare-statement shape). BOTH suffixes plus the port module: `globToRegExp('.ci/scripts/quality/*.sh')` is
    // `^\.ci/scripts/quality/[^/]*\.sh$`, which does not match the new `.py` leaf, and gate-manifest's leaf-self-inclusion oracle reds without it.
    paths: [
      '.claude/hooks/**/*.sh',
      '.ci/scripts/quality/*.sh',
      '.ci/scripts/quality/*.py',
      '.ci/rediacc_ci/quality/git_op_conditionals.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_git_op_conditionals.py'],
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
    // passes on a host with no shfmt on PATH. This gate exists so that stays true: the defect it names cost four instances in the renet submodule on 2026-08-27, each one a `go install` followed by a bare invocation, and CI could not see any of them because actions/setup-go masks it.
    id: 'check:ci-go-tool-path',
    run: 'npm run check:ci-go-tool-path',
    gate: true,
    paths: ['.ci/**', 'scripts/**'],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_go_tool_path.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Go tool PATH',
    },
  },
  {
    // The gap check:ci-parity leaves open: it proves a gate is WIRED into a workflow, never that the job it landed in can RUN it. Two tsx gates were added to a job that does checkout and nothing else, and run 33125687081 died on `tsx: not found` and took seven cancelled siblings with it. Verified against the pre-fix workflow: this reports exactly those two.
    id: 'check:ci-gate-prerequisites',
    run: 'npm run check:ci-gate-prerequisites',
    gate: true,
    // packages/*/package.json and workers/*/package.json joined 2026-08-30: the resolver now follows `npm run <key> -w <workspace>` into that workspace's OWN scripts (needed to find check:test:tutorial-player's real agent-browser dependency, two hops past root's package.json).
    paths: [
      '.github/workflows/**',
      'package.json',
      'packages/*/package.json',
      'workers/*/package.json',
      '.ci/scripts/quality/**',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_ci_gate_prerequisites.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Gate prerequisites',
    },
  },
  {
    // Found by hand three times in one session (2026-08-28: 891ff49db, 946e0e6da, 74114a26b) before this existed: a script preferring PR_HEAD_REF, invoked by a workflow step that never set it. On this repo's workflow_call chain the runner's default GITHUB_HEAD_REF does not reliably materialise, so the gap is silent -- a skipped check or a degraded one, never a crash.
    id: 'check:ci-pr-head-ref-completeness',
    run: 'npm run check:ci-pr-head-ref-completeness',
    gate: true,
    paths: ['.github/workflows/**', 'package.json', '.ci/scripts/**', 'scripts/**'],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_pr_head_ref_completeness.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'PR_HEAD_REF completeness',
    },
  },
  {
    // A guard that refuses PROSE is a guard nobody can write a doc line about. The class recurred FOUR times on 2026-08-28 and every instance was fixed by hand, including one reintroduced within the hour by the session doing the fixing -- which is the i18n lesson exactly. This probes each guard
    // with a sentence built from its OWN pattern, so it cannot go stale as
    // guards are added.
    id: 'check:ci-guard-mention-anchoring',
    run: 'npm run check:ci-guard-mention-anchoring',
    gate: true,
    // The script scans all 3 chains (pre-bash, pre-edit, pre-ask) since the peer's extension on 2026-08-28; this list had stayed pre-bash-only, the exact "half-populated path table" anti-pattern gate-author.md warns against -- a guard added under pre-edit/pre-ask would not have re-selected this gate on --changed. RE-KEYED BY THE W5 CUTOVER, which is invariant 2: the three chain
    // directories moved and a glob that matches nothing can only EXCLUDE. The gate now reads its PATTERNS from the frozen oracles and PROBES the live Python guards, so both trees select it; the port tree is what actually refuses commands, and it was the one this table would have stopped watching.
    paths: [
      '.claude/oracles/**',
      '.claude/rediacc_hooks/guards/**',
      '.claude/rediacc_hooks/dispatch.py',
      '.ci/scripts/quality/check_guard_mention_anchoring.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_guard_mention_anchoring.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Guard mention anchoring',
    },
  },
  {
    // The manifest is the pre-push lane's only source of truth about which gates are cheap and which files select them, and nothing re-reads it. Three oracles, each with both directions in --selftest: a `slow` claim must agree with the measured cache BOTH ways (a cheap gate marked slow is the invisible direction -- the push stays fast while coverage shrinks); a gate declaring
    // paths must include its own leaves, or editing the gate does not select the gate; and a declared glob must match at least one tracked file. Found eight live leaf violations and one mis-tiered gate on its first run.
    id: 'check:ci-gate-manifest',
    run: 'npm run check:ci-gate-manifest',
    gate: true,
    paths: ['scripts/ci-runner/**', 'scripts/gates/check-gate-manifest.ts'],
    pathsOrigin: 'declared',
    leaves: ['scripts/gates/check-gate-manifest.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Gate manifest self-consistency',
    },
  },
  {
    // TRAPS.md is a REGISTRY, not prose: every `## ` entry names the instrument that enforces it, and the gate proves that pointer RESOLVES and is LIVE. Presence alone would be worse than nothing -- the cheapest thing to name under a coverage gate is a check that cannot fire -- so a gate: pointer must be scheduled by `npm run ci`, a hook: rule must have both a firing and a silent
    // case, and a file: pointer must be reachable from something that runs it. No `paths`, deliberately: pointers resolve against the manifest, package.json, the dispatcher, the hook suite and settings.json, so almost any change can dangle one, and a half-populated path table would drop the gate from --changed exactly when it was needed.
    id: 'check:ci-trap-registry',
    run: 'npm run check:ci-trap-registry',
    gate: true,
    leaves: ['.ci/scripts/quality/check_trap_registry.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Trap registry dispositions',
    },
  },
  {
    // The runner's 21 assertions were its ONLY controls and ran on ONE side: `npm run ci` executes them on a developer machine and nothing in CI did, which is the "a gate that runs on one side only" case check:ci-parity exists to name. They pin the pre-push lane's correctness -- glob semantics (a `**` glob must match a root-level run.sh), gitlink widening (a changed submodule is
    // one diff entry, not a file list), and that --list reflects the SELECTION rather than every spec -- each with its converse.
    id: 'check:ci-runner-selftest',
    run: 'npm run check:ci-runner-selftest',
    gate: true,
    // The leaf must be inside the paths, or editing the runner does not select the gate that checks the runner (check:ci-gate-manifest asserts this).
    paths: ['scripts/ci-runner/**'],
    pathsOrigin: 'declared',
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
    // Triggers on the enforcement layer itself and on the coverage it is judged by, so weakening a guard and dropping its cases in one commit cannot slip through on an unrelated path filter.
    paths: [
      '.claude/hooks/**',
      'scripts/data/hook-inventory-baseline.json',
      'scripts/data/hook-coverage-baseline.json',
      '.ci/scripts/quality/check_hook_integrity.py',
      // Added 2026-09-06 with W11 P3. This gate's audited corpus AND its case corpus are now both decided by this file, and run.ts only selects a path-scoped gate when a changed file matches one of its globs. Without this entry a commit touching only the scope file runs a CI where this gate is not selected, so dropping a guard_dirs entry would be invisible: the corpus shrinks and
      // nothing reds. That is the silent-narrowing shape this program keeps finding.
      'scripts/data/hook-audit-scope.json',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_hook_integrity.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Hook integrity',
    },
  },
  {
    // A detector built as `producer | grep -q` under pipefail cannot reliably fail: grep -q exits at its first match, SIGPIPEs the producer, and pipefail makes that 141 the verdict. check-ci-watch-recipe.sh shipped exactly that in both detectors and certified 124 files clean over a real offender for as long as it existed.
    id: 'check:ci-pipefail-grep-q',
    run: 'npm run check:ci-pipefail-grep-q',
    slow: true, // 13.5s standalone / 37.0s contended: it greps every shell file twice
    gate: true,
    // `.ci/lib/**`, `.devcontainer/**` and `.ci/media/**` joined the corpus with the printf/echo widening, and this list is what decides whether CI RUNS the gate when one of them changes. It was expanded in gates.lock.json alone, which is generated from here -- so regenerating the lock would have quietly narrowed the gate back and left it not watching the very directories the
    // sweep just converted sites in. A green gate with less coverage than yesterday.
    paths: [
      '.ci/scripts/**',
      'scripts/**',
      '.claude/hooks/**',
      '.ci/lib/**',
      '.devcontainer/**',
      '.ci/media/**',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_pipefail_grep_q.py'],
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
    // The defect lives in PROSE agents copy, so the trigger set is the prose, not the code: every instruction surface that has ever carried the loop.
    paths: [
      '.claude/skills/ci-watch/**',
      '.claude/commands/**',
      '.claude/agents/**',
      '.claude/hooks/**',
      'docs/agent-reference/**',
      '.ci/scripts/quality/check_ci_watch_recipe.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_ci_watch_recipe.py'],
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
    // The pairs it checks: ci-trace.py against its skill, run.ts against ci-gates.md. Trigger on either script or either doc changing.
    paths: [
      '.ci/scripts/ci/ci-trace.py',
      '.claude/skills/ci-watch/**',
      'scripts/ci-runner/run.ts',
      'docs/agent-reference/ci-gates.md',
      // The port is both what CI RUNS (`leaves`) and what an edit SELECTS (`paths`). The bash twin that used to sit beside it here was retired in W7 P5.
      '.ci/scripts/quality/check_cli_doc_coverage.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_cli_doc_coverage.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: "CLI docs stay in sync with their scripts' real flags",
    },
  },
  // >>> gen-manifest: region 10
  {
    id: 'check:ci-ceph-image-pin',
    run: 'npm run check:ci-ceph-image-pin',
    gate: true,
    leaves: ['scripts/gates/check-ceph-image-pin.ts'],
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
    leaves: ['scripts/gates/check-naturalization-model-policy.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Naturalization model policy',
    },
  },
  // <<< gen-manifest: region 10
  {
    id: 'check:ci-script-exec-bit',
    run: 'npm run check:ci-script-exec-bit',
    slow: true, // 22.1s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check_script_exec_bit.py'],
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
    // `**/package.json` is not optional: the root manifest carries the `workspaces` array and every workspace manifest feeds the root lockfile's resolution, so a dependency bump
    // with no lockfile edit is exactly what `npm ci --dry-run` exists to catch.
    paths: [
      '**/package-lock.json',
      '**/package.json',
      'private/account',
      '.ci/scripts/quality/check_lockfile.py',
      '.ci/scripts/lib/common.sh',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_lockfile.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Lockfile',
    },
  },
  // >>> gen-manifest: region 11
  {
    id: 'check:ci-peer-deps',
    run: 'npm run check:ci-peer-deps',
    gate: true,
    leaves: ['.ci/scripts/quality/check_peer_deps.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Verify no peer dependency conflicts',
    },
  },
  // <<< gen-manifest: region 11
  {
    id: 'check:ci-security-audit',
    env: {
      GH_TOKEN: '${{ github.token }}',
    },
    run: 'npm run check:ci-security-audit',
    slow: true, // 60.9s measured
    gate: true,
    leaves: ['.ci/rediacc_ci/security/audit.py'],
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
    leaves: ['.ci/scripts/quality/check_scope_scripts_reachability.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Scope map, reachable scripts/ paths force full CI',
    },
  },
  // >>> gen-manifest: region 12
  {
    id: 'check:ci-mutate-check',
    run: 'npm run check:ci-mutate-check',
    gate: true,
    leaves: ['.ci/scripts/quality/check_mutate_check.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Mutation runner self-test',
    },
  },
  {
    id: 'check:ci-shell-lint',
    run: 'npm run check:ci-shell-lint',
    slow: true, // 124.0s measured
    gate: true,
    // shellcheck.sh enumerates with git ls-files '*.sh' plus untracked. toolchain.env is the only non-.sh input: it pins SHELLCHECK_VERSION, and a different shellcheck emits different findings.
    paths: ['**/*.sh', '.devcontainer/toolchain.env'],
    pathsOrigin: 'declared',
    leaves: ['.ci/rediacc_ci/security/shellcheck.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Shell lint',
    },
  },
  // >>> gen-manifest: region 13
  {
    id: 'check:ci-shell-format',
    run: 'npm run check:ci-shell-format',
    gate: true,
    leaves: ['.ci/rediacc_ci/security/shfmt.py'],
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
    leaves: ['.ci/scripts/quality/check_python_lint.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Python lint + format (ruff)',
    },
  },
  // <<< gen-manifest: region 13
  {
    id: 'check:ci-python-control-plants',
    run: 'npm run check:ci-python-control-plants',
    gate: true,
    // The verdict depends only on the Python gate sources under these two trees. TWO GLOBS AND NOT A FILE LIST, deliberately: a W7 P4 cutover landing a port under the first one is in scope the moment it exists, with no registration and no baseline row to hand-edit. That is the property a shrink-only baseline would have cost, and it is argued in
    // agent/PLAN-ci-vacuity-baseline-registry.md section 5.
    paths: ['.ci/rediacc_ci/**', '.ci/scripts/quality/**'],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_python_control_plants.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Python control plants',
    },
  },
  // >>> gen-manifest: region 14
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
  // <<< gen-manifest: region 14 Offline by construction: it compares .ci/config/actions-allowlist.json, a committed copy of repository settings, against every `uses:` line. The network lives only in --refresh, for the same reason check_secret_reachability splits them -- a gate that needs a token degrades to "passed" where the token is absent.
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
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_actions_allowlist.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Actions allowlist',
    },
  },
  // quality-i18n is the ONLY lane with fetch-depth 0 that also runs on the nightly, and this gate needs both: shallow makes it vacuous (see its header), and a clock-driven gate that never runs on a schedule first surfaces by ambushing an unrelated PR. It is a TENANT of that lane, not an i18n gate.
  {
    id: 'check:ci-plan-housekeeping',
    run: 'npm run check:ci-plan-housekeeping',
    gate: true,
    paths: [
      'agent/PLAN-*.md',
      '.ci/config/plan-lifecycle.json',
      '.ci/policy/.plan-housekeeping-allowlist',
      '.ci/scripts/quality/check_plan_housekeeping.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_plan_housekeeping.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Plan file housekeeping',
    },
  },
  // The comment sits ABOVE the brace deliberately: wl_reggate._manifest_gate_ids
  // matches /\{\s*id:/, so a comment INSIDE the brace makes the entry invisible to
  // check:ci-gate-reachability-coverage (manifest.ts:322 records that trap). Lane: quality-branch. A1-A5 compare the merge-base ledger against HEAD, and that is the only lane with BOTH fetch-depth 0 and the PR head ref. It is pull_request-only, so A1-A5 do not run on push -- the gate says so rather than letting a skip read as a clean result.
  {
    id: 'check:ci-resprofile',
    env: {
      GITHUB_BASE_REF: '${{ github.base_ref }}',
    },
    noProfile: true,
    run: 'npm run check:ci-resprofile',
    // Judges the PREVIOUS run's process-tree captures (rotated by this runner at start), so it never reads a torn file. Pristine until the baseline is seeded.
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
    // Box A2's other half. `gate-bind` pins header -> workflow for an emitted step; this pins workflow -> lock, and the two together close the chain. Without it a step's `env:` could be dropped in a rewrite and nothing would red: the measured receipt is stripping DOCKERHUB_TOKEN from ci-quality.yml and running the whole battery green.
    id: 'check:ci-step-env-parity',
    run: 'npm run check:ci-step-env-parity',
    gate: true,
    leaves: ['scripts/gates/check-ci-step-env-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Step env parity',
    },
  },
  {
    // W8 P2. Every environment variable this repo reads or supplies, classified by who supplies the value and who may read it. Five readers derive the corpus from tracked files on EVERY run and no count is written down anywhere: the box quoted 1,014, its own design note re-measured 745 then 721 then 777, and the swing was one developer's .env.pre-rename.bak. Four set-arithmetic
    // clauses hold the derived set against an eight-shard classification; the eighth shard is tombstones, so "a dead name came back" and "a new name is unclassified" are one assertion rather than two mechanisms to keep in sync.
    id: 'check:ci-env-manifest',
    run: 'npm run check:ci-env-manifest',
    gate: true,
    leaves: ['.ci/scripts/quality/check_env_manifest.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Env manifest',
    },
  },
  {
    // W8 P4. `set -a; source <envfile>` EXECUTES the file and lets it overwrite the shell, on files holding ACCOUNT_ED25519_PRIVATE_KEY and ACCOUNT_JWT_SECRET. Three sites adopted env_file_load; this sweeps for the pattern returning, RUNS each adopted site's own line against a planted override, and drives a real `set -a; source` on the same fixture demanding the OPPOSITE answer --
    // without which the per-site check would pass just as happily against a helper that read nothing at all.
    id: 'check:ci-env-file-adoption',
    run: 'npm run check:ci-env-file-adoption',
    gate: true,
    leaves: ['.ci/scripts/quality/check_env_file_adoption.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Env file adoption',
    },
  },
  {
    // D0. The exec baseline W5's "2 processes per Bash tool call" target is defined against;
    // it did not exist in the tree until 2026-09-09, so the target was unfalsifiable. Pins per-tool and per-event harness process counts from .claude/settings.json and refuses in BOTH directions, which is what makes D4's collapse claim its own numbers.
    id: 'check:ci-hook-exec-baseline',
    run: 'npm run check:ci-hook-exec-baseline',
    gate: true,
    leaves: ['.ci/scripts/quality/check_hook_exec_baseline.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Hook exec baseline',
    },
  },
  {
    // D1. `.claude/rediacc_hooks` has exactly ONE platform seam and nothing kept it that way. A /proc read added to a guard works for every reviewer, because every reviewer is on Linux, and fails silently on macOS by finding nothing. AST, not grep: a textual sweep
    // for pgrep returns 15 hits and 14 are prose or a pattern matched against someone
    // else's command line.
    id: 'check:ci-hook-cross-os',
    run: 'npm run check:ci-hook-cross-os',
    gate: true,
    leaves: ['.ci/scripts/quality/check_hook_cross_os.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Hook cross-OS seams',
    },
  },
  {
    // W4 P3d. The vendored blocker copy under .ci/breakpoint must stay a strict subset of the canonical list, and the corpus's "exactly five divergences" was a MAGIC NUMBER: it said which count, never which five, so it could not see one row leaving as another arrived. This derives all five and attributes each, and refuses rather than judging when the digest has already drifted
    // (that is check-breakpoint-drift's job).
    id: 'check:ci-vendored-blocker-derivation',
    run: 'npm run check:ci-vendored-blocker-derivation',
    gate: true,
    leaves: ['.ci/scripts/quality/check_vendored_blocker_derivation.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Vendored blocker derivation',
    },
  },
  {
    // The control-plant class in bash and TypeScript, tree-wide. Python is delegated to check:ci-python-control-plants and the delegation is ASSERTED, not documented: if that entry point stops existing or stops being registered, this gate REFUSES rather than leaving a third of the class unscanned. A control mutant built by raw substitution passes for free when its needle has gone
    // -- it scans unmutated text and asserts the opposite verdict about it. Seeded 2026-09-09 at 25 unproven plants of 33; the baseline is shrink-only and set-equal in both directions. NO `paths:` ON PURPOSE: the corpus is every tracked .sh and .ts, so a path table would make `--changed` drop this gate exactly when a control moves.
    id: 'check:ci-plant-proofs',
    run: 'npm run check:ci-plant-proofs',
    gate: true,
    leaves: ['.ci/scripts/quality/check_plant_proofs.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Control plant proofs',
    },
  },
  {
    // W8 P6. 445 module:NAME pairs across 164 tracked Python modules, derived from the AST and frozen as a shrink-only SET. Set equality BOTH ways is what makes the baseline untrimmable: deleting an entry whose read persists reds as NEW, banking one no read backs reds as STALE. A blanket `--write` `-baseline` (written split: the shrink-only gate's offerer scan is a text grep, so
    // quoting the flag whole makes this comment an offender) is refused whenever it would ADD a pair, so a trimmer cannot reseed past it; additions are typed with --allow-new, which is itself checked against the derived set so it cannot pre-bank. 124 read sites hold the name in a variable, so constant resolution recovers 87 pairs a literal scan cannot see -- it is load-bearing,
    // not polish.
    id: 'check:ci-python-env-registry',
    run: 'npm run check:ci-python-env-registry',
    gate: true,
    leaves: ['.ci/scripts/quality/check_python_env_registry.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Python env registry',
    },
  },
  // >>> gen-manifest: region 15
  {
    id: 'check:ci-secret-supply',
    run: 'npm run check:ci-secret-supply',
    gate: true,
    leaves: ['.ci/scripts/quality/check_secret_supply.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Secret supply',
    },
  },
  // <<< gen-manifest: region 15
  {
    // D2. 133 WORKLIST_* names read at 181 sites with no registry and no schema. A typo'd name reads as UNSET, and for the four flags defaulting to `on` that is fail-open. Set equality both ways. Derived from the AST rather than grep, which is why it is 133 and not the grep answer of 134: WORKLIST_EMAIL is prose-only history, read nowhere.
    id: 'check:ci-worklist-env-registry',
    run: 'npm run check:ci-worklist-env-registry',
    gate: true,
    leaves: ['.ci/scripts/quality/check_worklist_env_registry.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Worklist env registry',
    },
  },
  {
    // A gate-test that writes a REAL tracked file and restores it in a `finally` corrupts that file for real if a kill lands in the write-to-restore window -- it happened twice in one session to worklist-env-registry.json, from two unrelated causes. AST-scans every gate-test file for a module-level real-path constant that is also the target of a .write_text/.write_bytes call.
    id: 'check:ci-gate-test-real-file-plants',
    run: 'npm run check:ci-gate-test-real-file-plants',
    gate: true,
    leaves: ['.ci/scripts/quality/check_gate_test_real_file_plants.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Gate-test real-file plants',
    },
  },
  {
    // /tmp is a tmpfs with a FIXED inode count independent of df -h's block view -- a tree can show 19G free of 29G and still be totally exhausted. A real incident this campaign hit exactly that (pytest tmp_path retention, 1,048,574/1,048,576 inodes used) and every Bash call started failing with ENOSPC while disk space looked completely healthy.
    id: 'check:ci-tmpfs-health',
    run: 'npm run check:ci-tmpfs-health',
    gate: true,
    leaves: ['.ci/scripts/quality/check_tmpfs_health.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Tmpfs health',
    },
  },
  {
    // E2. rdc.sh's --native SEA build moved to rediacc_ci.native. `plan()` takes system and machine as ARGUMENTS defaulting to the host, so all three platform arms are driven
    // from one Linux box every run -- strictly more than the macOS CI job the box asked
    // for, which would have covered one arm.
    id: 'check:ci-rdc-native',
    run: 'npm run check:ci-rdc-native',
    gate: true,
    leaves: ['.ci/scripts/quality/check_rdc_native.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'rdc.sh wrapper budget and --native arms',
    },
  },
  {
    // W9 P2.0, the precondition that makes W9 P2's move safe. `scripts/data/domains.json` classified 228 files and NOTHING read it. Clause 1 (total classification) enforces
    // from day one and costs nothing today, which is the point: it refuses the file that
    // belongs to no domain, and a file nobody classified is one the move has no destination for. Scope is enumerated INDEPENDENTLY of the rules, or clause 1 would be a tautology.
    id: 'check:ci-domain-partition',
    run: 'npm run check:ci-domain-partition',
    gate: true,
    leaves: ['scripts/gates/check-domain-partition.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'scripts/ domain partition',
    },
  },
  {
    // U4. The Python twin of the dead-bash instrument. SIX execution routes, not three: wired, pytest, shadow, glob, imported, mentioned. Prose is deliberately NOT a route -- `agent/`, `docs/`, `*.md` and `.ci/shadow/` are excluded, the last so the shadow route can EXPIRE when its bash twin goes rather than vouching for itself forever.
    id: 'check:ci-dead-python',
    run: 'npm run check:ci-dead-python',
    gate: true,
    leaves: ['.ci/scripts/quality/check_dead_python.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Dead Python',
    },
  },
  {
    // W4 P4b. Four directions over the policy directory, because a one-way check reads a DELETED list as "nothing is suppressed": nothing on disk outside POLICY_FILES, nothing in POLICY_FILES missing from disk, Python and TypeScript agreeing on both the names and POLICY_DIR, and no literal policy-path join outside the two seams. Its honest control is a run against 19c45c78e, the
    // commit whose drift this estate actually suffered; it reds there naming exactly `.language-policy-allowlist`.
    id: 'check:ci-policy-inventory',
    run: 'npm run check:ci-policy-inventory',
    gate: true,
    leaves: ['.ci/scripts/quality/check_policy_inventory.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Policy inventory',
    },
  },
  {
    id: 'check:ci-plan-boxes',
    env: {
      GITHUB_BASE_REF: '${{ github.base_ref }}',
    },
    run: 'npm run check:ci-plan-boxes',
    gate: true,
    paths: [
      'agent/PLAN-*.md',
      '.ci/config/plan-boxes.json',
      '.ci/scripts/quality/check_plan_boxes.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_plan_boxes.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-branch',
      step: 'Plan checkbox ledger',
    },
  },
  {
    // The other half of box X0.1. X0.1 PREFIXED the ids so `D-A6` could not be transcribed as a gate rule; this asserts a `D-` id resolves to a row at all, and that a supersession is stated out loud in a commit rather than happening silently.
    id: 'check:ci-decision-ids',
    env: {
      GITHUB_BASE_REF: '${{ github.base_ref }}',
    },
    run: 'npm run check:ci-decision-ids',
    gate: true,
    leaves: ['.ci/scripts/quality/check_decision_ids.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-branch',
      step: 'Decision ids',
    },
  },
  {
    // The third plan gate, and it judges only lines a change ADDS. It was written, landed and then sat inert: it appeared in neither package.json nor the manifest, so it had never once run. That is the registration bottleneck's signature -- a worker finishes the logic in parallel and the last mile waits on the one file only the driver writes. Scope is plans and agent/INDEX.md
    // only. agent/<session>/STATE.md is deliberately excluded: it is read-only to every session but its owner, so a red there would name a line the reader is forbidden to fix.
    id: 'check:ci-plan-citations',
    env: {
      GITHUB_BASE_REF: '${{ github.base_ref }}',
    },
    run: 'npm run check:ci-plan-citations',
    gate: true,
    paths: ['agent/PLAN-*.md', 'agent/INDEX.md', '.ci/scripts/quality/check_plan_citations.py'],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_plan_citations.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-branch',
      step: 'Plan citations',
    },
  },
  {
    // The other half of the plan lifetime. check:ci-plan-boxes rules on a plan's boxes; this one rules on a COMPACTED plan's pointer back to its full text, which lives in a git blob and is the only thing standing between a record and an unreachable document that still advertises a recovery command.
    id: 'check:ci-plan-record',
    env: {
      GITHUB_BASE_REF: '${{ github.base_ref }}',
    },
    run: 'npm run check:ci-plan-record',
    gate: true,
    paths: [
      'agent/PLAN-*.md',
      // agent/INDEX.md joined the gate's subject on 2026-09-06 with W12 P1.7. It used to be excluded on the correct reasoning that no plan had been compacted, so the glob matched nothing and could only exclude. It now exists and carries the plan census that SessionStart reads instead of opening 83 files, and R8 compares it byte for byte, so a hand-edit must reach the only gate
      // that checks it.
      'agent/INDEX.md',
      '.ci/scripts/quality/check_plan_record.py',
      '.claude/hooks/stop/wl_planrec.py',
      '.claude/hooks/stop/wl_planindex.py',
    ],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_plan_record.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-branch',
      step: 'Plan records',
    },
  },
  {
    // The five lint rules configured `off` everywhere are outside the liveness gate's universe BY CONSTRUCTION -- it can only observe a rule that fires -- so nothing in this repository ever executed them. A RuleTester harness is the only instrument that can, which is why this is a separate gate and not a wider net cast by the liveness one.
    id: 'check:ci-lint-rule-units',
    run: 'npm run check:ci-lint-rule-units',
    gate: true,
    paths: ['eslint-rules/**', 'scripts/gates/check-lint-rule-units.ts'],
    pathsOrigin: 'declared',
    leaves: ['scripts/gates/check-lint-rule-units.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Lint rule unit specs',
    },
  },
  {
    // The manifest's machine-readable projection, and the gate that keeps it faithful. Three readers parse this file as TEXT because they are not TypeScript; the lock is the file they should read instead. Emitter and checker landed together (invariant 1, the rediacc/console#549 failure class).
    id: 'check:ci-gates-lock',
    run: 'npm run check:ci-gates-lock',
    gate: true,
    paths: [
      'scripts/ci-runner/manifest.ts',
      'scripts/ci-runner/gates.lock.json',
      'scripts/gen/gen-gates-lock.ts',
    ],
    pathsOrigin: 'declared',
    leaves: ['scripts/gen/gen-gates-lock.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Gates lock',
    },
  },
  {
    // The parity half of scripts/gen/gen-docs.ts, and the reason it is NOT a strict subset of gate-test:docs-gen: gen-docs DISCOVERS its targets by scanning for markers and refuses only when the target list is EMPTY, while that gate test asserts merely that one target was found. So a document that loses its markers stops being checked instead of failing, silently, with both green.
    // Measured: strip CLAUDE.md's two marker lines and gen-docs still exits 0 saying `ok CLAUDE.md`. That is the rediacc/console#549 class and invariant 1, an emitter landing without its checker.
    //
    // No `paths:` DELIBERATELY. Its providers read the gates lock, the hook wiring, every tracked file carrying BLOCKER: and the whole .ci tree, so any list short of "the repository" is wrong, and a half-populated one makes --changed drop the gate silently.
    id: 'check:ci-doc-region-parity',
    run: 'npm run check:ci-doc-region-parity',
    gate: true,
    leaves: ['scripts/gates/check-doc-region-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Doc region parity',
    },
  },
  {
    // THE TWO EMITTERS, registered so they are not hand-written keys.
    //
    // check:ci-package-key-budget was RED at HEAD because `gen:docs` and `gen:gates-lock` were added to package.json (W11 P0 and W2.1) without becoming manifest ids, so both counted against the hand-written budget of 49. The gate refuses a baseline that GROWS, and it is right to: a reseed that drains 30 and adds 1 still looks like progress in the totals, which is how a fresh
    // violation gets enshrined as permanent debt. The fix it asks for is to change the VALUE, and the honest value is that these two belong to the registry rather than beside it.
    //
    // gate:false because they WRITE. Nothing `needs` them, so the scheduler never runs them, which is the point: a sweep must never regenerate the artifact it is about to judge. Their verifying twins (check:ci-gates-lock above, and the docs parity gate) are the entries that carry `gate: true`.
    id: 'gen:gates-lock',
    run: 'npm run gen:gates-lock',
    gate: false,
    leaves: ['scripts/gen/gen-gates-lock.ts'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: an emitter, not a validation. CI verifies the committed lock through check:ci-gates-lock, which runs the same file in its default checking mode; a step pointer here would claim CI regenerates the artifact it is meant to be holding still.',
    },
  },
  {
    id: 'gen:docs',
    run: 'npm run gen:docs',
    gate: false,
    leaves: ['scripts/gen/gen-docs.ts'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: an emitter, not a validation. Same shape as gen:gates-lock above: CI checks the generated doc regions rather than rewriting them, so no CI step invokes this script.',
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
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_syncpack_sources.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'syncpack source coverage',
    },
  },
  // >>> gen-manifest: region 16
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
    id: 'check:ci-secret-scope',
    run: 'npm run check:ci-secret-scope',
    gate: true,
    leaves: ['scripts/gates/check-secret-scope.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Secret scope',
    },
  },
  {
    id: 'check:ci-release-key-canonical',
    run: 'npm run check:ci-release-key-canonical',
    gate: true,
    leaves: ['.ci/scripts/quality/check_release_key_canonical.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Release key canonical',
    },
  },
  {
    id: 'check:ci-staging-tag-guard',
    run: 'npm run check:ci-staging-tag-guard',
    gate: true,
    leaves: ['.ci/rediacc_ci/quality/staging_tag_guard.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Staging tag guard',
    },
  },
  {
    id: 'check:ci-release-signing-coverage',
    run: 'npm run check:ci-release-signing-coverage',
    gate: true,
    leaves: ['.ci/scripts/quality/check_release_signing_coverage.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Release signing coverage',
    },
  },
  {
    id: 'check:ci-tracked-credentials',
    run: 'npm run check:ci-tracked-credentials',
    gate: true,
    leaves: ['scripts/gates/check-tracked-credentials.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Tracked credentials',
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
  // <<< gen-manifest: region 16
  {
    id: 'check:ci-guard-feature-completeness',
    run: 'npm run check:ci-guard-feature-completeness',
    gate: true,
    paths: ['.claude/hooks/**', '.ci/scripts/quality/check_guard_feature_completeness.py'],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_guard_feature_completeness.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Guard feature completeness',
    },
  },
  {
    // An apt source rewritten to ONE mirror must carry a fallback to another. Born 2026-08-19, when azure.archive.ubuntu.com refused connections for ninety minutes and took down four consecutive CI attempts: every apt source had been rewritten to that single host, so the surrounding five-attempt retry loop hammered the same dead mirror five times. Existing checks counted retry
    // ATTEMPTS and never asked whether the attempts could reach a different SOURCE, which is why nothing caught it.
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
  // >>> gen-manifest: region 17
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
    leaves: ['scripts/gates/check-dead-service-methods.ts'],
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
    leaves: ['scripts/gates/check-retired-commands-in-docs.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Retired commands in docs',
    },
  },
  {
    id: 'check:ci-inner-timeout-reachable',
    run: 'npm run check:ci-inner-timeout-reachable',
    gate: true,
    leaves: ['.ci/scripts/quality/check_inner_timeout_reachable.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Inner kill timers are reachable',
    },
  },
  {
    id: 'check:ci-control-in-string',
    run: 'npm run check:ci-control-in-string',
    gate: true,
    leaves: ['scripts/gates/check-control-in-string.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Controls are not written inside string literals',
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
  // <<< gen-manifest: region 17
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
  // >>> gen-manifest: region 18
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
  // Answers the question the other two wiring gates cannot: not "is what we declared wired up?" but "did we forget to declare something?". A test file absent from the manifest is absent from BOTH sides of ci-parity, so parity agrees and reports success; gate-reachability can only ask about entries that registered. test-teammate-idle.py was committed with 20 controls and ran
  // nowhere, and this gate then found four more orphans of the same shape. Gate 1 of the sentence-wrapping pair. Source-level and sub-second, so it runs on every PR; the browser half (check:ci-sentence-lines) measures real line boxes and needs a build. Neither subsumes the other. Shrink-only baseline, seeded at 51 because the <Sentences> mechanism does not exist yet -- that is
  // what lets wave B land it incrementally without this gate being either useless or blocking. The half of www-round5's gate 3 the content schema does NOT cover. Per-doc subcategory legality moved into content/config.ts (z.enum + superRefine), where it cannot be bypassed; what is left is thumbnail coverage. The thumbnails are hand-authored and their generator was deleted, so a new
  // doc without one ships a blank browse card in all 13 locales silently -- one file serves every translation, resolved by base slug. Plyr's quality pane cannot host the language picker: it snaps every click to min(options), so the video plays a language nobody chose. Re-adding it is the regression that looks like it works.
  {
    id: 'check:ci-video-player-invariants',
    run: 'npm run check:ci-video-player-invariants',
    gate: true,
    leaves: ['scripts/gates/check-video-player-invariants.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Video player invariants',
    },
  },
  // A skill an agent may edit gets longer every pass, because appending beats rewriting. The cap is what forces the editing pass; skills opt in through `self-improving: true` in their own frontmatter rather than a list here.
  {
    id: 'check:ci-skill-size',
    run: 'npm run check:ci-skill-size',
    gate: true,
    leaves: ['scripts/gates/check-skill-size.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Self-improving skill size',
    },
  },
  // The mechanisms three /en/docs fixes rest on: the tally is announced not shown, the two headings are styled by one shared rule, and the category group is decided before first paint. Structural, not visual -- the interactive gate is wave D gate 2.
  {
    id: 'check:ci-docs-browse-invariants',
    run: 'npm run check:ci-docs-browse-invariants',
    gate: true,
    leaves: ['scripts/gates/check-docs-browse-invariants.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Docs browse invariants',
    },
  },
  // A copy button on a bare `}` or on a YAML key is a control that hands the reader
  // something they cannot paste anywhere. The classifier is lifted out of DocsLayout.astro and run over the real corpus, so this gate exercises the shipped script rather than a second copy of its rules.
  {
    id: 'check:ci-docs-copy-units',
    run: 'npm run check:ci-docs-copy-units',
    gate: true,
    leaves: ['scripts/gates/check-docs-copy-units.ts'],
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
    leaves: ['scripts/gates/check-docs-thumb-coverage.ts'],
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
    leaves: ['scripts/gates/check-sentence-wrapping.ts'],
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
  // <<< gen-manifest: region 18
  {
    id: 'check:ci-lint-scope-coverage',
    run: 'npm run check:ci-lint-scope-coverage',
    slow: true, // 163.0s measured
    gate: true,
    // Its corpus is every tracked js/ts file, so the five extension globs are load-bearing rather than decorative: a NEW source file under a directory no lint root reaches is exactly the failure this gate exists to catch. package.json carries the root lists it
    // follows; eslint.config.js and biome.json carry the ignore and allowlist halves.
    paths: [
      '**/*.js',
      '**/*.cjs',
      '**/*.mjs',
      '**/*.ts',
      '**/*.tsx',
      'package.json',
      'eslint.config.js',
      'biome.json',
      '.ci/scripts/quality/check_lint_scope_coverage.py',
    ],
    pathsOrigin: 'declared',
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
    // A formatter command may not narrow its own config's scope. Sibling of lint-scope-coverage: that one proves FILES reach a linter, this proves the COMMAND does not shrink what biome.json declares.
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
    id: 'check:ci-checkout-cone',
    // A step may not run a file its job never checked out. Corroborates the static claim (this job checks out X) against what the job actually RUNS.
    run: 'npm run check:ci-checkout-cone',
    gate: true,
    leaves: ['.ci/scripts/quality/check_checkout_cone.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Checkout cone covers what steps run',
    },
  },
  {
    id: 'check:ci-battery-clean-tree',
    // The battery's tree snapshot must not abort on a clean checkout. It extracts the REAL tree_state() rather than copying it, and refuses if that function is gone.
    run: 'npm run check:ci-battery-clean-tree',
    gate: true,
    leaves: ['.ci/scripts/quality/check_battery_clean_tree.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Battery clean-tree guard',
    },
  },
  {
    id: 'check:ci-workflow-env-provision',
    // A job may not use a shell variable nothing in that job provides. bash expands an unset name to the empty string, so the failure always surfaces downstream wearing somebody else's name.
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
  // >>> gen-manifest: region 19
  {
    id: 'check:ci-shell-commands',
    run: 'npm run check:ci-shell-commands',
    gate: true,
    leaves: ['.ci/rediacc_ci/security/check_commands.py'],
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
    leaves: ['.ci/scripts/quality/check_gate_id_convention.py'],
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
    leaves: ['.ci/scripts/quality/check_pool_writer_safety.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Pool-registered tests do not write the real tree',
    },
  },
  // <<< gen-manifest: region 19
  // >>> gen-manifest: region 20
  {
    id: 'check:ci-review-turn-capacity',
    run: 'npm run check:ci-review-turn-capacity',
    gate: true,
    leaves: ['.ci/scripts/quality/check_review_turn_capacity.py'],
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
    leaves: ['.ci/scripts/quality/check_review_cap_coherence.py'],
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
  // <<< gen-manifest: region 20
  {
    id: 'check:ci-gate-cwd-independence',
    run: 'npm run check:ci-gate-cwd-independence',
    gate: true,
    // why: a gate that names cwd to build a path means something different under every caller, and "it passed locally" is then true and useless
    leaves: ['scripts/gates/check-gate-cwd-independence.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Gate cwd independence',
    },
  },
  {
    id: 'check:ci-fixture-event-timestamps',
    run: 'npm run check:ci-fixture-event-timestamps',
    gate: true,
    // why: the store sorts by timestamp, so a fixture's literal past date folds before the item it closes and silently does nothing
    leaves: ['scripts/gates/check-fixture-event-timestamps.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Fixture event timestamps',
    },
  },
  {
    id: 'check:ci-worklist-path-resolution',
    run: 'npm run check:ci-worklist-path-resolution',
    gate: true,
    // why: three verbs each spelled "find the worklist" differently and only the unlucky one was ever wrong; a per-site test cannot see a cross-site rule
    leaves: ['scripts/gates/check-worklist-path-resolution.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Worklist path resolution',
    },
  },
  {
    id: 'check:ci-worklist-event-builders',
    run: 'npm run check:ci-worklist-event-builders',
    gate: true,
    // why: a second hand-rolled snapshot builder silently reopened finished work
    leaves: ['scripts/gates/check-worklist-event-builders.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Worklist event builders',
    },
  },
  {
    id: 'check:ci-workflows',
    run: 'npm run check:ci-workflows',
    slow: true, // 12.0s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check_workflows.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Workflow banned patterns',
    },
  },
  // >>> gen-manifest: region 21
  {
    id: 'check:ci-greenlight-closures',
    run: 'npm run check:ci-greenlight-closures',
    gate: true,
    leaves: ['.ci/scripts/quality/check_greenlight_closures.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Greenlight closure paths',
    },
  },
  // <<< gen-manifest: region 21
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
  // >>> gen-manifest: region 22
  {
    id: 'check:ci-actionlint',
    run: 'npm run check:ci-actionlint',
    gate: true,
    leaves: ['.ci/rediacc_ci/security/actionlint.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Workflow lint (actionlint)',
    },
  },
  // <<< gen-manifest: region 22
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
  // >>> gen-manifest: region 23
  {
    id: 'check:ci-app-admin-perm',
    run: 'npm run check:ci-app-admin-perm',
    gate: true,
    leaves: ['.ci/scripts/quality/check_no_app_admin_perm.py'],
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
    leaves: ['.ci/scripts/quality/check_tracked_sidecars.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Tracked runtime sidecars',
    },
  },
  // <<< gen-manifest: region 23
  {
    id: 'check:ci-scans-tracked-paths',
    run: 'npm run check:ci-scans-tracked-paths',
    gate: true,
    leaves: ['.ci/scripts/quality/check_ci_scans_tracked_paths.py'],
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
    // 20.8s measured serially on an idle machine, so this is the gate's own cost and not the 17x parallel load the pre-push lane runs under. The oracle judges the FLOOR of recent samples for exactly that reason, and the floor is over the line too.
    slow: true,
    gate: true,
    leaves: ['.ci/scripts/quality/check_agent_browser_exit.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'agent-browser exit status',
    },
  },
  // >>> gen-manifest: region 24
  {
    id: 'check:ci-silent-failures',
    run: 'npm run check:ci-silent-failures',
    gate: true,
    leaves: ['.ci/scripts/quality/check_silent_failure_patterns.py'],
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
    leaves: ['.ci/scripts/quality/check_compose_env.py'],
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
    leaves: ['.ci/scripts/quality/check_e2e_coverage.py'],
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
    leaves: ['scripts/gates/check-e2e-skip-hygiene.ts'],
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
    leaves: ['.ci/scripts/quality/check_audit_coverage.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Check audit logging coverage for CLI operations',
    },
  },
  // <<< gen-manifest: region 24
  {
    id: 'check:ci-cli-contract',
    run: 'npm run check:ci-cli-contract',
    slow: true, // 12.7s measured
    gate: true,
    needs: ['build:packages'],
    mutex: ['build-artifacts'],
    leaves: ['.ci/scripts/quality/check_cli_contract.py'],
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
    leaves: ['.ci/scripts/quality/check_command_tree.py'],
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
  // >>> gen-manifest: region 25
  {
    id: 'check:ci-design-tree',
    run: 'npm run check:ci-design-tree',
    gate: true,
    leaves: ['scripts/gates/check-design-tree.ts'],
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
    leaves: ['scripts/gates/check-i18n-placeholders.ts'],
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
    leaves: ['scripts/gates/check-i18n-untranslated.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n untranslated',
    },
  },
  // <<< gen-manifest: region 25
  {
    id: 'check:ci-i18n-cross-locale',
    run: 'npm run check:ci-i18n-cross-locale',
    // gate:false since 2026-09-06. Its constituents (check:ci-i18n-cross-locale-core, check:ci-locale-de-contamination and check:ci-locale-config-divergence) are scheduled individually below; scheduling this as well ran the latter two TWICE per full local run. Body and `leaves` unchanged so the step still resolves to every child's leaves.
    gate: false,
    leaves: [
      'scripts/gates/check-i18n-cross-locale.ts',
      'scripts/gates/check-locale-de-contamination.ts',
      'scripts/gates/check-locale-config-divergence.ts',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n cross-locale',
    },
  },
  // >>> gen-manifest: region 26
  {
    id: 'check:ci-i18n-cross-locale-core',
    run: 'npm run check:ci-i18n-cross-locale-core',
    gate: true,
    leaves: ['scripts/gates/check-i18n-cross-locale.ts'],
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
    leaves: ['scripts/gates/check-docs-structure-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Docs structure parity',
    },
  },
  // Chained into check:ci-i18n-cross-locale rather than given a workflow step of its own, so it inherits a REAL CI home instead of a 'local-only' BLOCKER. The two are the same defect class read by two instruments: the stopword detector identifies a language and can only look at the six locales it has function words for, while this one keys on byte equality with the German value
  // and is the only thing that can see contamination in ar/ja/ko/ru/zh/et.
  {
    id: 'check:ci-locale-de-contamination',
    run: 'npm run check:ci-locale-de-contamination',
    gate: true,
    leaves: ['scripts/gates/check-locale-de-contamination.ts'],
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
    leaves: ['scripts/gates/check-locale-sources.ts'],
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
    leaves: ['scripts/gates/check-cli-docs.ts'],
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
    leaves: ['.ci/scripts/quality/check_config_migrations.py'],
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
    leaves: ['scripts/gates/check-schema-coverage.ts'],
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
    leaves: ['scripts/gates/check-shared-constant-duplication.ts'],
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
    leaves: ['scripts/gates/check-shared-esm-resolvable.ts'],
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
    leaves: ['scripts/gates/check-runtime-imports-are-deps.ts'],
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
    leaves: ['scripts/gates/check-backup-manifest-shape-parity.ts'],
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
    leaves: ['scripts/gates/check-ci-fetch-integrity.ts'],
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
    leaves: ['scripts/gates/check-aws-credential-bridge.ts'],
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
    leaves: ['scripts/gates/check-worker-secret-names.ts'],
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
    leaves: ['scripts/gates/check-builder-env-contract.ts'],
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
    leaves: ['scripts/gates/check-backup-bucket-conformance.ts'],
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
    leaves: ['scripts/gates/check-backup-protocol-conformance.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Backup protocol conformance',
    },
  },
  // Covers the CLASS the conformance gate above cannot see: that gate pins the key fields EXIST on both sides of the wire, this one pins that the client never COMPOSES a key when one is missing. The composing fallback was introduced twice, and the second time it was duplicated into the read path, because each path's tests passed in isolation.
  {
    id: 'check:ci-no-client-key-composition',
    run: 'npm run check:ci-no-client-key-composition',
    gate: true,
    leaves: ['scripts/gates/check-no-client-key-composition.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'No client-side key composition',
    },
  },
  // The knobs are spelled in FOUR places (shared schema, account DTO, the sweep that enforces them, the CLI flags). A knob present in three and absent from the sweep is a rule that silently does nothing, and each layer's own tests pass because each layer is internally consistent.
  {
    id: 'check:ci-retention-knob-parity',
    run: 'npm run check:ci-retention-knob-parity',
    gate: true,
    leaves: ['scripts/gates/check-retention-knob-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Retention knob parity',
    },
  },
  // The CLASS behind four separate findings this program hit: an unrun test suite reads exactly like a passing one. private/account/web ran 1 of 34 files, packages/www ran none, packages/shared ran in CI but never locally, and packages/json runs nowhere. This gate makes a suite impossible to be invisible to BOTH CI and the omissions record.
  {
    id: 'check:ci-test-scripts-reachable',
    run: 'npm run check:ci-test-scripts-reachable',
    gate: true,
    leaves: ['scripts/gates/check-test-scripts-reachable.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Test suites are CI-reachable',
    },
  },
  // <<< gen-manifest: region 26
  {
    id: 'check:ci-editorconfig',
    run: 'npm run check:ci-editorconfig',
    // SLOW AGAIN, and the reversal is the record worth keeping. On 2026-09-06 I dropped `slow: true` on a window of [23.8, 4.6, 19.1, 4.7, 5.0]s, reading the 4.6s floor as the honest cost and the two large samples as contention. A day later the window is [28.4, 25.9, 26.3, 27.5, 26.2]s: a 25.9s FLOOR, so the cheap runs were the outlier and not the rule. The oracle judges the floor
    // precisely so one lucky run cannot argue a gate into the pre-push lane, and it caught my mistake within a day.
    slow: true,
    gate: true,
    leaves: ['.ci/scripts/quality/check_editorconfig.py'],
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
    // The non-obvious half is the packages/www/src/data/** block. Phase 5 runs build:account-onboarding, which reads account-onboarding.json, the storyboards and the transcripts, and a missing transcript is a hard failure. A TRANSCRIPT EDIT IN WWW CAN RED THIS GATE with no change anywhere near .ci/ or private/. Phase 4's biome pass only log_warns, so biome.json is deliberately NOT
    // here.
    paths: [
      'private/account',
      '.ci/scripts/quality/check_account_portal.py',
      '.ci/rediacc_ci/quality/account_portal.py',
      '.ci/scripts/lib/common.sh',
      'packages/www/scripts/build-account-onboarding.ts',
      'packages/www/src/data/account-onboarding.json',
      'packages/www/src/data/tutorial-storyboard/**',
      'packages/www/src/data/tutorial-transcripts/**',
      'packages/locales/**',
      'package.json',
    ],
    pathsOrigin: 'declared',
    heavy: true,
    leaves: ['.ci/scripts/quality/check_account_portal.py'],
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
    leaves: ['.ci/rediacc_ci/private/run_account.py'],
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
  // Runs the WHOLE private/account/web tree, not just the contract-coverage file it used to name. That one file was 1 of 34; the other 33 (config key slots, the config session provider, useJobStream, executor-session, all of src/lib) could go red while CI stayed green. Renamed rather than quietly widened, because the step name is the only thing a reader of a red log sees and
  // "Console contract coverage" would then be lying about 33 files.
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
    // The BARE gitlink, not `private/renet/**`. `git ls-files private/` returns four bare gitlinks with no files underneath, so a /** form translates to a regex matching nothing, and a glob that matches nothing can only exclude. A submodule content change reaches this repository's diff only as a pointer bump on that path.
    paths: ['private/renet', '.ci/rediacc_ci/private/run_renet.py', '.ci/rediacc_ci/core/common.py'],
    pathsOrigin: 'declared',
    // 40.4s measured 2026-08-27, and only now: it used to die at exit 127 in format.sh (goimports installed to $(go env GOPATH)/bin, which was on no PATH) about a second in, so its old "fast" tier was the cost of crashing early rather than of running. With that fixed it does the real work -- gofmt, goimports, golangci-lint and govulncheck over the whole module.
    slow: true,
    mutex: ['renet-bin'],
    leaves: ['.ci/rediacc_ci/private/run_renet.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Run renet quality',
    },
  },
  {
    id: 'check:ci-go-deps',
    env: {
      EXTERNAL_QUALITY_MODE: '${{ inputs.external_quality }}',
    },
    run: 'npm run check:ci-go-deps',
    gate: true,
    leaves: ['.ci/scripts/quality/check_go_deps.py'],
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
    // 1.4s measured. It shells out to `go build`, so a COLD Go build cache costs more than this -- but that is a once-per-tree cost, not the steady-state one the lane is sized against.
    gate: true,
    mutex: ['renet-bin'],
    leaves: ['.ci/scripts/quality/check_renet_types.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check renet types freshness',
    },
  },
  // No `renet-bin` mutex, deliberately: that group guards the shared WRITE of private/renet/bin/renet (the renet-types gate, and the renet quality battery that rebuilds it). This gate only runs `go test`, which writes nothing into bin/ and whose build cache is concurrency-safe, so serialising it behind the two binary writers would buy nothing.
  //
  // `local-only` is measured, not assumed. The tier-map tests DO run in CI, but through ct-tests.yml job test-renet step "Run renet tests", which resolves to the leaf .ci/rediacc_ci/private/run_renet.py (renet's whole `go test ./...` suite) and never to this script. Declaring that as a `step` pointer fails R3 with "the pointer names a step that runs something else", which is the
  // oracle working correctly: a manifest pointer asserts CI runs THIS leaf.
  {
    id: 'check:ci-renet-tiers',
    run: 'npm run check:ci-renet-tiers',
    gate: true,
    leaves: ['.ci/scripts/quality/check_renet_tier_map.py'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: no CI step invokes this script; the seven tier-map tests it drives already run in CI inside rediacc_ci.private.run_renet test (ct-tests.yml job test-renet, step "Run renet tests"), which resolves to that leaf and not this one, so a step pointer would claim CI runs a script it never invokes',
    },
  },
  // >>> gen-manifest: region 27
  {
    id: 'check:ci-embed-credits',
    run: 'npm run check:ci-embed-credits',
    gate: true,
    leaves: ['scripts/gates/check-embed-credits.ts'],
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
    leaves: ['scripts/gates/check-embed-arch-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check embed arch parity',
    },
  },
  // <<< gen-manifest: region 27
  {
    id: 'check:ci-embed-asset-freshness',
    env: {
      EXTERNAL_QUALITY_MODE: '${{ inputs.external_quality }}',
      GITHUB_TOKEN: '${{ github.token }}',
    },
    run: 'npm run check:ci-embed-asset-freshness',
    gate: true,
    leaves: [
      'scripts/gates/check-embed-asset-freshness.ts',
      'scripts/__tests__/github-token.control.ts',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check embed-asset upstream freshness',
    },
  },
  // >>> gen-manifest: region 28
  {
    id: 'check:ci-unverified-downloads',
    run: 'npm run check:ci-unverified-downloads',
    gate: true,
    leaves: ['scripts/gates/check-unverified-downloads.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Check every Dockerfile download is cryptographically verified',
    },
  },
  {
    id: 'check:ci-devcontainer-pins',
    env: {
      EXTERNAL_QUALITY_MODE: '${{ inputs.external_quality }}',
      GITHUB_TOKEN: '${{ github.token }}',
    },
    run: 'npm run check:ci-devcontainer-pins',
    gate: true,
    leaves: ['scripts/gates/check-devcontainer-pin-freshness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check devcontainer pin upstream freshness',
    },
  },
  // <<< gen-manifest: region 28
  {
    id: 'check:ci-embed-asset-versions',
    run: 'npm run check:ci-embed-asset-versions',
    gate: true,
    // 46s by the FLOOR of its last five measurements (46.4, 47.1, 47.9, 48.9, 51.7) -- not load noise, which is what the floor rule filters out. It unpacks and hashes embedded assets, so the cost is real work.
    slow: true,
    leaves: ['scripts/gates/check-embed-asset-versions.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check embedded asset versions match their pins',
    },
  },
  // >>> gen-manifest: region 29
  {
    id: 'check:ci-recovery-context',
    run: 'npm run check:ci-recovery-context',
    gate: true,
    leaves: ['scripts/gates/check-recovery-context.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check recovery functions get an uncancellable context',
    },
  },
  // <<< gen-manifest: region 29
  {
    id: 'check:ci-no-otlp-creds',
    run: 'npm run check:ci-no-otlp-creds',
    slow: true, // 21.2s measured
    gate: true,
    leaves: ['.ci/scripts/quality/check_no_otlp_creds.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-build-renet.yml',
      job: 'build-renet',
      step: 'Assert no OTLP credentials baked into the built binaries',
    },
  },
  // >>> gen-manifest: region 30
  {
    id: 'check:ci-subscription-schema',
    run: 'npm run check:ci-subscription-schema',
    gate: true,
    leaves: ['.ci/scripts/quality/check_subscription_schema.py'],
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
    leaves: ['scripts/gates/check-pricing-consistency.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Pricing consistency',
    },
  },
  // <<< gen-manifest: region 30
  {
    id: 'check:ci-seo',
    run: 'npm run check:ci-seo',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    // gate:false since 2026-09-06. Its two constituents (check:ci-seo-core and check:ci-client-bundle-budget) are scheduled individually below; scheduling this as well ran check-client-bundle-budget TWICE per full local run. The body and `leaves` stay byte-identical so the 'SEO' step still resolves to both children's leaves (R3, check-ci-parity.ts) and CI keeps one step.
    gate: false,
    needs: ['build:www'],
    leaves: ['scripts/gates/check-seo.ts', 'scripts/gates/check-client-bundle-budget.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'SEO',
    },
  },
  {
    id: 'check:ci-seo-core',
    run: 'npm run check:ci-seo-core',
    slow: true, // needs build:www; the closure rule (check-gate-manifest.ts) forces it
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/gates/check-seo.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'SEO',
    },
  },
  // The only gate that reads BUILT HTML against the source it was rendered from, so it is the only one that can see a page rendering another locale's document. `needs` build:www is not an optimisation: without dist it REFUSES rather than self-skipping, which is the difference between this and check:ci-seo's built-HTML scan sitting vacuous on a laptop for its whole life.
  {
    id: 'check:ci-docs-render-parity',
    run: 'npm run check:ci-docs-render-parity',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/gates/check-docs-render-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Docs render parity',
    },
  },
  // Its cheap source-level complement: no build, so it lives in the i18n lane. It is a proxy (an inline English string is invisible to it) and cannot replace the gate above. >>> gen-manifest: region 31
  {
    id: 'check:ci-page-locale-imports',
    run: 'npm run check:ci-page-locale-imports',
    gate: true,
    leaves: ['scripts/gates/check-page-locale-imports.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Page locale imports',
    },
  },
  // <<< gen-manifest: region 31
  {
    id: 'check:ci-external-links',
    env: {
      EXTERNAL_QUALITY_MODE: '${{ inputs.external_quality }}',
      GITHUB_TOKEN: '${{ github.token }}',
    },
    run: 'npm run check:ci-external-links',
    slow: true, // 17.2s measured
    gate: true,
    leaves: ['scripts/gates/check-external-links.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'External links',
    },
  },
  {
    id: 'check:ci-dkim-notify',
    env: {
      EXTERNAL_QUALITY_MODE: '${{ inputs.external_quality }}',
    },
    run: 'npm run check:ci-dkim-notify',
    gate: true,
    leaves: ['scripts/gates/check-dkim-notify.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'DKIM notify DNS',
    },
  },
  // >>> gen-manifest: region 32
  {
    id: 'check:ci-css-dom-refs',
    run: 'npm run check:ci-css-dom-refs',
    gate: true,
    leaves: ['scripts/gates/check-css-dom-refs.ts'],
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
    leaves: ['scripts/gates/check-svg-theme-reach.ts'],
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
    leaves: ['scripts/gates/check-dead-css.ts'],
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
    leaves: ['scripts/gates/check-viewport-unit-mixing.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Dead CSS',
    },
  },
  // <<< gen-manifest: region 32
  {
    id: 'check:ci-illustration-contract',
    run: 'npm run check:ci-illustration-contract',
    gate: true,
    leaves: ['scripts/gates/check-illustration-contract.ts'],
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
    // gate:false since 2026-09-06. Its two constituents (check:ci-redirect-integrity and check:ci-anchor-integrity) are scheduled individually below; scheduling this as well ran check-anchor-integrity TWICE per full local run. Body and `leaves` unchanged so the 'Redirects' step still resolves to both children's leaves and CI keeps one step.
    gate: false,
    needs: ['build:www'],
    leaves: [
      'scripts/gates/check-redirect-integrity.ts',
      'scripts/gates/check-anchor-integrity.ts',
    ],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Redirects',
    },
  },
  {
    id: 'check:ci-redirect-integrity',
    run: 'npm run check:ci-redirect-integrity',
    slow: true, // needs build:www; the closure rule forces it
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/gates/check-redirect-integrity.ts'],
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
    leaves: ['.ci/rediacc_ci/quality/browser_smoke.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Browser smoke',
    },
  },
  // >>> gen-manifest: region 33
  {
    id: 'check:ci-captcha-recovery',
    run: 'npm run check:ci-captcha-recovery',
    gate: true,
    leaves: ['scripts/gates/check-captcha-recovery.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Captcha recovery',
    },
  },
  // <<< gen-manifest: region 33
  {
    id: 'check:ci-page-density',
    run: 'npm run check:ci-page-density',
    slow: true, // drives 3 routes x 4 viewports in a container
    gate: true,
    leaves: ['.ci/rediacc_ci/quality/page_density.py'],
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
    // Reads packages/www/dist, so this is NOT an optimisation: without dist the gate REFUSES ("zero built pages found") rather than self-skipping, and the runner recorded that refusal as a FAILURE on every local lane. Seven sibling gates that read dist already declare this; these two never did.
    needs: ['build:www'],
    leaves: ['scripts/gates/check-landmarks.ts'],
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
    // Same as check:ci-landmarks above: without dist it refuses with "zero probes were comparable", which is correct anti-vacuity behaviour and was being classified as a failure.
    needs: ['build:www'],
    leaves: ['scripts/gates/check-ssr-locale.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'SSR locale',
    },
  },
  // >>> gen-manifest: region 34
  {
    id: 'check:ci-docker-image-freshness',
    env: {
      DOCKERHUB_TOKEN: '${{ env.BWS_DOCKERHUB_TOKEN }}',
    },
    run: 'npm run check:ci-docker-image-freshness',
    gate: true,
    leaves: ['scripts/gates/check-docker-image-freshness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Docker image freshness',
    },
  },
  // <<< gen-manifest: region 34
  {
    id: 'check:ci-baseline-key-semantics',
    run: 'npm run check:ci-baseline-key-semantics',
    gate: true,
    // `leaves` is what package.json's run command actually resolves to (the real source file check:ci-parity cross-checks); the 13 baseline JSON files this script reads at runtime belong in `paths` (change-detection selection), not here -- conflating the two is what check:ci-parity caught on this entry's first real run.
    paths: [
      'scripts/gates/check-baseline-key-semantics.ts',
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
    pathsOrigin: 'declared',
    leaves: ['scripts/gates/check-baseline-key-semantics.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Baseline key semantics',
    },
  },
  {
    // check:test:tutorial-player sat in package.json for three months with no manifest.ts entry and no workflow step -- found by hand this session, not by any gate. This is the gate: every check:test* key must resolve to a real manifest.ts entry wired to ci-quality.yml.
    id: 'check:ci-test-gate-wiring',
    run: 'npm run check:ci-test-gate-wiring',
    gate: true,
    paths: [
      'package.json',
      'scripts/ci-runner/manifest.ts',
      'scripts/gates/check-test-gate-wiring.ts',
    ],
    pathsOrigin: 'declared',
    leaves: ['scripts/gates/check-test-gate-wiring.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Test-gate wiring',
    },
  },
  // >>> gen-manifest: region 35
  {
    id: 'check:ci-search-index',
    run: 'npm run check:ci-search-index',
    gate: true,
    leaves: ['scripts/gates/check-search-index-freshness.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'Search index',
    },
  },
  // <<< gen-manifest: region 35
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
    leaves: ['.ci/scripts/quality/check_content_quality.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Check content for AI slop patterns',
    },
  },
  {
    // R1-R18, "the work, not the person". Shrink-only against .ci/config/prose-style-baseline.json: a green means NO NEW finding, never a clean tree, and the baselined count is printed on the success line so nobody reads it as more than that.
    //
    // NO `paths:`, DELIBERATELY. An entry without one is ALWAYS selected, which is what this gate needs: its corpus is every markdown file and every comment in the tree, so a half-populated path table would make `--changed` drop it silently on exactly the commits that introduced new prose.
    id: 'check:ci-prose-style',
    run: 'npm run check:ci-prose-style',
    slow: true, // 2503 files, 265k prose lines; 19.4s measured 2026-09-16
    gate: true,
    leaves: ['.ci/scripts/quality/check_prose_style.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Check prose style (the work, not the person)',
    },
  },
  // >>> gen-manifest: region 36
  {
    id: 'check:ci-nis2-quotes',
    run: 'npm run check:ci-nis2-quotes',
    gate: true,
    leaves: ['scripts/gates/check-directive-quotes.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Verify NIS2 directive quotations match the official source',
    },
  },
  // <<< gen-manifest: region 36
  {
    id: 'check:cli-examples',
    run: 'npm run check:cli-examples',
    slow: true, // 22.7s measured
    gate: true,
    leaves: ['scripts/gen/validate-cli-examples.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'CLI examples',
    },
  },
  // >>> gen-manifest: region 37
  {
    id: 'check:ci-tutorial-commands',
    run: 'npm run check:ci-tutorial-commands',
    gate: true,
    leaves: ['scripts/gates/check-tutorial-commands.ts'],
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
    leaves: ['scripts/gates/check-tutorial-noninteractive.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate tutorial commands are non-interactive',
    },
  },
  // <<< gen-manifest: region 37
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
      test: '.ci/rediacc_ci/tests/gates/test_gate_tutorial_render_queue.py',
      blocker:
        'BLOCKER: the predicate needs the render ledger and media manifest that only the tutorial pipeline writes, and test_gate_tutorial_render_queue.py:94 runs `node "$PREDICATE" --selftest` against the real tree under check:ci-pytest, so the real scan does execute in CI (ci-quality.yml quality-security, "Python package tests")',
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
    // The sibling gate to locale-tutorial-assets: that one proves the five files EXIST, this one proves the text inside them is drawable. Both were green while eighteen Arabic tutorials shipped with detached letters.
    id: 'check:ci-tutorial-card-fonts',
    run: 'npm run check:ci-tutorial-card-fonts',
    gate: true,
    // Leaves are the scripts the npm key RUNS, not everything it imports. card-fonts.ts is a module this gate reads; listing it here made check:ci-parity red on a leaves-vs-package.json mismatch.
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
  // >>> gen-manifest: region 38
  {
    id: 'check:ci-account-onboarding',
    run: 'npm run check:ci-account-onboarding',
    gate: true,
    leaves: ['scripts/gates/check-account-onboarding.ts'],
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
    leaves: ['scripts/gates/check-overrides-reasons.ts'],
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
    leaves: ['scripts/gates/check-syncpack-reasons.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'BLOCKER validator — syncpack versionGroups',
    },
  },
  // <<< gen-manifest: region 38
  {
    id: 'check:ci-suppression-liveness',
    run: 'npm run check:ci-suppression-liveness',
    gate: true,
    leaves: ['scripts/gates/check-suppression-liveness.ts'],
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
    leaves: ['scripts/gates/check-dead-bash.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Dead bash',
    },
  },
  {
    id: 'check:actions',
    env: {
      EXTERNAL_QUALITY_MODE: '${{ inputs.external_quality }}',
      GITHUB_TOKEN: '${{ github.token }}',
    },
    run: 'npm run check:actions',
    gate: true,
    leaves: ['scripts/gates/check-actions.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Action freshness',
    },
  },
  // >>> gen-manifest: region 39
  {
    id: 'check:ci-jq-boolean-default',
    run: 'npm run check:ci-jq-boolean-default',
    gate: true,
    leaves: ['scripts/gates/check-jq-boolean-default.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'jq boolean defaults',
    },
  },
  // <<< gen-manifest: region 39
  {
    id: 'check:ci-dead-case-arms',
    run: 'npm run check:ci-dead-case-arms',
    gate: true,
    leaves: ['.ci/scripts/quality/check_dead_case_arms.py'],
    ci: {
      kind: 'test',
      test: '.ci/rediacc_ci/tests/gates/test_gate_dead_case_arms.py',
      blocker:
        'BLOCKER: the gate is CONTROL-FIRST -- it plants a dead case arm with a runtime-generated key and refuses to report on the real tree unless its scanner catches that arm, so a green IS the fire proof; test_gate_dead_case_arms.py:test_real_tree_is_clean_and_the_control_fired runs it seam-free against the real tree under check:ci-pytest (ci-quality.yml quality-security)',
    },
  },
  {
    id: 'check:ci-label-refs',
    run: 'npm run check:ci-label-refs',
    gate: true,
    leaves: ['.ci/scripts/quality/check_label_references.py'],
    ci: {
      kind: 'test',
      test: '.ci/rediacc_ci/tests/gates/test_gate_label_references.py',
      blocker:
        'BLOCKER: test_gate_label_references.py:test_real_tree_is_clean_and_excludes_this_file runs the gate seam-free against the real tree under check:ci-pytest (ci-quality.yml quality-security, "Python package tests"), so the real sweep over .github/.ci executes every CI run; the fixture cases around it prove both fire directions',
    },
  },
  {
    id: 'check:ci-label-inventory',
    run: 'npm run check:ci-label-inventory',
    gate: true,
    leaves: ['.ci/scripts/quality/check_label_inventory.py'],
    ci: {
      kind: 'test',
      test: '.ci/rediacc_ci/tests/gates/test_gate_label_inventory.py',
      blocker:
        'BLOCKER: test_gate_label_inventory.py:test_real_tree_reconciles_against_an_injected_live_list runs the gate seam-free over the REAL .github/labels.yml under check:ci-pytest (ci-quality.yml quality-security) with the live list injected, so the real parse, the declared floor and the create-on-demand check execute every CI run; the live GitHub read runs on npm',
    },
  },
  {
    id: 'check:ci-profiler-coverage',
    run: 'npm run check:ci-profiler-coverage',
    gate: true,
    leaves: ['.ci/scripts/quality/check_profiler_coverage.py'],
    ci: {
      kind: 'test',
      test: '.ci/rediacc_ci/tests/gates/test_gate_profiler_coverage.py',
      blocker:
        'BLOCKER: test_gate_profiler_coverage.py:test_real_tree_seam_free runs the gate seam-free against the real tree under check:ci-pytest (ci-quality.yml quality-security) -- real workflows, real allowlist, real action.yml, real floors -- so the full job parse and both relations execute every CI run; the 22 fixture cases around it prove every fire direction',
    },
  },
  {
    id: 'check:ci-autopilot-workflow',
    run: 'npm run check:ci-autopilot-workflow',
    gate: true,
    leaves: ['.ci/scripts/security/check-autopilot-workflow-invariants.sh'],
    ci: {
      kind: 'test',
      test: '.ci/rediacc_ci/tests/gates/test_gate_autopilot_workflow_invariants.py',
      blocker:
        'BLOCKER: no quality lane can run this against the live ruleset, but test_gate_autopilot_workflow_invariants.py:30,175 points both GATE and REAL at the real .github/workflows/autopilot.yml, so check:ci-pytest (ci-quality.yml quality-security, "Python package tests") executes the real scan over the real tree every CI run',
    },
  },
  // >>> gen-manifest: region 40
  {
    id: 'check:ci-go-module-sync',
    run: 'npm run check:ci-go-module-sync',
    gate: true,
    leaves: ['.ci/scripts/quality/check_go_module_sync.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-go',
      step: 'Check Go module sync against the renet worktree',
    },
  },
  // <<< gen-manifest: region 40
  {
    // Structural, not semantic. "every declared env var must be referenced" was measured first and rejected: 290 of 849 step env vars have no textual reference, because gh and aws read theirs implicitly. This checks the one shape that is unambiguously a defect -- a step key after a step-boundary comment, left behind when the step itself was deleted.
    id: 'check:ci-workflow-orphan-step-keys',
    run: 'npm run check:ci-workflow-orphan-step-keys',
    gate: true,
    leaves: ['scripts/gates/check-workflow-orphan-step-keys.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Workflow orphan step keys',
    },
  },
  {
    id: 'check:ci-workflow-invariants',
    run: 'npm run check:ci-workflow-invariants',
    gate: true,
    leaves: ['.ci/scripts/security/check-ci-workflow-invariants.sh'],
    ci: {
      kind: 'test',
      test: '.ci/rediacc_ci/tests/gates/test_gate_ci_workflow_invariants.py',
      blocker:
        'BLOCKER: no quality lane runs this against the live workflow, but test_gate_ci_workflow_invariants.py:35-36 points both GATE and REAL at the real .github/workflows/ci.yml, so check:ci-pytest (ci-quality.yml quality-security, "Python package tests") executes the real scan over the real tree every CI run',
    },
  },
  {
    id: 'check:ci-autopilot-bp-align',
    run: 'npm run check:ci-autopilot-bp-align',
    gate: true,
    leaves: ['.ci/scripts/quality/check_autopilot_breakpoint_alignment.py'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh',
      blocker:
        'BLOCKER: test-autopilot-breakpoint-alignment.sh:59 runs the gate seam-free against the real .ci/breakpoint/workflow/breakpoint.yml and .github/workflows/autopilot.yml inside the gate-test battery (ci-quality.yml quality-security, "Quality-gate unit tests"), so the real comparison executes every CI run; the mutated-copy cases around it prove both fire directions',
    },
  },

  // --------------------------------------------------------------------------- WAVE 0 OF THE www-simplification PROGRAM: eight gates for defect classes that nothing in this repo could see. Seven of the eight are RED on the tree they landed on, DELIBERATELY -- they encode bugs a later wave fixes, and a gate introduced green over a live defect is a gate that ratifies it.
  //
  // FIVE OF THEM RIDE AN EXISTING WORKFLOW STEP rather than adding one, by being chained into that step's npm key. The precedent is check:ci-locale-de-contamination (see its comment above), and the pairings are by SUBJECT, not by convenience:
  //   em-dash-surfaces        -> "i18n"; 2,401 of its 2,451 findings are locale VALUES, and
  // check-content-quality.sh keeps the markdown half of the same ban. It was first pointed at the AI-slop step, which is the better SUBJECT match, and check-ci-parity refused it: that step invokes the script by path, not through npm, so the chain would never have reached CI. The pairing has to follow what the step RUNS, not what it is called.
  //   locale-config-divergence-> "i18n cross-locale"; catalog-versus-catalog integrity,
  // beside de-contamination. Its true subject twin, check_i18n_value_types.py, compares the TYPE of every non-string leaf where this compares the VALUE -- but that step is a bare script path too, so it cannot host a chain.
  //   dead-translation-keys   -> "i18n"; check-translation-key-usage.ts in the same chain
  // walks source->catalog, and this walks catalog->source.
  //   anchor-integrity        -> "Redirects"; both assert that a link in the BUILT output
  // resolves to something.
  //   client-bundle-budget    -> "SEO"; page weight is read from the same built HTML, and
  // the step already sits behind build:www. The remaining three have no honest step to ride and are covered by a gate test that drives their REAL scan against the REAL tree inside the gate-test battery. WAVE 1's gate, registered here because w2-i18n correctly did not touch the root
  // package.json or this file. Without it a STALE CLIENT CATALOG SHIPS SILENTLY: wave 1
  // replaced the thirteen static locale imports with generated per-locale bundles under
  // packages/www/src/i18n/{client,client-route}/, and those bundles are committed
  // artifacts of packages/www/src/i18n/translations/. Nothing else compares the two, and the TypeScript build that used to be the backstop for "a locale file went missing" is exactly what wave 1 removed (01-verified-context.md flagged this as the hazard of the wave). The npm key runs --selftest FIRST, so its five cases -- clean tree, stale, deleted, stray non-site-locale, wiped
  // bundle -- gate the real comparison on every invocation rather than sitting behind a flag nobody passes.
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
  // >>> gen-manifest: region 41
  {
    id: 'check:ci-em-dash-surfaces',
    run: 'npm run check:ci-em-dash-surfaces',
    gate: true,
    leaves: ['scripts/gates/check-em-dash-surfaces.ts'],
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
    leaves: ['scripts/gates/check-locale-config-divergence.ts'],
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
    leaves: ['scripts/gates/check-dead-translation-keys.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-i18n',
      step: 'i18n',
    },
  },
  // <<< gen-manifest: region 41 Both of these read packages/www/dist, so `needs: ['build:www']` is not an optimisation: without it they would be scheduled before the build and REFUSE, which is correct but useless. Same reasoning as check:ci-docs-render-parity above.
  {
    id: 'check:ci-anchor-integrity',
    run: 'npm run check:ci-anchor-integrity',
    slow: true, // needs build:www (131.9s); the runner demoted it anyway
    gate: true,
    needs: ['build:www'],
    leaves: ['scripts/gates/check-anchor-integrity.ts'],
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
    leaves: ['scripts/gates/check-player-css-scope.ts'],
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
    leaves: ['scripts/gates/check-client-bundle-budget.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'SEO',
    },
  },
  {
    id: 'check:ci-language-policy',
    run: 'npm run check:ci-language-policy',
    gate: true,
    // The verdict depends on tracked files under .ci and .claude and on nothing
    // else, so these two globs are the COMPLETE dependency set rather than a
    // narrowing for speed. The allowlist, the baseline and the blocker-validator this gate shells out to all live under .ci/ and are covered by the first.
    paths: ['.ci/**', '.claude/**'],
    pathsOrigin: 'declared',
    leaves: ['.ci/scripts/quality/check_language_policy.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Language policy',
    },
  },
  {
    id: 'check:ci-layout-overflow',
    run: 'npm run check:ci-layout-overflow',
    gate: true,
    leaves: ['scripts/gates/check-layout-overflow.ts'],
    ci: {
      kind: 'test',
      test: '.ci/rediacc_ci/tests/gates/test_gate_layout_overflow.py',
      blocker:
        'BLOCKER: no quality lane owns CSS overflow, and the two shapes it detects are invisible to a browser scan because ' +
        'querySelectorAll returns no pseudo-elements; test_gate_layout_overflow.py:98 runs the gate seam-free against the real ' +
        'stylesheets under check:ci-pytest, so every declaration block is parsed each CI run, and the mutant beside it reds the ' +
        'controls',
    },
  },
  {
    id: 'check:ci-hydration-clean',
    run: 'npm run check:ci-hydration-clean',
    gate: true,
    leaves: ['scripts/gates/check-hydration-clean.ts'],
    ci: {
      kind: 'test',
      test: '.ci/rediacc_ci/tests/gates/test_gate_hydration_clean.py',
      blocker:
        'BLOCKER: no quality lane reads React state initializers, and the defect is decidable only from the source pair (server ' +
        'render, client render); test_gate_hydration_clean.py:92 runs the gate seam-free against the real packages/www components ' +
        'under check:ci-pytest, so the real scan runs every CI run, and the mutant beside it requires the indirect control to go ' +
        'red',
    },
  },
  {
    id: 'check:ci-form-validation',
    run: 'npm run check:ci-form-validation',
    gate: true,
    leaves: ['scripts/gates/check-form-validation.ts'],
    ci: {
      kind: 'test',
      test: '.ci/rediacc_ci/tests/gates/test_gate_form_validation.py',
      blocker:
        'BLOCKER: no quality lane inspects form submit handlers, and the defect is a MISSING guard rather than a present one, so ' +
        'nothing else can express it; test_gate_form_validation.py:100 runs the gate seam-free against the real components under ' +
        'check:ci-pytest, so the real scan of all six forms runs every CI run, and the mutant case beside it requires the control ' +
        'to go red',
    },
  },

  // The parity gate itself. It replaces the two it deleted, and it inherits their workflow step (ci-quality.yml quality-content) rather than adding a new one, so the surface keeps exactly one parity step.
  {
    // B4. `--changed` scopes by `paths` and only 46 of 465 gates declare any, so the other 419 are selected by nothing. Worse than fail-open: on an EMPTY file list the rule INVERTS -- no file matches any glob, so the 46 scoped gates drop and the run reports green having skipped them. Both unusable change sets (unresolvable differ, zero files) now REFUSE instead of scoping. No
    // `paths` key here on purpose: always selected.
    id: 'check:ci-changed-selection',
    run: 'npm run check:ci-changed-selection',
    gate: true,
    leaves: ['scripts/gates/check-changed-selection.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Changed-file selection contract',
    },
  },
  {
    // C2 (W2.5 tier 1). `pathsOrigin` is required whenever `paths` is present, both directions, and a `'declared'` origin's globs must each match at least one tracked file -- the 46 hand-typed arrays this box's own paths key powers had nothing asserting they still match anything on disk.
    id: 'check:ci-paths-origin',
    run: 'npm run check:ci-paths-origin',
    gate: true,
    leaves: ['scripts/gates/check-paths-origin.ts'],
    paths: [
      'scripts/ci-runner/manifest.ts',
      'scripts/ci-runner/gate-spec.ts',
      'scripts/gates/check-paths-origin.ts',
      'scripts/ci-runner/gates.lock.json',
    ],
    pathsOrigin: 'declared',
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Paths-origin provenance',
    },
  },
  {
    // E1. The shadow ledger proves the bash and Python `setup` agreed over five frozen trees and says nothing about tomorrow's, so the phase ORDER is re-derived from both implementations on every run. Order and not just the set: swapping two phases leaves the finding count and the name set identical, so an unordered comparison passes it.
    id: 'check:ci-setup-port-parity',
    run: 'npm run check:ci-setup-port-parity',
    gate: true,
    leaves: ['.ci/rediacc_ci/setup/port_parity.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Setup port parity',
    },
  },
  // >>> gen-manifest: region 42
  {
    id: 'check:ci-parity',
    run: 'npm run check:ci-parity',
    gate: true,
    leaves: ['scripts/gates/check-ci-parity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-content',
      step: 'Validate parity between the local gate set and the CI quality surface',
    },
  },
  // <<< gen-manifest: region 42

  // F3: two Quality/Static steps that ran in CI and nowhere else. The forward gate could not see them because its BARE_GATE pattern only covered
  // .ci/scripts/{quality,security}/check-*.sh; these live in .ci/scripts/test/
  // and start with test-. They are invoked by path, not by an npm key, because the Static lane is a bare checkout with no node_modules -- the same reason ci-quality.yml:166-171 already gives for its sibling test-install-sh-config.sh.
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

  // Prerequisite nodes. They validate nothing, so gate:false; they run only when something that needs them is selected.
  //
  // build:www is what closes F5. check:ci-seo's built-HTML link scan self-skips without packages/www/dist (ci-quality.yml:738-740) and the old `&&` chain never built www, so that scan has been vacuous locally for its whole life.
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
    env: {
      GITHUB_TOKEN: '${{ github.token }}',
    },
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

  // The CI-side aggregate. gate:false because its 62 constituents are scheduled individually below: scheduling this as one unit too would run the whole 443s battery twice, and 443s is 43% of the measured serial total (plan section 2). The npm key stays because CI wants one step for it.
  {
    // B3. A matrix job's result is ONE roll-up, so shards are invisible without an intra-workflow aggregator. Clause 1 is the SET of `<lane>#<i>/<of>` receipts, not a count, and each receipt carries its own `of` and gate count -- so a leg that ran against a different plan is caught even when the totals agree. Its shard counts come
    // from `SHARD_COUNTS` in lanes.ts, the same constant the matrix emitter will read, so
    // no second copy of the number exists to drift.
    id: 'check:ci-quality-complete',
    run: 'npm run check:ci-quality-complete',
    gate: true,
    leaves: ['scripts/gates/check-quality-complete.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-wiring',
      step: 'Quality shard aggregation',
    },
  },
  {
    // NO `env:`. The PR_HEAD_REF this carried was empty on push, schedule and the nightly dispatch, and nothing under `.ci/rediacc_ci/` reads it from the ambient environment -- the battery's tests scrub it or pin their own.
    id: 'check:ci-quality-gates',
    run: 'npm run check:ci-quality-gates',
    gate: false,
    leaves: ['.ci/rediacc_ci/battery.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },

  // --------------------------------------------------------------------------- The battery, flattened. The battery runner runs these 57 serially behind one opaque npm key; scheduling them individually is what lifts the parallel ceiling
  // from 2.4x to roughly 7x and what makes the summary name the failing test.
  //
  // Assertion 7 pins this set against the on-disk glob the battery uses, so a newly added test cannot be silently omitted here -- without that rule this flattening would recreate #549 fifty-seven times over.
  //
  // ISOLATION IS A HYPOTHESIS, NOT A GIVEN. test-claude-hooks.sh failed once Since 2026-08-08 the battery enforces this in-step: the two writers run as an exclusive serial chain and the real-tree scanners are held until it finishes. See its header. inside the SERIAL battery and could not be reproduced standalone (plan finding F8). Any red that appears only under parallelism gets a
  // named mutex group, never a retry.
  //
  // THE THREE WRITERS NAMED BELOW ARE A RECORD OF 2026-07-31, and one of them,
  // test-gate-paths-exist.sh, was retired in W7 P5 census batch B4; its detector,
  // its fixtures and its controls are carried by
  // .ci/rediacc_ci/tests/gates/test_gate_paths_exist.py, which writes into
  // .ci/scripts for the same reason.
  //
  // A HAZARD OF THIS CLASS, ONE INSTANCE FIXED AND TWO OPEN. Three gates write a file into the REAL working tree for the duration of their run, and a tree-scanning gate running concurrently trips over it. Observed live on 2026-07-31: FIXED .ci/scripts/test/gates/test-gate-paths-exist.sh
  //     wrote scripts/.gate-paths-exist{,-noise}-fixture.ts and broke check:lint
  //     with `ENOENT ... open '.../scripts/.gate-paths-exist-fixture.ts'`, exit 2
  //     (eslint enumerated the file, then the control deleted it). Its fixtures
  // now go to .ci/scripts, which that gate's own scan_targets() walks and no linter does. Re-run green with both controls firing and zero dotfiles observed in scripts/ for the whole 142s run. OPEN the config-migrations gate (its bash twin's line 68, now `rediacc_ci.quality.config_migrations`) -> packages/cli/.config-migrations-check.tmp.ts, which broke check:format. Cannot use the
  // same fix: biome covers packages/**/*.ts, and the script must stay under packages/cli for node to resolve @rediacc/shared. OPEN the anti-vacuity meta-gate (its bash twin's line 255, now `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py`) -> scripts/.gate-anti-vacuity-fixture.ts, same shape, no victim observed. Cannot use the same fix either: the empty-tree run
  // builds its fixture tree with `cp -r "$REPO_ROOT/scripts"`, so the
  // file has to exist under the real scripts/ at copy time to reach the harness at all. The hazard PREDATES the runner: `npm run check:lint` in one terminal while `npm run check:ci-quality-gates` runs in another hits the same ENOENT, and that is how it was first seen here, not through the pool.
  //
  // `mktemp` is NOT the fix, which is the trap: test-gate-paths-exist.sh's scan_targets() (:62-64) hardcodes `cd $REPO_ROOT` and `find scripts`, so a fixture outside the real tree stops being scanned and its control at :178-192 silently stops firing; and the config-migrations gate's generated script must sit under packages/cli for node to resolve @rediacc/shared and its relative
  // fixtures dir. Both files have to stay in the tree.
  //
  // PREFER AN IGNORE RULE OVER A MUTEX, on measured cost. The insertion points
  // exist: eslint.config.js's global `ignores` array and biome.json's
  // `files.includes`, which already takes negated patterns. Both lists are "this is not source" exclusions (dist, node_modules, generated .d.ts), and a fixture that lives for milliseconds and is never committed belongs there. Cost: zero scheduling time, and it stands on its own merits whether or not the runner exists.
  //
  // USE THE FOUR EXACT PATHS, NOT A GLOB. `scripts/.gate-*-fixture.ts` would silently exempt any future file matching it; four literals cannot, because they name exactly the files that exist. The failure mode also inverts the right way: a fifth writer added later is NOT covered, so it trips the scanner loudly the first time it races instead of being silently absorbed. That matches
  // how the rest of this repo's suppressions work, enumerated rather than pattern-matched.
  //
  // Both halves were PROVEN on a throwaway tree, each with a control that fires (2026-07-31), rather than reasoned from the tools' documented semantics.
  // Both probes ran against the WORKSPACE tools, eslint 9 and biome 2.5.6,
  // reached by linking the real node_modules into the scratch dir:
  //   eslint  no ignore entry -> exit 1 on a planted parse error;
  // exact-path `ignores` entry -> exit 0.
  //   biome   no negation -> "Checked 2 files", flags the temp file, exit 1;
  // exact-path `!` negation -> "Checked 1 file", exit 0. That biome run, and only that one, is what establishes that biome DOES walk dotfiles, which is why check:format was a victim at all. An earlier attempt without the node_modules link exited 0 in silence on a deliberately misformatted file; `npx` had resolved something other than the workspace biome, so that run is evidence
  // about npx resolution and about nothing else. Do not read it as biome skipping dotfiles: a tool that never ran produces a green indistinguishable from a passing one, which is this whole file's subject.
  //
  // A mutex group binding the three writers against check:lint / check:format / lint:unused is the fallback, and it is expensive. It would serialise 511.7s of work against an observed 264.2s wall, a 1.94x regression that drops the run from about 9x to about 4.7x. It also binds the two LONGEST gates in the set to each other, because one of the writers is the critical path:
  // test-gate-paths-exist.sh measured 142.6s standalone on an idle tree and 264.1s under parallel load, against check:lint at 194.8s under the same load. (The plan's 116.7s for check:lint is stale; do not cost this from it.) No mutex is declared here, deliberately, because that trade wants an explicit decision rather than a silent default.
  {
    id: 'gate-test:autopilot-breakpoint-alignment',
    run: '.ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh',
    reads: ['tree:repo'],
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
    id: 'check:ci-release-bump-skip',
    run: 'npm run check:ci-release-bump-skip',
    gate: true,
    leaves: ['.ci/scripts/quality/check_release_bump_skip.py'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/quality/check_release_bump_skip.py',
      blocker:
        'BLOCKER: the gate IS the test -- it drives the real dispatch-release.sh decide branch with a shimmed gh through all five paths, so ci-quality.yml quality-security runs the real decision every CI run; it exists because a bump-none merge and a broken decision both produce "no release" and only the emitted signal distinguishes them, which no release gate could see',
    },
  },
  {
    id: 'check:ci-regions-sync',
    run: 'npm run check:ci-regions-sync',
    gate: true,
    leaves: ['.ci/scripts/quality/check_regions_sync.py'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-regions-sync.sh',
      blocker:
        'BLOCKER: test-regions-sync.sh drives the REAL gate over the REAL regions.json and packages/shared/src/regions/data.json ' +
        'inside the gate-test battery (ci-quality.yml quality-security, "Quality-gate unit tests"), and its controls plant a divergence, an ' +
        'empty file and invalid JSON to prove all three refusals fire; the two files are held together by hand (no build step ' +
        'syncs them, despite what index.ts used to claim) and data.json is the ONLY region list users get because ' +
        '${SITE_URL}/regions.json returns 404, so silent drift would ship to every install',
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
  // RETIRED WITH ITS SUBJECT: gate-test:claude-hooks, the heaviest entry in this file at 537.4s, was a 40-line wrapper around `.claude/hooks/test-hooks.sh` and had no other work in it. The harness is gone, ported to pytest under `.claude/rediacc_hooks/tests/`, and its label multiset was compared run-against-run before the deletion rather than diff-against-diff. The ports are
  // collected by check:ci-pytest, whose `paths` already carry `.claude/hooks/**` and `.claude/rediacc_hooks/**`, so nothing lost selection when this entry left.
  //
  // RETIRED, AND THE LAST TWO `mutex: ['tree:repo']` ENTRIES WENT WITH THEM: gate-test:gate-anti-vacuity and gate-test:generate-tag-inputs. Their pytest ports (test_gate_gate_anti_vacuity.py, test_gate_generate_tag_inputs.py) carry every case and still write the tracked tree, so the exclusive claim moved to check:ci-pytest, which is where they now run.
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
    id: 'check:ci-pytest',
    run: 'npm run check:ci-pytest',
    gate: true,
    // SLOW ON PURPOSE, and it gets slower with every port, which is the point. The tier oracle measured 367.9s (the FLOOR of the last five samples, per check-gate-manifest.ts:503, so not a contended one-off) and asked for this flag. It is not a regression to fix: the gate runs the WHOLE Python suite, 9165 tests, and W7 P3 adds roughly 200 more per batch as bash gate tests are
    // ported to it. It is already parallel at `-n 8 --dist loadgroup` (823.93s to 396s, 2.08x, measured 2026-09-07), and the operator ruled STOP AT 2.08x rather than take the two further optimisations that were measured and costed. So the honest declaration is that this is a slow gate, not that it is a fast gate having a bad day.
    slow: true,
    // THE GATE NOW RUNS pytest UNDER `-n 8`, so it claims 8 scheduler slots rather than 1. pool.ts:242 caps effective weight at the pool size, so this reads as "the whole pool" on a 2-slot CI runner and as 8 of 22 locally. Declaring less than `-n` asks for would be an undeclared claim on the machine -- the same defect class as the missing `mutex` that let the CLAUDE.md-rewriting
    // gate run alongside this one.
    weight: 8,
    leaves: ['.ci/rediacc_ci/check_pytest.py'],
    // THIS GATE DRIVES REAL BASH TWINS AGAINST THE REAL TREE and declared no isolation while doing it, so pool.ts was free to schedule the `tree:repo` writers -- one of which rewrites CLAUDE.md -- alongside it. test_twin_parity.py:203-208 names this hazard in prose and cannot fix it
    // from inside pytest, because the claim has to be made HERE.
    //
    // `mutex` AND NOT `reads` SINCE THE LAST TWO tree:repo GATE TESTS WERE RETIRED, and the upgrade is the whole reason those retirements are safe. `gate-test:gate-anti-vacuity` and `gate-test:generate-tag-inputs` each carried `mutex: ['tree:repo']` and each wrote the tracked tree; their pytest ports still do, and the ports run HERE. A shared claim releases this gate to
    // run beside every other `tree:repo` reader, which is exactly the overlap that reddened gate-test:claude-hooks in 2026-08-17 with a bash syntax error in a file that parses clean. The exclusive claim is what `check:ci-pool-writer-safety` now checks for, so a downgrade back to `reads` is a red rather than a silent flake.
    mutex: ['tree:repo'],
    // The old set was ['.ci/rediacc_ci/**', 'pyproject.toml'] and could not see two things this gate actually runs: `.claude/rediacc_hooks/**` is a testpaths root, and `.ci/scripts/test/gates/**` holds the twins test_twin_parity drives. Under `--changed` an edit to either did not select this gate, which is a path filter reporting a pass over code it never looked at.
    //
    // WIDENED AGAIN WHEN gate-test:claude-hooks WAS RETIRED, and the widening is the whole reason that retirement does not open a selection hole. The four entries below carried the SUBJECTS of the harness this gate now collects: the guards and the chain head under `.claude/hooks/**`, the wiring the settings file declares, the git fixture the trapguard cases source, and the
    // inline-python detector whose verdicts those cases assert. The harness declared every one of them; dropping its entry without moving them would have left editing a guard select no gate that runs it, which is the same pass-over-unread-code this comment already records once.
    paths: [
      '.ci/rediacc_ci/**',
      '.claude/rediacc_hooks/**',
      '.ci/scripts/test/gates/**',
      '.claude/hooks/**',
      '.claude/settings.json',
      '.ci/scripts/test/lib/git-fixture.sh',
      '.ci/scripts/quality/check_inline_python.py',
      'pyproject.toml',
    ],
    pathsOrigin: 'declared',
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      // quality-security, NOT quality-static, and this was a live defect rather than a preference. Measured 2026-09-07: 23 of the 64 ported gate tests shell out to node tooling (npx, tsx, npm run, node_modules), and quality-static is one of only three lanes that runs NO setup-workspace, so it has neither node nor the workspace deps. Driven with node hidden from PATH, exactly as
      // that runner sees it, three of those ported modules gave 24 failed / 1 passed. They do not skip; they fail.
      //
      // CI has not caught it because every port is still UNTRACKED, so the checkout CI runs has never contained one. The red would have arrived on the commit that landed them, which is the worst moment to discover a lane cannot run its own gate.
      //
      // quality-security is the coherent home rather than merely a working one: it has node, a 20 minute timeout against 18 steps, and it ALREADY hosts the "Quality-gate unit tests" battery that runs all 149 bash twins. The gate driving the ported versions of those same tests belongs beside them.
      job: 'quality-security',
      step: 'Python package tests',
    },
  },
  // >>> gen-manifest: region 43
  {
    id: 'check:ci-pathspec-scope',
    run: 'npm run check:ci-pathspec-scope',
    gate: true,
    leaves: ['.ci/scripts/quality/check_pathspec_scope.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Pathspec scope',
    },
  },
  // <<< gen-manifest: region 43
  {
    id: 'check:ci-package-key-budget',
    run: 'npm run check:ci-package-key-budget',
    gate: true,
    leaves: ['scripts/gates/check-package-key-budget.ts'],
    paths: [
      'scripts/gates/check-package-key-budget.ts',
      'package.json',
      'scripts/ci-runner/manifest.ts',
      'scripts/data/package-key-budget-baseline.json',
    ],
    pathsOrigin: 'declared',
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Package key budget',
    },
  },
  {
    id: 'gate-test:blocker-golden-corpus',
    run: '.ci/scripts/test/gates/test-blocker-golden-corpus.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-blocker-golden-corpus.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-security',
      step: 'Quality-gate unit tests',
    },
  },
  {
    id: 'gate-test:media-r2',
    run: '.ci/scripts/test/gates/test-media-r2.sh',
    gate: true,
    qualityGateTest: true,
    leaves: ['.ci/scripts/test/gates/test-media-r2.sh'],
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
    reads: ['tree:repo'],
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
    // A sweep added retry_schema_exhaustion to the judge call sites one at a time and MISSED THE FIFTH, in wl_shapedup.py -- the commit that found it says so in its own subject. Five examples checked individually is not the claim that the set is uniform, and the fifth is what an example-based sweep drops. Enumerated from source, so a sixth site is covered the day it is written.
    id: 'check:ci-schema-call-sites',
    run: 'npm run check:ci-schema-call-sites',
    gate: true,
    leaves: ['.ci/scripts/quality/check_schema_call_sites.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Schema call sites',
    },
  },
  {
    // docker-npm-pin-exclusions.json was matched with `k in line`, so the bare
    // `npm install` key claimed the `npm install --omit=dev` line and the correct entry
    // was reported as dead scaffolding. The invariant is the MATCHER, not the key shape: a first draft gated key prefixes and flagged two live, correct, harmless keys.
    id: 'check:ci-allowlist-key-matching',
    run: 'npm run check:ci-allowlist-key-matching',
    gate: true,
    leaves: ['.ci/scripts/quality/check_allowlist_key_matching.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Allowlist key matching',
    },
  },
  {
    // 25 orphaned `pr-*` environments accumulated because a job-level `environment:` creates an object CI has no permission to delete. The block was removed by hand and only a comment stood in its place.
    id: 'check:ci-environment-names',
    run: 'npm run check:ci-environment-names',
    gate: true,
    leaves: ['.ci/scripts/quality/check_environment_names.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Environment names',
    },
  },
  {
    // Re-derives every declared gate's registration and compares. It found a real mis-placement on its first run against the tree: check:ci-environment-names was hand-registered in quality-code when its needs put it in quality-static.
    id: 'check:ci-gate-bind',
    run: 'npm run check:ci-gate-bind',
    gate: true,
    leaves: ['scripts/gate-bind.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Gate binding',
    },
  },
  {
    // A gate that scans and finds nothing prints a tick indistinguishable from a clean tree. Seeded shrink-only: 47 enumerating checks carry no vacuity guard today, and a wall of 47 is a gate somebody disables.
    id: 'check:ci-enumeration-vacuity',
    run: 'npm run check:ci-enumeration-vacuity',
    gate: true,
    leaves: ['scripts/gates/check-enumeration-vacuity.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Enumeration vacuity',
    },
  },
  {
    // A build that broke with no commit behind it: private/account's image resolved its whole dep tree live, and a package published that morning crashed npm's arborist. This is the regression test for the CLASS, not for that package.
    id: 'check:ci-docker-npm-pins',
    run: 'npm run check:ci-docker-npm-pins',
    gate: true,
    // Just the script, matching every other Python gate here: check:ci-parity requires the manifest's leaves to be what `npm run <id>` actually resolves to, and a leaf list wider than the command is a claim the runner cannot honour. The gate still scans every tracked Dockerfile -- it enumerates from git, not
    // from this list -- so a new one is covered the moment it is committed.
    leaves: ['.ci/scripts/quality/check_docker_npm_pins.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Dockerfile npm pins',
    },
  },
  {
    id: 'gate-test:plan-housekeeping',
    run: '.ci/scripts/test/gates/test-plan-housekeeping.sh',
    // 7.6s alone, ~20s in the pre-push lane, and the lane is what the tier is about. It drives the REAL gate against 13 fixture git repositories, so its cost is 13 process trees rather than anything it computes -- exactly the shape that stretches under 20x contention. It was already borderline (samples 19.9-23.0s) and a 13th case tipped it.
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
  // W3 P2 heavy-job proxies. Each runs the SAME script a heavy CI job runs, on a reduced input, and returns 77 (pool.ts CANNOT_RUN -> `blocked`) when its toolchain is absent. Every one is `local-only`: their subjects run in ci.yml's
  // package-tests job, ct-tests.yml, ct-update-flow.yml and ci-ops-test.yml, none
  // of which is in paritySurface(), so a `step` pointer would fail R3 correctly.
  //
  // NO `paths` ON ANY OF THEM, and that is a decision rather than an omission. Each depends on the CLI bundle, the renet submodule, constants.sh, toolchain.env, the packaging scripts and the workflow it mirrors; enumerating that is the half-populated table this file's own header warns makes `--changed` drop gates silently. Always-selected is the safe direction.
  //
  // The `slow:` values are PROVISIONAL. They were measured on a contended tree
  // with five writer agents live, which driver-contract section 5 makes
  // inadmissible; only the three above 5 s carry it and the retier box owns the final values.
  {
    id: 'check:ci-proxy-linux-packages',
    run: 'npm run check:ci-proxy-linux-packages',
    gate: true,
    leaves: ['.ci/scripts/test/proxies/proxy-linux-packages.sh'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: CI runs the un-reduced subject at .github/workflows/ci.yml job package-tests, step "Run Linux package tests", which installs each package inside eight distro containers. That job is outside paritySurface(), so this proxy is the local half and CI is the full half; a step pointer would claim CI runs the --dry-run form, which it does not.',
    },
  },
  {
    id: 'check:ci-proxy-rdc-update',
    run: 'npm run check:ci-proxy-rdc-update',
    gate: true,
    leaves: ['.ci/scripts/test/proxies/proxy-rdc-update.sh'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: CI runs .ci/scripts/test/test-rdc-update.sh all in .github/workflows/ct-update-flow.yml:70 against a real SEA binary from build-cli-linux-x64. A developer checkout has only the node bundle, so the happy and rollback scenarios cannot run here; the proxy names both every run and runs all seven once RDC_BINARY is set.',
    },
  },
  {
    id: 'check:ci-proxy-license-e2e',
    run: 'npm run check:ci-proxy-license-e2e',
    slow: true,
    gate: true,
    heavy: true,
    leaves: ['.ci/scripts/test/proxies/proxy-license-e2e.sh'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: CI runs the identical script at .github/workflows/ct-tests.yml:1848, a workflow outside paritySurface(). The subject needs passwordless sudo to install fixtures under the hardcoded /var/lib/rediacc/license, so it is cannot-run rather than failing on a host without it.',
    },
  },
  {
    id: 'check:ci-proxy-go-unit',
    run: 'npm run check:ci-proxy-go-unit',
    slow: true,
    gate: true,
    heavy: true,
    leaves: ['.ci/scripts/test/proxies/proxy-go-unit.sh'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: CI runs the full suite under root with -race via ct-tests.yml -> rediacc_ci.private.run_renet -> private/renet/.ci/scripts/test/run-tests.sh. This proxy drops root, the race detector and the account-server phase, and excludes the 8 packages whose tests need privilege, so it covers 60 of 68 and must not claim the CI step.',
    },
  },
  {
    id: 'check:ci-proxy-ops-host-check',
    run: 'npm run check:ci-proxy-ops-host-check',
    gate: true,
    leaves: ['.ci/scripts/test/proxies/proxy-ops-host-check.sh'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: the CI step .github/workflows/ci-ops-test.yml:573-575 is "renet ops host check || true" and therefore cannot fail on any platform; the only real assertion on its output is Windows-only at :584-589. A step pointer would claim coverage that the trailing || true removes.',
    },
  },
  {
    id: 'check:ci-proxy-cli-manifest',
    run: 'npm run check:ci-proxy-cli-manifest',
    gate: true,
    leaves: ['.ci/scripts/test/proxies/proxy-cli-manifest.sh'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: .ci/scripts/build/generate-cli-manifest.sh runs only on the release path in cd-stage.yml, which is outside paritySurface(), and had no test of any kind. The proxy drives it against a synthetic dist directory in a tmpdir, so it asserts the generator rather than a release.',
    },
  },
  {
    id: 'check:ci-proxy-docker-prepull',
    run: 'npm run check:ci-proxy-docker-prepull',
    slow: true,
    gate: true,
    leaves: ['.ci/scripts/test/proxies/proxy-docker-prepull.sh'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: .ci/scripts/infra/docker-prepull.sh runs inside docker build jobs outside paritySurface() and had no test. The proxy needs a live daemon and a reachable registry, both of which are cannot-run rather than findings on a developer machine.',
    },
  },
  {
    id: 'check:ci-proxy-ensure-nfpm',
    run: 'npm run check:ci-proxy-ensure-nfpm',
    gate: true,
    leaves: ['.ci/scripts/test/proxies/proxy-ensure-nfpm.sh'],
    ci: {
      kind: 'local-only',
      blocker:
        'BLOCKER: ensure-nfpm.sh is invoked by ci.yml and cd-stage.yml as a setup step, never as a validation, and is the single site enforcing NFPM_VERSION and its sha256. The proxy runs it in a throwaway repo root so the cold-cache fetch-and-verify branch is actually reached; a step pointer would name a step that installs rather than asserts.',
    },
  },
  {
    id: 'check:test-provisioning',
    run: 'npm run check:test-provisioning',
    gate: true,
    weight: 2,
    leaves: ['.ci/scripts/test/proxies/proxy-unit-tests.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Run provisioning unit tests',
    },
  },
  {
    id: 'check:test-e2e-unit',
    run: 'npm run check:test-e2e-unit',
    gate: true,
    weight: 2,
    leaves: ['.ci/scripts/test/proxies/proxy-unit-tests.sh'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-packages',
      step: 'Run e2e-tests unit suite',
    },
  },
  {
    // six bash enumerations answered "what a machine needs" and none compared the set installed against the set used, so a pinned tool could be required by a gate and named nowhere -- which is how the drafted table came to carry no pytest row
    id: 'check:ci-install-table',
    run: 'npm run check:ci-install-table',
    gate: true,
    leaves: ['.ci/rediacc_ci/setup/tools.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'Install table',
    },
  },
  // >>> gen-manifest: region 44
  {
    id: 'check:ci-gen-manifest',
    run: 'npm run check:ci-gen-manifest',
    gate: true,
    leaves: ['scripts/gen/gen-manifest.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-code',
      step: 'Generated manifest regions',
    },
  },
  {
    id: 'check:ci-w7p5a-real-run-blockers',
    run: 'npm run check:ci-w7p5a-real-run-blockers',
    gate: true,
    leaves: ['.ci/scripts/quality/check_w7p5a_real_run_blockers.py'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-static',
      step: 'W7P5-a real-run blocklist',
    },
  },
  // <<< gen-manifest: region 44
];

/** The root workflow every CI run enters through. */
