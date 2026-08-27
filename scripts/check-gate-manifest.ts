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
  // A GATE IS ALSO SLOW BY CLOSURE, and without this the two oracles here
  // contradict each other. check:ci-client-bundle-budget costs 0.8s ITSELF and
  // 132s through `needs: build:www`: the closure oracle says mark it, the tier
  // oracle then says it is too cheap to be marked. Both are right about
  // different costs, so tier defers to closure -- the number that decides lane
  // membership is what the gate costs to RUN, prerequisites included.
  const slowByClosure = slowByClosureSet(specs);
  for (const spec of specs) {
    const ms = dur[spec.id];
    if (typeof ms !== 'number') continue;
    if (spec.slow === true && ms < BUDGET_MS / SLACK && !slowByClosure.has(spec.id)) {
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

/**
 * TIER CONSISTENCY ALONG `needs`, which is the direction the tier oracle above
 * cannot see. `slow` PROPAGATES: a gate is only as cheap as its prerequisites,
 * because buildGraph pulls them in transitively. So `slow` on B and not-slow on
 * A-needs-B is not two independent claims, it is one claim contradicting
 * itself.
 *
 * The runner already handles this at RUNTIME -- select() computes a fixpoint
 * and demotes A -- but a runtime demotion is discovered by running, and the
 * manifest goes on asserting that A is in the lane. Seven gates were being
 * demoted this way (all needing `build:www`, 131.9s) with nothing in the
 * manifest saying so, and marking a NEW prerequisite slow would silently pull
 * more gates out of the lane with no diff to review.
 *
 * Asserting it here turns the runner's demotion list into an invariant: after
 * this, a demotion at runtime means the manifest and the graph have diverged,
 * which is exactly the condition worth a red.
 */
/**
 * Ids whose `needs` closure reaches a gate marked slow, IGNORING the gate's own
 * marking but honouring its prerequisites'.
 *
 * The first draft derived this by re-running closureFindings over specs with
 * `slow` stripped from ALL of them -- which made nothing slow, so the set came
 * back empty and the interaction control failed. It also parsed the id back out
 * of a human-readable sentence with `.text.split(' ')[0]`, which would have
 * broken silently the first time anyone reworded the message. One traversal,
 * shared by both callers, returning ids.
 */
function slowByClosureSet(specs: readonly GateSpec[]): Set<string> {
  const byId = new Map(specs.map((s) => [s.id, s]));
  const slow = new Set(specs.filter((s) => s.slow === true).map((s) => s.id));
  const out = new Set<string>();
  const walk = (id: string, seen: Set<string>): string | undefined => {
    for (const need of byId.get(id)?.needs ?? []) {
      if (seen.has(need)) continue;
      seen.add(need);
      if (slow.has(need)) return need;
      const deeper = walk(need, seen);
      if (deeper !== undefined) return deeper;
    }
    return undefined;
  };
  for (const spec of specs) if (walk(spec.id, new Set()) !== undefined) out.add(spec.id);
  return out;
}

function closureFindings(specs: readonly GateSpec[]): Finding[] {
  const byId = new Map(specs.map((s) => [s.id, s]));
  const slow = new Set(specs.filter((s) => s.slow === true).map((s) => s.id));
  const via_ = (id: string, seen: Set<string>): string | undefined => {
    for (const need of byId.get(id)?.needs ?? []) {
      if (seen.has(need)) continue;
      seen.add(need);
      if (slow.has(need)) return need;
      const deeper = via_(need, seen);
      if (deeper !== undefined) return deeper;
    }
    return undefined;
  };
  const out: Finding[] = [];
  for (const spec of specs) {
    if (spec.slow === true) continue;
    const via = via_(spec.id, new Set());
    if (via !== undefined) {
      out.push({
        oracle: 'closure',
        text: `${spec.id} is in the pre-push lane but its needs closure reaches slow gate ${via} — it costs that gate's time, so the lane is not what the manifest claims. Mark it \`slow: true\` (the runner already demotes it at runtime).`,
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

  // Closure, both directions AND transitively -- a one-hop-only check would
  // pass the two-hop case, which is the shape that actually occurs.
  const a = spec({ id: 'a', needs: ['b'] });
  const b = spec({ id: 'b', needs: ['c'] });
  const cSlow = spec({ id: 'c', slow: true });
  const cFast = spec({ id: 'c' });
  check('closure: a fast gate needing a slow gate is caught', closureFindings([spec({ id: 'a', needs: ['c'] }), cSlow]).length === 1);
  check('closure: it follows the chain, not just one hop', closureFindings([a, b, cSlow]).length === 2);
  check('closure CONTROL: an all-fast chain passes', closureFindings([a, b, cFast]).length === 0);
  check('closure CONTROL: a slow gate needing a slow gate is not a finding', closureFindings([spec({ id: 'a', needs: ['c'], slow: true }), cSlow]).length === 0);
  check('closure CONTROL: a cycle does not hang the walk', closureFindings([spec({ id: 'a', needs: ['b'] }), spec({ id: 'b', needs: ['a'] })]).length === 0);

  // THE TWO ORACLES MUST NOT CONTRADICT EACH OTHER. This fired live: a gate
  // costing 0.8s itself but 132s through its closure was told to mark itself
  // slow by one oracle and unmark itself by the other.
  check(
    'tier defers to closure: a cheap gate that is slow by closure may stay marked',
    tierFindings([spec({ id: 'a', needs: ['c'], slow: true }), spec({ id: 'c', slow: true })], { a: 800 }).length === 0
  );
  check(
    'tier CONTROL: a cheap gate slow by NOTHING is still caught',
    tierFindings([spec({ id: 'a', slow: true })], { a: 800 }).length === 1
  );


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
    process.stdout.write('check-gate-manifest: selftest ok (19 controls)\n');
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
    ...closureFindings(GATES),
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
