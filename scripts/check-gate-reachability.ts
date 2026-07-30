#!/usr/bin/env node
/**
 * Gate: every `check:ci-*` script must actually RUN somewhere.
 *
 * WHY THIS EXISTS. `npm run ci` is a hand-maintained `&&` chain, not an
 * auto-collected list. So adding a gate is two steps that nothing tied
 * together: define `check:ci-foo` in package.json, and remember to append it to
 * the chain. Miss the second and the gate is inert. It looks present, it is
 * greppable, it passes review, and it examines nothing.
 *
 * `check-ci-chain-parity.ts` does not catch this, deliberately. It enforces one
 * direction only, that every gate a WORKFLOW names is reachable from `npm run
 * ci` (its own words: "Workflow subset of ci is required; the reverse is not").
 * Since most gates run in CI only through the aggregate `npm run ci` step, a
 * key that no workflow names individually is invisible to it.
 *
 * This is the same defect class as a gate whose planted-defect selftest sits
 * behind a flag nothing invokes, which shipped in this repo on 2026-07-29 in
 * check-i18n-cross-locale.ts: a check that cannot run is indistinguishable from
 * a check that always passes.
 *
 * REACHABILITY IS TRANSITIVE, and getting that wrong is the trap. Gates
 * legitimately nest: `check:ci-i18n-locale-only` is not in the `ci` string at
 * all, it is invoked by `check:i18n`, which is. A naive substring test over
 * `scripts.ci` reports it as dead and is simply wrong. This walks the graph.
 *
 * An entry in `.ci-chain-exempt` is the sanctioned escape, and it already
 * requires a BLOCKER reason validated elsewhere. Exempt gates are reported, not
 * failed: the file exists to record holes, not to hide them.
 *
 * Usage:
 *   tsx scripts/check-gate-reachability.ts [--skip-control]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const EXEMPT_FILE = '.ci-chain-exempt';
const ROOT_SCRIPT = 'ci';
const GATE_KEY = /^check:ci-/;

/** Every script name reachable from `root` by following `npm run <name>`. */
export function reachableFrom(scripts: Record<string, string>, root: string): Set<string> {
  const seen = new Set<string>();
  const walk = (name: string): void => {
    if (seen.has(name) || !scripts[name]) return;
    seen.add(name);
    // One `npm run <name>` may appear many times in a chain; the Set dedupes.
    for (const m of scripts[name].matchAll(/npm run ([\w:.@/-]+)/g)) walk(m[1]);
  };
  walk(root);
  return seen;
}

/** Gate keys that no path from `npm run ci` ever executes. */
export function unreachableGates(
  scripts: Record<string, string>,
  exemptNames: Set<string>
): string[] {
  const reachable = reachableFrom(scripts, ROOT_SCRIPT);
  return Object.keys(scripts)
    .filter((k) => GATE_KEY.test(k))
    .filter((k) => !reachable.has(k))
    .filter((k) => !exemptNames.has(k))
    .sort();
}

/** Script names and shell paths named in .ci-chain-exempt, comments stripped. */
function readExempt(base: string): Set<string> {
  const p = path.join(base, EXEMPT_FILE);
  if (!fs.existsSync(p)) return new Set();
  return new Set(
    fs
      .readFileSync(p, 'utf8')
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith('#'))
  );
}

/**
 * A gate exempted by SHELL PATH rather than by script name still counts as
 * exempt. `.ci-chain-exempt` lists `.ci/scripts/quality/check-release-state.sh`
 * while package.json calls it `check:ci-release-state`; matching only on the
 * key name would fail a gate the repo has already, deliberately, excused.
 */
function exemptKeyNames(scripts: Record<string, string>, exempt: Set<string>): Set<string> {
  const out = new Set(exempt);
  for (const [key, body] of Object.entries(scripts)) {
    for (const e of exempt) {
      if (e.endsWith('.sh') && body.includes(e)) out.add(key);
    }
  }
  return out;
}

/**
 * CONTROL. Runs the real resolver against a synthetic package whose gate is
 * deliberately unwired, and fails if it is not reported. Same shape as
 * scripts/check-schema-coverage.ts: prove the instrument can fire BEFORE
 * trusting the real pass.
 */
function control(): void {
  const fail = (why: string): never => {
    console.error(`✗ CONTROL FAILED: ${why}`);
    console.error('  This gate cannot be trusted until its own control fires.');
    process.exit(1);
  };

  // 1. It must FIND an unwired gate.
  const planted = {
    ci: 'npm run check:ci-alpha && npm run check:i18n',
    'check:i18n': 'tsx a.ts && npm run check:ci-nested',
    'check:ci-alpha': 'tsx alpha.ts',
    'check:ci-nested': 'tsx nested.ts',
    'check:ci-orphan': 'tsx orphan.ts',
  };
  const found = unreachableGates(planted, new Set());
  if (JSON.stringify(found) !== JSON.stringify(['check:ci-orphan'])) {
    fail(`expected exactly ['check:ci-orphan'], got ${JSON.stringify(found)}`);
  }

  // 2. It must NOT flag a gate reached only through another script. This half
  //    is what a naive substring check over `scripts.ci` gets wrong.
  if (found.includes('check:ci-nested')) fail('transitively reachable gate reported as dead');

  // 3. An exemption must silence it, or the escape hatch does not work.
  if (unreachableGates(planted, new Set(['check:ci-orphan'])).length !== 0) {
    fail('an exempted gate was still reported');
  }

  console.log('  PASS  reports a gate that is defined but never run');
  console.log('  PASS  does not report a gate reached through another script');
  console.log('  PASS  an exemption silences the report');
}

function main(): void {
  const argv = process.argv.slice(2);
  if (!argv.includes('--skip-control')) control();

  const pkgPath = path.join(REPO_ROOT, 'package.json');
  if (!fs.existsSync(pkgPath)) {
    console.error(`✗ Refusing to run: no package.json at ${REPO_ROOT}.`);
    process.exit(1);
  }
  const scripts: Record<string, string> = JSON.parse(fs.readFileSync(pkgPath, 'utf8')).scripts ?? {};
  const gateCount = Object.keys(scripts).filter((k) => GATE_KEY.test(k)).length;
  if (gateCount === 0) {
    // Anti-vacuity: a package with no gates would pass trivially forever.
    console.error('✗ Refusing to run: package.json defines no check:ci-* gates.');
    process.exit(1);
  }

  const exempt = exemptKeyNames(scripts, readExempt(REPO_ROOT));
  const dead = unreachableGates(scripts, exempt);

  if (dead.length > 0) {
    console.error(
      `✗ ${dead.length} gate(s) are defined but never run by \`npm run ci\`:\n\n` +
        dead.map((d) => `    ${d}  =>  ${scripts[d]}`).join('\n') +
        `\n\nA gate that runs nowhere is indistinguishable from one that always passes.\n` +
        `Either append it to the \`ci\` chain in package.json, or add it to\n` +
        `${EXEMPT_FILE} with a BLOCKER reason saying why it cannot run locally.\n`
    );
    process.exit(1);
  }

  console.log(
    `✓ All ${gateCount} check:ci-* gate(s) are reachable from \`npm run ci\` ` +
      `(${exempt.size} exempted).`
  );
}

main();
