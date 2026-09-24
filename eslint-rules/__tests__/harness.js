/**
 * Host-backed rule tester for `eslint-rules/`, replacing the ESLint `RuleTester` this file used to wrap.
 *
 * WHY THIS EXISTS, and what it is NOT duplicating.
 *
 * `.ci/scripts/quality/check_lint_rule_liveness.py` already proves that every ENABLED rule can fire, by planting one violation per rule and asserting the rule catches it. That gate is derived from eslint.config.js, which is its strength and also its blind spot: a rule set to 'off' everywhere is, by construction, outside its universe. Measured on 2026-09-06, its own output says so out loud:
 *
 *   30 enabled custom/i18n rule(s) each fired on a planted violation
 *   (35 registered, 5 off by documented decision, ...)
 *
 * Those 5 have NO proof of any kind. Nothing in the repository ever executes them, so a refactor that breaks one is silent until somebody turns the rule back on and discovers it reports nothing, which is exactly the shape of the 2026-08-06 incident the liveness gate was built for.
 *
 * The second thing liveness cannot see, even for an enabled rule, is BEHAVIOUR: one planted violation proves a rule is not dead, not that it reports the right messageId, respects its options, produces a correct autofix, or stays quiet on the valid case next door. This module is the instrument for that, now running the rule through `scripts/lib/rule-host.ts` instead of ESLint's own `RuleTester` -- the same engine `check-source-rules.ts` uses, so a spec and the gate can never quietly disagree about what a rule does.
 *
 * DIVISION OF LABOUR, so neither gate grows into the other:
 *   liveness  -> "can this ENABLED rule fire at all, in its real config block"
 *   this      -> "does this rule behave, including the ones config never runs"
 *
 * SHAPE OF A SPEC. A spec file is `<rule-id>.spec.js` beside this file. It default-exports a function receiving this module's exports and returning an array of `runCases` invocations already performed. Failures are collected rather than thrown so one broken rule does not hide the other four. The case shape (`code`, `filename`, `options`, `errors`, `output`) is the same one the specs already wrote against ESLint's `RuleTester`, so no spec file needed to change when the engine underneath it did.
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { RULES_DIR } from '../lib/paths.js';
import {
  runJsonRule,
  runSourceRule,
  applyFixes,
  interpolate,
} from '../../scripts/lib/rule-host.ts';

/** A tester descriptor for the JSON locale rules: `Document(node)` over a momoa AST via `runJsonRule`. */
export const jsonRuleTester = () => ({ kind: 'json' });

/** A tester descriptor for the rules that run over JS and TS source, via `runSourceRule`. */
export const sourceRuleTester = () => ({ kind: 'source' });

/**
 * Materialise a throwaway directory tree, run a callback against it, remove it.
 *
 * Two of the five untested rules resolve real directories (`no-unused-keys` takes a `sourceDir` option that must be an existing directory; the option resolver REFUSES a missing one on purpose, because a path that does not exist makes a rule read nothing and report nothing). A fixture on disk is therefore part of the test, not a convenience.
 *
 * The directory goes under the system temp dir and never inside the repository, so a crashed run cannot leave a file the tree's own enumeration gates would later count.
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

const DEFAULT_FILENAME = { json: 'test.json', source: 'test.ts' };

/** Run one case (a bare code string or `{code, filename, options}`) through the host, tagged by the tester's kind. */
function runOne(tester, caseDef) {
  const normalized = typeof caseDef === 'string' ? { code: caseDef } : caseDef;
  const filename = path.resolve(normalized.filename ?? DEFAULT_FILENAME[tester.kind]);
  const run = { filename, cwd: process.cwd(), options: normalized.options ?? [] };
  const findings =
    tester.kind === 'json'
      ? runJsonRule(normalized.rule, normalized.code, run)
      : runSourceRule(normalized.rule, normalized.code, run);
  return { normalized, findings };
}

