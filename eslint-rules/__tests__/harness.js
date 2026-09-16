/**
 * RuleTester harness for `eslint-rules/`.
 *
 * WHY THIS EXISTS, and what it is NOT duplicating.
 *
 * `.ci/scripts/quality/check_lint_rule_liveness.py` already proves that every
 * ENABLED rule can fire, by planting one violation per rule and asserting the
 * rule catches it. That gate is derived from eslint.config.js, which is its
 * strength and also its blind spot: a rule set to 'off' everywhere is, by
 * construction, outside its universe. Measured on 2026-09-06, its own output
 * says so out loud:
 *
 *   30 enabled custom/i18n rule(s) each fired on a planted violation
 *   (35 registered, 5 off by documented decision, ...)
 *
 * Those 5 have NO proof of any kind. Nothing in the repository ever executes
 * them, so a refactor that breaks one is silent until somebody turns the rule
 * back on and discovers it reports nothing, which is exactly the shape of the
 * 2026-08-06 incident the liveness gate was built for.
 *
 * The second thing liveness cannot see, even for an enabled rule, is BEHAVIOUR:
 * one planted violation proves a rule is not dead, not that it reports the
 * right messageId, respects its options, produces a correct autofix, or stays
 * quiet on the valid case next door. RuleTester is the instrument for that.
 *
 * DIVISION OF LABOUR, so neither gate grows into the other:
 *   liveness  -> "can this ENABLED rule fire at all, in its real config block"
 *   this      -> "does this rule behave, including the ones config never runs"
 *
 * SHAPE OF A SPEC. A spec file is `<rule-id>.spec.js` beside this file. It
 * default-exports a function receiving this module's exports and returning an
 * array of RuleTester invocations already performed. Failures are collected
 * rather than thrown so one broken rule does not hide the other four.
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { RuleTester } from 'eslint';
import json from '@eslint/json';

import { RULES_DIR } from '../lib/paths.js';

/**
 * A RuleTester for the JSON locale rules.
 *
 * These rules run under the `json/json` language from @eslint/json, whose AST
 * is NOT ESTree: an Object node carries `members` DIRECTLY rather than under
 * `body`. Five rules once read `node.body?.members` on it, walked an empty list
 * and could not report anything ever, while configured at severity 'error'. A
 * RuleTester configured with any other language would reproduce that bug rather
 * than catch it, so the language here is not a detail.
 *
 * @returns {RuleTester}
 */
export const jsonRuleTester = () => new RuleTester({ plugins: { json }, language: 'json/json' });

/**
 * A RuleTester for the rules that run over JS and TS source.
 *
 * @returns {RuleTester}
 */
export const sourceRuleTester = () =>
  new RuleTester({
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  });

/**
 * Materialise a throwaway directory tree, run a callback against it, remove it.
 *
 * Two of the five untested rules resolve real directories (`no-unused-keys`
 * takes a `sourceDir` option that must be an existing directory; the option
 * resolver REFUSES a missing one on purpose, because a path that does not exist
 * makes a rule read nothing and report nothing). A fixture on disk is therefore
 * part of the test, not a convenience.
 *
 * The directory goes under the system temp dir and never inside the repository,
 * so a crashed run cannot leave a file the tree's own enumeration gates would
 * later count.
 *
 * @param {Record<string, string>} files Relative path to file content.
 * @param {(dir: string) => void} fn Receives the absolute fixture root.
 * @returns {void}
 */
export const withFixture = (files, fn) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'eslint-rules-spec-'));
  try {
    for (const [rel, content] of Object.entries(files)) {
      const abs = path.join(dir, rel);
      fs.mkdirSync(path.dirname(abs), { recursive: true });
      fs.writeFileSync(abs, content);
    }
    fn(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
};

/**
 * Run one RuleTester case set and return a structured result instead of
 * throwing.
 *
 * RuleTester's own reporting is an exception on the FIRST failure, which is the
 * right default for a watch loop and the wrong one for a gate: it turns five
 * broken rules into one message and four unknowns. Here every case is attempted
 * and every failure is collected, so a single run reports the whole truth.
 *
 * The case count is returned because it is the anti-vacuity number. A spec that
 * declares a rule and supplies zero cases would otherwise pass, and a green with
 * nothing behind it is the failure this repository spends the most effort on.
 *
 * @param {RuleTester} tester
 * @param {string} ruleId
 * @param {import('eslint').Rule.RuleModule} rule
 * @param {{ valid?: unknown[], invalid?: unknown[] }} cases
 * @returns {{ ruleId: string, valid: number, invalid: number, failures: string[] }}
 */
export const runCases = (tester, ruleId, rule, cases) => {
  const valid = cases.valid ?? [];
  const invalid = cases.invalid ?? [];
  const failures = [];

  // RuleTester delegates to describe/it when they exist. Supplying them turns
  // its throw-on-first-failure into per-case isolation without reimplementing
  // any of its assertions.
  const prevDescribe = RuleTester.describe;
  const prevIt = RuleTester.it;
  RuleTester.describe = (_name, body) => body();
  RuleTester.it = (name, body) => {
    try {
      body();
    } catch (error) {
      failures.push(
        `${ruleId}: ${name}\n      ${String(error.message).replaceAll('\n', '\n      ')}`
      );
    }
  };
  try {
    tester.run(ruleId, rule, { valid, invalid });
  } finally {
    RuleTester.describe = prevDescribe;
    RuleTester.it = prevIt;
  }

  return { ruleId, valid: valid.length, invalid: invalid.length, failures };
};

/**
 * Absolute path of this directory, for the spec discovery in the gate.
 *
 * Anchored through lib/paths.js rather than through a fresh `import.meta.url`
 * dance, because a second hand-counted anchor in this tree is the exact thing
 * that module exists to remove.
 */
export const SPEC_DIR = path.join(RULES_DIR, '__tests__');

/**
 * Spec files are `.js`, NOT `.mjs`, and that is load-bearing rather than taste.
 *
 * The repository root is `"type": "module"`, so a `.js` file here is already
 * ESM. eslint.config.js gives this tree its node globals through the glob
 * `eslint-rules/**\/*.js`, which does not match `.mjs` or `.cjs`. Measured
 * 2026-09-06: `eslint --print-config` on a `.mjs` under this directory reports
 * NO node globals, so the first `process` or `URL` reference in it is a
 * `no-undef` error for a reason that has nothing to do with the code.
 */
export const SPEC_SUFFIX = '.spec.js';
