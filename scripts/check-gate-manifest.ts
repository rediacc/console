#!/usr/bin/env tsx
/**
 * check:ci-gate-manifest -- the ci-runner manifest describes itself honestly.
 *
 * Three oracles over `scripts/ci-runner/manifest.ts`, all mechanical, all
 * offline. They exist because the pre-push lane's whole value rests on the
 * manifest being true about two things nobody re-reads: which gates are cheap,
 * and which files select them.
 *
 * 1. TIER HONESTY, BOTH DIRECTIONS. `slow: true` is a claim about cost, and
 *    `.ci/cache/gate-durations.json` is the measurement. A gate marked slow
 *    that is in fact cheap fails just as loudly as a fast one that is
 *    expensive -- and it is the FIRST direction that needs a gate, because it
 *    is invisible: the push stays fast while the lane quietly covers less. The
 *    other direction announces itself by making every push slower.
 *
 * 2. LEAF SELF-INCLUSION. A gate that declares `paths` but does not include its
 *    OWN implementation cannot be selected by editing itself. Found live: eight
 *    gates, including two whose entire job is testing a script that does not
 *    select them. Mechanical, free, and monotone-safe -- the fix only ever
 *    widens a selection.
 *
 * 3. NON-EMPTY GLOBS. A declared glob matching zero tracked files is dead: it
 *    can only ever exclude. Deliberately NOT the stronger "the regex agrees
 *    with `git ls-files <glob>`" check, because the two genuinely disagree and
 *    the stronger form would assert the wrong side. Measured 2026-08-27:
 *    `**\/*.sh` matches 518 tracked files under the runner's matcher and 516
 *    under git's pathspec, differing on root-level `run.sh` and `rdc.sh`. The
 *    runner's answer is the one that matches what check-shell-size.sh actually
 *    scans (`git ls-files '*.sh'`), so pinning it to git's would be pinning it
 *    to the wrong semantics. Recorded here so the next reader does not
 *    "strengthen" this into a false gate.
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { GATES, type GateSpec } from './ci-runner/manifest';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** The lane's budget. A gate at or above this belongs in the slow tier. */
const BUDGET_MS = 10_000;
/** Hysteresis, so a gate hovering at the line does not flip the gate red on
 *  every measurement. Only a gate that is wrong by a factor is reported. */
const SLACK = 2;

function globToRegExp(glob: string): RegExp {
  const body = glob.replace(/\*\*\/|\*\*|[*?.+^${}()|[\]\\]/g, (token) => {
    if (token === '**/') return '(?:.*/)?';
    if (token === '**') return '.*';
    if (token === '*') return '[^/]*';
    if (token === '?') return '.';
    return `\\${token}`;
  });
  return new RegExp(`^${body}$`);
}

interface Finding {
  oracle: string;
  text: string;
}

function tierFindings(specs: readonly GateSpec[], dur: Record<string, number>): Finding[] {
  const out: Finding[] = [];
  for (const spec of specs) {
    const ms = dur[spec.id];
    if (typeof ms !== 'number') continue;
    if (spec.slow === true && ms < BUDGET_MS / SLACK) {
      out.push({
        oracle: 'tier',
        text: `${spec.id} is marked slow but measures ${(ms / 1000).toFixed(1)}s — cheap enough for the pre-push lane. Drop \`slow: true\`.`,
      });
    }
    if (spec.slow !== true && ms > BUDGET_MS * SLACK) {
      out.push({
        oracle: 'tier',
        text: `${spec.id} is in the pre-push lane but measures ${(ms / 1000).toFixed(1)}s. Mark \`slow: true\` with a one-line reason, or make it faster.`,
      });
    }
  }
  return out;
}

function leafFindings(specs: readonly GateSpec[]): Finding[] {
  const out: Finding[] = [];
  for (const spec of specs) {
    if (spec.paths === undefined) continue; // no paths = always selected = fine
    for (const leaf of spec.leaves) {
      if (!leaf.includes('/')) continue; // an npm key, not a file
      if (!spec.paths.some((g) => globToRegExp(g).test(leaf))) {
        out.push({
          oracle: 'leaf',
          text: `${spec.id} declares paths but not its own leaf ${leaf} — editing the gate does not select the gate.`,
        });
      }
    }
  }
  return out;
}

