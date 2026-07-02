import { describe, expect, it } from 'vitest';
import {
  COMMAND_DOMAINS,
  COMMAND_REGISTRY,
  getCommandDef,
  isExperimentalEnabled,
} from '../command-registry.js';

describe('config/command-registry', () => {
  describe('getCommandDef', () => {
    it('finds existing commands', () => {
      expect(getCommandDef('machine')).toBeDefined();
      expect(getCommandDef('repo')).toBeDefined();
      expect(getCommandDef('config')).toBeDefined();
    });

    it('returns undefined for unknown commands', () => {
      expect(getCommandDef('nonexistent')).toBeUndefined();
    });

    it('has no leftover cloud-era commands', () => {
      for (const name of [
        'auth',
        'team',
        'region',
        'bridge',
        'organization',
        'user',
        'permission',
        'audit',
        'ceph',
        'repository',
        'queue',
        'protocol',
      ]) {
        expect(getCommandDef(name)).toBeUndefined();
      }
    });
  });

  describe('registry shape', () => {
    it('every entry has a valid domain', () => {
      for (const def of COMMAND_REGISTRY) {
        expect(Object.keys(COMMAND_DOMAINS)).toContain(def.domain);
      }
    });

    it('entry names are unique', () => {
      const names = COMMAND_REGISTRY.map((d) => d.name);
      expect(new Set(names).size).toBe(names.length);
    });

    it('machine experimental subcommands are declared', () => {
      const def = getCommandDef('machine');
      expect(def?.subcommands?.containers.experimental).toBe(true);
      expect(def?.subcommands?.health.experimental).toBe(true);
    });
  });

  describe('isExperimentalEnabled', () => {
    it('reflects REDIACC_EXPERIMENTAL env var', () => {
      const prev = process.env.REDIACC_EXPERIMENTAL;
      try {
        process.env.REDIACC_EXPERIMENTAL = '1';
        expect(isExperimentalEnabled()).toBe(true);
        delete process.env.REDIACC_EXPERIMENTAL;
        expect(isExperimentalEnabled()).toBe(false);
      } finally {
        if (prev === undefined) {
          delete process.env.REDIACC_EXPERIMENTAL;
        } else {
          process.env.REDIACC_EXPERIMENTAL = prev;
        }
      }
    });
  });
});
