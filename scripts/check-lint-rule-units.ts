/**
 * check:ci-lint-rule-units -- RuleTester unit specs for `eslint-rules/`.
 *
 * WHY THIS EXISTS, AND WHY IT IS NOT check_lint_rule_liveness.py.
 *
 * The liveness gate derives its universe from eslint.config.js and mutation-
 * tests every rule that any block ENABLES. That is its strength and its blind
 * spot in the same sentence: a rule configured 'off' everywhere is outside its
 * universe by construction. Its own 2026-09-06 output says so:
 *
 *   30 enabled custom/i18n rule(s) each fired on a planted violation
 *   (35 registered, 5 off by documented decision, ...)
 *
 * Those five have no proof of any kind. Nothing in the repository executes
 * them, so a refactor that breaks one is invisible until somebody turns it back
 * on and finds it silent. `i18n/sorted-keys` is one of the five, and it is
 * precisely the rule that had 2172 real findings hiding behind the 2026-08-06
 * `node.body?.members` bug.
 *
 * The second gap applies even to an ENABLED rule. One planted violation proves
 * a rule is not dead. It does not prove the rule reports the right messageId,
 * honours its options, produces a correct autofix, or stays quiet on the valid
 * case next door. Every option in these five rules changes the verdict, and no
 * planted violation can see a verdict change.
 *
 * DIVISION OF LABOUR, so the two gates do not grow into each other:
 *   liveness  -> can this ENABLED rule fire at all, in its real config block
 *   this      -> does the rule behave, including the ones config never runs
 *
 * WHAT THIS GATE REFUSES TO DO. It does not require a spec for all 35 rules
 * today. A gate that demands 30 specs nobody has written is a gate somebody
 * switches off, which is the failure mode check_lint_rule_liveness.py's own
 * header warns about at length. So the enforced rules are:
 *
 *   1. Every spec present must PASS.
 *   2. Every spec must name a rule that actually exists (no stale specs).
 *   3. The spec count and the case count may only GROW (shrink-only floors,
 *      derived from the corpus rather than hand-typed).
 *
 * and the untested set is REPORTED on every run, so scheduling the rest is a
 * decision somebody makes with the list in front of them rather than a number
 * in a plan.
 *
 * ---- gate ----
 * step: Lint rule unit specs
 * needs: node
 * selftest: true
 * lane: quality-content
 * why: The five lint rules configured 'off' everywhere are outside the liveness gate's universe by construction, so nothing else in the repository ever executes them.
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { RULES_DIR, REPO_ROOT } from '../eslint-rules/lib/paths.js';
import {
  SPEC_DIR,
  SPEC_SUFFIX,
  jsonRuleTester,
  sourceRuleTester,
  runCases,
  withFixture,
} from '../eslint-rules/__tests__/harness.js';

const GREEN = '[32m';
const RED = '[31m';
const DIM = '[2m';
const NC = '[0m';

/**
 * Shrink-only floors, in the sense driver-contract section 6 requires: a floor
 * exists so a collapsed glob cannot report success, and it is raised when the
 * corpus grows. These two are the smallest honest statement of "the specs ran".
 */
const MIN_SPECS = 5;
const MIN_CASES = 40;

interface SpecResult {
  ruleId: string;
  valid: number;
  invalid: number;
  failures: string[];
}

/**
 * The rule universe, derived from the source tree rather than listed.
 *
 * A hand-written list is exactly the artefact that misses a file, which is the
 * lesson recorded in check_lint_rule_liveness.py's header after its own probe
 * list covered 3 rules out of 30. The ids are built the way eslint.config.js
 * builds them: the two i18n plugin registries supply their own keys, and every
 * other rule module at the top of `eslint-rules/` is a `custom/` rule named
 * after its file.
 */
