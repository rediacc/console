/**
 * check:ci-gate-bind -- a gate's four registrations must match what its own header says.
 *
 * WHY. Registering a gate means editing package.json, scripts/ci-runner/manifest.ts and
 * .github/workflows/ci-quality.yml by hand, and each has a convention that only ever
 * announces itself as a red gate: a Python gate must be the BARE path in package.json
 * (a `python3` prefix makes check:ci-parity resolve its leaves to `[python3]`), the
 * manifest's leaves must equal what the npm script resolves to and be git-tracked, and
 * the workflow step name must match `ci.step` exactly. The JOB is worse, because it is
 * silent: check:ci-docker-npm-pins landed in quality-static, which checks out no
 * submodules, so the file it exists to scan dropped out of its enumeration and its
 * correct exclusions were reported as dead (CI job 100870135489).
 *
 * All four are derivable from the gate's own header plus lane capabilities read out of
 * the workflow. This is the CHECK half: it re-derives and compares. Nothing is emitted
 * yet, so a mismatch is reported rather than silently rewritten -- the migration is
 * coexist-and-drain, and a gate with no header is simply not this gate's business.
 *
 * ---- gate ----
 * step: Gate binding
 * needs: node
 * why: four hand-written registrations per gate, each with a convention that only
 *      announces itself as a red gate
 * ---- end gate ----
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { laneCapabilities, placeGate, satisfies } from './ci-runner/lanes.js';
import { derivedId, derivedRun, inferredNeeds, parseGateHeader } from './lib/gate-header.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const WORKFLOW = '.github/workflows/ci-quality.yml';
const SUBJECT = /\/(check|test)[-_][\w-]+\.(py|sh|ts)$/;

const read = (rel: string): string => fs.readFileSync(path.join(ROOT, rel), 'utf-8');

const tracked = (): string[] =>
  execFileSync('git', ['-C', ROOT, 'ls-files', '.ci/scripts', 'scripts'], { encoding: 'utf-8' })
    .split('\n')
    .filter((f) => f !== '' && SUBJECT.test(f));

/** Every declared gate: its path, its header, and what convention derives from them. */
export interface Bound {
  file: string;
  id: string;
  run: string;
  step: string;
  needs: string[];
  lane?: string;
}

export function bind(file: string, source: string): Bound | null {
  const h = parseGateHeader(source);
  if (h === null) return null;
  const needs = [...new Set([...h.needs, ...inferredNeeds(source)])].sort();
  return {
    file,
    id: h.id ?? derivedId(file),
    run: h.run ?? derivedRun(file, h.selftest === true),
    step: h.step,
    needs,
    ...(h.lane === undefined ? {} : { lane: h.lane }),
  };
}

