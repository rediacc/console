/**
 * The single gate inventory both halves of the local CI runner consume.
 *
 * scripts/check-ci-parity.ts reads it as the authoritative "what the local run
 * executes" set, and scripts/ci-runner/run.ts schedules it. Before this file
 * existed both facts were encoded in one place: the 93-step `&&` string at
 * package.json `scripts.ci`. Two gates parsed that string as their input, so
 * the moment `scripts.ci` became a runner invocation they would have read an
 * empty chain and gone green over everything -- the exact failure class of
 * rediacc/console#549, at scale. See docs/agent/0731-2/PLAN-npm-ci-parallel-parity.md
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
  /** npm script key, or a synthetic node id like 'build:packages'. */
  id: string;
  /** Exact command to run, and the exact rerun line printed on failure. */
  run: string;
  /**
   * false for prerequisite nodes (build:*) that validate nothing, and for the
   * CI-side aggregate check:ci-quality-gates whose 57 constituents are
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
  /** Set on the 57 entries flattened out of .ci/scripts/test/gates/. Their set
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
  { id: 'check:version', run: 'npm run check:version', gate: true, leaves: ['scripts/check-workspace-versions.ts','syncpack'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Versions" } },
  { id: 'check:deps', run: 'npm run check:deps', gate: true, leaves: ['scripts/check-deps.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "External dependency freshness" } },
  { id: 'check:lint', run: 'npm run check:lint', gate: true, weight: 2, heavy: true, leaves: ['eslint','biome'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Lint" } },
  { id: 'lint:unused', run: 'npm run lint:unused', gate: true, heavy: true, leaves: ['knip'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Unused exports (knip)" } },
  { id: 'check:ci-knip-blockers', run: 'npm run check:ci-knip-blockers', gate: true, leaves: ['scripts/check-knip-blockers.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "knip BLOCKER reasons" } },
  { id: 'check:format', run: 'npm run check:format', gate: true, leaves: ['biome'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Format" } },
  { id: 'check:i18n', run: 'npm run check:i18n', gate: true, leaves: ['scripts/check-translation-hashes.ts','scripts/check-translation-completeness.ts','scripts/check-translation-key-usage.ts','scripts/check-cli-i18n-key-usage.ts','packages/cli/scripts/check-cli-i18n-help-render.ts','scripts/check-docs-inline-translations.ts','scripts/check-docs-untranslated-text.ts','scripts/check-account-email-templates.ts','packages/www/scripts/validate-cli-docs.js','packages/www/scripts/validate-docs-cli-usage.js','packages/www/scripts/validate-landing-cli-usage.js','packages/www/scripts/validate-translation-freshness.js','packages/www/scripts/validate-content.js','packages/www/scripts/validate-tutorial-transcripts.js','packages/www/scripts/validate-tutorial-audio.js','packages/www/scripts/validate-tutorial-cast-output.js','packages/www/scripts/validate-content-accuracy.js','packages/www/scripts/validate-comparison-refs.js','scripts/check-component-hardcoded-strings.ts','scripts/check-cli-docs.ts','scripts/check-i18n-naturalization.ts','scripts/check-locale-only-edits.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "i18n" } },
  { id: 'check:ci-i18n-cli-key-usage', run: 'npm run check:ci-i18n-cli-key-usage', gate: true, leaves: ['scripts/check-cli-i18n-key-usage.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "i18n" } },
  { id: 'check:ci-i18n-cli-help-render', run: 'npm run check:ci-i18n-cli-help-render', gate: true, leaves: ['packages/cli/scripts/check-cli-i18n-help-render.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "i18n" } },
  { id: 'check:cli-docs', run: 'npm run check:cli-docs', gate: true, leaves: ['scripts/check-cli-docs.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "i18n" } },
  { id: 'check:ci-i18n-locale-only', run: 'npm run check:ci-i18n-locale-only', gate: true, leaves: ['scripts/check-locale-only-edits.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "i18n" } },
  { id: 'check:types', run: 'npm run check:types', gate: true, mutex: ['build-artifacts'], heavy: true, leaves: ['tsc'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "TypeScript" } },
  { id: 'check:test-cli', run: 'npm run check:test-cli', gate: true, weight: 2, heavy: true, leaves: ['vitest'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-packages', step: "Run CLI unit tests" } },
  // A FOURTH www-dist consumer, which the plan's F5 list did not have.
  // workers/www/src/__tests__/redirect-aliases.test.ts:3 statically imports
  // packages/www/dist/route-manifest.json. `astro build` empties dist before
  // repopulating it, so under parallelism this read the emptied directory and
  // died with "Cannot find module ../../../../packages/www/dist/route-manifest.json".
  // It passed at --jobs 1 only because dist happened to be left populated by an
  // earlier build, so the missing edge was latent in the serial world too. The
  // `ci` pointer below already recorded the truth: CI runs it in the lane that
  // builds www first.
  { id: 'check:test-workers', run: 'npm run check:test-workers', gate: true, needs: ['build:www'], leaves: ['vitest'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-www-build', step: "Worker unit tests (workers/www)" } },
  { id: 'check:ci-install-sh-config', run: 'npm run check:ci-install-sh-config', gate: true, leaves: ['.ci/scripts/test/test-install-sh-config.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: "install.sh config tests" } },
  { id: 'check:ci-rdc-sh-env', run: 'npm run check:ci-rdc-sh-env', gate: true, leaves: ['.ci/scripts/test/test-rdc-sh-env.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: "rdc.sh env tests" } },
  { id: 'check:ci-npmrc', run: 'npm run check:ci-npmrc', gate: true, leaves: ['.ci/scripts/quality/check-npmrc.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Block legacy-peer-deps workarounds" } },
  { id: 'check:ci-lockfile', run: 'npm run check:ci-lockfile', gate: true, leaves: ['.ci/scripts/quality/check-lockfile.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Lockfile" } },
  { id: 'check:ci-peer-deps', run: 'npm run check:ci-peer-deps', gate: true, leaves: ['.ci/scripts/quality/check-peer-deps.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Verify no peer dependency conflicts" } },
  { id: 'check:ci-security-audit', run: 'npm run check:ci-security-audit', gate: true, leaves: ['.ci/scripts/security/audit.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: "Audit" } },
  { id: 'check:ci-shell-lint', run: 'npm run check:ci-shell-lint', gate: true, leaves: ['.ci/scripts/security/shellcheck.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: "Shell lint" } },
  { id: 'check:ci-shell-format', run: 'npm run check:ci-shell-format', gate: true, leaves: ['.ci/scripts/security/shfmt.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: "Shell format" } },
  { id: 'check:ci-shell-commands', run: 'npm run check:ci-shell-commands', gate: true, leaves: ['.ci/scripts/security/check-commands.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: "Shell commands exist on the runner image" } },
  { id: 'check:ci-workflows', run: 'npm run check:ci-workflows', gate: true, leaves: ['.ci/scripts/quality/check-workflows.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Workflow banned patterns" } },
  { id: 'check:ci-workflow-gates', run: 'npm run check:ci-workflow-gates', gate: true, leaves: ['.ci/scripts/security/check-workflow-gates.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Workflow structural gates" } },
  { id: 'check:ci-actionlint', run: 'npm run check:ci-actionlint', gate: true, leaves: ['.ci/scripts/security/actionlint.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Workflow lint (actionlint)" } },
  { id: 'check:ci-breakpoint-drift', run: 'npm run check:ci-breakpoint-drift', gate: true, leaves: ['.ci/breakpoint/scripts/check-breakpoint-drift.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Breakpoint drift" } },
  { id: 'check:ci-app-admin-perm', run: 'npm run check:ci-app-admin-perm', gate: true, leaves: ['.ci/scripts/quality/check-no-app-admin-perm.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "App admin permission" } },
  { id: 'check:ci-silent-failures', run: 'npm run check:ci-silent-failures', gate: true, leaves: ['.ci/scripts/quality/check-silent-failure-patterns.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: "Silent-failure patterns" } },
  { id: 'check:ci-compose-env', run: 'npm run check:ci-compose-env', gate: true, leaves: ['.ci/scripts/quality/check-compose-env.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: "Compose env" } },
  { id: 'check:ci-e2e-coverage', run: 'npm run check:ci-e2e-coverage', gate: true, leaves: ['.ci/scripts/quality/check-e2e-coverage.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Check E2E test coverage for all renet functions" } },
  { id: 'check:ci-e2e-skip-hygiene', run: 'npm run check:ci-e2e-skip-hygiene', gate: true, leaves: ['scripts/check-e2e-skip-hygiene.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Check E2E skip hygiene (no collected-then-skipped suites)" } },
  { id: 'check:ci-audit-coverage', run: 'npm run check:ci-audit-coverage', gate: true, leaves: ['.ci/scripts/quality/check-audit-coverage.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: "Check audit logging coverage for CLI operations" } },
  { id: 'check:ci-cli-contract', run: 'npm run check:ci-cli-contract', gate: true, needs: ['build:packages'], mutex: ['build-artifacts'], leaves: ['.ci/scripts/quality/check-cli-contract.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-packages', step: "CLI contract" } },
  { id: 'check:ci-command-tree', run: 'npm run check:ci-command-tree', gate: true, needs: ['build:packages'], mutex: ['build-artifacts'], leaves: ['.ci/scripts/quality/check-command-tree.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Command tree" } },
  { id: 'check:ci-command-planes', run: 'npm run check:ci-command-planes', gate: true, leaves: ['packages/cli/scripts/check-command-planes.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Command planes" } },
  { id: 'check:ci-design-tree', run: 'npm run check:ci-design-tree', gate: true, leaves: ['scripts/check-design-tree.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Design tree" } },
  { id: 'check:ci-i18n-placeholders', run: 'npm run check:ci-i18n-placeholders', gate: true, leaves: ['scripts/check-i18n-placeholders.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "i18n placeholders" } },
  { id: 'check:ci-i18n-untranslated', run: 'npm run check:ci-i18n-untranslated', gate: true, leaves: ['scripts/check-i18n-untranslated.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "i18n untranslated" } },
  { id: 'check:ci-i18n-cross-locale', run: 'npm run check:ci-i18n-cross-locale', gate: true, leaves: ['scripts/check-i18n-cross-locale.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "i18n cross-locale" } },
  { id: 'check:ci-locale-sources', run: 'npm run check:ci-locale-sources', gate: true, leaves: ['scripts/check-locale-sources.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "Locale sources" } },
  { id: 'check:ci-i18n-command-parity', run: 'npm run check:ci-i18n-command-parity', gate: true, leaves: ['scripts/check-cli-docs.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "i18n command parity" } },
  { id: 'check:ci-config-migrations', run: 'npm run check:ci-config-migrations', gate: true, leaves: ['.ci/scripts/quality/check-config-migrations.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-packages', step: "Check config-migration runner + fixtures" } },
  { id: 'check:ci-schema-coverage', run: 'npm run check:ci-schema-coverage', gate: true, leaves: ['scripts/check-schema-coverage.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Schema coverage" } },
  { id: 'check:ci-editorconfig', run: 'npm run check:ci-editorconfig', gate: true, leaves: ['.ci/scripts/quality/check-editorconfig.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: "EditorConfig" } },
  { id: 'check:ci-account-portal', run: 'npm run check:ci-account-portal', gate: true, heavy: true, leaves: ['.ci/scripts/quality/check-account-portal.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-packages', step: "Check account portal (typecheck + build)" } },
  { id: 'check:ci-account-server', run: 'npm run check:ci-account-server', gate: true, mutex: ['account-vitest'], weight: 2, heavy: true, leaves: ['.ci/scripts/private/run-account.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Run account integration tests" } },
  { id: 'check:ci-account-layer-isolation', run: 'npm run check:ci-account-layer-isolation', gate: true, heavy: true, leaves: ['eslint'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Check account route layer isolation" } },
  { id: 'check:ci-account-config-auth', run: 'npm run check:ci-account-config-auth', gate: true, leaves: ['node'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Check config token auth requires org membership" } },
  { id: 'check:ci-account-no-node-env-routes', run: 'npm run check:ci-account-no-node-env-routes', gate: true, leaves: ['grep','echo'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Assert no NODE_ENV branching in account routes" } },
  { id: 'check:ci-account-no-admin-role', run: 'npm run check:ci-account-no-admin-role', gate: true, leaves: ['grep','echo'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Check no admin user role (must be root)" } },
  { id: 'check:ci-account-scope-audit', run: 'npm run check:ci-account-scope-audit', gate: true, mutex: ['account-vitest'], weight: 2, heavy: true, leaves: ['vitest'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Check scope registry audit" } },
  { id: 'check:ci-console-coverage', run: 'npm run check:ci-console-coverage', gate: true, mutex: ['account-vitest'], weight: 2, heavy: true, leaves: ['vitest'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-packages', step: "Console contract coverage" } },
  { id: 'check:ci-renet', run: 'npm run check:ci-renet', gate: true, mutex: ['renet-bin'], leaves: ['.ci/scripts/private/run-renet.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Run renet quality" } },
  { id: 'check:ci-go-deps', run: 'npm run check:ci-go-deps', gate: true, leaves: ['.ci/scripts/quality/check-go-deps.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Check Go dependency freshness" } },
  { id: 'check:ci-renet-types', run: 'npm run check:ci-renet-types', gate: true, mutex: ['renet-bin'], leaves: ['.ci/scripts/quality/check-renet-types.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Check renet types freshness" } },
  { id: 'check:ci-embed-credits', run: 'npm run check:ci-embed-credits', gate: true, leaves: ['scripts/check-embed-credits.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Check embed credits consistency" } },
  { id: 'check:ci-embed-arch-parity', run: 'npm run check:ci-embed-arch-parity', gate: true, leaves: ['scripts/check-embed-arch-parity.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Check embed arch parity" } },
  { id: 'check:ci-embed-asset-freshness', run: 'npm run check:ci-embed-asset-freshness', gate: true, leaves: ['scripts/check-embed-asset-freshness.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Check embed-asset upstream freshness" } },
  { id: 'check:ci-no-otlp-creds', run: 'npm run check:ci-no-otlp-creds', gate: true, leaves: ['.ci/scripts/quality/check-no-otlp-creds.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-build-renet.yml', job: 'build-renet', step: "Assert no OTLP credentials baked into the built binaries" } },
  { id: 'check:ci-subscription-schema', run: 'npm run check:ci-subscription-schema', gate: true, leaves: ['.ci/scripts/quality/check-subscription-schema.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go', step: "Check subscription schema consistency" } },
  { id: 'check:ci-pricing-consistency', run: 'npm run check:ci-pricing-consistency', gate: true, leaves: ['scripts/check-pricing-consistency.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Pricing consistency" } },
  { id: 'check:ci-seo', run: 'npm run check:ci-seo', gate: true, needs: ['build:www'], leaves: ['scripts/check-seo.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-www-build', step: "SEO" } },
  { id: 'check:ci-external-links', run: 'npm run check:ci-external-links', gate: true, leaves: ['scripts/check-external-links.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "External links" } },
  { id: 'check:ci-dkim-notify', run: 'npm run check:ci-dkim-notify', gate: true, leaves: ['scripts/check-dkim-notify.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "DKIM notify DNS" } },
  { id: 'check:ci-redirects', run: 'npm run check:ci-redirects', gate: true, needs: ['build:www'], leaves: ['scripts/check-redirect-integrity.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-www-build', step: "Redirects" } },
  { id: 'check:ci-search-index', run: 'npm run check:ci-search-index', gate: true, leaves: ['scripts/check-search-index-freshness.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n', step: "Search index" } },
  { id: 'check:ci-cta-bolt', run: 'npm run check:ci-cta-bolt', gate: true, needs: ['build:www'], leaves: ['packages/www/scripts/check-cta-bolt-uniqueness.js'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-www-build', step: "CTA bolt" } },
  { id: 'check:ci-content-quality', run: 'npm run check:ci-content-quality', gate: true, leaves: ['.ci/scripts/quality/check-content-quality.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Check content for AI slop patterns" } },
  { id: 'check:ci-nis2-quotes', run: 'npm run check:ci-nis2-quotes', gate: true, leaves: ['scripts/check-directive-quotes.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Verify NIS2 directive quotations match the official source" } },
  { id: 'check:cli-examples', run: 'npm run check:cli-examples', gate: true, leaves: ['scripts/validate-cli-examples.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "CLI examples" } },
  { id: 'check:ci-tutorial-commands', run: 'npm run check:ci-tutorial-commands', gate: true, leaves: ['scripts/check-tutorial-commands.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Validate tutorial storyboard commands against the live CLI" } },
  { id: 'check:ci-tutorial-noninteractive', run: 'npm run check:ci-tutorial-noninteractive', gate: true, leaves: ['scripts/check-tutorial-noninteractive.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Validate tutorial commands are non-interactive" } },
  { id: 'check:ci-tutorial-parity', run: 'npm run check:ci-tutorial-parity', gate: true, leaves: ['packages/www/scripts/check-tutorial-parity.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Validate tutorial cast/storyboard/transcript/mdx parity" } },
  { id: 'check:ci-tutorial-casts', run: 'npm run check:ci-tutorial-casts', gate: true, leaves: ['packages/www/scripts/validate-tutorial-cast-output.js'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Block fallback hacks and error output in tutorial recordings" } },
  { id: 'check:ci-tutorial-render-queue', run: 'npm run check:ci-tutorial-render-queue', gate: true, leaves: ['packages/www/scripts/list-tutorial-render-pairs.js'], ci: { kind: 'test', test: '.ci/scripts/test/gates/test-tutorial-render-queue.sh', blocker: "BLOCKER: the predicate needs the render ledger and media manifest that only the tutorial pipeline writes, and test-tutorial-render-queue.sh:79 runs `node \"$PREDICATE\" --selftest` against the real tree inside run-all.sh, so the real scan does execute in CI (ci-quality.yml quality-security, \"Quality-gate unit tests\")" } },
  { id: 'check:ci-locale-tutorial-assets', run: 'npm run check:ci-locale-tutorial-assets', gate: true, leaves: ['packages/www/scripts/check-locale-tutorial-assets.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Validate per-locale tutorial video assets exist" } },
  { id: 'check:ci-solution-videos', run: 'npm run check:ci-solution-videos', gate: true, leaves: ['packages/www/scripts/check-solution-videos.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Validate localized solution videos exist" } },
  { id: 'check:ci-solution-video-engine', run: 'npm run check:ci-solution-video-engine', gate: true, leaves: ['packages/www/scripts/check-solution-video-engine.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Validate solution narration engine is current" } },
  { id: 'check:ci-tutorial-caption-sync', run: 'npm run check:ci-tutorial-caption-sync', gate: true, leaves: ['packages/www/scripts/check-tutorial-caption-sync.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Validate published tutorial word-timing sync (real ASR alignment, not estimated)" } },
  { id: 'check:ci-account-onboarding', run: 'npm run check:ci-account-onboarding', gate: true, leaves: ['scripts/check-account-onboarding.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: "Validate account onboarding splash against canonical tutorials" } },
  { id: 'check:ci-overrides-reasons', run: 'npm run check:ci-overrides-reasons', gate: true, leaves: ['scripts/check-overrides-reasons.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: "BLOCKER validator — package.json overrides" } },
  { id: 'check:ci-syncpack-reasons', run: 'npm run check:ci-syncpack-reasons', gate: true, leaves: ['scripts/check-syncpack-reasons.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: "BLOCKER validator — syncpack versionGroups" } },
  { id: 'check:ci-suppression-liveness', run: 'npm run check:ci-suppression-liveness', gate: true, leaves: ['scripts/check-suppression-liveness.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: "Suppression liveness — are our allowlist entries still needed?" } },
  { id: 'check:ci-dead-bash', run: 'npm run check:ci-dead-bash', gate: true, leaves: ['scripts/check-dead-bash.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Dead bash" } },
  { id: 'check:actions', run: 'npm run check:actions', gate: true, leaves: ['scripts/check-actions.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "Action freshness" } },
  { id: 'check:ci-jq-boolean-default', run: 'npm run check:ci-jq-boolean-default', gate: true, leaves: ['scripts/check-jq-boolean-default.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-code', step: "jq boolean defaults" } },
  { id: 'check:ci-autopilot-workflow', run: 'npm run check:ci-autopilot-workflow', gate: true, leaves: ['.ci/scripts/security/check-autopilot-workflow-invariants.sh'], ci: { kind: 'test', test: '.ci/scripts/test/gates/test-autopilot-workflow-invariants.sh', blocker: "BLOCKER: no quality lane can run this against the live ruleset, but test-autopilot-workflow-invariants.sh:23-24 points both GATE and REAL at the real .github/workflows/autopilot.yml, so run-all.sh (ci-quality.yml quality-security, \"Quality-gate unit tests\") executes the real scan over the real tree every CI run" } },

  // The parity gate itself. It replaces the two it deleted, and it inherits
  // their workflow step (ci-quality.yml quality-content) rather than adding a
  // new one, so the surface keeps exactly one parity step.
  { id: 'check:ci-parity', run: 'npm run check:ci-parity', gate: true, leaves: ['scripts/check-ci-parity.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: 'Validate parity between the local gate set and the CI quality surface' } },

  // F3: two Quality/Static steps that ran in CI and nowhere else. The forward
  // gate could not see them because its BARE_GATE pattern only covered
  // .ci/scripts/{quality,security}/check-*.sh; these live in .ci/scripts/test/
  // and start with test-. They are invoked by path, not by an npm key, because
  // the Static lane is a bare checkout with no node_modules -- the same reason
  // ci-quality.yml:166-171 already gives for its sibling test-install-sh-config.sh.
  { id: 'test:write-once-guard', run: '.ci/scripts/test/test-write-once-guard.sh', gate: true, leaves: ['.ci/scripts/test/test-write-once-guard.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: 'Write-once guard tests' } },
  { id: 'test:install-script', run: '.ci/scripts/test/test-install-script.sh', gate: true, leaves: ['.ci/scripts/test/test-install-script.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: 'Install-script tests' } },

  // Prerequisite nodes. They validate nothing, so gate:false; they run only
  // when something that needs them is selected.
  //
  // build:www is what closes F5. check:ci-seo's built-HTML link scan self-skips
  // without packages/www/dist (ci-quality.yml:738-740) and the old `&&` chain
  // never built www, so that scan has been vacuous locally for its whole life.
  { id: 'build:packages', run: 'npm run build:packages', gate: false, mutex: ['build-artifacts'], heavy: true, leaves: ['tsc'], ci: { kind: 'local-only', blocker: 'BLOCKER: a prerequisite, not a validation; CI gets the same artifacts from the per-lane build steps (ci-quality.yml quality-code TypeScript, quality-packages CLI contract) and has no single step that corresponds to this node' } },
  { id: 'build:www', run: 'npm run build:www', gate: false, mutex: ['www-dist'], heavy: true, leaves: ['astro'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-www-build', step: 'Build www (produces dist/route-manifest.json)' } },

  // The CI-side aggregate. gate:false because its 57 constituents are scheduled
  // individually below: scheduling this as one unit too would run the whole
  // 443s battery twice, and 443s is 43% of the measured serial total (plan
  // section 2). The npm key stays because CI wants one step for it.
  { id: 'check:ci-quality-gates', run: 'npm run check:ci-quality-gates', gate: false, leaves: ['.ci/scripts/test/run-all.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },

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
  { id: 'gate-test:actions-release-age', run: '.ci/scripts/test/gates/test-actions-release-age.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-actions-release-age.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:age-check', run: '.ci/scripts/test/gates/test-age-check.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-age-check.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:autopilot-harness', run: '.ci/scripts/test/gates/test-autopilot-harness.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-autopilot-harness.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:autopilot-no-bypass', run: '.ci/scripts/test/gates/test-autopilot-no-bypass.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-autopilot-no-bypass.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:autopilot-workflow-invariants', run: '.ci/scripts/test/gates/test-autopilot-workflow-invariants.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-autopilot-workflow-invariants.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:blocker-validator', run: '.ci/scripts/test/gates/test-blocker-validator.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-blocker-validator.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:breakpoint-drift', run: '.ci/scripts/test/gates/test-breakpoint-drift.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-breakpoint-drift.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:breakpoint-mode-selection', run: '.ci/scripts/test/gates/test-breakpoint-mode-selection.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-breakpoint-mode-selection.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:breakpoint-naming', run: '.ci/scripts/test/gates/test-breakpoint-naming.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-breakpoint-naming.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:breakpoint-pins', run: '.ci/scripts/test/gates/test-breakpoint-pins.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-breakpoint-pins.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:breakpoint-portability', run: '.ci/scripts/test/gates/test-breakpoint-portability.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-breakpoint-portability.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:breakpoint-secret-exposure', run: '.ci/scripts/test/gates/test-breakpoint-secret-exposure.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-breakpoint-secret-exposure.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:breakpoint-teardown', run: '.ci/scripts/test/gates/test-breakpoint-teardown.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-breakpoint-teardown.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:channel-for-event', run: '.ci/scripts/test/gates/test-channel-for-event.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-channel-for-event.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:ci-complete-tiers', run: '.ci/scripts/test/gates/test-ci-complete-tiers.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-ci-complete-tiers.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:ci-job-aggregation', run: '.ci/scripts/test/gates/test-ci-job-aggregation.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-ci-job-aggregation.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:ci-parity', run: '.ci/scripts/test/gates/test-ci-parity.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-ci-parity.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:ci-runner', run: '.ci/scripts/test/gates/test-ci-runner.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-ci-runner.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:claude-hooks', run: '.ci/scripts/test/gates/test-claude-hooks.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-claude-hooks.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:dead-bash', run: '.ci/scripts/test/gates/test-dead-bash.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-dead-bash.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:e2e-coverage', run: '.ci/scripts/test/gates/test-e2e-coverage.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-e2e-coverage.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:embed-arch-parity', run: '.ci/scripts/test/gates/test-embed-arch-parity.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-embed-arch-parity.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:embed-asset-freshness', run: '.ci/scripts/test/gates/test-embed-asset-freshness.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-embed-asset-freshness.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:embed-credits', run: '.ci/scripts/test/gates/test-embed-credits.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-embed-credits.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:emit-advisory', run: '.ci/scripts/test/gates/test-emit-advisory.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-emit-advisory.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:gate-anti-vacuity', run: '.ci/scripts/test/gates/test-gate-anti-vacuity.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-gate-anti-vacuity.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:gate-paths-exist', run: '.ci/scripts/test/gates/test-gate-paths-exist.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-gate-paths-exist.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:generate-tag-inputs', run: '.ci/scripts/test/gates/test-generate-tag-inputs.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-generate-tag-inputs.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:go-deps-probe-failure', run: '.ci/scripts/test/gates/test-go-deps-probe-failure.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-go-deps-probe-failure.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:greenlight', run: '.ci/scripts/test/gates/test-greenlight.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-greenlight.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:knip-blockers', run: '.ci/scripts/test/gates/test-knip-blockers.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-knip-blockers.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:nightly-status-report', run: '.ci/scripts/test/gates/test-nightly-status-report.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-nightly-status-report.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:overrides-reasons', run: '.ci/scripts/test/gates/test-overrides-reasons.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-overrides-reasons.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:positional-detector', run: '.ci/scripts/test/gates/test-positional-detector.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-positional-detector.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:release-state-consistency', run: '.ci/scripts/test/gates/test-release-state-consistency.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-release-state-consistency.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:renet-deadcode', run: '.ci/scripts/test/gates/test-renet-deadcode.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-renet-deadcode.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:review-status', run: '.ci/scripts/test/gates/test-review-status.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-review-status.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:schema-coverage', run: '.ci/scripts/test/gates/test-schema-coverage.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-schema-coverage.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:scope-baseline-attest', run: '.ci/scripts/test/gates/test-scope-baseline-attest.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-scope-baseline-attest.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:scope-engine', run: '.ci/scripts/test/gates/test-scope-engine.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-scope-engine.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:scope-gate-outputs', run: '.ci/scripts/test/gates/test-scope-gate-outputs.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-scope-gate-outputs.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:scrub-sentinel-empty', run: '.ci/scripts/test/gates/test-scrub-sentinel-empty.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-scrub-sentinel-empty.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:shell-counter-increment', run: '.ci/scripts/test/gates/test-shell-counter-increment.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-shell-counter-increment.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:skip-plan-reconcile', run: '.ci/scripts/test/gates/test-skip-plan-reconcile.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-skip-plan-reconcile.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:slim-timeout', run: '.ci/scripts/test/gates/test-slim-timeout.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-slim-timeout.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:stage-artifacts-channel', run: '.ci/scripts/test/gates/test-stage-artifacts-channel.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-stage-artifacts-channel.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:suppression-liveness', run: '.ci/scripts/test/gates/test-suppression-liveness.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-suppression-liveness.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:swallowed-failures', run: '.ci/scripts/test/gates/test-swallowed-failures.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-swallowed-failures.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:tutorial-render-queue', run: '.ci/scripts/test/gates/test-tutorial-render-queue.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-tutorial-render-queue.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:watchdog-binary-exec-guard', run: '.ci/scripts/test/gates/test-watchdog-binary-exec-guard.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-watchdog-binary-exec-guard.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:watchdog-cancel-label', run: '.ci/scripts/test/gates/test-watchdog-cancel-label.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-watchdog-cancel-label.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:watchdog-classifier-chain', run: '.ci/scripts/test/gates/test-watchdog-classifier-chain.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-watchdog-classifier-chain.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:watchdog-log-capture', run: '.ci/scripts/test/gates/test-watchdog-log-capture.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-watchdog-log-capture.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:watchdog-retry-allowlist', run: '.ci/scripts/test/gates/test-watchdog-retry-allowlist.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-watchdog-retry-allowlist.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:watchdog-schedule-exemption', run: '.ci/scripts/test/gates/test-watchdog-schedule-exemption.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-watchdog-schedule-exemption.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:watchdog-supersession', run: '.ci/scripts/test/gates/test-watchdog-supersession.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-watchdog-supersession.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:workflow-contracts', run: '.ci/scripts/test/gates/test-workflow-contracts.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-workflow-contracts.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:workflow-env-shell-vars', run: '.ci/scripts/test/gates/test-workflow-env-shell-vars.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-workflow-env-shell-vars.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
  { id: 'gate-test:workflow-inline', run: '.ci/scripts/test/gates/test-workflow-inline.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-workflow-inline.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } },
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
