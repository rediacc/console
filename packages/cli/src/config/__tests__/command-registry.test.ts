import { describe, expect, it } from 'vitest';
import {
  ALL_MODES,
  COMMAND_REGISTRY,
  SELF_HOSTED_MODES,
  formatModeTag,
  getCommandDef,
} from '../command-registry.js';

describe('config/command-registry', () => {
  describe('formatModeTag', () => {
    it('returns [cloud|local|s3] for all-modes', () => {
      expect(formatModeTag(ALL_MODES)).toBe('[cloud|local|s3]');
    });

    it('returns [cloud] for cloud-only', () => {
      expect(formatModeTag(['cloud'])).toBe('[cloud]');
    });

    it('returns [local|s3] for self-hosted modes', () => {
      expect(formatModeTag(SELF_HOSTED_MODES)).toBe('[local|s3]');
    });
  });

  describe('getCommandDef', () => {
    it('finds existing commands', () => {
      expect(getCommandDef('auth')).toBeDefined();
      expect(getCommandDef('machine')).toBeDefined();
      expect(getCommandDef('repo')).toBeDefined();
    });

    it('returns undefined for unknown commands', () => {
      expect(getCommandDef('nonexistent')).toBeUndefined();
    });
  });

  describe('mode assignments', () => {
    const cloudOnly = [
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
    ];

    const localS3Only = ['repo', 'snapshot'];

    const allModes = [
      'machine',
      'storage',
      'run',
      'sync',
      'term',
      'backup',
      'context',
      'doctor',
      'update',
      'protocol',
      'vscode',
    ];

    for (const name of cloudOnly) {
      it(`"${name}" is cloud-only`, () => {
        const def = getCommandDef(name);
        expect(def).toBeDefined();
        expect(def!.modes).toEqual(['cloud']);
      });
    }

    for (const name of localS3Only) {
      it(`"${name}" is local|s3 only`, () => {
        const def = getCommandDef(name);
        expect(def).toBeDefined();
        expect(def!.modes).toEqual(SELF_HOSTED_MODES);
      });
    }

    for (const name of allModes) {
      it(`"${name}" supports all modes`, () => {
        const def = getCommandDef(name);
        expect(def).toBeDefined();
        expect(def!.modes).toEqual(ALL_MODES);
      });
    }
  });

  describe('subcommand overrides', () => {
    it('machine assign-bridge is cloud-only', () => {
      const def = getCommandDef('machine');
      expect(def?.subcommands?.['assign-bridge']?.modes).toEqual(['cloud']);
    });

    it('machine test-connection is cloud-only', () => {
      const def = getCommandDef('machine');
      expect(def?.subcommands?.['test-connection']?.modes).toEqual(['cloud']);
    });

    it('storage browse is local|s3', () => {
      const def = getCommandDef('storage');
      expect(def?.subcommands?.browse?.modes).toEqual(SELF_HOSTED_MODES);
    });

    it('backup sync is local|s3', () => {
      const def = getCommandDef('backup');
      expect(def?.subcommands?.sync?.modes).toEqual(SELF_HOSTED_MODES);
    });

    it('backup schedule is local|s3', () => {
      const def = getCommandDef('backup');
      expect(def?.subcommands?.schedule?.modes).toEqual(SELF_HOSTED_MODES);
    });
  });

  describe('registry completeness', () => {
    it('has no duplicate command names', () => {
      const names = COMMAND_REGISTRY.map((c) => c.name);
      const unique = new Set(names);
      expect(names.length).toBe(unique.size);
    });

    it('every command has a valid domain', () => {
      const validDomains = ['INFRASTRUCTURE', 'REPOSITORIES', 'EXECUTION', 'ORGANIZATION', 'TOOLS'];
      for (const cmd of COMMAND_REGISTRY) {
        expect(validDomains).toContain(cmd.domain);
      }
    });
  });
});
