/**
 * Controls for scripts/gates/lib/run-control.ts (foldedControl): the rejected-import branch must
 * exit 1 and name the harness, a harness that settles its result after import must not be cut off,
 * and a run without --selftest must load nothing. Each case drives a real child under tsx.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

const LIB = path.resolve(import.meta.dirname, '../gates/lib/run-control.ts');
const TSX = path.resolve(import.meta.dirname, '../../node_modules/.bin/tsx');

let failed = 0;
function check(name: string, ok: boolean, detail = ''): void {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok || !detail ? '' : ` -- ${detail}`}`);
  if (!ok) failed++;
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'run-control-'));
function drive(harnessBody: string | null, args: string[]) {
  const harness = path.join(tmp, 'harness.ts');
  if (harnessBody !== null) fs.writeFileSync(harness, harnessBody);
  else fs.rmSync(harness, { force: true });
  const gate = path.join(tmp, 'gate.ts');
  fs.writeFileSync(
    gate,
    `import { foldedControl } from ${JSON.stringify(LIB)};\n` +
      `if (!foldedControl(() => import('./harness.ts'))) console.log('GATE-RAN');\n`
  );
  return spawnSync(TSX, [gate, ...args], { encoding: 'utf8' });
}

try {
  const missing = drive(null, ['--selftest']);
  check('a harness that fails to load is rc 1', missing.status === 1, String(missing.status));
  check(
    'the failure names the harness path',
    missing.stderr.includes('./harness.ts'),
    missing.stderr
  );

  const late = drive(`setTimeout(() => { process.exitCode = 3; }, 150);\n`, ['--selftest']);
  check('a harness settling after import is not cut off', late.status === 3, String(late.status));

  const clean = drive(`console.log('HARNESS-RAN');\n`, ['--selftest']);
  check(
    'a passing harness is rc 0 and the gate body is skipped',
    clean.status === 0 &&
      clean.stdout.includes('HARNESS-RAN') &&
      !clean.stdout.includes('GATE-RAN'),
    clean.stdout
  );

  const plain = drive(`console.log('HARNESS-RAN');\n`, []);
  check(
    'without --selftest the gate runs and no harness loads',
    plain.stdout.includes('GATE-RAN') && !plain.stdout.includes('HARNESS-RAN'),
    plain.stdout
  );
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
if (failed > 0) process.exit(1);
console.log('OK: run-control controls passed');
