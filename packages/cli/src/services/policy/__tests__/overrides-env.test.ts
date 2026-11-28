import { describe, expect, it } from 'vitest';
import { parseOptIn, readEnvOverrides } from '../overrides-env.js';

describe('parseOptIn', () => {
  it('grants nothing for an unset, empty or blank value', () => {
    expect(parseOptIn(undefined)).toBeNull();
    expect(parseOptIn('')).toBeNull();
    expect(parseOptIn(' , ')).toBeNull();
  });

  it('reads a trimmed, case-preserving name list', () => {
    expect(parseOptIn(' mail , Web ')).toEqual(['mail', 'Web']);
  });

  it('turns any * entry into a wildcard', () => {
    expect(parseOptIn('*')).toBe('*');
    expect(parseOptIn('mail,*,web')).toBe('*');
  });
});

describe('readEnvOverrides', () => {
  const env = { REDIACC_ALLOW_GRAND_REPO: 'mail', REDIACC_ALLOW_CLUSTER_OPS: '*' };

  it('keeps an opt-in a human set before the agent started', () => {
    expect(readEnvOverrides({ env, isLegitimate: () => true })).toEqual({
      grandRepos: ['mail'],
      clusterOps: '*',
      source: 'env',
    });
  });

  it('drops an opt-in the ancestry walk cannot prove, per variable', () => {
    const legit = (name: string) => name === 'REDIACC_ALLOW_CLUSTER_OPS';
    expect(readEnvOverrides({ env, isLegitimate: legit })).toEqual({
      grandRepos: null,
      clusterOps: '*',
      source: 'env',
    });
  });

  it('reports source none when nothing survives', () => {
    expect(readEnvOverrides({ env, isLegitimate: () => false })).toEqual({
      grandRepos: null,
      clusterOps: null,
      source: 'none',
    });
  });

  it('never asks the ancestry walk about an unset variable', () => {
    const asked: string[] = [];
    readEnvOverrides({
      env: {},
      isLegitimate: (name) => {
        asked.push(name);
        return true;
      },
    });
    expect(asked).toEqual([]);
  });
});
