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
 * selftest: true
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
/**
 * EVERY tracked script, not just conventionally-named ones.
 *
 * This was `/(check|test)[-_][\w-]+\.(py|sh|ts)$/`, a naming heuristic standing in for
 * correctness. `--extract check:ci-shell-format` wrote a valid header into
 * .ci/scripts/security/shfmt.sh -- which matches no such name -- and this gate then
 * reported "2 declared gate(s)" and a clean bill of health while ignoring the third
 * entirely. A declaration that is silently not read is worse than one that is rejected.
 *
 * `bind()` returns null for a file with no header, so the filter costs a read per file
 * and buys the guarantee that a header anywhere is a header that counts.
 */
const SUBJECT = /\.(py|sh|ts)$/;

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

const OPEN_RE = /^\s*# >>> gate-bind\b/;
const CLOSE_RE = /^\s*# <<< gate-bind\s*$/;

/**
 * The emitted step for one gate, in the shape every hand-written gate step already has.
 *
 * The `if:` guard is not optional decoration: 189 of the 258 steps in ci-quality.yml
 * carry it, and a gate step without it runs after its own job's setup has failed and
 * reports a confusing second failure instead of the real one.
 */
export function emitStep(b: Bound): string[] {
  return [
    `      - name: ${b.step}`,
    "        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}",
    `        run: ${b.run.startsWith('tsx ') ? `npm run ${b.id}` : b.run}`,
  ];
}

/**
 * Replace each lane's gate-bind region with the steps its gates derive to.
 *
 * REGION-SCOPED, and the prose inside the opening marker is PRESERVED: the marker block
 * explains itself to whoever opens the file, and a generator that ate its own
 * explanation every run would train people to stop reading it.
 */
export function rewriteRegions(
  workflow: string,
  byLane: Map<string, Bound[]>
): { text: string; lanes: string[] } {
  const lines = workflow.split('\n');
  const out: string[] = [];
  const touched: string[] = [];
  let job = '';
  let i = 0;
  while (i < lines.length) {
    const raw = lines[i];
    const m = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(raw);
    if (m) job = m[1];
    if (!OPEN_RE.test(raw)) {
      out.push(raw);
      i += 1;
      continue;
    }
    // keep the marker and its explanatory comment lines, drop the emitted steps
    out.push(raw);
    i += 1;
    while (i < lines.length && /^\s*#/.test(lines[i]) && !CLOSE_RE.test(lines[i])) {
      out.push(lines[i]);
      i += 1;
    }
    for (const b of (byLane.get(job) ?? []).slice().sort((a, z) => a.step.localeCompare(z.step))) {
      out.push(...emitStep(b));
    }
    while (i < lines.length && !CLOSE_RE.test(lines[i])) i += 1;
    if (i < lines.length) {
      out.push(lines[i]);
      i += 1;
    }
    touched.push(job);
  }
  return { text: out.join('\n'), lanes: touched };
}

/** What the manifest already says about a hand-registered gate. */
export interface Registered {
  file: string;
  step: string;
  job: string;
  /** The `//` prose above the entry. This IS the `why:`, so extraction loses nothing. */
  why: string[];
}

export function registered(manifest: string, id: string): Registered | { error: string } {
  // Padded so the FIRST entry in the file is bounded like every other one: without this
  // the backward search for `\n  {` finds nothing at offset 0 and the entry reads as
  // unbounded. Caught by this gate's own fixture, which is exactly that shape.
  const text = `\n${manifest}\n`;
  const at = text.indexOf(`id: '${id}'`);
  if (at === -1) return { error: `no manifest entry with id '${id}'` };
  const start = text.lastIndexOf('\n  {\n', at);
  const end = text.indexOf('\n  },\n', at);
  if (start === -1 || end === -1) return { error: `could not bound the entry for '${id}'` };
  const block = text.slice(start, end);
  const field = (k: string): string => new RegExp(`\\b${k}: '([^']*)'`).exec(block)?.[1] ?? '';
  const file = /leaves: \[\s*'([^']+)'/.exec(block)?.[1] ?? '';
  // Only the prose ABOVE `id:`. A comment further down explains a later field.
  const head = block.slice(0, block.indexOf('id:'));
  const why = head
    .split('\n')
    .filter((l) => /^\s*\/\//.test(l))
    .map((l) => l.replace(/^\s*\/\/\s?/, '').trimEnd());
  const out: Registered = { file, step: field('step'), job: field('job'), why };
  if (out.file === '' || out.step === '' || out.job === '') {
    return { error: `entry '${id}' is missing leaves, ci.step or ci.job` };
  }
  return out;
}

