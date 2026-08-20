#!/usr/bin/env tsx
/**
 * check:ci-guard-mutations - does each declared guard actually have a test that
 * FAILS when the guard is deleted?
 *
 * WHY THIS EXISTS. A passing unit suite proves the code does not crash. It does
 * not prove any assertion pins the behaviour it names. Both halves of that gap
 * were paid for in one session:
 *
 *   - `colWidths: undefined` was handed to cli-table3, which reads
 *     `options.colWidths[0]` unconditionally. Every table narrow enough to need
 *     no shrinking threw. The change had been "verified" against the one wide
 *     table whose path returns an array, so nothing exercised the crash.
 *   - The replacement test for `wrapProse` was VACUOUS: it stayed green with the
 *     guard it claimed to test deleted, because a short word ahead of the long
 *     token makes both branches behave identically. Only mutating the source
 *     exposed it.
 *
 * `check:test-cli` cannot catch either by construction: it runs the tests and
 * reports that they passed. This gate runs them against a DELIBERATELY BROKEN
 * copy of the source and requires them to fail.
 *
 * SAFETY. Mutation never touches the working tree. Everything happens in a
 * throwaway sandbox under `packages/cli/.guard-mutations.<pid>.<rand>.tmp/` (matched by the
 * existing `*.tmp` gitignore rule), because this tree is shared with other
 * sessions and an in-place mutation poisons their measurements even when it is
 * restored correctly afterwards.
 *
 * CONTROL-FIRST. The gate self-fails when its own instrument cannot fire:
 *   - the pristine sandbox must PASS (else the harness, not the guard, is broken)
 *   - `--selftest` plants a mutation that changes NOTHING and requires the gate
 *     to report it as unprotected, proving the detection is real
 *
 * ADDING A GUARD: append to MUTANTS. `find` must occur exactly once in `file`.
 */
import { execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PKG = join(REPO, 'packages/cli');
// UNIQUE per process. `npm run ci` is a parallel worker pool, so a fixed path
// lets one run `rm -rf` another's sandbox mid-flight - which surfaces as a
// control failure that a serial rerun cannot reproduce. Still ends in `.tmp`,
// so the existing gitignore rule covers it.
const SANDBOX = join(PKG, `.guard-mutations.${process.pid}.${randomBytes(4).toString('hex')}.tmp`);

interface Mutant {
  /** What the guard protects, in one line. */
  name: string;
  /** Source file, relative to packages/cli. */
  file: string;
  /** Exact text of the guard. Must appear exactly once. */
  find: string;
  /** The guard removed - what the code looked like when it was broken. */
  replace: string;
  /** Test file, relative to packages/cli, expected to FAIL once mutated. */
  test: string;
}

const MUTANTS: Mutant[] = [
  {
    name: 'colWidths is omitted, not passed as undefined, when a table already fits',
    file: 'src/services/core/output.ts',
    find: '...(widths ? { colWidths: widths } : {}),',
    replace: 'colWidths: widths,',
    test: 'src/services/__tests__/output.test.ts',
  },
  {
    name: 'wrapProse keeps an over-long FIRST token intact instead of emitting a blank line',
    file: 'src/services/core/output.ts',
    find: "if (candidate.length <= width || line === '') {",
    replace: 'if (candidate.length <= width) {',
    test: 'src/services/__tests__/output.test.ts',
  },
  {
    name: 'machine-readable relay lines are identified by the brace test, not loosely',
    file: 'src/services/executor/output-lines.ts',
    find: "if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return false;",
    replace: 'if (!trimmed) return false;',
    test: 'src/services/__tests__/machine-readable-relay.test.ts',
  },
  {
    name: 'withheld relay lines are WRAPPED when replayed, not dumped at full width',
    file: 'src/services/executor/output-lines.ts',
    find: 'for (const row of wrapProse(line, terminalWidth())) process.stderr.write(`${row}\\n`);',
    replace: 'process.stderr.write(`${line}\\n`);',
    test: 'src/services/__tests__/quiet-stderr-replay.test.ts',
  },
];

/** A mutation that provably changes no behaviour, used only by --selftest. */
const NO_OP_MUTANT: Mutant = {
  name: 'CONTROL: a comment edit must NOT be reported as protected',
  file: 'src/services/core/output.ts',
  find: 'export function wrapProse(',
  replace: '/* selftest no-op */ export function wrapProse(',
  test: 'src/services/__tests__/output.test.ts',
};

/**
 * Pristine text of every mutated file, snapshotted ONCE.
 *
 * Read from the sandbox, not the live tree, and never re-read: this worktree is
 * shared, and a peer session editing `output.ts` between two mutants would
 * otherwise make the occurrence assertion throw or mutate against shifted
 * content. One snapshot makes the whole run consistent with the sandbox it
 * actually tested.
 */
const pristine = new Map<string, string>();

/**
 * Refuse loudly when the subject is absent.
 *
 * Without this the gate dies on a raw ENOENT from `cpSync`, which is a failure
 * but not a legible one, and "no input" must be a hard, self-describing error
 * rather than something the reader has to decode. Registered in the repo's
 * anti-vacuity meta-gate, which points a validator at an empty tree and
 * requires a non-zero exit WITH a matching diagnostic.
 */
function assertSubjectPresent(): void {
  const missing: string[] = [];
  if (!existsSync(join(PKG, 'src'))) missing.push('packages/cli/src');
  for (const m of [...MUTANTS, NO_OP_MUTANT]) {
    for (const f of [m.file, m.test]) {
      if (!existsSync(join(PKG, f)) && !missing.includes(f)) missing.push(f);
    }
  }
  if (missing.length > 0) {
    console.error(
      `✗ required subject missing, so this gate can assert NOTHING:\n` +
        missing.map((f) => `    - ${f}`).join('\n') +
        `\n  A mutation gate with no source to mutate must fail, never report success.`
    );
    process.exit(1);
  }
}

function buildSandbox(): void {
  assertSubjectPresent();
  rmSync(SANDBOX, { recursive: true, force: true });
  mkdirSync(SANDBOX, { recursive: true });
  cpSync(join(PKG, 'src'), join(SANDBOX, 'src'), { recursive: true });
  for (const f of ['vitest.config.ts', 'package.json']) {
    if (existsSync(join(PKG, f))) cpSync(join(PKG, f), join(SANDBOX, f));
  }
  pristine.clear();
  for (const m of [...MUTANTS, NO_OP_MUTANT]) {
    if (!pristine.has(m.file)) pristine.set(m.file, readFileSync(join(SANDBOX, m.file), 'utf8'));
  }
}

/** Run one test file inside the sandbox. Returns true when it PASSED. */
function testPasses(testPath: string): boolean {
  try {
    execFileSync('npx', ['vitest', 'run', '--root', SANDBOX, testPath, '--reporter=dot'], {
      cwd: PKG,
      stdio: 'pipe',
      encoding: 'utf8',
    });
    return true;
  } catch {
    return false;
  }
}

function applyMutation(m: Mutant): void {
  const source = pristine.get(m.file);
  if (source === undefined) throw new Error(`no snapshot for ${m.file}`);
  const hits = source.split(m.find).length - 1;
  if (hits !== 1) {
    throw new Error(
      `mutant "${m.name}": its \`find\` text occurs ${hits} times in ${m.file}, expected exactly 1. ` +
        `The guard was probably edited; update the mutant to match the code.`
    );
  }
  writeFileSync(join(SANDBOX, m.file), source.replace(m.find, m.replace));
}

function restore(m: Mutant): void {
  writeFileSync(join(SANDBOX, m.file), pristine.get(m.file) ?? '');
}

function main(): number {
  const selftest = process.argv.includes('--selftest');
  console.log('Guard Mutations');
  console.log('='.repeat(60));

  buildSandbox();

  // CONTROL: the untouched sandbox must pass, or nothing below means anything.
  const control = MUTANTS[0];
  if (!testPasses(control.test)) {
    console.error(
      `\n✗ CONTROL FAILED: ${control.test} does not pass against an UNMUTATED sandbox.\n` +
        `  The harness is broken, not the guard. No mutant result below would be trustworthy.`
    );
    rmSync(SANDBOX, { recursive: true, force: true });
    return 1;
  }
  console.log(`control: pristine sandbox passes ${control.test}`);

  const unprotected: string[] = [];
  for (const m of MUTANTS) {
    applyMutation(m);
    const stillGreen = testPasses(m.test);
    restore(m);
    if (stillGreen) {
      unprotected.push(m.name);
      console.log(`  UNPROTECTED  ${m.name}`);
    } else {
      console.log(`  protected    ${m.name}`);
    }
  }

  let selftestFailed = false;
  if (selftest) {
    applyMutation(NO_OP_MUTANT);
    const stillGreen = testPasses(NO_OP_MUTANT.test);
    restore(NO_OP_MUTANT);
    if (stillGreen) {
      console.log(`  selftest ok  a behaviour-neutral edit is correctly reported as unprotected`);
    } else {
      console.error(
        `\n✗ SELFTEST FAILED: a comment-only edit made ${NO_OP_MUTANT.test} fail.\n` +
          `  That means the test is sensitive to something other than behaviour, so a ` +
          `"protected" verdict from this gate cannot be trusted.`
      );
      selftestFailed = true;
    }
  }

  rmSync(SANDBOX, { recursive: true, force: true });

  if (selftestFailed) return 1;
  if (unprotected.length > 0) {
    console.error(
      `\n✗ ${unprotected.length} guard(s) have NO test that fails when the guard is deleted.\n` +
        unprotected.map((n) => `    - ${n}`).join('\n') +
        `\n\n  A green suite is not evidence for these. Sharpen the test until deleting the ` +
        `guard turns it red, the way the wrapProse test had to be sharpened.`
    );
    return 1;
  }

  console.log(`\n✓ all ${MUTANTS.length} declared guard(s) are pinned by a test that fails without them.`);
  return 0;
}

function cleanup(): void {
  rmSync(SANDBOX, { recursive: true, force: true });
}
for (const sig of ['SIGINT', 'SIGTERM'] as const) {
  process.on(sig, () => {
    cleanup();
    process.exit(130);
  });
}

let code = 1;
try {
  code = main();
} finally {
  // `main` removes the sandbox on every normal path; this catches a throw.
  cleanup();
}
process.exit(code);
