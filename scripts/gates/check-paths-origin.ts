#!/usr/bin/env node
/**
 * W2.5 tier 1 (C2). `paths` scopes 46 of 465 gates for `--changed`
 * (`scripts/gates/check-changed-selection.ts`), and every one of those 46 globs was
 * hand-typed into `scripts/ci-runner/manifest.ts` with nothing asserting it still
 * matches anything on disk. A stale glob does not fail loudly: the gate it scopes
 * just stops being selected by any real change set, silently, the same shape as the
 * empty-change-set defect B4 fixed for the OTHER 419 entries.
 *
 * `pathsOrigin` (`scripts/ci-runner/gate-spec.ts`) records how a `paths` array came to
 * be, and this gate enforces the two things recording it is for:
 *
 *   1. CARDINALITY EQUALITY, BOTH DIRECTIONS. `paths` with no `pathsOrigin` and
 *      `pathsOrigin` with no `paths` are both refused -- the field is meaningless
 *      alone in either direction, and an origin nobody declared is exactly the kind
 *      of silent drift this gate exists to catch.
 *   2. THE ORIGIN'S OWN CLAIM, VERIFIED. `'declared'` means a human enumerated the
 *      globs, so each glob is checked against `git ls-files`: a glob matching ZERO
 *      tracked files is as wrong as an empty `paths` array and just as invisible
 *      without this. `` `derived:${tool}` `` means some other command PRINTS the
 *      paths list, one per line; the check RE-RUNS it and asserts the output still
 *      equals what is declared, so a derivation that has drifted from its own output
 *      is caught rather than trusted.
 *
 * NO ENTRY USES `derived:` TODAY. Every one of the 46 is a human-typed literal
 * array, so the `derived:` branch is real code with zero real callers -- exactly
 * B2's `SHARD_COUNTS` shape, proven only by `--selftest`'s fixture until W2.5's
 * tier 2 (traced paths, out of scope here) gives it a first live user. Leaving
 * it unbuilt until then would mean the box's own stated acceptance ("a
 * `derived:<tool>` origin must reproduce under re-running") is untestable by
 * construction the day someone adds the first one.
 *
 * ---- gate ----
 * step: Paths-origin provenance
 * lane: quality-code
 * needs: node
 * selftest: true
 * why: a stale or undeclared paths glob silently drops out of every --changed
 *   run, the same vacuity B4 fixed for entries with no paths at all
 * ---- end gate ----
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { globToRegExp } from '../ci-runner/run';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const LOCK = path.join(REPO_ROOT, 'scripts', 'ci-runner', 'gates.lock.json');

/**
 * Floor for the anti-vacuity refusal in `main`. 47 paths-bearing entries exist as of
 * 2026-09-15; 30 leaves room for real removals while still catching a collapsed scan.
 */
const MIN_SCOPED_ENTRIES = 30;

interface LockEntry {
  id: string;
  paths?: string[];
  pathsOrigin?: string;
}

/**
 * A REFUSAL, not a finding: the gate cannot see its subject at all (an empty
 * lock, an empty tracked-file corpus), so folding it into the tally would let
 * "asserted nothing" print a passing count. Same convention as
 * check-changed-selection.ts.
 */
function refuse(text: string): never {
  process.stderr.write(`✗ ${text}\n`);
  process.exit(1);
}

function readLock(): LockEntry[] {
  const parsed: unknown = JSON.parse(fs.readFileSync(LOCK, 'utf-8'));
  if (!Array.isArray(parsed)) throw new Error(`${LOCK} does not contain an array`);
  return parsed as LockEntry[];
}

/**
 * Pure over its inputs so `--selftest` can drive every branch (including
 * `derived:`, which has no live caller) without a real git tree or a real
 * subprocess. `main()` supplies the real tracked-file list and a real
 * `runDerived`; selftest supplies fixtures for both.
 */