async function ruleUniverse(): Promise<Set<string>> {
  const ids = new Set<string>();

  const index = (await import(path.join(RULES_DIR, 'i18n', 'index.js'))) as {
    i18nJsonPlugin: { rules: Record<string, unknown> };
    i18nSourcePlugin: { rules: Record<string, unknown> };
  };
  for (const name of Object.keys(index.i18nJsonPlugin.rules)) ids.add(`i18n/${name}`);
  for (const name of Object.keys(index.i18nSourcePlugin.rules)) ids.add(`i18n-source/${name}`);

  for (const entry of fs.readdirSync(RULES_DIR, { withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith('.js')) continue;
    const mod = (await import(path.join(RULES_DIR, entry.name))) as Record<string, unknown>;
    const isRule = Object.values(mod).some(
      (v) =>
        v !== null &&
        typeof v === 'object' &&
        typeof (v as { create?: unknown }).create === 'function'
    );
    if (isRule) ids.add(`custom/${entry.name.replace(/\.js$/, '')}`);
  }

  return ids;
}

/** Spec modules on disk, sorted so the report is stable. */
function specFiles(): string[] {
  if (!fs.existsSync(SPEC_DIR)) return [];
  return fs
    .readdirSync(SPEC_DIR)
    .filter((n) => n.endsWith(SPEC_SUFFIX))
    .sort()
    .map((n) => path.join(SPEC_DIR, n));
}

async function runSpecs(): Promise<SpecResult[]> {
  const out: SpecResult[] = [];
  for (const file of specFiles()) {
    const mod = (await import(file)) as {
      ruleId?: string;
      default?: (h: unknown) => Promise<SpecResult[]>;
    };
    if (typeof mod.default !== 'function' || typeof mod.ruleId !== 'string') {
      out.push({
        ruleId: path.basename(file),
        valid: 0,
        invalid: 0,
        failures: [
          `${path.relative(REPO_ROOT, file)}: a spec must export \`ruleId\` and a default function.`,
        ],
      });
      continue;
    }
    const results = await mod.default({
      jsonRuleTester,
      sourceRuleTester,
      runCases,
      withFixture,
    });
    // Every invocation inside one spec file is folded onto that file's rule id,
    // so the report is one line per RULE rather than one per fixture.
    const folded: SpecResult = { ruleId: mod.ruleId, valid: 0, invalid: 0, failures: [] };
    for (const r of results) {
      folded.valid += r.valid;
      folded.invalid += r.invalid;
      folded.failures.push(...r.failures);
    }
    out.push(folded);
  }
  return out;
}

/**
 * The control. It asserts the harness reports a failure when an expectation is
 * WRONG, in both directions: a rule that should report and does not, and a rule
 * that should stay silent and does not.
 *
 * Without this, a harness whose `runCases` swallowed every assertion would print
 * the same green as a working one, which is the whole reason this repository
 * runs controls rather than trusting exit codes.
 */
async function selftest(): Promise<number> {
  const { sortedKeys } = (await import(path.join(RULES_DIR, 'i18n', 'sorted-keys.js'))) as {
    sortedKeys: never;
  };

  const missedReport = runCases(jsonRuleTester(), 'control/should-have-reported', sortedKeys, {
    valid: [],
    // Sorted keys. The rule is correct to stay silent, so DEMANDING an error
    // must be recorded as a failure.
    invalid: [{ code: '{"a": "1", "b": "2"}', errors: [{ messageId: 'unsorted' }] }],
  });

  const falseAlarm = runCases(jsonRuleTester(), 'control/should-have-been-quiet', sortedKeys, {
    // Unsorted keys. The rule is correct to report, so calling this valid must
    // be recorded as a failure.
    valid: [{ code: '{"b": "2", "a": "1"}' }],
    invalid: [],
  });

  const problems: string[] = [];
  if (missedReport.failures.length === 0) {
    problems.push('CONTROL FAILED: a demanded-but-absent error was not reported as a failure.');
  }
  if (falseAlarm.failures.length === 0) {
    problems.push('CONTROL FAILED: an unexpected error on a "valid" case was not reported.');
  }

  // And the corpus must not be empty, or the two controls above are the only
  // thing this file ever proves.
  const specs = specFiles();
  if (specs.length === 0) {
    problems.push(`CONTROL FAILED: no ${SPEC_SUFFIX} files found in ${SPEC_DIR}.`);
  }

  if (problems.length > 0) {
    for (const p of problems) console.error(`${RED}${p}${NC}`);
    return 1;
  }
  console.log(
    `${GREEN}✓${NC} lint rule units selftest: the harness reports both a missing error ` +
      `and an unexpected one; ${specs.length} spec file(s) present`
  );
  return 0;
}

async function main(): Promise<number> {
  if (process.argv.includes('--selftest')) return selftest();

  const universe = await ruleUniverse();
  const results = await runSpecs();

  const failures: string[] = [];
  let cases = 0;

  for (const r of results) {
    cases += r.valid + r.invalid;
    if (r.valid + r.invalid === 0) {
      failures.push(
        `${r.ruleId}: spec supplied zero cases, which is a green with nothing behind it.`
      );
    }
    if (!universe.has(r.ruleId)) {
      failures.push(
        `${r.ruleId}: spec names a rule that does not exist. Either the rule was deleted ` +
          'and the spec is stale, or the id is misspelled and the spec is testing nothing.'
      );
    }
    failures.push(...r.failures);
  }

  if (results.length < MIN_SPECS) {
    failures.push(
      `Only ${results.length} spec file(s) ran, floor is ${MIN_SPECS}. A collapsed glob ` +
        'reports success exactly like a clean tree, so the floor is the difference.'
    );
  }
  if (cases < MIN_CASES) {
    failures.push(`Only ${cases} case(s) ran, floor is ${MIN_CASES}.`);
  }

  const tested = new Set(results.map((r) => r.ruleId));
  const untested = [...universe].filter((id) => !tested.has(id)).sort();

  if (failures.length > 0) {
    console.error(`${RED}✗ lint rule unit specs${NC}`);
    for (const f of failures) console.error(`  ${f}`);
    return 1;
  }

  for (const r of results) {
    console.log(`${GREEN}✓${NC} ${r.ruleId}${DIM} ${r.valid} valid, ${r.invalid} invalid${NC}`);
  }
  console.log(
    `${GREEN}✓${NC} lint rule unit specs: ${results.length} rule(s), ${cases} case(s), ` +
      `${untested.length} of ${universe.size} rule(s) still without a spec`
  );
  console.log(`${DIM}  no spec yet: ${untested.join(', ')}${NC}`);
  return 0;
}

if (path.resolve(process.argv[1] ?? '') === path.resolve(fileURLToPath(import.meta.url))) {
  main()
    .then((code) => process.exit(code))
    .catch((error: unknown) => {
      console.error(`${RED}✗ lint rule unit specs crashed${NC}`);
      console.error(error);
      process.exit(1);
    });
}
