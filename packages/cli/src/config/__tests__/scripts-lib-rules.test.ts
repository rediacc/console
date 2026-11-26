/**
 * Review 03c9e724.1: IMPORT_RE in plane-rules.ts matches a bare side-effect `import '...'`; a regex edit that drops that branch reopens the false pass for config-only domains.
 * Review 219d0972.5: the `feedback report` executor-served note keeps the caveat about the recorded-command history.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { EXECUTOR_SERVED } from '../../../scripts/lib/contract-curation.js';
import { createReachability } from '../../../scripts/lib/plane-rules.js';

const MARKER = 'services/executor/executor-factory';
const roots: string[] = [];

function tree(entryBody: string): string {
  const src = fs.mkdtempSync(path.join(os.tmpdir(), 'plane-rules-'));
  roots.push(src);
  fs.mkdirSync(path.join(src, 'services/executor'), { recursive: true });
  fs.writeFileSync(path.join(src, 'services/executor/executor-factory.ts'), 'export {};\n');
  fs.writeFileSync(path.join(src, 'entry.ts'), entryBody);
  return src;
}

afterEach(() => {
  for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

describe('createReachability import forms', () => {
  it('follows a bare side-effect import to the machine seam', () => {
    const src = tree("import './services/executor/executor-factory.js';\n");
    expect(createReachability(src, [MARKER])('entry.ts').machineTouching).toBe(true);
  });

  it('follows an indented bare import after other statements', () => {
    const src = tree("const a = 1;\n  import './services/executor/executor-factory.js';\n");
    expect(createReachability(src, [MARKER])('entry.ts').machineTouching).toBe(true);
  });

  it('follows a named import, as before (control)', () => {
    const src = tree("import { x } from './services/executor/executor-factory.js';\n");
    expect(createReachability(src, [MARKER])('entry.ts').machineTouching).toBe(true);
  });

  it('does not reach the seam from a file that imports nothing (control)', () => {
    const src = tree('export const a = 1;\n');
    expect(createReachability(src, [MARKER])('entry.ts').machineTouching).toBe(false);
  });
});

describe('executor-served notes', () => {
  it('feedback report records that the recorded-command forms read the executor history', () => {
    expect(EXECUTOR_SERVED['feedback report']).toMatch(/--last/);
    expect(EXECUTOR_SERVED['feedback report']).toMatch(/command history the EXECUTOR holds/);
  });
});