function pathsOriginFindings(
  entries: readonly LockEntry[],
  tracked: readonly string[],
  runDerived: (cmd: string) => string[]
): string[] {
  const findings: string[] = [];
  const hasPaths = (e: LockEntry): boolean => e.paths !== undefined;
  const hasOrigin = (e: LockEntry): boolean => e.pathsOrigin !== undefined;

  for (const e of entries) {
    if (hasPaths(e) && !hasOrigin(e)) {
      findings.push(
        `${e.id}: declares \`paths\` with no \`pathsOrigin\` -- required whenever paths is present.`
      );
    }
    if (hasOrigin(e) && !hasPaths(e)) {
      findings.push(
        `${e.id}: declares \`pathsOrigin\` with no \`paths\` -- pathsOrigin describes how paths ` +
          `was produced, so it is meaningless without one.`
      );
    }
  }

  for (const e of entries) {
    if (!hasPaths(e) || !hasOrigin(e)) continue;
    const origin = e.pathsOrigin as string;
    const globs = e.paths as string[];
    if (origin === 'declared') {
      for (const g of globs) {
        const re = globToRegExp(g);
        if (!tracked.some((f) => re.test(f))) {
          findings.push(
            `${e.id}: declared glob \`${g}\` matches ZERO tracked files -- a dead glob drops out ` +
              `of every --changed run and nothing else would say so.`
          );
        }
      }
    } else if (origin.startsWith('derived:')) {
      const cmd = origin.slice('derived:'.length);
      if (cmd.length === 0) {
        findings.push(`${e.id}: pathsOrigin "derived:" names no tool to re-run.`);
        continue;
      }
      let reproduced: string[];
      try {
        reproduced = runDerived(cmd);
      } catch (err) {
        findings.push(
          `${e.id}: re-running derived tool \`${cmd}\` failed: ${(err as Error).message.split('\n')[0]}`
        );
        continue;
      }
      const want = new Set(globs);
      const got = new Set(reproduced);
      const missing = [...want].filter((p) => !got.has(p));
      const extra = [...got].filter((p) => !want.has(p));
      if (missing.length > 0 || extra.length > 0) {
        findings.push(
          `${e.id}: derived tool \`${cmd}\` no longer reproduces its declared paths on re-running ` +
            `-- missing [${missing.join(', ')}], extra [${extra.join(', ')}].`
        );
      }
    } else {
      findings.push(
        `${e.id}: pathsOrigin "${origin}" is neither \`'declared'\` nor \`` + 'derived:<tool>`.'
      );
    }
  }
  return findings;
}

