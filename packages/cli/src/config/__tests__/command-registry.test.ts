import { describe, expect, it } from 'vitest';
import { cli } from '../../cli.js';
import { COMMAND_DOMAINS, COMMAND_REGISTRY, getCommandDef } from '../command-registry.js';

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
    /**
     * The registry must name EVERY top-level command, and only real ones.
     *
     * It had drifted to 14 entries against 18 live domains — `cluster`, `credits`,
     * `job` and `serve` were in no entry at all. That is not cosmetic: the MCP
     * coverage check used to iterate the REGISTRY, so a domain missing from it was
     * not merely ungrouped, it was UNCHECKED. Every leaf beneath it could drift out
     * of MCP with nothing failing, which is exactly how `serve` reached main
     * carrying no command metadata of any kind.
     *
     * Asserted in BOTH directions: a missing entry hides commands from the checks
     * that read the registry, and a leftover entry describes a command that is gone.
     */
    it('names every top-level command, and only real ones', () => {
      const live = new Set(cli.commands.map((c) => c.name()).filter((n) => n !== 'help'));
      const registered = new Set(COMMAND_REGISTRY.map((d) => d.name));

      const unregistered = [...live].filter((name) => !registered.has(name)).sort();
      const orphaned = [...registered].filter((name) => !live.has(name)).sort();

      expect({ unregistered, orphaned }).toEqual({ unregistered: [], orphaned: [] });
    });

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
      // `health` is a registry entry but carries no gating any more — it used to
      // be experimental, which made `rdc machine health` answer "unknown
      // command" unless an env var was set, so the one command that aggregates
      // machine issues was the one nobody could run.
      expect(def?.subcommands?.health).toBeDefined();
      // containers/services/repos were folded into `machine status --containers` etc.
      // by the P4 reshape. A registry entry for a command that no longer exists is a
      // name waiting to be silently re-bound, so it must stay gone.
      expect(def?.subcommands?.containers).toBeUndefined();
      expect(def?.subcommands?.services).toBeUndefined();
      expect(def?.subcommands?.repos).toBeUndefined();
    });
  });
});
