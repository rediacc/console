import { describe, expect, it } from 'vitest';
import {
  ALL_MODES,
  COMMAND_REGISTRY,
  getCommandDef,
  SELF_HOSTED_MODES,
} from '../command-registry.js';

describe('config/command-registry', () => {
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
      'protocol',
    ];

    const localOnly = ['repo', 'ops'];

    const allModes = [
      'machine',
      'storage',
      'run',
      'sync',
      'term',
      'config',
      'doctor',
      'update',
      'vscode',
      'store',
      'agent',
      'mcp',
    ];

    for (const name of cloudOnly) {
      it(`"${name}" is cloud-only`, () => {
        const def = getCommandDef(name);
        expect(def).toBeDefined();
        expect(def!.modes).toEqual(['cloud']);
      });
    }

    for (const name of localOnly) {
      it(`"${name}" is local only`, () => {
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

    it('storage browse is local', () => {
      const def = getCommandDef('storage');
      expect(def?.subcommands?.browse.modes).toEqual(SELF_HOSTED_MODES);
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