/** Every mismatch between one expected `invalid` case and what the host actually found, as human-readable lines. */
function invalidCaseProblems(rule, normalized, findings) {
  const problems = [];
  const expected = normalized.errors;
  if (typeof expected === 'number') {
    if (findings.length !== expected)
      problems.push(`expected ${expected} problem(s), got ${findings.length}`);
    return problems;
  }
  if (findings.length !== expected.length) {
    problems.push(
      `expected ${expected.length} problem(s), got ${findings.length}: ${JSON.stringify(findings.map((f) => f.messageId))}`
    );
    return problems;
  }
  expected.forEach((exp, i) => {
    const actual = findings[i];
    if (exp.messageId && exp.messageId !== actual.messageId) {
      problems.push(
        `error #${i + 1}: expected messageId "${exp.messageId}", got "${actual.messageId}"`
      );
    }
    if (exp.data) {
      const template = rule.meta?.messages?.[exp.messageId];
      const expectedMessage = template ? interpolate(template, exp.data) : undefined;
      if (expectedMessage !== undefined && expectedMessage !== actual.message) {
        problems.push(
          `error #${i + 1}: expected message ${JSON.stringify(expectedMessage)}, got ${JSON.stringify(actual.message)}`
        );
      }
    }
  });
  if (normalized.output !== undefined) {
    const fixed = applyFixes(normalized.code, findings);
    if (fixed !== normalized.output) {
      problems.push(
        `expected output ${JSON.stringify(normalized.output)}, got ${JSON.stringify(fixed)}`
      );
    }
  }
  return problems;
}

/**
 * Run one rule's `valid`/`invalid` case set and return a structured result instead of throwing.
 *
 * Every case is attempted and every failure is collected, so a single run reports the whole truth rather than stopping at the first broken case.
 *
 * The case count is returned because it is the anti-vacuity number. A spec that declares a rule and supplies zero cases would otherwise pass, and a green with nothing behind it is the failure this repository spends the most effort on.
 *
 * @param {{kind: string}} tester From `jsonRuleTester()`/`sourceRuleTester()`.
 * @param {string} ruleId
 * @param {import('../../scripts/lib/rule-host.ts').RuleModule} rule
 * @param {{ valid?: unknown[], invalid?: unknown[] }} cases
 * @returns {{ ruleId: string, valid: number, invalid: number, failures: string[] }}
 */
export const runCases = (tester, ruleId, rule, cases) => {
  const valid = cases.valid ?? [];
  const invalid = cases.invalid ?? [];
  const failures = [];

  valid.forEach((caseDef, index) => {
    try {
      const { findings } = runOne(
        tester,
        typeof caseDef === 'string' ? { code: caseDef, rule } : { ...caseDef, rule }
      );
      if (findings.length > 0) {
        failures.push(
          `${ruleId}: valid case #${index + 1}\n      expected 0 problems, got ${findings.length}: ${findings.map((f) => f.messageId ?? f.message).join(', ')}`
        );
      }
    } catch (error) {
      failures.push(
        `${ruleId}: valid case #${index + 1} threw\n      ${String(error?.message ?? error)}`
      );
    }
  });

  invalid.forEach((caseDef, index) => {
    try {
      const { normalized, findings } = runOne(tester, { ...caseDef, rule });
      const problems = invalidCaseProblems(rule, normalized, findings);
      if (problems.length > 0) {
        failures.push(`${ruleId}: invalid case #${index + 1}\n      ${problems.join('\n      ')}`);
      }
    } catch (error) {
      failures.push(
        `${ruleId}: invalid case #${index + 1} threw\n      ${String(error?.message ?? error)}`
      );
    }
  });

  return { ruleId, valid: valid.length, invalid: invalid.length, failures };
};

/**
 * Absolute path of this directory, for the spec discovery in the gate.
 *
 * Anchored through lib/paths.js rather than through a fresh `import.meta.url` dance, because a second hand-counted anchor in this tree is the exact thing that module exists to remove.
 */
export const SPEC_DIR = path.join(RULES_DIR, '__tests__');

/**
 * Spec files are `.js`, NOT `.mjs`, and that is load-bearing rather than taste.
 *
 * The repository root is `"type": "module"`, so a `.js` file here is already ESM. eslint.config.js gives this tree its node globals through the glob `eslint-rules/**\/*.js`, which does not match `.mjs` or `.cjs`. Measured 2026-09-06: `eslint --print-config` on a `.mjs` under this directory reports NO node globals, so the first `process` or `URL` reference in it is a `no-undef` error for a reason that has nothing to do with the code.
 */
export const SPEC_SUFFIX = '.spec.js';
