/**
 * Controls for scripts/lib/entry-point.ts.
 *
 * THE DEFECT THIS PINS. A gate's main()-guard compared `path.resolve(process.argv[1])` with
 * `import.meta.filename` (or the URL forms of the same). Node and tsx resolve symlinks for
 * `import.meta.*` and leave `argv[1]` alone, so a gate launched through a symlinked
 * directory evaluated false, never ran main(), and exited 0 having checked nothing. A path
 * with a space broke the `file://${...}` form the same way. Each case below launches a real
 * child under tsx; the OLD comparison is run beside it as the control that the fixture
 * really reproduces the defect (a symlink fixture that the old guard also passes would make
 * every green below meaningless).
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { isEntryPoint } from '../lib/entry-point.js';

const LIB = path.resolve(import.meta.dirname, '../lib/entry-point.ts');
const TSX = path.resolve(import.meta.dirname, '../../node_modules/.bin/tsx');

let failed = 0;
function check(name: string, ok: boolean): void {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`);
  if (!ok) failed++;
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'entry-point-'));
const realDir = path.join(tmp, 'real dir');
const linkDir = path.join(tmp, 'link');
fs.mkdirSync(realDir);
fs.symlinkSync(realDir, linkDir);

const probe = `import { isEntryPoint } from ${JSON.stringify(LIB)};
import path from 'node:path';
console.log(JSON.stringify({
  isEntryPoint: isEntryPoint(import.meta.filename),
  old: path.resolve(process.argv[1] ?? '') === import.meta.filename,
}));
`;
fs.writeFileSync(path.join(realDir, 'probe.ts'), probe);
fs.writeFileSync(
  path.join(realDir, 'importer.ts'),
  `import { isEntryPoint } from ${JSON.stringify(LIB)};
import * as probe from ${JSON.stringify(path.join(realDir, 'probe.ts'))};
void probe;
console.log(JSON.stringify({ other: isEntryPoint(${JSON.stringify(path.join(realDir, 'probe.ts'))}) }));
`
);

function run(file: string): Record<string, boolean> {
  const out = execFileSync(TSX, [file], { encoding: 'utf8' });
  return JSON.parse(out.trim().split('\n').pop() ?? '{}') as Record<string, boolean>;
}

try {
  const direct = run(path.join(realDir, 'probe.ts'));
  check('true when run by its real path (which contains a space)', direct.isEntryPoint === true);
  check('control: old comparison also true by the real path', direct.old === true);

  const viaLink = run(path.join(linkDir, 'probe.ts'));
  check('true when run through a symlinked directory', viaLink.isEntryPoint === true);
  check('control: old comparison is FALSE through the symlink', viaLink.old === false);

  const other = run(path.join(realDir, 'importer.ts'));
  check('false for a file that is not the one launched', other.other === false);
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

check(
  'false when this process was not given a script path',
  (() => {
    const saved = process.argv[1];
    process.argv[1] = '';
    try {
      return isEntryPoint(import.meta.filename) === false;
    } finally {
      process.argv[1] = saved;
    }
  })()
);
check(
  'false when a path does not exist',
  isEntryPoint(path.join(os.tmpdir(), 'no-such-file.ts')) === false
);

process.exit(failed === 0 ? 0 : 1);
