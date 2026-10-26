#!/usr/bin/env tsx
/**
 * check:ci-standalone-selftests -- selftests that no other CI gate runs are run here, and
 * each one has to report its controls.
 *
 * WHY. A selftest is only worth its controls if something runs it where a red is seen.
 * Seven selftests ran nowhere in CI until 2026-10-14, and this table holds them plus one:
 *
 *   - four pins selftests under scripts/lib/pins/ (the embed, toolchain and devcontainer
 *     drivers and the transaction journal). No package.json script, manifest entry,
 *     workflow step or pytest file ran them, and three could not even start in a checkout
 *     without the private submodules. The fifth, drivers/selftest.ts, is also driven by
 *     .ci/rediacc_ci/tests/gates/test_gate_pin_family_drivers.py one mutant per process; it
 *     runs here too, so the pins set has one owner;
 *   - the `--selftest` legs of three gates CI never runs at all: check:types:incremental and
 *     check:ci-proxy-image-smoke are `local-only` by a BLOCKER about their FULL run (a cache
 *     twin of check:types, a docker build), and check:env-credential-drift is no manifest
 *     gate (its full run needs Bitwarden secrets). None of the three selftests needs any of
 *     that: each is offline and runs in under three seconds.
 *
 * WHAT IT RUNS. Every entry of SELFTESTS, by NAME, so check:ci-selftest-reachability sees
 * each one is run. The pins part of the table cannot fall behind the tree: git lists every
 * tracked `scripts/lib/pins/**\/*selftest*.ts`, and a pins selftest the table does not name
 * (or a name git does not track) is red before anything runs. Each entry runs as its own
 * process (`tsx` for .ts, `python3` for .py) from the repository root, and counts as a pass
 * only when ALL hold:
 *
 *   - the exit code is 0;
 *   - it reported at least one control: `PASS` lines by default, or the count its own
 *     summary line states (`selftest ok (41 assertions)`) where it prints no PASS lines. A
 *     run that verified nothing is refused, whatever its exit code says;
 *   - it printed no `FAIL` line on either stream.
 *
 * The verdict line names each entry with its control and MUTANT counts, so a count that
 * collapses is visible in a green log.
 *
 * SUBMODULES. Three pins selftests copy live files from private/renet and private/account into
 * their temporary trees. `requireSubmodule` is the shared contract: absent under CI is a hard
 * failure naming the fix, absent locally is a loud NOT CHECKED line for those three only.
 *
 * THE CONTROLS (`--selftest`). `judgeRun` both ways on synthetic outputs (a clean run, a
 * silent exit 0, a FAIL on stderr under exit 0, a non-zero exit with PASS lines, a summary
 * count of zero); `tableDrift` both ways (an untabled selftest and a stale name are red, an
 * exact table is not); and two real processes through the same `runSelftest` the real run
 * uses: a planted selftest that exits 0 and prints nothing must be judged red, one that
 * prints a PASS line green.
 *
 * ---- gate ----
 * step: Standalone selftests
 * needs: node, private/renet, private/account
 * selftest: true
 * why: seven selftests were run by no CI gate, so their controls could not go red where
 *      anyone would see it. This runs every one of them, and the pins set whole, and refuses
 *      a run that reports no controls
 * ---- end gate ----
 *
 * Usage:
 *   npx tsx scripts/gates/check-standalone-selftests.ts [--selftest]
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { stripVTControlCharacters } from 'node:util';
import { type ControlCase, refused, refuseIfEmpty, summarizeControls } from '../lib/controls.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { REPO_ROOT } from '../lib/repo-root.js';
import { requireSubmodule, submodulePath } from '../lib/submodule-presence.js';

/**
 * Where the pins selftests live; the pathspec git enumerates for the drift check.
 *
 * `:(glob)` is load-bearing. Without it git matches `*` across slashes and reads `**\/` as
 * "at least one more directory", so the plain spelling lists the four files under drivers/
 * and silently drops scripts/lib/pins/txn-selftest.ts.
 */
