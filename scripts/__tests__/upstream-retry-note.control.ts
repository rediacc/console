/**
 * Controls for the retry note of scripts/lib/upstream.ts (review c7aec94f.1).
 *
 * THE DEFECT THIS PINS. retryUpstream() printed `? <who>: attempt N of M failed (...), asking
 * again in S s` on STDOUT, so a command printing `--json` there (`npm run pins -- plan --all
 * --json`) emitted the note ahead of its document and json.load failed whenever an upstream
 * needed a retry. The note is progress and belongs on stderr; CI logs merge both streams, so
 * ci_diagnose's RETRY_NOTE_RE still reads it. A real tsx child runs one transient failure then
 * an answer, and its two streams are read apart.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

const LIB = path.resolve(import.meta.dirname, '../lib/upstream.ts');
const TSX = path.resolve(import.meta.dirname, '../../node_modules/.bin/tsx');

let failed = 0;
function check(name: string, ok: boolean): void {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`);
  if (!ok) failed++;
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'upstream-retry-'));
try {
  const child = path.join(tmp, 'child.mts');
  fs.writeFileSync(
    child,
    [
      `import { retryUpstream } from ${JSON.stringify(LIB)};`,
      'let n = 0;',
      "const value = await retryUpstream({ asked: 'GET h/p', host: 'h', who: 'pin' }, async () =>",
      "  ++n === 1 ? { what: 'HTTP 503', retry: true, status: 503, retryAfterS: null, unreachable: false } : { value: 'ok' }",
      ');',
      "process.stdout.write(JSON.stringify({ value, attempts: n }) + '\\n');",
    ].join('\n')
  );
  const r = spawnSync(TSX, [child], { encoding: 'utf8', env: { ...process.env, NO_COLOR: '1' } });
  check('the child exits 0', r.status === 0);
  let doc: { value?: string; attempts?: number } | null = null;
  try {
    doc = JSON.parse(r.stdout);
  } catch {
    doc = null;
  }
  check('stdout is exactly the JSON document, with no retry note before it', doc?.value === 'ok');
  check('the second attempt answered', doc?.attempts === 2);
  check(
    'the retry note is on stderr in the wording ci_diagnose reads',
    /\? pin: attempt 1 of \d+ failed \(HTTP 503\), asking again in /.test(r.stderr)
  );
  check('the note is not on stdout', !r.stdout.includes('asking again'));
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

console.log(
  failed === 0 ? 'upstream retry note: all controls pass' : `upstream retry note: ${failed} failed`
);
process.exit(failed === 0 ? 0 : 1);
