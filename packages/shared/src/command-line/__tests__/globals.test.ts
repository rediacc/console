import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { GLOBAL_OPTIONS } from '../contract-index.js';

describe('GLOBAL_OPTIONS', () => {
  it('lists the root options registered in packages/cli/src/cli.ts, and only those plus help and version', () => {
    const cli = readFileSync(
      fileURLToPath(new URL('../../../../cli/src/cli.ts', import.meta.url)),
      'utf-8'
    );
    const registered = [
      ...cli.matchAll(/^\s*\.option\('(?:(-\w), )?--([a-z-]+)( <[^>]+>)?'/gm),
    ].map((m) => ({
      long: m[2],
      ...(m[1] ? { short: m[1].slice(1) } : {}),
      valueTaking: m[3] !== undefined,
    }));
    expect(registered.length).toBeGreaterThanOrEqual(10);
    const mine = GLOBAL_OPTIONS.filter((o) => o.long !== 'help' && o.long !== 'version').map(
      (o) => ({
        long: o.long,
        ...(o.short ? { short: o.short } : {}),
        valueTaking: o.valueTaking,
      })
    );
    expect(mine).toEqual(registered);
  });
});
