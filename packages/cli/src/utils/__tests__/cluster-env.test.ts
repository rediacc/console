import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { isClusterAllowedByEnv, isClusterEnvWildcard } from '../cluster-env.js';

describe('cluster-env', () => {
  beforeEach(() => {
    delete process.env.REDIACC_ALLOW_CLUSTER_OPS;
  });

  afterEach(() => {
    delete process.env.REDIACC_ALLOW_CLUSTER_OPS;
  });

  describe('isClusterAllowedByEnv', () => {
    it('returns false when unset', () => {
      expect(isClusterAllowedByEnv('prod')).toBe(false);
    });

    it('returns false for empty string', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = '';
      expect(isClusterAllowedByEnv('prod')).toBe(false);
    });

    it('returns true for wildcard', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = '*';
      expect(isClusterAllowedByEnv('prod')).toBe(true);
      expect(isClusterAllowedByEnv('anything')).toBe(true);
    });

    it('matches a single cluster name', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod';
      expect(isClusterAllowedByEnv('prod')).toBe(true);
      expect(isClusterAllowedByEnv('other')).toBe(false);
    });

    it('matches any entry in a comma-separated list', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod,edge,staging';
      expect(isClusterAllowedByEnv('prod')).toBe(true);
      expect(isClusterAllowedByEnv('edge')).toBe(true);
      expect(isClusterAllowedByEnv('staging')).toBe(true);
      expect(isClusterAllowedByEnv('dev')).toBe(false);
    });

    it('trims whitespace around list entries', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = ' prod , edge ';
      expect(isClusterAllowedByEnv('prod')).toBe(true);
      expect(isClusterAllowedByEnv('edge')).toBe(true);
    });

    it('is case-sensitive', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'Prod';
      expect(isClusterAllowedByEnv('prod')).toBe(false);
      expect(isClusterAllowedByEnv('Prod')).toBe(true);
    });

    it('treats `*` in a list as wildcard', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod,*,edge';
      expect(isClusterAllowedByEnv('anything')).toBe(true);
      expect(isClusterAllowedByEnv('prod')).toBe(true);
    });

    it('ignores empty entries from stray commas', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = ',,prod,';
      expect(isClusterAllowedByEnv('prod')).toBe(true);
      expect(isClusterAllowedByEnv('other')).toBe(false);
    });

    it('returns false for only commas', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = ',,,';
      expect(isClusterAllowedByEnv('prod')).toBe(false);
    });
  });

  describe('isClusterEnvWildcard', () => {
    it('returns false when unset', () => {
      expect(isClusterEnvWildcard()).toBe(false);
    });

    it('returns false for empty string', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = '';
      expect(isClusterEnvWildcard()).toBe(false);
    });

    it('returns true for `*`', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = '*';
      expect(isClusterEnvWildcard()).toBe(true);
    });

    it('returns false for a single cluster name', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod';
      expect(isClusterEnvWildcard()).toBe(false);
    });

    it('returns false for a list without `*`', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod,edge,staging';
      expect(isClusterEnvWildcard()).toBe(false);
    });

    it('returns true when `*` is one of the list entries', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod,*,edge';
      expect(isClusterEnvWildcard()).toBe(true);
    });

    it('trims whitespace around `*`', () => {
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod, * , edge';
      expect(isClusterEnvWildcard()).toBe(true);
    });
  });
});
