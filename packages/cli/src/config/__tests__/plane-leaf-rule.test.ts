/**
 * Per-leaf plane rule (Rule 3) — driven in BOTH directions.
 *
 * The domain-granular plane gate cannot see the mistake this codebase actually
 * makes. A config-only leaf relocated into a machine-reaching noun inherits that
 * noun's `machine` default and becomes proxyCapable: Rule 1 does not fire (the
 * noun really does reach machines), Rule 2 does not fire (the noun has dozens of
 * other machine leaves), and no stale-entry test fires (there was no entry to go
 * stale). Bug #51 shipped through exactly that gap — `repo admin archive
 * {list,restore,purge}` claimed plane `machine` after moving out of `config`,
 * which would have let a proxied `archive purge` permanently delete the PROXY
 * HOST's archived records instead of the caller's.
 *
 * So this file does not merely assert the tree is clean today. It asserts the
 * rule can FAIL, by handing it a leaf that is deliberately mis-planed and
 * requiring a violation naming that leaf. A rule only ever observed to pass is
 * not a control, and that is the finding this whole phase turns on.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  createReachability,
  evaluateLeafPlanes,
  instrumentRegistration,
  type LeafPlaneClaim,
  leafModules,
} from '../../../scripts/lib/plane-rules.js';

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

// Commander must be patched before the CLI registers anything, so every import
// that pulls in the command tree has to be dynamic and has to come after this.
const registeredIn = instrumentRegistration(SRC);

const { cli } = await import('../../cli.js');
const { getCommandPlane } = await import('../command-planes.js');
const { createDescriptionResolver, loadLocale, walkContractCommands } = await import(
  '../../../scripts/lib/command-tree-lib.js'
);

const reachOf = createReachability(SRC);
const commands = walkContractCommands(cli, createDescriptionResolver(loadLocale('en')));
const modules = leafModules(cli, registeredIn);

const realClaims: LeafPlaneClaim[] = commands.map((cmd) => ({
  pathKey: cmd.pathKey,
  plane: getCommandPlane(cmd.pathKey),
  module: modules.get(cmd.pathKey) ?? null,
}));

describe('per-leaf plane rule', () => {
  it('attributes every leaf to a source module', () => {
    // An unattributable leaf is one the rule cannot judge, and a machine-plane
    // claim nobody judges is the hole this rule exists to close. Fail loudly
    // rather than skipping: if Commander ever changes how it records
    // registration, this is the assertion that says so.
    const orphans = realClaims.filter((c) => !c.module).map((c) => c.pathKey);
    expect(orphans).toEqual([]);
  });

  it('greens on the real tree', () => {
    expect(evaluateLeafPlanes(realClaims, reachOf)).toEqual([]);
  });

  it('reds when a config-only leaf claims the machine plane (bug #51, reconstructed)', () => {
    // repo-admin.ts imports no executor and no SSH: the archive leaves only read
    // and write the caller's config archive map. Claiming `machine` for one is
    // precisely the relocation mistake, so the rule must refuse it.
    const misPlaned = realClaims.map((claim) =>
      claim.pathKey === 'repo admin archive purge' ? { ...claim, plane: 'machine' } : claim
    );

    const violations = evaluateLeafPlanes(misPlaned, reachOf);

    expect(violations).toHaveLength(1);
    expect(violations[0]).toContain('repo admin archive purge');
    expect(violations[0]).toContain('commands/repo-admin.ts');
    expect(violations[0]).toContain('proxyCapable');
  });

  it('reds on a leaf it cannot attribute', () => {
    const violations = evaluateLeafPlanes(
      [{ pathKey: 'ghost leaf', plane: 'machine', module: null }],
      reachOf
    );

    expect(violations).toHaveLength(1);
    expect(violations[0]).toContain('could not be attributed');
  });

  it('accepts a machine claim from a module that really reaches a machine', () => {
    // The rule must not simply refuse every machine claim: `repo up` is honestly
    // machine-plane, and a rule that reds on it would be noise, not a control.
    const repoUp = realClaims.find((c) => c.pathKey === 'repo up');
    expect(repoUp?.plane).toBe('machine');
    expect(evaluateLeafPlanes(repoUp ? [repoUp] : [], reachOf)).toEqual([]);
  });
});
