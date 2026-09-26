#!/usr/bin/env tsx
/**
 * check:ci-package-key-budget -- the HAND-MAINTAINED half of package.json's script keys
 * may only shrink.
 *
 * ---- gate ----
 * step: Package key budget
 * needs: node
 * why: every registration box appends a key and nothing ever removes one
 * ---- end gate ----
 *
 * WHY A BUDGET AT ALL. The tooling transformation adds a registration box per ported gate,
 * and every one of them appends a key. Left alone the file grows monotonically and nobody
 * ever removes anything, which is how a 300-key package.json happens.
 *
 * WHY NOT A BUDGET ON THE TOTAL, which is what the plan originally asked for. Measured
 * 2026-09-06: 310 keys, of which 261 are gate ids the manifest schedules. Those are supposed
 * to grow, one per new gate, and a ceiling on the total would fire on exactly the work the
 * program exists to do while saying nothing about the sprawl. Splitting the two is the whole
 * point: the registry half is DERIVED and free to grow, the hand-written half is not.
 *
 * WHY A SET AND NOT A COUNT. A count lets a key be swapped for a different key, which is how
 * a budget quietly becomes a rename allowance. The baseline records the NAMES, so retiring
 * `foo` does not buy you `bar`.
 *
 * THE MANIFEST IS IMPORTED, NOT PARSED. scripts/ci-runner/manifest.ts already has three
 * tools reading it as TEXT with regexes, and the registry workstream has to port all three
 * before it can generate that file. A fourth text reader would be a fourth thing to port, so
 * this gate takes the typed import and keeps working when the file becomes generated.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GATES } from '../ci-runner/manifest';
import {
  baselineAdditions,
  renderRefusal,
  writeBaselineVerdict,
} from '../lib/shrink-only-baseline';
import { refused } from '../lib/controls';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const BASELINE = path.join(ROOT, 'scripts/data/package-key-budget-baseline.json');

/**
 * Anti-vacuity floors. A collapsed read of either input makes every key look hand-written
 * or every key look derived, and both directions report a clean tree. Measured today: 310
 * script keys and 402 manifest ids, so these sit far enough below to survive real churn and
 * far enough above zero to catch an empty parse.
 */
const MIN_SCRIPT_KEYS = 200;
const MIN_MANIFEST_IDS = 300;

export const nonRegistryKeys = (
  scriptKeys: readonly string[],
  manifestIds: ReadonlySet<string>
): string[] => scriptKeys.filter((k) => !manifestIds.has(k)).sort();

const readBaseline = (): string[] => {
  if (!fs.existsSync(BASELINE)) return [];
  return JSON.parse(fs.readFileSync(BASELINE, 'utf-8')) as string[];
};

const selftest = (): number => {
  const ids = new Set(['check:a', 'check:b']);
  const cases: { name: string; ok: boolean }[] = [
    {
      name: 'a manifest id is classified as registry, not hand-written',
      ok: nonRegistryKeys(['check:a', 'dev'], ids).join() === 'dev',
    },
    {
      name: 'a NEW hand-written key is an addition',
      ok: baselineAdditions(['dev'], ['dev', 'scratch']).join() === 'scratch',
    },
    {
      name: 'CONTROL: a swap is caught, so the budget is not a rename allowance',
      ok: baselineAdditions(['dev'], ['other']).join() === 'other',
    },
    {
      name: 'retiring a key is not an addition',
      ok: baselineAdditions(['dev', 'scratch'], ['dev']).length === 0,
    },
    {
      name: 'CONTROL: an empty manifest would make every key look hand-written',
      ok: nonRegistryKeys(['check:a'], new Set()).length === 1,
    },
  ];
  const bad = cases.filter((c) => !c.ok);
  for (const c of cases) console.log(`  ${c.ok ? 'ok  ' : 'FAIL'} ${c.name}`);
  if (bad.length > 0) {
    console.error(`✗ selftest: ${bad.length} control(s) failed`);
    return 1;
  }
  console.log(`✓ selftest: ${cases.length} controls passed`);
  return 0;
};

const main = (): number => {
  const args = process.argv.slice(2);
  if (args.includes('--selftest')) return selftest();
  if (selftest() !== 0) {
    console.error('✗ instrument control failed; the verdict below would be meaningless');
    return 1;
  }

  const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf-8')) as {
    scripts?: Record<string, string>;
  };
  const scriptKeys = Object.keys(pkg.scripts ?? {});
  const manifestIds = new Set(GATES.map((g) => g.id));

  if (scriptKeys.length < MIN_SCRIPT_KEYS) {
    return refused(
      `✗ VACUOUS: read ${scriptKeys.length} script key(s), floor ${MIN_SCRIPT_KEYS}. package.json did not parse as expected.`
    );
  }
  if (manifestIds.size < MIN_MANIFEST_IDS) {
    return refused(
      `✗ VACUOUS: read ${manifestIds.size} manifest id(s), floor ${MIN_MANIFEST_IDS}. Every key would read as hand-written.`
    );
  }

  const current = nonRegistryKeys(scriptKeys, manifestIds);
  const previous = readBaseline();

  if (args.includes('--write-baseline')) {
    fs.writeFileSync(BASELINE, `${JSON.stringify(current, null, 2)}\n`);
    console.log(`wrote ${current.length} hand-written key(s) to the baseline`);
    return 0;
  }

  const additions = baselineAdditions(previous, current);
  const verdict = writeBaselineVerdict({
    baselineExists: fs.existsSync(BASELINE),
    firstSeedFlag: false,
    additions,
  });
  if (verdict) {
    return refused(
      renderRefusal(verdict, {
        baselineLabel: 'scripts/data/package-key-budget-baseline.json',
        noun: 'hand-written package.json script key',
        previousCount: previous.length,
        newCount: current.length,
      })
    );
  }

  const retired = previous.filter((k) => !current.includes(k));
  console.log(
    `✓ package.json script keys: ${scriptKeys.length} total, ${scriptKeys.length - current.length} scheduled by the manifest, ${current.length} hand-written (baseline ${previous.length}).`
  );
  if (retired.length > 0) {
    console.log(
      `  ${retired.length} key(s) retired since the baseline; re-run with --write-baseline to record the shrink: ${retired.join(', ')}`
    );
  }
  return 0;
};

process.exit(main());
