/**
 * Regression guard for BUG #37's PHYSICS, which outlive the bug itself.
 *
 * Commander binds an option to whichever command DECLARES it, even when the flag
 * trails a subcommand, and `_checkForMissingMandatoryOptions()` walks UP the
 * parent chain. So on an ACTIONABLE PARENT (an `.action()` plus subcommands):
 *   - a `.requiredOption()` fires for the subcommands too, and
 *   - an option declared on both parent and child is captured by the PARENT.
 * That is what broke `repo replicate refresh --name x` (#37).
 *
 * w2b re-keys both families to the repo REF (spec §4.4: ONE set per repo), which
 * dissolves the bug by construction:
 *   - `repo canary` is now a pure GROUP with `create` as a real subcommand, so it
 *     declares no options at all and `--weight` is `--weight` again (no more
 *     `--initial-weight` carry-fix).
 *   - `repo replicate` REMAINS an actionable parent (spec §5.4 keeps the bare
 *     create form), so its physics still bite. These tests pin the two mitigations
 *     that keep it safe: no requiredOption on the parent, and `--debug` reaching a
 *     subcommand's action via optsWithGlobals().
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../services/cluster/repo-replicate-ops.js', () => ({
  refreshReplicaSet: vi.fn(() => Promise.resolve()),
  removeReplicaSet: vi.fn(() => Promise.resolve()),
  replicateRepo: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../services/cluster/repo-replicate.js', () => ({
  getReplicaSetForRepo: vi.fn(() => Promise.resolve({ repo: 'shop' })),
  replicaSetNameFor: (r: string) => `${r}-replicas`,
}));
vi.mock('../../services/cluster/repo-release.js', () => ({
  canarySetNameFor: (r: string) => `${r}-canary`,
  createCanary: vi.fn(() => Promise.resolve()),
  getCanaryForRepo: vi.fn(() => Promise.resolve({ repo: 'shop' })),
  removeCanary: vi.fn(() => Promise.resolve()),
  setCanaryWeight: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../utils/command-policy.js', () => ({
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
  assertCommandPolicy: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: vi.fn((ref: string) =>
    Promise.resolve({
      name: ref,
      repoKey: ref,
      machineName: 'm1',
      kubeCluster: 'prod',
      datastore: 'ds-data',
      tag: 'grand',
    })
  ),
}));

import { removeCanary, setCanaryWeight } from '../../services/cluster/repo-release.js';
import { refreshReplicaSet, removeReplicaSet } from '../../services/cluster/repo-replicate-ops.js';
import { registerRepoCanaryCommands } from '../repo-canary.js';
import { registerRepoReplicateCommands } from '../repo-replicate.js';

/** A bare program carrying only the two re-keyed command families. */
function repoProgram(): Command {
  const program = new Command();
  program.exitOverride();
  const repo = program.command('repo');
  registerRepoReplicateCommands(repo);
  registerRepoCanaryCommands(repo);
  return program;
}

function find(program: Command, ...path: string[]): Command | undefined {
  let cmd: Command | undefined = program;
  for (const name of path) {
    cmd = cmd?.commands.find((c) => c.name() === name);
  }
  return cmd;
}

describe('repo replicate / canary: keyed by the repo ref (spec §4.4)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('routes `repo replicate refresh <ref>` to the child with the ref', async () => {
    await repoProgram().parseAsync(['repo', 'replicate', 'refresh', 'shop'], { from: 'user' });
    expect(refreshReplicaSet).toHaveBeenCalledWith('shop', undefined);
  });

  it('routes `repo replicate remove <ref>` to the child with the ref', async () => {
    await repoProgram().parseAsync(['repo', 'replicate', 'remove', 'shop:test'], { from: 'user' });
    expect(removeReplicaSet).toHaveBeenCalledWith('shop:test', undefined);
  });

  it('routes `repo canary weight <ref> --weight <n>` to the child (natural flag name)', async () => {
    await repoProgram().parseAsync(['repo', 'canary', 'weight', 'shop', '--weight', '50'], {
      from: 'user',
    });
    expect(setCanaryWeight).toHaveBeenCalledWith('shop', 50, undefined);
  });

  it('routes `repo canary remove <ref>` to the child', async () => {
    await repoProgram().parseAsync(['repo', 'canary', 'remove', 'shop'], { from: 'user' });
    expect(removeCanary).toHaveBeenCalledWith('shop', undefined);
  });

  it('neither family carries an identity option any more (--repo/--name/--set are gone)', () => {
    const program = repoProgram();
    for (const path of [
      ['repo', 'replicate'],
      ['repo', 'replicate', 'status'],
      ['repo', 'replicate', 'remove'],
      ['repo', 'replicate', 'refresh'],
      ['repo', 'canary'],
      ['repo', 'canary', 'create'],
      ['repo', 'canary', 'status'],
      ['repo', 'canary', 'weight'],
      ['repo', 'canary', 'remove'],
    ]) {
      const longs = find(program, ...path)?.options.map((o) => o.long) ?? [];
      for (const dead of ['--repo', '--name', '--set', '--cluster', '--initial-weight']) {
        expect(longs, `${path.join(' ')} options`).not.toContain(dead);
      }
    }
  });

  it('every leaf takes the ref positionally', () => {
    const program = repoProgram();
    for (const path of [
      ['repo', 'replicate'],
      ['repo', 'replicate', 'status'],
      ['repo', 'replicate', 'remove'],
      ['repo', 'replicate', 'refresh'],
      ['repo', 'canary', 'create'],
      ['repo', 'canary', 'status'],
      ['repo', 'canary', 'weight'],
      ['repo', 'canary', 'remove'],
    ]) {
      // `registeredArguments` is Commander's public view of `.argument()` calls.
      const args = (
        find(program, ...path) as unknown as { registeredArguments: { name(): string }[] }
      ).registeredArguments;
      expect(
        args.map((a) => a.name()),
        `${path.join(' ')} args`
      ).toEqual(['ref']);
    }
  });

  it('the actionable parent declares NO requiredOption (it would fire on subcommands)', () => {
    // _checkForMissingMandatoryOptions walks up the parent chain, so a mandatory
    // flag here would make `replicate status <ref>` demand --replicas.
    const parent = find(repoProgram(), 'repo', 'replicate');
    expect(parent?.options.filter((o) => o.mandatory)).toEqual([]);
  });

  it('`--debug` on a subcommand still reaches its action (the parent captures the flag)', async () => {
    await repoProgram().parseAsync(['repo', 'replicate', 'refresh', 'shop', '--debug'], {
      from: 'user',
    });
    // Commander binds --debug to `replicate` (it declares it too); optsWithGlobals
    // is what carries it back down. Without that, --debug is silently inert.
    expect(refreshReplicaSet).toHaveBeenCalledWith('shop', true);
  });

  it('preserves trailing global flags (no enablePositionalOptions)', () => {
    const program = new Command();
    program.exitOverride().option('-o, --output <format>', 'output', 'table');
    const repo = program.command('repo');
    let seen: string | undefined;
    repo.command('list').action(() => {
      seen = program.opts().output as string;
    });

    program.parse(['repo', 'list', '-o', 'json'], { from: 'user' });
    expect(seen).toBe('json');
  });
});
