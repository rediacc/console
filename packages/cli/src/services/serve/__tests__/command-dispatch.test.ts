/**
 * Turning a request into argv.
 *
 * The loopback drives this over HTTP with a real CLI on both ends. This pins the
 * translation itself, which is the part with edges: a switch is not a value, a
 * variadic repeats, and an option nobody declared is a refusal rather than a
 * shrug.
 */

import { CLI_CONTRACT, getCommand } from '@rediacc/shared/cli-contract';
import { describe, expect, it } from 'vitest';
import { buildArgv, CommandRejected, prepareCommand } from '../command-dispatch.js';

function entryFor(pathKey: string) {
  const entry = getCommand(pathKey);
  if (!entry) throw new Error(`"${pathKey}" is missing from the contract`);
  return entry;
}

describe('buildArgv', () => {
  it('is the argv a local rdc would have been given', () => {
    const argv = buildArgv(entryFor('repo status'), { name: 'demo', machine: 'prod-1' });

    // --output json and --yes are forced, never taken from the caller: the
    // executor has no terminal to render a table into and nobody to answer a
    // prompt. They lead, because they are root options.
    expect(argv.slice(0, 3)).toEqual(['--output', 'json', '--yes']);
    expect(argv).toContain('repo');
    expect(argv).toContain('status');
    expect(argv).toContain('--name');
    expect(argv).toContain('demo');
  });

  it('makes a true switch a bare flag and a false one nothing at all', () => {
    const withSwitch = buildArgv(entryFor('repo status'), {
      name: 'demo',
      'skip-router-restart': true,
    });
    expect(withSwitch).toContain('--skip-router-restart');

    const without = buildArgv(entryFor('repo status'), {
      name: 'demo',
      'skip-router-restart': false,
    });
    // Not `--skip-router-restart false`, which Commander would read as a command.
    expect(without).not.toContain('--skip-router-restart');
    expect(without).not.toContain('false');
  });

  it('refuses a value where a switch belongs', () => {
    expect(() =>
      buildArgv(entryFor('repo status'), { name: 'demo', 'skip-router-restart': 'yes please' })
    ).toThrow(CommandRejected);
  });

  it('refuses an option the command does not declare, and names the ones it does', () => {
    expect(() => buildArgv(entryFor('repo status'), { 'not-an-option': 'x' })).toThrow(
      /has no --not-an-option option\. It accepts: /
    );
  });

  it('refuses an object where text belongs, so nothing can smuggle structure through', () => {
    expect(() => buildArgv(entryFor('repo status'), { name: { $ne: null } })).toThrow(
      CommandRejected
    );
  });
});

describe('prepareCommand', () => {
  it('refuses a command that does not exist', () => {
    expect(() => prepareCommand('repo nonsense', {})).toThrow(/no "rdc repo nonsense" command/i);
  });

  it('accepts a machine-plane command and hands back its argv', () => {
    const prepared = prepareCommand('repo status', { name: 'demo', machine: 'prod-1' });

    expect(prepared.entry.pathKey).toBe('repo status');
    expect(prepared.argv).toContain('status');
  });
});

describe('prepareCommand enforces proxyCapable (SEC-1)', () => {
  // The executor must refuse every command the contract marks non-proxyable, not
  // just interactive and `other`-plane ones. The client's --proxy refusal is
  // advisory: a request can reach /v1/command without going through the CLI, so
  // this is where the boundary actually holds. Each of these would, if it ran on
  // the executor, act on the executor's own host or hand back its held secrets.

  it.each([
    // config plane: returns the executor's OWN decrypted config in plaintext.
    ['config ssh show', {}], // the executor's SSH private key
    ['config show', {}],
    // client-side transfer: the paths are the EXECUTOR's filesystem when proxied.
    ['repo sync upload', { machine: 'm', repository: 'r', local: '/root/.ssh/id_rsa' }],
    ['repo sync download', { machine: 'm', repository: 'r', local: '/tmp/exfil' }],
    ['config storage import', { file: '/etc/passwd' }],
    // interactive: would hang a request forever holding a slot.
    ['term connect', { machine: 'm' }],
    // other plane: acts on the executor process, not on infrastructure.
    ['update', {}],
  ])('refuses %s, however the policy is written', (pathKey, params) => {
    const entry = getCommand(pathKey);
    if (!entry) throw new Error(`"${pathKey}" is missing from the contract`);
    // Guard the premise: these are exactly the commands the contract says are
    // not proxyable. If one flips to proxyCapable, this test should be revisited,
    // not silently pass.
    expect(entry.proxyCapable).toBe(false);
    expect(() => prepareCommand(pathKey, params)).toThrow(CommandRejected);
  });

  it('refuses EVERY non-proxyable command in the contract, with a reason', () => {
    // The exhaustive version of the cases above: no non-proxyable command is
    // dispatchable, and each refusal carries the contract's own explanation.
    for (const entry of CLI_CONTRACT.commands) {
      if (entry.proxyCapable) continue;
      let rejected: unknown;
      try {
        prepareCommand(entry.pathKey, {});
      } catch (error) {
        rejected = error;
      }
      expect(rejected, `${entry.pathKey} should be refused`).toBeInstanceOf(CommandRejected);
      expect((rejected as CommandRejected).message.length).toBeGreaterThan(0);
    }
  });

  it('still accepts a proxyable machine-plane command', () => {
    expect(() => prepareCommand('repo status', { name: 'demo', machine: 'prod-1' })).not.toThrow();
  });
});
