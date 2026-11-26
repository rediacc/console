import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { OPS_BACKEND_CHOICES } from '../backends.js';

describe('OPS_BACKEND_CHOICES', () => {
  it('lists every member of the OpsBackend union', () => {
    const src = readFileSync(
      new URL('../../../services/executor/ops-executor.ts', import.meta.url),
      'utf-8'
    );
    const union = /export type OpsBackend = ([^;]+);/.exec(src)?.[1] ?? '';
    const members = [...union.matchAll(/'([^']+)'/g)].map((m) => m[1]);
    expect(members.length).toBeGreaterThan(0);
    expect([...OPS_BACKEND_CHOICES].sort((a, b) => a.localeCompare(b))).toEqual(
      members.sort((a, b) => a.localeCompare(b))
    );
  });
});