/** The header body, unprefixed. The caller decides how each language carries a comment. */
export function headerLines(
  r: Registered,
  needs: string[],
  pinLane: boolean,
  id?: string
): string[] {
  const out = [
    '---- gate ----',
    `step: ${r.step}`,
    `needs: ${needs.length ? needs.join(', ') : 'none'}`,
  ];
  // `id:` is an OVERRIDE, emitted only where the path does not imply the registered id:
  // .ci/scripts/security/shfmt.sh derives check:ci-shfmt and is registered as
  // check:ci-shell-format. 308 of 378 ids need no override, and writing one into all of
  // them would turn a convention into 378 restatements of itself.
  if (id !== undefined && derivedId(r.file) !== id) out.push(`id: ${id}`);
  if (pinLane) out.push(`lane: ${r.job}`);
  if (r.why.length > 0) {
    out.push(`why: ${r.why[0]}`);
    for (const line of r.why.slice(1)) out.push(`     ${line}`);
  }
  out.push('---- end gate ----');
  return out;
}

/**
 * Put the header where the file already keeps its prose, so extraction reads as
 * documentation rather than as a machine stamp: a Python module docstring, a shell
 * comment block under the shebang, a TypeScript block comment. Falls back to a
 * standalone line-comment block, which the parser accepts in every one of them.
 */