/** Does the workflow contain this step name, in this job? */
export function stepInJob(workflow: string, job: string, step: string): boolean {
  const lines = workflow.split('\n');
  let cur = '';
  for (const raw of lines) {
    const m = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(raw);
    if (m) {
      cur = m[1];
      continue;
    }
    if (cur !== job) continue;
    const name = /^\s+-?\s*name:\s*(.+?)\s*$/.exec(raw);
    if (name && name[1].replace(/^["']|["']$/g, '') === step) return true;
  }
  return false;
}

function selftest(): number {
  let bad = 0;
  const ck = (label: string, ok: boolean, detail?: unknown): void => {
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}`);
    if (!ok) {
      bad += 1;
      console.log(`        ${JSON.stringify(detail)}`);
    }
  };

  const py = ['# ---- gate ----', '# step: X', '# needs: none', '# ---- end gate ----'].join('\n');
  const b = bind('.ci/scripts/quality/check_a_b.py', py);
  ck(
    'id and run derive from the path',
    b?.id === 'check:ci-a-b' && b?.run === '.ci/scripts/quality/check_a_b.py',
    b
  );
  ck(
    'an INFERRED need is unioned with the declared ones',
    bind(
      '.ci/scripts/quality/check_a.py',
      `${py}\ngit ls-files --recurse-submodules`
    )?.needs.includes('submodules')
  );
  ck(
    'a file with no header is not this gate’s business',
    bind('x/check-a.py', 'print(1)') === null
  );

  const wf =
    'jobs:\n  quality-code:\n    steps:\n      - name: Gate binding\n        run: x\n  other:\n    steps:\n      - name: Elsewhere\n';
  ck('stepInJob finds a step in its own job', stepInJob(wf, 'quality-code', 'Gate binding'));
  ck('CONTROL: it does NOT find it in a different job', !stepInJob(wf, 'other', 'Gate binding'));
  ck('CONTROL: a step that is not there is not found', !stepInJob(wf, 'quality-code', 'Nope'));
  return bad;
}

function main(argv: string[]): void {
  if (argv.includes('--selftest')) {
    const n = selftest();
    console.log(`${n === 0 ? '✓' : '✗'} gate-bind selftest: ${n} failure(s)`);
    process.exit(n === 0 ? 0 : 1);
  }

  console.log('gate binding: controls first, then the verdict');
  if (selftest() !== 0) {
    console.error('✗ instrument control failed; every verdict below would be meaningless');
    process.exit(2);
  }

  const pkg = JSON.parse(read('package.json')) as { scripts: Record<string, string> };
  const manifest = read('scripts/ci-runner/manifest.ts');
  const workflow = read(WORKFLOW);
  const caps = laneCapabilities(workflow);

  const declared: Bound[] = [];
  for (const f of tracked()) {
    const b = bind(f, read(f));
    if (b !== null) declared.push(b);
  }

  // ANTI-VACUITY. Until the drain lands, "no gate declares a header" is what a broken
  // scan looks like and what a clean tree looks like, and they must not be the same.
  if (declared.length === 0) {
    console.error(
      '✗ VACUOUS: not one tracked gate carries a `---- gate ----` header. Either the ' +
        'parser stopped matching or the declarations were removed; refusing a verdict.'
    );
    process.exit(1);
  }

  const problems: string[] = [];
  for (const b of declared) {
    if (pkg.scripts[b.id] === undefined) {
      problems.push(`${b.file}: declares id '${b.id}', which package.json has no script for`);
    } else if (pkg.scripts[b.id] !== b.run) {
      problems.push(
        `${b.file}: package.json runs "${pkg.scripts[b.id]}" but its header derives "${b.run}"`
      );
    }

    const entry = new RegExp(`id: '${b.id.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}'`).test(
      manifest
    );
    if (!entry) problems.push(`${b.file}: no manifest entry with id '${b.id}'`);

    const placed = placeGate(caps, b.needs);
    const job = b.lane ?? ('lane' in placed ? placed.lane : '');
    if (job === '') {
      problems.push(`${b.file}: ${'error' in placed ? placed.error : 'no lane'}`);
      continue;
    }
    const lane = caps.get(job);
    if (lane === undefined) {
      problems.push(`${b.file}: pinned lane '${job}' is not a job of ${WORKFLOW}`);
      continue;
    }
    if (!satisfies(lane, b.needs)) {
      problems.push(`${b.file}: lane '${job}' does not provide all of ${JSON.stringify(b.needs)}`);
    }
    if (!stepInJob(workflow, job, b.step)) {
      problems.push(`${b.file}: ${WORKFLOW} job '${job}' has no step named "${b.step}"`);
    }
  }

  if (problems.length > 0) {
    console.error(`✗ ${problems.length} binding problem(s):`);
    for (const p of problems) console.error(`    ${p}`);
    for (const line of [
      '',
      '  A gate declares its step and its needs in its own header; the id, the run',
      '  command and the lane are derived. When they disagree with what is registered,',
      '  the registration is what drifted -- fix it there, or correct the header.',
    ]) {
      console.error(line);
    }
    process.exit(1);
  }

  console.log(
    `✓ gate binding: ${declared.length} declared gate(s), each matching its package.json ` +
      'script, its manifest entry, and a workflow step in a lane that provides its needs'
  );
  console.log(
    '  Blind spot: this checks the gates that DECLARE a header. The rest are still ' +
      'registered by hand and are check:ci-parity’s business until the drain reaches them.'
  );
}

main(process.argv.slice(2));
