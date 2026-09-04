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
 *      announces itself as a red gate. The binder declares itself through the same
 *      header it reads, so the first thing it verifies is that IT is registered right
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

/**
 * ...but NOT the gate-test tree. Two reasons, and the second is the load-bearing one:
 *
 *   1. .ci/scripts/test/gates/test-gate-header.sh carries a sample header as FIXTURE
 *      data -- quoted array elements it feeds to the parser. Widening SUBJECT read it
 *      as a real declaration for `step: Dockerfile npm pins',` (trailing quote included).
 *      Same class as the heredoc false positive already recorded in
 *      scripts/check-enumeration-vacuity.ts: a quoted body is data, not code.
 *   2. All 132 gate-tests share the single step 'Quality-gate unit tests'. None of them
 *      owns a step, so none of them can legitimately declare one -- see the shared-step
 *      guard in --extract. Excluding the tree states that once instead of per file.
 */
const NOT_SUBJECT = /\/test\/gates\//;

const read = (rel: string): string => fs.readFileSync(path.join(ROOT, rel), 'utf-8');

const tracked = (): string[] =>
  execFileSync('git', ['-C', ROOT, 'ls-files', '.ci/scripts', 'scripts'], { encoding: 'utf-8' })
    .split('\n')
    .filter((f) => f !== '' && SUBJECT.test(f) && !NOT_SUBJECT.test(f));

/** One extraction attempt: every guard, no I/O decision. `next` is null when refused. */
export function planExtract(
  manifestText: string,
  id: string,
  readFile: (f: string) => string,
  pkgRun: string,
  caps: ReturnType<typeof laneCapabilities>,
  strip: boolean
): { file: string; next: string; step: string; job: string } | { error: string } {
  const reg = registered(manifestText, id);
  if ('error' in reg) return { error: reg.error };
  if (!inScope(reg.file)) {
    return {
      error: `${reg.file} is outside the scan (.ci/scripts, scripts); stays hand-registered`,
    };
  }
  const sharers = (
    manifestText.match(
      new RegExp(`step: '${reg.step.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}'`, 'g')
    ) ?? []
  ).length;
  if (sharers > 1) {
    return { error: `step "${reg.step}" is shared by ${sharers} entries; no one gate owns it` };
  }
  reg.run = pkgRun;
  let src: string;
  try {
    src = readFile(reg.file);
  } catch {
    return { error: `${reg.file} could not be read` };
  }
  if (strip) src = stripHeader(src);
  const needs = inferredNeeds(src);
  const placed = placeGate(caps, needs);
  const pinLane = !('lane' in placed) || placed.lane !== reg.job;
  const next = insertHeader(reg.file, src, headerLines(reg, needs, pinLane, id));
  if (typeof next !== 'string') return { error: `${reg.file}: ${next.error}` };
  const rb = bind(reg.file, next);
  const runOk = reg.run === '' || rb?.run === reg.run;
  if (rb === null || rb.id !== id || rb.step !== reg.step || !runOk) {
    const got = rb === null ? 'nothing' : `${rb.id} / "${rb.step}" / ${rb.run}`;
    return { error: `${reg.file}: header re-derives ${got}, not ${id} / "${reg.step}"` };
  }
  return { file: reg.file, next, step: reg.step, job: reg.job };
}

