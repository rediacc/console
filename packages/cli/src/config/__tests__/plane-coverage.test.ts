/**
 * Command Plane Coverage
 *
 * Every command the CLI can actually run must declare where it runs. The web
 * console and the proxy read `plane` to decide whether a command may be
 * executed remotely, so an unclassified command is not a missing label — it is
 * a command that reaches those consumers with no answer to "does this touch a
 * machine?".
 *
 * Walks the LIVE Commander tree (the same walker the contract generator uses)
 * and fails when a command resolves no plane, or when the plane map has grown
 * entries that no longer match a real command.
 */
import { describe, expect, it } from 'vitest';
import {
  createDescriptionResolver,
  loadLocale,
  walkContractCommands,
} from '../../../scripts/lib/command-tree-lib.js';
import { cli } from '../../cli.js';
import { COMMAND_PLANES, getCommandPlane, isInteractiveCommand } from '../command-planes.js';

const resolver = createDescriptionResolver(loadLocale('en'));
const COMMANDS = walkContractCommands(cli, resolver);

/** Every command path in the live tree, including non-runnable groups. */
function allTreePaths(): Set<string> {
  const paths = new Set<string>();
  const walk = (cmd: (typeof cli.commands)[number], prefix: string): void => {
    if (cmd.name() === 'help') return;
    const path = prefix ? `${prefix} ${cmd.name()}` : cmd.name();
    paths.add(path);
    for (const sub of cmd.commands) walk(sub, path);
  };
  for (const cmd of cli.commands) walk(cmd, '');
  return paths;
}

describe('command plane coverage', () => {
  it('every runnable command resolves a plane', () => {
    const unresolved: string[] = [];

    for (const cmd of COMMANDS) {
      try {
        getCommandPlane(cmd.pathKey);
      } catch {
        unresolved.push(cmd.pathKey);
      }
    }

    if (unresolved.length > 0) {
      const hint = unresolved
        .map((p) => `  - "${p}": add a plane in command-metadata.ts (or to an ancestor)`)
        .join('\n');
      expect.fail(`${unresolved.length} command(s) resolve no plane:\n${hint}`);
    }
  });

  it('resolves only known planes', () => {
    for (const cmd of COMMANDS) {
      expect(['config', 'machine', 'other']).toContain(getCommandPlane(cmd.pathKey));
    }
  });

  /**
   * A count snapshot, so that moving a command between planes is a deliberate,
   * reviewable edit rather than a silent side effect. Update the numbers when
   * you add a command, and say why in the commit.
   */
  it('plane counts match the recorded distribution', () => {
    const counts = { config: 0, machine: 0, other: 0 };
    for (const cmd of COMMANDS) counts[getCommandPlane(cmd.pathKey)]++;

    // +5 machine: the `rdc job` verbs (list/status/logs/cancel/gc). Each SSHes
    // to a machine to drive `renet job ...` against its detached-job spool.
    expect(COMMANDS.length).toBe(182);
    expect(counts).toEqual({ config: 68, machine: 94, other: 20 });
  });

  it('records the interactive commands', () => {
    const interactive = COMMANDS.filter((c) => isInteractiveCommand(c.pathKey))
      .map((c) => c.pathKey)
      .sort();

    // Commands that need a TTY or never return: an interactive shell, $EDITOR,
    // a tunnel or stream held until Ctrl+C, a browser callback, or a daemon
    // that listens until SIGINT.
    expect(interactive).toEqual([
      'config audit tail',
      'config edit',
      'config field rotate',
      'config remote enable',
      'ops ssh',
      'repo tunnel',
      'serve',
      'term connect',
      'vscode connect',
    ]);
  });

  it('records the machine-plane commands a remote executor could run', () => {
    // These are the candidates for proxying. The contract narrows them further
    // via PROXY_EXCLUSIONS in generate-cli-contract.ts (client-side transfers,
    // and commands whose effect lands in the caller's own config); the exclusion
    // set itself is asserted in the shared cli-contract tests.
    const machineNonInteractive = COMMANDS.filter(
      (c) => getCommandPlane(c.pathKey) === 'machine' && !isInteractiveCommand(c.pathKey)
    ).map((c) => c.pathKey);

    expect(machineNonInteractive).toContain('repo up');

    // The `rdc job` verbs are proxyable too: even `job logs --follow` streams to
    // stdout and ends on its own when the job finishes, so none of them needs a
    // TTY and a headless executor can drive all five.
    expect(machineNonInteractive).toContain('job logs');
    expect(machineNonInteractive.length).toBe(90);
  });

  it('plane and interactive entries all point at real commands', () => {
    const treePaths = allTreePaths();

    const stale = Object.keys(COMMAND_PLANES).filter((path) => !treePaths.has(path));

    if (stale.length > 0) {
      expect.fail(
        `COMMAND_PLANES entries that are not commands in the CLI tree: ${stale.join(', ')}`
      );
    }
  });
});