export const PINS_SELFTEST_PATHSPEC = ':(glob)scripts/lib/pins/**/*selftest*.ts';
const PINS_DIR = 'scripts/lib/pins/';

/** How one standalone selftest is run and how its controls are counted. */
export interface Standalone {
  /** Arguments after the file. */
  args: readonly string[];
  /** A summary line whose first capture is the control count, for a selftest that prints no PASS lines. */
  controls?: RegExp;
  /** Submodule paths it copies from; absent locally skips it with a NOT CHECKED line. */
  submodules?: readonly string[];
}

const PRIVATE = ['private/renet', 'private/account'] as const;

/**
 * Every standalone selftest. drivers/selftest.ts proves its mutants in-process only under
 * `--selftest`; the other pins selftests prove theirs on a bare run.
 */
export const SELFTESTS: Readonly<Record<string, Standalone>> = {
  'scripts/lib/pins/drivers/devcontainer-selftest.ts': { args: [], submodules: PRIVATE },
  'scripts/lib/pins/drivers/embed-selftest.ts': { args: [], submodules: PRIVATE },
  'scripts/lib/pins/drivers/selftest.ts': { args: ['--selftest'] },
  'scripts/lib/pins/drivers/toolchain-selftest.ts': { args: [], submodules: PRIVATE },
  'scripts/lib/pins/ran-line-selftest.ts': { args: [] },
  'scripts/lib/pins/txn-selftest.ts': { args: [] },
  'scripts/ci-runner/typecheck-incremental.ts': {
    args: ['--selftest'],
    controls: /selftest ok \((\d+) assertions?\)/,
  },
  'scripts/gates/check-env-credential-drift.ts': { args: ['--selftest'] },
  '.ci/scripts/quality/check_proxy_image_smoke.py': { args: ['--selftest'] },
  '.ci/scripts/housekeeping/retire-shadowed-secrets.py': { args: ['--selftest'] },
  // isEntryPoint (scripts/lib/entry-point.ts) through a symlink and a spaced path, with the old comparison as the control.
  'scripts/__tests__/entry-point.control.ts': { args: [] },
  // isEntryPoint's refusal of a module URL (scripts/lib/entry-point.ts): the throw that keeps a gate's main() from being skipped silently.
  'scripts/lib/entry-point-selftest.ts': { args: [] },
  // retryUpstream (scripts/lib/upstream.ts) keeps its retry note on stderr, so a --json stdout stays parseable.
  'scripts/__tests__/upstream-retry-note.control.ts': { args: [] },
};

/** Where the table and the tree disagree over the pins selftests. */
export function tableDrift(
  tracked: readonly string[],
  table: Readonly<Record<string, Standalone>> = SELFTESTS
): { untabled: string[]; stale: string[] } {
  const names = Object.keys(table).filter((f) => f.startsWith(PINS_DIR));
  return {
    untabled: tracked.filter((f) => !names.includes(f)),
    stale: names.filter((f) => !tracked.includes(f)),
  };
}

/** What one selftest process left behind. */
export interface SelftestRun {
  file: string;
  status: number | null;
  stdout: string;
  stderr: string;
}

/** The verdict on one run, with the counts the success line prints. */
export interface Judgement {
  ok: boolean;
  controls: number;
  fail: number;
  mutants: number;
  why: string;
}

/** Colour escapes sit between the indent and the word, so they are stripped before any count. */
const lines = (s: string): string[] => stripVTControlCharacters(s).split('\n');