function globFindings(specs: readonly GateSpec[], tracked: readonly string[]): Finding[] {
  const out: Finding[] = [];
  for (const spec of specs) {
    for (const g of spec.paths ?? []) {
      const re = globToRegExp(g);
      if (!tracked.some((f) => re.test(f))) {
        out.push({
          oracle: 'glob',
          text: `${spec.id} declares \`${g}\`, which matches no tracked file. A glob that matches nothing can only exclude.`,
        });
      }
    }
  }
  return out;
}

/** CONTROL-FIRST. Each oracle is run against a planted defect and must find it,
 *  and against a clean fixture and must not. A gate whose green has never been
 *  contrasted with a red is not evidence. */
function selftest(tracked: readonly string[]): number {
  let bad = 0;
  const check = (label: string, cond: boolean): void => {
    if (cond) process.stdout.write(`  PASS  ${label}\n`);
    else {
      bad += 1;
      process.stdout.write(`  FAIL  ${label}\n`);
    }
  };
  const spec = (over: Partial<GateSpec>): GateSpec =>
    ({
      id: 'x',
      run: 'true',
      gate: true,
      leaves: ['.ci/x.sh'],
      ci: { kind: 'local-only', blocker: 'BLOCKER: selftest fixture' },
      ...over,
    }) as GateSpec;

  check('tier: a slow-marked gate that is cheap is caught', tierFindings([spec({ slow: true })], { x: 100 }).length === 1);
  check('tier CONTROL: a slow-marked gate that IS slow passes', tierFindings([spec({ slow: true })], { x: 60_000 }).length === 0);
  check('tier: a fast-lane gate that is expensive is caught', tierFindings([spec({})], { x: 60_000 }).length === 1);
  check('tier CONTROL: a fast-lane gate that IS fast passes', tierFindings([spec({})], { x: 100 }).length === 0);
  check('tier CONTROL: an unmeasured gate is not judged', tierFindings([spec({ slow: true })], {}).length === 0);

  check('leaf: a gate excluding its own leaf is caught', leafFindings([spec({ paths: ['other/**'] })]).length === 1);
  check('leaf CONTROL: a gate including its own leaf passes', leafFindings([spec({ paths: ['.ci/**'] })]).length === 0);
  check('leaf CONTROL: a gate with NO paths is out of scope', leafFindings([spec({})]).length === 0);

  check('glob: a glob matching nothing is caught', globFindings([spec({ paths: ['no/such/dir/**'] })], tracked).length === 1);
  check('glob CONTROL: a glob matching something passes', globFindings([spec({ paths: ['.ci/**'] })], tracked).length === 0);
  check(
    'glob CONTROL: the tracked list is real, or every glob would look dead',
    tracked.length > 500
  );

  // The `**/` semantics this file deliberately does NOT gate on, pinned so the
  // comment above cannot rot into a claim nobody can check.
  check('the runner matcher treats **/ as zero-or-more dirs', globToRegExp('**/*.sh').test('run.sh'));
  return bad;
}

function main(): number {
  const tracked = execFileSync('git', ['ls-files'], {
    cwd: REPO,
    encoding: 'utf-8',
    maxBuffer: 64 * 1024 * 1024,
  })
    .split('\n')
    .filter(Boolean);

  if (process.argv.slice(2).includes('--selftest')) {
    const bad = selftest(tracked);
    if (bad > 0) {
      process.stderr.write('CONTROL FAILED: check-gate-manifest oracles did not fire\n');
      return 1;
    }
    process.stdout.write('check-gate-manifest: selftest ok (12 controls)\n');
    return 0;
  }

  let dur: Record<string, number> = {};
  try {
    dur = JSON.parse(fs.readFileSync(path.join(REPO, '.ci', 'cache', 'gate-durations.json'), 'utf-8'));
  } catch {
    // NOT fatal, and NOT silent. The cache is written by real runs, so a fresh
    // clone has none and the tier oracle simply has nothing to say yet. Saying
    // so is the difference between "no findings" and "did not look".
    process.stdout.write('- tier oracle: no duration cache yet, so cost claims are unjudged\n');
  }

  const findings = [
    ...tierFindings(GATES, dur),
    ...leafFindings(GATES),
    ...globFindings(GATES, tracked),
  ];

  if (findings.length === 0) {
    process.stdout.write(
      `✓ gate manifest: ${GATES.length} entries, ${Object.keys(dur).length} measured; tiers, leaves and globs all agree\n`
    );
    return 0;
  }
  process.stderr.write(`✗ ${findings.length} gate-manifest finding(s):\n\n`);
  for (const f of findings) process.stderr.write(`  [${f.oracle}] ${f.text}\n`);
  process.stderr.write('\n');
  return 1;
}

process.exitCode = main();