/** Every gate id the manifest declares, in file order. */
export const manifestIds = (manifestText: string): string[] => [
  ...new Set((manifestText.match(/id: '([^']+)'/g) ?? []).map((m) => m.slice(5, -1))),
];

/** The paths this gate reads, so `--extract` can refuse to write outside them. */
export const inScope = (f: string): boolean =>
  /^(\.ci\/scripts|scripts)\//.test(f) && SUBJECT.test(f) && !NOT_SUBJECT.test(f);

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
/**
 * Is the lane's `# >>> gate-bind` region placed AFTER that lane's `- id: setup` step?
 *
 * Every emitted step guards on `steps.setup.outcome == 'success'`. A region placed above
 * that step references a step that has not run: the expression evaluates empty, every
 * gate in the region SKIPS, and the job reports green having run none of them. That is
 * the worst shape a CI change can take, and it is invisible in a diff -- the steps are
 * all there, correctly written, in the wrong place.
 *
 * Placed once per lane by hand, so checked once per lane here.
 */
export function regionAfterSetup(workflow: string, job: string): boolean {
  const lines = workflow.split('\n');
  const j = lines.findIndex((l) => l.trim() === `${job}:`);
  if (j === -1) return true;
  const nextJob = lines.findIndex((l, i) => i > j && /^  [a-z][a-z0-9-]*:$/.test(l));
  const end = nextJob === -1 ? lines.length : nextJob;
  const setup = lines.findIndex((l, i) => i > j && i < end && l.trim() === '- id: setup');
  const region = lines.findIndex(
    (l, i) => i > j && i < end && l.trim().startsWith('# >>> gate-bind')
  );
  if (setup === -1 || region === -1) return true;
  return region > setup;
}

/**
 * How many times does this step name appear in this job?
 *
 * A gate that becomes DECLARED gets its step emitted inside the lane's region -- but its
 * original hand-written step is still sitting further down the same job. `stepInJob` only
 * asks whether the step EXISTS, so both copies pass it, and the gate then runs twice per
 * CI job: silent, green, and paid for on every run. With 174 gates extractable in one
 * command, this is the difference between a migration and 174 duplicated steps.
 */
export function stepCountInJob(workflow: string, job: string, step: string): number {
  const lines = workflow.split('\n');
  const j = lines.findIndex((l) => l.trim() === `${job}:`);
  if (j === -1) return 0;
  const nextJob = lines.findIndex((l, i) => i > j && /^  [a-z][a-z0-9-]*:$/.test(l));
  const end = nextJob === -1 ? lines.length : nextJob;
  return lines.slice(j, end).filter((l) => l.trim() === `- name: ${step}`).length;
}

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
/**
 * A DECLARED NEED IS ACQUIRED, not merely used to pick a lane.
 *
 * check_git_history_depth.py declares `needs: python-yaml`, and placement duly sent it to
 * quality-static -- the only lane that installs PyYAML. But that lane installs it INSIDE
 * each step's own `run` block, and the gate-bind region sits above all of them, so the
 * emitted step ran before any install existed. check:ci-python-gate-deps caught it: a
 * script importing yaml in a job whose earlier steps never name it dies with
 * ModuleNotFoundError on a clean runner and passes on any machine that happens to have
 * the module. The lane answers WHERE; this answers WITH WHAT.
 */
const ACQUIRE: Record<string, string[]> = {
  'python-yaml': [
    '          python3 -m pip install --user --disable-pip-version-check "PyYAML==${PYYAML_VERSION}"',
    '          python3 -c "import yaml; print(\'PyYAML\', yaml.__version__)"',
  ],
};

export function emitStep(b: Bound): string[] {
  const cmd = b.run.startsWith('tsx ') ? `npm run ${b.id}` : b.run;
  const acquire = b.needs.flatMap((n) => ACQUIRE[n] ?? []);
  const head = [
    `      - name: ${b.step}`,
    "        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}",
  ];
  if (acquire.length === 0) return [...head, `        run: ${cmd}`];
  return [...head, '        run: |', ...acquire, `          ${cmd}`];
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
  /** package.json's script body -- the real command. The manifest only holds `npm run <id>`. */
  run: string;
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
  const out: Registered = { file, step: field('step'), job: field('job'), run: '', why };
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
  // `run:` likewise. Three registered shapes do not derive: `tsx X --selftest` alone,
  // `tsx X --selftest && tsx X`, and `tsx X && tsx <a different control file>`. The
  // second is `selftest: true`; the other two are genuinely per-gate, and inventing
  // derivation rules for them would encode five gates' habits as a convention.
  const wanted = r.run ?? '';
  if (wanted !== '' && wanted === derivedRun(r.file, true)) {
    out.push('selftest: true');
  } else if (wanted !== '' && wanted !== derivedRun(r.file)) {
    out.push(`run: ${wanted}`);
  }
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
/**
 * Remove a declared header, so `--rebind` can re-emit one that matches a registration
 * that has since moved. Without it the only repair for a header written wrong is a hand
 * edit, which is the thing this tool exists to stop asking for.
 */
export function stripHeader(source: string): string {
  const lines = source.split('\n');
  const open = lines.findIndex((l) => /^\s*(?:#|\/\/|\*)?\s*-{2,}\s*gate\s*-{2,}\s*$/.test(l));
  if (open === -1) return source;
  const close = lines.findIndex((l, i) => i > open && /-{2,}\s*end gate\s*-{2,}\s*$/.test(l));
  if (close === -1) return source;
  const rest = lines.slice(close + 1);
  // The blank line the emitter added after the block goes with it.
  if (rest[0] === '' || rest[0]?.trim() === '*') rest.shift();
  return [...lines.slice(0, open), ...rest].join('\n');
}

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
  // A JS/TS FILE NEVER TAKES THE `#` FALLBACK. `#` is a comment in Python and shell and
  // a SYNTAX ERROR in TypeScript, and the fallback reached eight scripts that open with
  // `#!/usr/bin/env node`: the block-comment branch wanted `/**` on line 0, the shebang
  // is on line 0, so each was written with `# ` and stopped parsing. They are all
  // `tsx`-invoked gates, so the breakage was total and immediate.
  const js = /\.(ts|js|cjs|mjs)$/.test(file);
  const after = lines[0]?.startsWith('#!') ? 1 : 0;
  if (js) {
    if (lines[after]?.startsWith('/**')) {
      const close = lines.findIndex((l, i) => i > after && l.trim() === '*/');
      if (close !== -1) {
        return [
          ...lines.slice(0, close),
          ' *',
          ...body.map((l) => ` * ${l}`),
          ...lines.slice(close),
        ].join('\n');
      }
    }
    return [
      ...lines.slice(0, after),
      ...body.map((l) => `// ${l}`),
      '',
      ...lines.slice(after),
    ].join('\n');
  }
  // The normal path for .sh, and the fallback for anything else that takes `#`.
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
    )?.needs.includes('submodules') === true
  );
  // Both controls below are regressions, found by wiring ONE gate through this binder.
  // Each mis-inference is silent: it does not fail, it moves the gate to a fatter lane.
  ck(
    'CONTROL: private/account named in PROSE infers nothing (a comment is not code)',
    !bind(
      '.ci/scripts/quality/check_a.py',
      `${py}\n# explains a defect in private/account/Dockerfile\nx = 1`
    )?.needs.includes('submodules') === true
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
    bind('.ci/scripts/quality/check_a.sh', `${py}\nnode scripts/x.js`)?.needs.includes('node') ===
      true
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
      reg.run === '' &&
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
      { file: '.ci/scripts/security/shfmt.sh', step: 'S', job: 'q', run: '', why: [] },
      [],
      false,
      'check:ci-shell-format'
    ).includes('id: check:ci-shell-format')
  );
  ck(
    'CONTROL: an id the path DOES imply is left to the convention',
    !headerLines(
      { file: '.ci/scripts/quality/check_a_b.py', step: 'S', job: 'q', run: '', why: [] },
      [],
      false,
      'check:ci-a-b'
    ).some((l) => l.startsWith('id:'))
  );
  ck(
    'stripHeader removes a declared block and leaves the rest intact',
    (() => {
      const withHdr = insertHeader(
        'scripts/check-a.ts',
        '#!/usr/bin/env node\nexport const x = 1;\n',
        ['---- gate ----', 'step: A', '---- end gate ----']
      );
      if (typeof withHdr !== 'string') return false;
      const back = stripHeader(withHdr);
      return parseGateHeader(back) === null && back.includes('export const x = 1;');
    })()
  );
  ck(
    'CONTROL: stripHeader leaves a file with no header alone',
    stripHeader('const x = 1;\n') === 'const x = 1;\n'
  );
  ck(
    'CONTROL: extracting into a file that already declares one is refused',
    typeof insertHeader('.ci/scripts/quality/check_a_b.py', py, ['---- gate ----']) !== 'string'
  );
  ck(
    'a shell script carries the header as # comments under its shebang',
    (() => {
      const r2 = { file: 'x', step: 'A B', job: 'quality-static', run: '', why: [] };
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
    'a .ts file with a SHEBANG gets // comments, never #, and still parses',
    (() => {
      const r2 = { file: 'scripts/check-a.ts', step: 'A', job: 'q', run: '', why: [] };
      const next = insertHeader(
        'scripts/check-a.ts',
        '#!/usr/bin/env node\nexport const x = 1;\n',
        headerLines(r2, [], false)
      );
      return (
        typeof next === 'string' &&
        !next.includes('# ---- gate ----') &&
        next.includes('// ---- gate ----') &&
        parseGateHeader(next)?.step === 'A'
      );
    })()
  );
  ck(
    'CONTROL: a .sh file still gets # comments',
    (() => {
      const r2 = { file: '.ci/scripts/quality/check-a.sh', step: 'A', job: 'q', run: '', why: [] };
      const next = insertHeader(
        '.ci/scripts/quality/check-a.sh',
        '#!/usr/bin/env bash\nset -e\n',
        headerLines(r2, [], false)
      );
      return typeof next === 'string' && next.includes('# ---- gate ----');
    })()
  );
  ck(
    'a gate-test is out of scope: its header is fixture data and it owns no step',
    NOT_SUBJECT.test('.ci/scripts/test/gates/test-gate-header.sh')
  );
  ck(
    'CONTROL: a real gate under .ci/scripts is still in scope',
    !NOT_SUBJECT.test('.ci/scripts/quality/check_environment_names.py')
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
  const WF_OK = [
    '  a:',
    '    steps:',
    '      - id: setup',
    '      # >>> gate-bind',
    '      # <<< gate-bind',
    '',
  ].join('\n');
  const WF_BAD = [
    '  a:',
    '    steps:',
    '      # >>> gate-bind',
    '      # <<< gate-bind',
    '      - id: setup',
    '',
  ].join('\n');
  ck('a region below `id: setup` is accepted', regionAfterSetup(WF_OK, 'a'));
  ck(
    'CONTROL: a region ABOVE `id: setup` is refused -- its steps would silently skip',
    !regionAfterSetup(WF_BAD, 'a')
  );
  ck(
    'CONTROL: a lane with no region at all is not this check’s business',
    regionAfterSetup(['  a:', '    steps:', '      - id: setup', ''].join('\n'), 'a')
  );
  ck(
    'a declared python-yaml need is ACQUIRED in the emitted step, at the pin',
    (() => {
      const out = emitStep({
        file: 'x.py',
        id: 'check:ci-x',
        run: 'x.py',
        step: 'X',
        needs: ['python-yaml'],
      });
      return (
        out.includes('        run: |') &&
        out.some((l) => l.includes('PyYAML==${PYYAML_VERSION}')) &&
        out[out.length - 1] === '          x.py'
      );
    })()
  );
  ck(
    'CONTROL: a gate that needs nothing gets a one-line run, not a block',
    emitStep({ file: 'x.py', id: 'check:ci-x', run: 'x.py', step: 'X', needs: [] }).includes(
      '        run: x.py'
    )
  );
  const DUP = [
    '  a:',
    '    steps:',
    '      - name: X',
    '        run: x',
    '      - name: X',
    '        run: x',
    '',
  ].join('\n');
  ck(
    'two steps of the same name in one job are counted as two',
    stepCountInJob(DUP, 'a', 'X') === 2
  );
  ck(
    'CONTROL: one is one, so an ordinary emitted step is not accused',
    stepCountInJob('  a:\n    steps:\n      - name: X\n        run: x\n', 'a', 'X') === 1
  );
  ck(
    'CONTROL: a duplicate in a DIFFERENT job is not this job’s problem',
    stepCountInJob(`${DUP.replace('  a:', '  b:')}`, 'a', 'X') === 0
  );
  ck('a gate under scripts/ is in scope', inScope('scripts/check-deps.ts'));
  ck(
    'CONTROL: packages/cli/scripts is NOT -- a header there is never read',
    !inScope('packages/cli/scripts/check-cli-i18n-help-render.ts')
  );
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

  // --extract-all: one process for the whole manifest.
  //
  // WHY THIS EXISTS AS A MODE RATHER THAN A SHELL LOOP. Extracting 20 gates with
  // `for id in ...; do npx tsx gate-bind.ts --extract $id; done` cost ~40s, and about
  // 38 of those were node and tsx starting up 20 times. The scan itself is ~1s over 603
  // files. Batching removes the only cost that mattered; nothing here is CPU-bound
  // enough for workers to beat one pass.
  if (argv.includes('--extract-all')) {
    const dry = argv.includes('--dry-run');
    const manifestText = read('scripts/ci-runner/manifest.ts');
    const pkg = (JSON.parse(read('package.json')) as { scripts: Record<string, string> }).scripts;
    const caps = laneCapabilities(read(WORKFLOW));
    const done: string[] = [];
    const refused = new Map<string, string[]>();
    for (const id of manifestIds(manifestText)) {
      const plan = planExtract(manifestText, id, read, pkg[id] ?? '', caps, false);
      if ('error' in plan) {
        // Grouped by REASON, not listed per gate: ~200 refusals of four shapes is a
        // wall, and a wall is what stops anyone reading the handful that matter.
        const key = plan.error.includes('is shared by')
          ? 'shares a step with other gates (sub-gate of an aggregate)'
          : plan.error.includes('outside the scan')
            ? 'outside .ci/scripts and scripts'
            : plan.error.includes('already declares')
              ? 'already declares a header'
              : plan.error.includes('re-derives')
                ? 'registration does not round-trip from the path'
                : 'other';
        refused.set(key, [...(refused.get(key) ?? []), id]);
        continue;
      }
      if (!dry) fs.writeFileSync(path.join(ROOT, plan.file), plan.next);
      done.push(`${id} -> ${plan.job} / "${plan.step}"`);
    }
    console.log(`${dry ? 'would extract' : 'extracted'}: ${done.length}`);
    for (const line of done) console.log(`    ${line}`);
    console.log(`refused: ${[...refused.values()].reduce((a, b) => a + b.length, 0)}`);
    for (const [why, ids] of [...refused].sort((a, b) => b[1].length - a[1].length)) {
      console.log(`    ${String(ids.length).padStart(4)}  ${why}`);
    }
    if (!dry && done.length > 0) {
      console.log('\nNow run `--write`, and place a `# >>> gate-bind` region in any lane');
      console.log('that has none. Then re-run with no flags to verify every binding.');
    }
    process.exit(0);
  }

  const rbAt = argv.indexOf('--rebind');
  const exAt = rbAt !== -1 ? rbAt : argv.indexOf('--extract');
  if (exAt !== -1) {
    const id = argv[exAt + 1];
    if (id === undefined || id.startsWith('--')) {
      console.error('✗ --extract needs a gate id, e.g. --extract check:ci-shell-format');
      process.exit(1);
    }
    const manifestText = read('scripts/ci-runner/manifest.ts');
    const reg = registered(manifestText, id);
    if ('error' in reg) {
      console.error(`✗ ${reg.error}`);
      process.exit(1);
    }
    const pkgScripts = (JSON.parse(read('package.json')) as { scripts: Record<string, string> })
      .scripts;
    reg.run = pkgScripts[id] ?? '';
    // A HEADER THE BINDER WILL NEVER READ IS WORSE THAN NO HEADER. The scan is
    // `git ls-files .ci/scripts scripts`; extraction wrote valid headers into
    // packages/cli/scripts/ and packages/www/scripts/, which sit outside it, and they
    // were simply never seen -- the same silent-ignore this gate already closed once
    // for file NAMES, returning through file PATHS.
    if (!inScope(reg.file)) {
      console.error(
        `✗ ${id}: ${reg.file} is outside this gate's scan (.ci/scripts, scripts), so a ` +
          'header there would never be read. It stays hand-registered.'
      );
      process.exit(1);
    }
    // A GATE WITH NO STEP OF ITS OWN CANNOT DECLARE ONE. 132 gate-tests share the single
    // step 'Quality-gate unit tests' and 10 i18n checks share 'i18n': they are sub-gates
    // of one aggregate command, not steps. Emitting a header for each would write the
    // same step name N times into a lane. This is the ceiling on what --extract can
    // ever cover, and it is better stated here than discovered per gate.
    const sharers = (
      manifestText.match(
        new RegExp(`step: '${reg.step.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}'`, 'g')
      ) ?? []
    ).length;
    if (sharers > 1) {
      console.error(
        `✗ ${id}: step "${reg.step}" is shared by ${sharers} manifest entries, so no one ` +
          'gate owns it. Sub-gates of an aggregate step stay hand-registered.'
      );
      process.exit(1);
    }
    const src = rbAt !== -1 ? stripHeader(read(reg.file)) : read(reg.file);
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
    // RUN IS PART OF THE ROUND TRIP. Checking only id and step let six headers be
    // written whose `run` disagreed with package.json -- the gate then reported them as
    // binding problems, which is the tool creating the work it exists to remove.
    const runOk = reg.run === '' || rb?.run === reg.run;
    if (rb === null || rb.id !== id || rb.step !== reg.step || !runOk) {
      const got = rb === null ? 'nothing' : `${rb.id} / "${rb.step}" / ${rb.run}`;
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
    if (!regionAfterSetup(workflow, job)) {
      problems.push(
        `${b.file}: job '${job}' has its \`# >>> gate-bind\` region ABOVE its \`- id: setup\` ` +
          "step, so every emitted step's `steps.setup.outcome` guard is empty and they all skip"
      );
    }
    const copies = stepCountInJob(workflow, job, b.step);
    if (copies > 1) {
      problems.push(
        `${b.file}: job '${job}' has ${copies} steps named "${b.step}" -- the emitted one ` +
          'and a hand-written leftover. Delete the hand-written copy; the region owns it now.'
      );
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