/** Count controls, FAIL and MUTANT lines and decide. Exported so the controls drive it directly. */
export function judgeRun(run: SelftestRun, spec: Pick<Standalone, 'controls'> = {}): Judgement {
  const out = lines(run.stdout);
  const all = [...out, ...lines(run.stderr)];
  let controls = out.filter((l) => /^\s*PASS\s/.test(l)).length;
  if (spec.controls) {
    const m = all.map((l) => spec.controls?.exec(l)).find((x) => x);
    controls = m ? Number(m[1]) : 0;
  }
  const fail = all.filter((l) => /^\s*FAIL\s/.test(l)).length;
  const mutants = all.filter((l) => /^\s*(PASS\s+)?MUTANT\s/.test(l)).length;
  let why = '';
  if (run.status !== 0) why = `exit ${run.status ?? 'signal'}`;
  else if (fail > 0) why = `${fail} FAIL line(s) under exit 0`;
  else if (controls === 0) why = 'exit 0 with no control reported: the run verified nothing';
  return { ok: why === '', controls, fail, mutants, why };
}

/** Run one selftest file as its own process, from the repository root. */
export function runSelftest(
  file: string,
  args: readonly string[] = SELFTESTS[file]?.args ?? [],
  root: string = REPO_ROOT
): SelftestRun {
  const prog = file.endsWith('.py') ? 'python3' : path.join(root, 'node_modules', '.bin', 'tsx');
  const r = spawnSync(prog, [file, ...args], {
    cwd: root,
    encoding: 'utf8',
    env: { ...process.env, NO_COLOR: '1' },
    maxBuffer: 64 * 1024 * 1024,
  });
  return {
    file,
    status: r.error ? null : r.status,
    stdout: r.stdout ?? '',
    stderr: `${r.stderr ?? ''}${r.error ? `\n${r.error.message}` : ''}`,
  };
}

/** The tracked pins selftests, from git. */
export function pinsSelftests(root: string = REPO_ROOT): string[] {
  const out = spawnSync('git', ['-C', root, 'ls-files', '--', PINS_SELFTEST_PATHSPEC], {
    encoding: 'utf8',
  });
  if (out.status !== 0) {
    throw new Error(`git ls-files failed (exit ${out.status}): ${out.stderr}`);
  }
  return out.stdout.split('\n').filter(Boolean).sort();
}

