import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { isGrandEnvWildcard, isRepoAllowedByGrandEnv } from '../grand-env.js';

describe('grand-env', () => {
  beforeEach(() => {
    delete process.env.REDIACC_ALLOW_GRAND_REPO;
  });

  afterEach(() => {
    delete process.env.REDIACC_ALLOW_GRAND_REPO;
  });

  describe('isRepoAllowedByGrandEnv', () => {
    it('returns false when unset', () => {
      expect(isRepoAllowedByGrandEnv('mail')).toBe(false);
    });

    it('returns false for empty string', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = '';
      expect(isRepoAllowedByGrandEnv('mail')).toBe(false);
    });

    it('returns true for wildcard', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = '*';
      expect(isRepoAllowedByGrandEnv('mail')).toBe(true);
      expect(isRepoAllowedByGrandEnv('anything')).toBe(true);
    });

    it('matches a single repo name', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
      expect(isRepoAllowedByGrandEnv('mail')).toBe(true);
      expect(isRepoAllowedByGrandEnv('other')).toBe(false);
    });

    it('matches any entry in a comma-separated list', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail,web,gitlab';
      expect(isRepoAllowedByGrandEnv('mail')).toBe(true);
      expect(isRepoAllowedByGrandEnv('web')).toBe(true);
      expect(isRepoAllowedByGrandEnv('gitlab')).toBe(true);
      expect(isRepoAllowedByGrandEnv('nextcloud')).toBe(false);
    });

    it('trims whitespace around list entries', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = ' mail , web ';
      expect(isRepoAllowedByGrandEnv('mail')).toBe(true);
      expect(isRepoAllowedByGrandEnv('web')).toBe(true);
    });

    it('is case-sensitive', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = 'Mail';
      expect(isRepoAllowedByGrandEnv('mail')).toBe(false);
      expect(isRepoAllowedByGrandEnv('Mail')).toBe(true);
    });

    it('treats `*` in a list as wildcard', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail,*,web';
      expect(isRepoAllowedByGrandEnv('anything')).toBe(true);
      expect(isRepoAllowedByGrandEnv('mail')).toBe(true);
    });

    it('ignores empty entries from stray commas', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = ',,mail,';
      expect(isRepoAllowedByGrandEnv('mail')).toBe(true);
      expect(isRepoAllowedByGrandEnv('other')).toBe(false);
    });

    it('returns false for only commas', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = ',,,';
      expect(isRepoAllowedByGrandEnv('mail')).toBe(false);
    });
  });

  describe('isGrandEnvWildcard', () => {
    it('returns false when unset', () => {
      expect(isGrandEnvWildcard()).toBe(false);
    });

    it('returns false for empty string', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = '';
      expect(isGrandEnvWildcard()).toBe(false);
    });

    it('returns true for `*`', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = '*';
      expect(isGrandEnvWildcard()).toBe(true);
    });

    it('returns false for a single repo name', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
      expect(isGrandEnvWildcard()).toBe(false);
    });

    it('returns false for a list without `*`', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail,web,gitlab';
      expect(isGrandEnvWildcard()).toBe(false);
    });

    it('returns true when `*` is one of the list entries', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail,*,web';
      expect(isGrandEnvWildcard()).toBe(true);
    });

    it('trims whitespace around `*`', () => {
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail, * , web';
      expect(isGrandEnvWildcard()).toBe(true);
    });
  });
});
