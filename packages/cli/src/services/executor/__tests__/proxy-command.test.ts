/**
 * The `--proxy` client, at the two seams the loopback cannot reach cheaply.
 *
 * The loopback proves the whole path end to end. These pin the two pieces of it
 * that are easy to get subtly wrong and expensive to provoke over HTTP: turning a
 * parsed command back into wire params, and what happens when the executor's
 * stream ends badly.
 */

import { getCommand } from '@rediacc/shared/cli-contract';
import { Command } from 'commander';
import { describe, expect, it } from 'vitest';
import {
  ProxyClient,
  ProxyStreamTruncatedError,
  ProxyVersionMismatchError,
} from '../proxy-client.js';
import { assertProxyCapable, paramsFromCommand } from '../proxy-command.js';

/** Parse argv with a throwaway Commander tree and hand back the action command. */
function parse(argv: string[]): Command {
  const program = new Command();
  let seen: Command | undefined;
  program
    .command('status')
    .option('--name <name>', 'name')
    .option('-m, --machine <name>', 'machine')
    .option('--skip-router-restart', 'switch')
    .option('--debug', 'switch')
    .option('--exclude <patterns...>', 'variadic')
    .action((_options, command: Command) => {
      seen = command;
    });
  program.parse(argv, { from: 'user' });
  if (!seen) throw new Error('command did not run');
  return seen;
}

/** The contract entry for a real command, so the test speaks the same list the wire does. */
const REPO_STATUS = getCommand('repo status');

describe('paramsFromCommand', () => {
  it('keys options by their long flag, not by the name Commander stores them under', () => {
    const entry = getCommand('repo status');
    if (!entry) throw new Error('repo status is missing from the contract');

    const params = paramsFromCommand(entry, parse(['status', '--name', 'demo', '-m', 'prod-1']));

    expect(params).toEqual({ name: 'demo', machine: 'prod-1' });
  });

  it('turns a camelCased switch back into the flag the contract declares', () => {
    const entry = getCommand('repo status');
    if (!entry) throw new Error('repo status is missing from the contract');

    // Commander stores --skip-router-restart as `skipRouterRestart`. The executor
    // validates against the contract, which knows it as `skip-router-restart`.
    const params = paramsFromCommand(
      entry,
      parse(['status', '--name', 'demo', '--skip-router-restart'])
    );

    expect(params['skip-router-restart']).toBe(true);
    expect(params).not.toHaveProperty('skipRouterRestart');
  });

  it('sends nothing for a switch the operator did not pass', () => {
    const entry = getCommand('repo status');
    if (!entry) throw new Error('repo status is missing from the contract');

    const params = paramsFromCommand(entry, parse(['status', '--name', 'demo']));

    // Absent, not `false`: the audit record should say what was asked for.
    expect(params).not.toHaveProperty('debug');
    expect(params).not.toHaveProperty('skip-router-restart');
  });

  it('never sends an option the command does not declare', () => {
    const entry = getCommand('repo status');
    if (!entry) throw new Error('repo status is missing from the contract');

    // The command command carries a value the contract does not know about. Only
    // declared options are read, so it cannot travel.
    const command = parse(['status', '--name', 'demo']);
    command.setOptionValue('somethingElse', 'smuggled');

    const params = paramsFromCommand(entry, command);

    expect(Object.values(params)).not.toContain('smuggled');
  });
});

describe('assertProxyCapable', () => {
  it('refuses a command the contract says cannot be proxied, with its own reason', () => {
    expect(() => assertProxyCapable('term connect', false, 'It needs your terminal.')).toThrow(
      'It needs your terminal.'
    );
  });

  it('allows one the contract cleared', () => {
    expect(() => assertProxyCapable('repo status', true)).not.toThrow();
  });
});

describe('ProxyClient', () => {
  function clientWith(fetchImpl: typeof fetch): ProxyClient {
    return new ProxyClient({
      baseUrl: 'https://executor.test',
      getToken: () => Promise.resolve('rdt_token'),
      contractVersion: 'contract-v1',
      fetchImpl,
    });
  }

  function ndjson(lines: unknown[]): Response {
    const body = lines.map((line) => `${JSON.stringify(line)}\n`).join('');
    return new Response(body, { status: 200 });
  }

  it('reports a contract disagreement as one, rather than as a mystery failure', async () => {
    const client = clientWith(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            error: 'contract_version_mismatch',
            clientContractVersion: 'contract-v1',
            executorContractVersion: 'contract-v9',
            executorCliVersion: '9.9.9',
          }),
          { status: 409, headers: { 'content-type': 'application/json' } }
        )
      )
    );

    await expect(client.run('repo status', {}, () => {})).rejects.toThrow(
      ProxyVersionMismatchError
    );
  });

  it('refuses to call a truncated stream a success', async () => {
    // The executor died mid-operation: events arrived, a result never did. The
    // work may still be running on the machine, so reporting success here would
    // be the worst possible lie.
    const client = clientWith(() =>
      Promise.resolve(ndjson([{ kind: 'event', event: { type: 'step_start', name: 'snapshot' } }]))
    );

    await expect(client.run('repo status', {}, () => {})).rejects.toThrow(
      ProxyStreamTruncatedError
    );
    await expect(client.run('repo status', {}, () => {})).rejects.toThrow(/may still be running/i);
  });

  it('sends the command path and its params, and nothing else', async () => {
    let sent: unknown;
    const client = clientWith((_url, init) => {
      sent = JSON.parse(String(init?.body));
      return Promise.resolve(
        ndjson([
          { kind: 'result', result: { success: true, exitCode: 0, durationMs: 1 }, stdout: 'ok' },
        ])
      );
    });

    const outcome = await client.run('repo status', { name: 'demo' }, () => {});

    expect(sent).toEqual({
      contractVersion: 'contract-v1',
      pathKey: 'repo status',
      params: { name: 'demo' },
    });
    // No function name, no machine address, no key, no config: the executor
    // derives everything else from the command itself.
    expect(JSON.stringify(sent)).not.toContain('functionName');
    expect(outcome.stdout).toBe('ok');
  });

  it('is pointed at a command the contract actually has', () => {
    // Guards the fixtures above: a rename would otherwise quietly gut this file.
    expect(REPO_STATUS).toBeDefined();
  });
});
