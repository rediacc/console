import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const GENERATOR = fileURLToPath(
  new URL('../../scripts/generate-skill-reference.ts', import.meta.url)
);
const CLI_DIR = fileURLToPath(new URL('../..', import.meta.url));

describe('generate-skill-reference option defaults', () => {
  it('omits the default suffix for an empty-array default', () => {
    const out = execFileSync('npx', ['tsx', GENERATOR], {
      cwd: CLI_DIR,
      encoding: 'utf8',
      maxBuffer: 32 * 1024 * 1024,
    });
    expect(out).not.toContain('(default: )');
    expect(out).toContain('(default: ');
  }, 120_000);
});
