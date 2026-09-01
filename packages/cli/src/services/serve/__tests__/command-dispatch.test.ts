/**
 * Turning a request into argv.
 *
 * The loopback drives this over HTTP with a real CLI on both ends. This pins the
 * translation itself, which is the part with edges: a switch is not a value, a
 * variadic repeats, and an option nobody declared is a refusal rather than a
 * shrug.
 */

import type { ContractCommand, ContractPositional } from '@rediacc/shared/cli-contract';
import { CLI_CONTRACT, getCommand } from '@rediacc/shared/cli-contract';
import type { Command } from 'commander';
import { describe, expect, it } from 'vitest';
import { positionalsFromCommand } from '../../executor/proxy-command.js';
import {
  buildArgv,
  buildPositionals,
  CommandRejected,
  prepareCommand,
} from '../command-dispatch.js';

function entryFor(pathKey: string) {
  const entry = getCommand(pathKey);
  if (!entry) throw new Error(`"${pathKey}" is missing from the contract`);
  return entry;
}

/** One synthetic positional, so an argv rule can be tested without a real leaf. */
function pos(name: string, extra: Partial<ContractPositional> = {}): ContractPositional {
  return {
    name,
    kind: 'plain',
    required: false,
    variadic: false,
    descriptionKey: null,
    label: '',
    ...extra,
  };
}

/** A synthetic contract entry carrying the given positionals and nothing else. */
function synthEntry(positionals: ContractPositional[]): ContractCommand {
  return {
    path: ['thing', 'do'],
    pathKey: 'thing do',
    domain: 'thing',
    group: null,
    plane: 'machine',
    descriptionKey: null,
    label: '',
    options: [],
    positionals,
    hasSubcommands: false,
    interactive: false,
    proxyCapable: true,
    detachable: true,
    machineOption: null,
    repoOption: null,
    machinePositional: null,
    repoPositional: null,
  };
}

describe('buildArgv', () => {
  // `repo list` is the flag vehicle here: after the §2.3 reshape the repo verbs
  // that take a `<ref>` require a positional, so they throw "needs <ref>" before
  // any flag logic runs. `repo list` keeps `--machine`/`--cluster` as filters and
  // has NO positional, so it exercises the flag mechanics cleanly.
  it('is the argv a local rdc would have been given', () => {
    const argv = buildArgv(entryFor('repo list'), { machine: 'prod-1' });

    // --output json and --yes are forced, never taken from the caller: the
    // executor has no terminal to render a table into and nobody to answer a
    // prompt. They lead, because they are root options.
    expect(argv.slice(0, 3)).toEqual(['--output', 'json', '--yes']);
    expect(argv).toContain('repo');
    expect(argv).toContain('list');
    expect(argv).toContain('--machine');
    expect(argv).toContain('prod-1');
  });

  it('makes a true switch a bare flag and a false one nothing at all', () => {
    const withSwitch = buildArgv(entryFor('repo list'), {
      machine: 'prod-1',
      'skip-router-restart': true,
    });
    expect(withSwitch).toContain('--skip-router-restart');

    const without = buildArgv(entryFor('repo list'), {
      machine: 'prod-1',
      'skip-router-restart': false,
    });
    // Not `--skip-router-restart false`, which Commander would read as a command.
    expect(without).not.toContain('--skip-router-restart');
    expect(without).not.toContain('false');
  });

  it('refuses a value where a switch belongs', () => {
    expect(() =>
      buildArgv(entryFor('repo list'), { machine: 'prod-1', 'skip-router-restart': 'yes please' })
    ).toThrow(CommandRejected);
  });

  it('refuses an option the command does not declare, and names the ones it does', () => {
    expect(() => buildArgv(entryFor('repo list'), { 'not-an-option': 'x' })).toThrow(
      /has no --not-an-option option\. It accepts: /
    );
  });

  it('refuses an object where text belongs, so nothing can smuggle structure through', () => {
    expect(() => buildArgv(entryFor('repo list'), { machine: { $ne: null } })).toThrow(
      CommandRejected
    );
  });
});

