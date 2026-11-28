import { describe, expect, it } from 'vitest';
import { getCommand } from '../index.js';
import { MASKED, maskParams } from '../mask.js';
import type { ContractCommand } from '../types.js';

const ENTRY = {
  options: [{ long: 'token', sensitive: true }, { long: 'name' }, { long: 'token-file' }],
  positionals: [{ name: 'ref' }],
} as unknown as ContractCommand;

describe('maskParams', () => {
  it('masks a contract-sensitive option and keeps an ordinary one', () => {
    expect(maskParams(ENTRY, { token: 'abc', name: 'web' })).toEqual({
      token: MASKED,
      name: 'web',
    });
  });

  it('keeps a known non-sensitive option even when its name looks sensitive', () => {
    expect(maskParams(ENTRY, { 'token-file': '/tmp/t' })).toEqual({ 'token-file': '/tmp/t' });
  });

  it('masks an unknown api-token key and keeps an unknown plain key (control)', () => {
    expect(maskParams(ENTRY, { 'api-token': 'secret', colour: 'red' })).toEqual({
      'api-token': MASKED,
      colour: 'red',
    });
  });

  it('masks a positional by its name alone: a sensitive name is masked, an innocuous one keeps its value', () => {
    expect(maskParams(ENTRY, { password: 'x', ref: 'web:prod' })).toEqual({
      password: MASKED,
      ref: 'web:prod',
    });
  });

  it('masks a sensitive key when no contract entry exists', () => {
    expect(maskParams(undefined, { 'api-token': 'x', note: 'n' })).toEqual({
      'api-token': MASKED,
      note: 'n',
    });
  });

  it('masks a sensitive key nested in an object or array', () => {
    const out = maskParams(ENTRY, { env: { PASSWORD: 'x', A: '1' }, list: [{ secret: 's' }] });
    expect(out).toEqual({ env: { PASSWORD: MASKED, A: '1' }, list: [{ secret: MASKED }] });
  });

  it('answers from the bundled contract for a real command', () => {
    const entry = getCommand('repo up');
    expect(entry).toBeDefined();
    expect(maskParams(entry, { 'api-token': 'x' })['api-token']).toBe(MASKED);
  });
});
