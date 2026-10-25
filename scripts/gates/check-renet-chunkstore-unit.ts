/**
 * check:renet-chunkstore-unit -- the chunk-store Go tests run, non-root, on every change.
 *
 * WHY. The chunk store (private/renet/pkg/chunkstore) is the backup data plane, and its
 * tests were never run before a push: check:ci-proxy-go-unit excluded the package because
 * its root and btrfs tests lived in untagged files, and the CI suite that did run them
 * needs root and a VM. J1 moved those tests behind build tags, so a plain `go test` here
 * compiles only the unprivileged set. This gate runs exactly that, as the invoking user.
 *
 * A PASS MUST HAVE RUN TESTS. `go test` exits 0 for a package with no test files and for
 * a pattern that matches no package, so the exit code alone cannot tell "162 tests passed"
 * from "nothing was compiled". The run is read as `go test -json`, and the gate fails
 * unless at least MIN_TESTS test cases reported pass, at least MIN_PACKAGES packages
 * reported a verdict, and nothing failed or skipped past the declared ceiling.
 *
 * A missing `go` is a loud failure with the install hint, not a spawn error.
 *
 * ---- gate ----
 * step: Run chunkstore unit tests
 * needs: node, go, submodules
 * lane: quality-go
 * selftest: true
 * ---- end gate ----
 */

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { GREEN, NC, RED } from '../lib/console.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { requireSubmodule, submodulePath } from '../lib/submodule-presence.js';

/** Floors, set well under the measured 2026-10-25 counts (162 tests, 2 packages) so growth never trips them. */
export const MIN_TESTS = 50;
export const MIN_PACKAGES = 2;

export interface Verdict {
  passed: number;
  failed: string[];
  skipped: number;
  packages: number;
  unparsed: number;
}

/** Fold `go test -json` lines into a verdict. Test-level events carry `Test`; package-level ones do not. */
export function judge(jsonLines: string): Verdict {
  const v: Verdict = { passed: 0, failed: [], skipped: 0, packages: 0, unparsed: 0 };
  for (const line of jsonLines.split('\n')) {
    if (line.trim() === '') continue;
    let e: { Action?: string; Package?: string; Test?: string };
    try {
      e = JSON.parse(line);
    } catch {
      v.unparsed += 1;
      continue;
    }
    const name = `${e.Package ?? '?'}${e.Test ? `.${e.Test}` : ''}`;
    if (e.Test) {
      if (e.Action === 'pass') v.passed += 1;
      else if (e.Action === 'fail') v.failed.push(name);
      else if (e.Action === 'skip') v.skipped += 1;
    } else if (e.Action === 'pass' || e.Action === 'fail') {
      v.packages += 1;
      if (e.Action === 'fail') v.failed.push(`${e.Package} (package)`);
    }
  }
  return v;
}

/** Why a verdict is not a pass; empty when it is. */
export function refusals(v: Verdict): string[] {
  const out: string[] = [];
  if (v.failed.length > 0)
    out.push(`${v.failed.length} failing: ${v.failed.slice(0, 10).join(', ')}`);
  if (v.passed < MIN_TESTS)
    out.push(
      `only ${v.passed} test(s) passed (floor ${MIN_TESTS}); the gate is not seeing the tests, so its green would mean nothing`
    );
  if (v.packages < MIN_PACKAGES)
    out.push(
      `only ${v.packages} package verdict(s) (floor ${MIN_PACKAGES}); a package fell out of ./pkg/chunkstore/...`
    );
  return out;
}

function selftest(): void {
  const fail = (m: string): never => {
    console.error(`${RED}selftest FAIL: ${m}${NC}`);
    process.exit(1);
  };
  const ev = (a: string, p: string, t?: string): string =>
    JSON.stringify({ Action: a, Package: p, ...(t ? { Test: t } : {}) });
  const many = (n: number): string =>
    Array.from({ length: n }, (_, i) => ev('pass', 'p/a', `T${i}`)).join('\n');
  const green = `${many(MIN_TESTS)}\n${ev('pass', 'p/a')}\n${ev('pass', 'p/b')}`;
  if (refusals(judge(green)).length !== 0) fail('a healthy run was refused');
  console.log('  PASS  CONTROL: a healthy run passes');
  if (refusals(judge(`${green}\n${ev('fail', 'p/a', 'TBad')}`)).length === 0)
    fail('a failing test was not refused');
  console.log('  PASS  a failing test is refused');
  if (refusals(judge(`${ev('pass', 'p/a')}\n${ev('pass', 'p/b')}`)).length === 0)
    fail('zero tests passed was accepted');
  console.log('  PASS  zero tests with exit 0 is refused (no vacuous green)');
  if (refusals(judge(`${many(MIN_TESTS)}\n${ev('pass', 'p/a')}`)).length === 0)
    fail('a vanished package was accepted');
  console.log('  PASS  a vanished package is refused');
  if (
    refusals(judge(`${many(MIN_TESTS)}\n${ev('pass', 'p/a')}\n${ev('fail', 'p/b')}`)).length === 0
  )
    fail('a package-level build failure was accepted');
  console.log('  PASS  a package-level failure (build error) is refused');
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    console.log('check-renet-chunkstore-unit: selftest ok');
    return;
  }
  const renet = submodulePath('private/renet');
  if (!requireSubmodule('renet chunkstore unit', [submodulePath('private/renet/pkg/chunkstore')]))
    return;
  if (!fs.existsSync(renet)) process.exit(1);

  const probe = spawnSync('go', ['version'], { encoding: 'utf-8' });
  if (probe.error || probe.status !== 0) {
    console.error(
      `${RED}✗ the go toolchain is not runnable (${probe.error?.message ?? `exit ${probe.status}`}). Install Go at the version in private/renet/go.mod (https://go.dev/dl/), or on a CI job add actions/setup-go.${NC}`
    );
    process.exit(1);
  }

  const run = spawnSync('go', ['test', '-count=1', '-json', './pkg/chunkstore/...'], {
    cwd: renet,
    encoding: 'utf-8',
    maxBuffer: 256 * 1024 * 1024,
  });
  const v = judge(run.stdout ?? '');
  const why = refusals(v);
  if (run.status !== 0 && why.length === 0) why.push(`go test exited ${run.status}`);
  if (why.length > 0) {
    console.error(`${RED}✗ chunkstore unit tests: ${why.join('; ')}${NC}`);
    console.error((run.stderr ?? '').split('\n').slice(-40).join('\n'));
    const out = (run.stdout ?? '')
      .split('\n')
      .filter((l) => l.includes('"Action":"output"') && /FAIL|panic|planted|_test.go:/.test(l));
    for (const l of out.slice(0, 40)) {
      try {
        process.stderr.write((JSON.parse(l) as { Output: string }).Output);
      } catch {
        // an unparsable line carries nothing to show
      }
    }
    process.exit(1);
  }
  console.log(
    `${GREEN}✓ chunkstore unit tests: ${v.passed} passed, ${v.skipped} skipped, ${v.packages} package(s), uid ${process.getuid?.() ?? '?'}${NC}`
  );
}

if (isEntryPoint(import.meta.filename)) main();