describe('positionals', () => {
  it('emits declared positionals bare, in declared order, between path and flags', () => {
    const entry = synthEntry([pos('ref', { required: true }), pos('extra')]);
    const argv = buildArgv(entry, {}, { ref: 'shop', extra: 'x' });

    // Root leads, then the path, then the bare positionals in declared order.
    expect(argv).toEqual(['--output', 'json', '--yes', 'thing', 'do', 'shop', 'x']);
  });

  it('places positionals before flags, so Commander parses both cleanly', () => {
    const entry = synthEntry([pos('ref', { required: true })]);
    // A flag rides in params; a positional rides in the positionals bag.
    entry.options = [
      {
        flags: '-m, --machine <name>',
        long: 'machine',
        short: 'm',
        valueTaking: true,
        variadic: false,
        mandatory: false,
        defaultValue: null,
        descriptionKey: null,
        label: '',
        tier: 'common',
      },
    ];
    const argv = buildArgv(entry, { machine: 'prod-1' }, { ref: 'shop' });
    expect(argv).toEqual([
      '--output',
      'json',
      '--yes',
      'thing',
      'do',
      'shop',
      '--machine',
      'prod-1',
    ]);
  });

  it('refuses a positional the command does not declare (argv-injection defence)', () => {
    const entry = synthEntry([pos('ref')]);
    expect(() => buildPositionals(entry, { nope: 'x' })).toThrow(/has no nope positional/);
  });

  it('refuses a required positional that was omitted', () => {
    const entry = synthEntry([pos('ref', { required: true })]);
    expect(() => buildPositionals(entry, {})).toThrow(/needs <ref>/);
  });

  it('repeats a variadic positional and refuses many values for a scalar one', () => {
    const variadic = synthEntry([pos('refs', { variadic: true })]);
    expect(buildPositionals(variadic, { refs: ['a', 'b', 'c'] })).toEqual(['a', 'b', 'c']);

    const scalar = synthEntry([pos('ref')]);
    expect(() => buildPositionals(scalar, { ref: ['a', 'b'] })).toThrow(/takes a single value/);
  });

  it('reads positionals off a parsed command index-for-index, skipping the empty ones', () => {
    const entry = synthEntry([pos('ref', { required: true }), pos('rest', { variadic: true })]);

    // processedArgs is what Commander fills, aligned with registeredArguments and
    // therefore with entry.positionals: index 0 is <ref>, index 1 is [rest...].
    const withBoth = { processedArgs: ['shop', ['a', 'b']] } as unknown as Command;
    expect(positionalsFromCommand(entry, withBoth)).toEqual({ ref: 'shop', rest: ['a', 'b'] });

    // An empty variadic contributes nothing, so it does not travel as [].
    const emptyRest = { processedArgs: ['shop', []] } as unknown as Command;
    expect(positionalsFromCommand(entry, emptyRest)).toEqual({ ref: 'shop' });
  });
});

describe('prepareCommand', () => {
  it('refuses a command that does not exist', () => {
    expect(() => prepareCommand('repo nonsense', {})).toThrow(/no "rdc repo nonsense" command/i);
  });

  it('accepts a machine-plane command and hands back its argv', () => {
    // repo status <ref>: the repo rides the positionals bag; the machine is derived.
    const prepared = prepareCommand('repo status', {}, { ref: 'demo' });

    expect(prepared.entry.pathKey).toBe('repo status');
    expect(prepared.argv).toContain('status');
    expect(prepared.argv).toContain('demo');
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
    // (sync now takes a positional <ref>; the machine is derived, so only the
    // client-side --local path remains as a flag.)
    ['repo sync upload', { local: '/root/.ssh/id_rsa' }],
    ['repo sync download', { local: '/tmp/exfil' }],
    ['storage import', { file: '/etc/passwd' }],
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
    expect(() => prepareCommand('repo status', {}, { ref: 'demo' })).not.toThrow();
  });
});