function selftest(): number {
  let fail = 0;
  const check = (name: string, ok: boolean): void => {
    if (!ok) fail += 1;
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${name}\n`);
  };
  const run = (
    entries: LockEntry[],
    tracked: string[],
    runDerived: (cmd: string) => string[] = () => []
  ) => pathsOriginFindings(entries, tracked, runDerived);

  check(
    'CONTROL: an entry with neither paths nor pathsOrigin is silent -- the ordinary, unscoped case',
    run([{ id: 'a' }], ['x.ts']).length === 0
  );
  check(
    'paths with no pathsOrigin is a finding',
    run([{ id: 'a', paths: ['x.ts'] }], ['x.ts'])[0]?.includes('no `pathsOrigin`') === true
  );
  check(
    'pathsOrigin with no paths is a finding',
    run([{ id: 'a', pathsOrigin: 'declared' }], ['x.ts'])[0]?.includes('no `paths`') === true
  );
  check(
    'CONTROL: a declared glob matching a tracked file is silent',
    run([{ id: 'a', paths: ['x.ts'], pathsOrigin: 'declared' }], ['x.ts']).length === 0
  );
  check(
    'a declared glob matching nothing tracked is a finding',
    run([{ id: 'a', paths: ['nope.ts'], pathsOrigin: 'declared' }], ['x.ts'])[0]?.includes(
      'matches ZERO tracked files'
    ) === true
  );
  check(
    'CONTROL: a glob-shaped pattern (**/*.ts) still matches via the real matcher, not string equality',
    run([{ id: 'a', paths: ['**/*.ts'], pathsOrigin: 'declared' }], ['deep/nested/x.ts']).length ===
      0
  );
  check(
    'one dead glob among several live ones is still caught -- a union check would hide it',
    run([{ id: 'a', paths: ['x.ts', 'dead.ts'], pathsOrigin: 'declared' }], ['x.ts'])[0]?.includes(
      '`dead.ts`'
    ) === true
  );
  check(
    'an unrecognised pathsOrigin value is a finding',
    run([{ id: 'a', paths: ['x.ts'], pathsOrigin: 'made-up' }], ['x.ts'])[0]?.includes(
      'is neither'
    ) === true
  );

  // THE derived: BRANCH, unreachable on the live tree today -- proven only here.
  check(
    'CONTROL: a derived origin that reproduces exactly is silent',
    run(
      [{ id: 'a', paths: ['x.ts', 'y.ts'], pathsOrigin: 'derived:print-paths' }],
      ['x.ts', 'y.ts'],
      () => ['x.ts', 'y.ts']
    ).length === 0
  );
  check(
    'a derived origin naming no tool is a finding',
    run([{ id: 'a', paths: ['x.ts'], pathsOrigin: 'derived:' }], ['x.ts'])[0]?.includes(
      'names no tool'
    ) === true
  );
  check(
    'a derived origin that now prints something MISSING from its declared set is a finding',
    run(
      [{ id: 'a', paths: ['x.ts', 'y.ts'], pathsOrigin: 'derived:print-paths' }],
      ['x.ts', 'y.ts'],
      () => ['x.ts']
    )[0]?.includes('missing [y.ts]') === true
  );
  check(
    'a derived origin that now prints something EXTRA beyond its declared set is a finding',
    run([{ id: 'a', paths: ['x.ts'], pathsOrigin: 'derived:print-paths' }], ['x.ts'], () => [
      'x.ts',
      'y.ts',
    ])[0]?.includes('extra [y.ts]') === true
  );
  check(
    'a derived tool that fails to re-run is a finding naming the tool, not a thrown exception',
    run([{ id: 'a', paths: ['x.ts'], pathsOrigin: 'derived:broken-tool' }], ['x.ts'], () => {
      throw new Error('command not found');
    })[0]?.includes('re-running derived tool `broken-tool` failed') === true
  );
  check(
    'CONTROL: several clean entries together stay silent -- no cross-entry leakage',
    run(
      [
        { id: 'a', paths: ['x.ts'], pathsOrigin: 'declared' },
        { id: 'b' },
        { id: 'c', paths: ['y.ts'], pathsOrigin: 'declared' },
      ],
      ['x.ts', 'y.ts']
    ).length === 0
  );

  // THE REAL LOCK AND THE REAL TREE, read the way main() reads them. A fixture proving the logic while the tracked file it aims at carries zero real findings would be a control on the function and nothing about the estate.
  if (fs.existsSync(LOCK)) {
    const tracked = execFileSync('git', ['ls-files'], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      maxBuffer: 64 * 1024 * 1024,
    })
      .split('\n')
      .filter(Boolean);
    const entries = readLock();
    const scoped = entries.filter((e) => e.paths !== undefined || e.pathsOrigin !== undefined);
    check(
      `the tracked lock ${LOCK} declares ${scoped.length} paths/pathsOrigin-bearing entry(ies), which must be non-zero`,
      scoped.length > 0
    );
    const real = pathsOriginFindings(entries, tracked, (cmd) =>
      execFileSync('bash', ['-c', cmd], {
        cwd: REPO_ROOT,
        encoding: 'utf-8',
        maxBuffer: 64 * 1024 * 1024,
      })
        .split('\n')
        .filter(Boolean)
    );
    check(
      `the real lock and tree carry zero findings today (saw ${real.length})`,
      real.length === 0
    );
  }

  return fail === 0 ? 0 : 1;
}

function main(): number {
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  const entries = readLock();
  if (entries.length === 0) {
    refuse(
      `${LOCK} declares ZERO entries, so this gate is not seeing the estate and its green would mean nothing.`
    );
  }
  const tracked = execFileSync('git', ['ls-files'], {
    cwd: REPO_ROOT,
    encoding: 'utf-8',
    maxBuffer: 64 * 1024 * 1024,
  })
    .split('\n')
    .filter(Boolean);
  if (tracked.length === 0) {
    refuse(
      `\`git ls-files\` returned nothing from ${REPO_ROOT}, so no glob could be checked against a real corpus.`
    );
  }

  const findings = pathsOriginFindings(entries, tracked, (cmd) =>
    execFileSync('bash', ['-c', cmd], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      maxBuffer: 64 * 1024 * 1024,
    })
      .split('\n')
      .filter(Boolean)
  );
  const scoped = entries.filter((e) => e.paths !== undefined).length;

  // ANTI-VACUITY FLOOR. This gate reports success by finding NOTHING, so a lock that failed to parse, a renamed `paths` key, or a filter that silently matched zero entries all print the same tick as a clean tree. 47 paths-bearing entries exist
  // today; the floor sits well below that rather than at it, because a floor equal to
  // the current count turns every legitimate removal into a failure and teaches people to lower floors.
  if (scoped < MIN_SCOPED_ENTRIES) {
    console.error(
      `✗ VACUOUS: only ${scoped} paths-bearing entry(ies) found in ${path.relative(REPO_ROOT, LOCK)}, ` +
        `below the floor of ${MIN_SCOPED_ENTRIES}. This gate passes by finding nothing, so a corpus ` +
        `this small means the SCAN broke, not that every origin is sound. Refusing rather than ticking.`
    );
    return 1;
  }

  if (findings.length > 0) {
    console.error(
      `✗ paths-origin: ${findings.length} finding(s) across ${scoped} paths-bearing entry(ies):`
    );
    for (const f of findings) console.error(`    ${f}`);
    return 1;
  }
  console.log(
    `✓ paths-origin: ${scoped} paths-bearing entry(ies), all carrying a pathsOrigin that ` +
      `checks out against ${tracked.length} tracked file(s)`
  );
  return 0;
}

process.exit(main());