export function insertHeader(
  file: string,
  source: string,
  body: string[]
): string | { error: string } {
  if (parseGateHeader(source) !== null) return { error: 'already declares a header' };
  const lines = source.split('\n');

  if (file.endsWith('.py')) {
    const open = lines.findIndex((l) => /^\s*(?:[rub]*)"""/.test(l));
    if (open !== -1) {
      const close = lines.findIndex((l, i) => i > open && l.includes('"""'));
      if (close !== -1) {
        const at = lines[close].trim() === '"""' ? close : close;
        return [...lines.slice(0, at), '', ...body, ...lines.slice(at)].join('\n');
      }
    }
  }
  if (file.endsWith('.ts') && lines[0]?.startsWith('/**')) {
    const close = lines.findIndex((l) => l.trim() === '*/');
    if (close !== -1) {
      return [
        ...lines.slice(0, close),
        ' *',
        ...body.map((l) => ` * ${l}`),
        ...lines.slice(close),
      ].join('\n');
    }
  }
  // Fallback, and the normal path for .sh: a comment block under the shebang.
  const after = lines[0]?.startsWith('#!') ? 1 : 0;
  return [...lines.slice(0, after), ...body.map((l) => `# ${l}`), '', ...lines.slice(after)].join(
    '\n'
  );
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
  // Both controls below are regressions, found by wiring ONE gate through this binder.
  // Each mis-inference is silent: it does not fail, it moves the gate to a fatter lane.
  ck(
    'CONTROL: private/account named in PROSE infers nothing (a comment is not code)',
    !bind(
      '.ci/scripts/quality/check_a.py',
      `${py}\n# explains a defect in private/account/Dockerfile\nx = 1`
    )?.needs.includes('submodules')
  );
  ck(
    'CONTROL: a variable named `node` is not a node runtime',
    !bind(
      '.ci/scripts/quality/check_a.py',
      `${py}\nfor node in ast.walk(t):\n    pass`
    )?.needs.includes('node')
  );
  ck(
    'CONTROL: but an actual `node script.js` invocation still is',
    bind('.ci/scripts/quality/check_a.sh', `${py}\nnode scripts/x.js`)?.needs.includes('node')
  );
  const MANIFEST_FIXTURE = [
    '  {',
    '    // why it exists, line one',
    '    // and line two',
    "    id: 'check:ci-a-b',",
    "    leaves: ['.ci/scripts/quality/check_a_b.py'],",
    '    ci: {',
    "      kind: 'step',",
    "      job: 'quality-static',",
    "      step: 'A B',",
    '    },',
    '  },',
    '',
  ].join('\n');
  const reg = registered(MANIFEST_FIXTURE, 'check:ci-a-b');
  ck(
    'a manifest entry yields its file, step, job and the prose above it',
    !('error' in reg) &&
      reg.file === '.ci/scripts/quality/check_a_b.py' &&
      reg.step === 'A B' &&
      reg.job === 'quality-static' &&
      reg.why.join('|') === 'why it exists, line one|and line two',
    reg
  );
  ck(
    'CONTROL: an id the manifest does not carry is an error, not an empty entry',
    'error' in registered(MANIFEST_FIXTURE, 'check:ci-nope')
  );
  ck(
    'an extracted header round-trips: what it derives is what was registered',
    (() => {
      if ('error' in reg) return false;
      const doc = `"""Doc.\n\nMore.\n"""\nx = 1\n`;
      const next = insertHeader(
        '.ci/scripts/quality/check_a_b.py',
        doc,
        headerLines(reg, [], false)
      );
      if (typeof next !== 'string') return false;
      const b2 = bind('.ci/scripts/quality/check_a_b.py', next);
      return b2?.id === 'check:ci-a-b' && b2?.step === 'A B';
    })()
  );
  ck(
    'an id the path does not imply is emitted as an explicit override',
    headerLines(
      { file: '.ci/scripts/security/shfmt.sh', step: 'S', job: 'q', why: [] },
      [],
      false,
      'check:ci-shell-format'
    ).includes('id: check:ci-shell-format')
  );
  ck(
    'CONTROL: an id the path DOES imply is left to the convention',
    !headerLines(
      { file: '.ci/scripts/quality/check_a_b.py', step: 'S', job: 'q', why: [] },
      [],
      false,
      'check:ci-a-b'
    ).some((l) => l.startsWith('id:'))
  );
  ck(
    'CONTROL: extracting into a file that already declares one is refused',
    typeof insertHeader('.ci/scripts/quality/check_a_b.py', py, ['---- gate ----']) !== 'string'
  );
  ck(
    'a shell script carries the header as # comments under its shebang',
    (() => {
      const r2 = { file: 'x', step: 'A B', job: 'quality-static', why: [] };
      const next = insertHeader(
        '.ci/scripts/quality/check-a-b.sh',
        '#!/usr/bin/env bash\nset -e\n',
        headerLines(r2, [], false)
      );
      return (
        typeof next === 'string' && next.startsWith('#!') && parseGateHeader(next)?.step === 'A B'
      );
    })()
  );
  ck(
    'CONTROL: a header in a file the naming convention does not cover is still bound',
    bind('.ci/scripts/security/shfmt.sh', `${py}`) !== null
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

  const b2: Bound = {
    file: 'x/check_a.py',
    id: 'check:ci-a',
    run: 'x/check_a.py',
    step: 'A',
    needs: [],
  };
  ck(
    'an emitted step carries the if: guard 189 of 258 steps already have',
    emitStep(b2)[1].includes("!cancelled() && steps.setup.outcome == 'success'"),
    emitStep(b2)
  );
  ck(
    'a .ts gate is emitted as `npm run <id>`, a script as its bare path',
    emitStep({ ...b2, run: 'tsx x/check-a.ts' })[2].trim() === 'run: npm run check:ci-a' &&
      emitStep(b2)[2].trim() === 'run: x/check_a.py'
  );

  const region = [
    'jobs:',
    '  quality-static:',
    '    steps:',
    '      # >>> gate-bind (generated)',
    '      # explanatory prose',
    '      - name: STALE',
    '        run: old',
    '      # <<< gate-bind',
    '      - name: hand-written after',
  ].join('\n');
  const rw = rewriteRegions(region, new Map([['quality-static', [b2]]]));
  ck(
    'rewriting replaces the region body but KEEPS its prose',
    rw.text.includes('# explanatory prose') &&
      !rw.text.includes('STALE') &&
      rw.text.includes('- name: A'),
    rw.text
  );
  ck(
    'and leaves hand-written steps outside it alone',
    rw.text.includes('- name: hand-written after')
  );
  ck(
    'rewriting is IDEMPOTENT -- the second pass changes nothing',
    rewriteRegions(rw.text, new Map([['quality-static', [b2]]])).text === rw.text
  );
  return bad;
}

function main(argv: string[]): void {
  const write = argv.includes('--write');
  if (argv.includes('--selftest')) {
    const n = selftest();
    console.log(`${n === 0 ? '✓' : '✗'} gate-bind selftest: ${n} failure(s)`);
    process.exit(n === 0 ? 0 : 1);
  }

  const exAt = argv.indexOf('--extract');
  if (exAt !== -1) {
    const id = argv[exAt + 1];
    if (id === undefined || id.startsWith('--')) {
      console.error('✗ --extract needs a gate id, e.g. --extract check:ci-shell-format');
      process.exit(1);
    }
    const reg = registered(read('scripts/ci-runner/manifest.ts'), id);
    if ('error' in reg) {
      console.error(`✗ ${reg.error}`);
      process.exit(1);
    }
    const src = read(reg.file);
    const needs = inferredNeeds(src);
    // PIN THE LANE ONLY WHEN THE INFERENCE DISAGREES. Emitting `lane:` unconditionally
    // would freeze today's placement into 129 files and make the derivation decorative.
    const placed = placeGate(laneCapabilities(read(WORKFLOW)), needs);
    const pinLane = !('lane' in placed) || placed.lane !== reg.job;
    const next = insertHeader(reg.file, src, headerLines(reg, needs, pinLane, id));
    if (typeof next !== 'string') {
      console.error(`✗ ${reg.file}: ${next.error}`);
      process.exit(1);
    }
    // THE EXTRACTION MUST ROUND-TRIP. A header that re-derives something OTHER than what
    // is registered would move the gate silently, which is the class this tool closes.
    const rb = bind(reg.file, next);
    if (rb === null || rb.id !== id || rb.step !== reg.step) {
      const got = rb === null ? 'nothing' : `${rb.id} / "${rb.step}"`;
      console.error(
        `✗ ${reg.file}: emitted header re-derives ${got}, not ${id} / "${reg.step}". Not written.`
      );
      process.exit(1);
    }
    fs.writeFileSync(path.join(ROOT, reg.file), next);
    console.log(`✓ ${reg.file} now declares its own binding (step "${reg.step}", lane ${reg.job})`);
    console.log('  Re-run with no flags to confirm it still matches its registration.');
    process.exit(0);
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

  if (write) {
    const byLane = new Map<string, Bound[]>();
    for (const b of declared) {
      const placed = placeGate(caps, b.needs);
      const job = b.lane ?? ('lane' in placed ? placed.lane : '');
      if (job === '') {
        console.error(`✗ ${b.file}: ${'error' in placed ? placed.error : 'no lane'}`);
        process.exit(1);
      }
      byLane.set(job, [...(byLane.get(job) ?? []), b]);
    }
    const { text, lanes } = rewriteRegions(workflow, byLane);
    // EVERY LANE WITH GATES MUST HAVE A REGION. Emitting into a file that has none
    // would silently drop the step and report success -- the vacuity shape again.
    const missing = [...byLane.keys()].filter((j) => !lanes.includes(j));
    if (missing.length > 0) {
      console.error(
        `✗ no \`# >>> gate-bind\` region in ${missing.join(', ')}. Place one by hand ` +
          "after that lane's setup steps; the binder never moves a region."
      );
      process.exit(1);
    }
    if (text === workflow) {
      console.log(`gate-bind --write: ${WORKFLOW} already matches (${declared.length} gate(s))`);
    } else {
      fs.writeFileSync(path.join(ROOT, WORKFLOW), text);
      console.log(`gate-bind --write: rewrote ${lanes.length} region(s) in ${WORKFLOW}`);
    }
    return;
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