function selftestCases(): ControlCase[] {
  const run = (status: number | null, stdout: string, stderr = ''): SelftestRun => ({
    file: 'x-selftest.ts',
    status,
    stdout,
    stderr,
  });
  const cases: ControlCase[] = [];
  const add = (name: string, j: Judgement, want: boolean): void => {
    cases.push({ name, ok: j.ok === want, detail: `ok=${j.ok} why=${j.why}` });
  };
  add('a clean run with PASS lines passes', judgeRun(run(0, '  PASS  a\n  PASS  b\n')), true);
  add(
    'a clean run with colour escapes between indent and word still counts its PASS lines',
    judgeRun(run(0, '  \x1b[32mPASS\x1b[0m  a\n')),
    true
  );
  add('exit 0 with no output is refused as vacuous', judgeRun(run(0, '')), false);
  add(
    'exit 0 with a FAIL on stderr is refused',
    judgeRun(run(0, '  PASS  a\n', '  FAIL  b\n')),
    false
  );
  add('a non-zero exit is refused even with PASS lines', judgeRun(run(1, '  PASS  a\n')), false);
  add('a crash (no exit status) is refused', judgeRun(run(null, '')), false);
  const summary = { controls: /selftest ok \((\d+) assertions?\)/ };
  add(
    'a summary count is read where no PASS line is printed',
    judgeRun(run(0, 'x: selftest ok (41 assertions)\n'), summary),
    true
  );
  add(
    'a summary count of zero is refused as vacuous',
    judgeRun(run(0, 'x: selftest ok (0 assertions)\n'), summary),
    false
  );
  add(
    'a missing summary line is refused even beside PASS lines',
    judgeRun(run(0, '  PASS  a\n'), summary),
    false
  );
  const m = judgeRun(run(0, '  PASS  a\nMUTANT x: red as it must be (1): a\n'));
  cases.push({ name: 'a MUTANT line is counted', ok: m.mutants === 1, detail: `${m.mutants}` });

  const pins = Object.keys(SELFTESTS).filter((f) => f.startsWith(PINS_DIR));
  const extra = tableDrift([...pins, `${PINS_DIR}new-selftest.ts`]);
  cases.push({
    name: 'a tracked pins selftest the table does not name is drift',
    ok: extra.untabled.join() === `${PINS_DIR}new-selftest.ts` && extra.stale.length === 0,
    detail: JSON.stringify(extra),
  });
  const gone = tableDrift(pins.slice(1));
  cases.push({
    name: 'a table name git does not track is drift',
    ok: gone.stale.join() === pins[0] && gone.untabled.length === 0,
    detail: JSON.stringify(gone),
  });
  const exact = tableDrift(pins);
  cases.push({
    name: 'an exact table is not drift, and the non-pins entries are outside the drift scope',
    ok: exact.stale.length === 0 && exact.untabled.length === 0,
    detail: JSON.stringify(exact),
  });

  // The real process path: planted selftests, run exactly as the real run runs them.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'standalone-selftests-'));
  try {
    const silent = path.join(dir, 'silent-selftest.ts');
    fs.writeFileSync(silent, 'process.exit(0);\n');
    const j = judgeRun(runSelftest(silent, []));
    cases.push({
      name: 'a planted selftest that exits 0 and prints nothing, run as a real process, is red',
      ok: !j.ok && j.controls === 0,
      detail: `ok=${j.ok} controls=${j.controls} why=${j.why}`,
    });
    const real = path.join(dir, 'real-selftest.py');
    fs.writeFileSync(real, "print('  PASS  planted')\n");
    const k = judgeRun(runSelftest(real, []));
    cases.push({
      name: 'a planted .py selftest that prints a PASS line, run as a real process, is green',
      ok: k.ok && k.controls === 1,
      detail: `ok=${k.ok} controls=${k.controls} why=${k.why}`,
    });
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  return cases;
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) return summarizeControls(selftestCases());

  const tracked = refuseIfEmpty(
    pinsSelftests(),
    `tracked ${PINS_SELFTEST_PATHSPEC}`,
    'The pathspec matched nothing: the pins selftests moved or the glob broke.'
  );
  const drift = tableDrift(tracked);
  if (drift.untabled.length > 0 || drift.stale.length > 0) {
    return refused(
      '✗ SELFTESTS in scripts/gates/check-standalone-selftests.ts disagrees with the tree:',
      ...drift.untabled.map(
        (f) => `    ${f}: a tracked pins selftest the table does not name; add it`
      ),
      ...drift.stale.map((f) => `    ${f}: named by the table, tracked by nothing; remove it`)
    );
  }

  const red: string[] = [];
  let redCount = 0;
  let skipped = 0;
  const shape: string[] = [];
  const entries = Object.entries(SELFTESTS);
  for (const [file, spec] of entries) {
    if (
      spec.submodules &&
      !requireSubmodule(
        file,
        spec.submodules.map((s) => submodulePath(s))
      )
    ) {
      skipped += 1;
      continue;
    }
    const run = runSelftest(file, spec.args);
    const j = judgeRun(run, spec);
    shape.push(`${path.basename(file)} ${j.controls}${j.mutants ? `+${j.mutants} mutant` : ''}`);
    if (!j.ok) {
      redCount += 1;
      red.push(`  ${file}: ${j.why}`);
      const tail = `${run.stdout}\n${run.stderr}`.trim().split('\n').slice(-15);
      red.push(...tail.map((l) => `      ${l}`));
    }
  }
  if (red.length > 0) {
    return refused(
      `✗ standalone selftests: ${redCount} of ${entries.length} red`,
      ...red,
      '  Run the named file (`npx tsx <file>` or `python3 <file>`, with the args in SELFTESTS)',
      '  to see every control, and fix the code or the control.'
    );
  }
  const ran = entries.length - skipped;
  console.log(
    `✓ ${ran} of ${entries.length} standalone selftests passed${skipped ? ` (${skipped} NOT CHECKED, above)` : ''}; controls per file: ${shape.join(', ')}`
  );
  return 0;
}

if (isEntryPoint(import.meta.filename)) process.exit(main(process.argv.slice(2)));
