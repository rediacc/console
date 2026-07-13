/**
 * The `--proxy` client, at the two seams the loopback cannot reach cheaply.
 *
 * The loopback proves the whole path end to end. These pin the two pieces of it
 * that are easy to get subtly wrong and expensive to provoke over HTTP: turning a
 * parsed command back into wire params, and what happens when the executor's
 * stream ends badly.
 */

import { getCommand } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import { Command } from 'commander';
import { describe, expect, it } from 'vitest';
import {
  ProxyClient,
  ProxyStreamTruncatedError,
  ProxyVersionMismatchError,
} from '../proxy-client.js';
import { assertDetachable, assertProxyCapable, paramsFromCommand } from '../proxy-command.js';

/**
 * Parse argv with a throwaway Commander tree and hand back the action command.
 * Modelled on `repo cat <ref>` — after the §2.3 reshape the repo verbs derive
 * their machine, so the flags that still travel are value flags (--remote-file,
 * --max-bytes) and switches (--stat, --skip-router-restart), not `-m`/`--name`.
 */
function parse(argv: string[]): Command {
  const program = new Command();
  let seen: Command | undefined;
  program
    .command('cat')
    .argument('<ref>')
    .option('--remote-file <path>', 'value')
    .option('--max-bytes <n>', 'value')
    .option('--stat', 'switch')
    .option('--skip-router-restart', 'switch')
    .option('--debug', 'switch')
    .action((_ref, _options, command: Command) => {
      seen = command;
    });
  program.parse(argv, { from: 'user' });
  if (!seen) throw new Error('command did not run');
  return seen;
}

/** The contract entry for a real command, so the test speaks the same list the wire does. */
const REPO_CAT = getCommand('repo cat');

describe('paramsFromCommand', () => {
  it('keys options by their long flag, not by the name Commander stores them under', () => {
    const entry = getCommand('repo cat');
    if (!entry) throw new Error('repo cat is missing from the contract');

    const params = paramsFromCommand(
      entry,
      parse(['cat', 'shop', '--remote-file', '/etc/hostname', '--max-bytes', '100'])
    );

    expect(params).toEqual({ 'remote-file': '/etc/hostname', 'max-bytes': '100' });
  });

  it('turns a camelCased switch back into the flag the contract declares', () => {
    const entry = getCommand('repo cat');
    if (!entry) throw new Error('repo cat is missing from the contract');

    // Commander stores --skip-router-restart as `skipRouterRestart`. The executor
    // validates against the contract, which knows it as `skip-router-restart`.
    const params = paramsFromCommand(
      entry,
      parse(['cat', 'shop', '--remote-file', '/etc/hostname', '--skip-router-restart'])
    );

    expect(params['skip-router-restart']).toBe(true);
    expect(params).not.toHaveProperty('skipRouterRestart');
  });

  it('sends nothing for a switch the operator did not pass', () => {
    const entry = getCommand('repo cat');
    if (!entry) throw new Error('repo cat is missing from the contract');

    const params = paramsFromCommand(
      entry,
      parse(['cat', 'shop', '--remote-file', '/etc/hostname'])
    );

    // Absent, not `false`: the audit record should say what was asked for.
    expect(params).not.toHaveProperty('debug');
    expect(params).not.toHaveProperty('skip-router-restart');
    expect(params).not.toHaveProperty('stat');
  });

  it('never sends an option the command does not declare', () => {
    const entry = getCommand('repo cat');
    if (!entry) throw new Error('repo cat is missing from the contract');

    // The command carries a value the contract does not know about. Only declared
    // options are read, so it cannot travel.
    const command = parse(['cat', 'shop', '--remote-file', '/etc/hostname']);
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

describe('assertDetachable', () => {
  it('allows a detachable command through', () => {
    const entry = getCommand('repo up');
    expect(entry?.detachable).toBe(true);
    expect(() => assertDetachable('repo up', entry)).not.toThrow();
  });

  it('refuses a job command with a circular-detach message', () => {
    const entry = getCommand('job logs');
    expect(entry?.detachable).toBe(false);
    expect(() => assertDetachable('job logs', entry)).toThrow(/manages detached jobs/i);
  });

  it('refuses a non-detachable command with its proxy-blocked reason', () => {
    const entry = getCommand('term connect');
    expect(entry?.detachable).toBe(false);
    // term connect is not proxyable (interactive), so it is not detachable either,
    // and the message is the same reason the proxy would give.
    expect(() => assertDetachable('term connect', entry)).toThrow(/terminal|--proxy/i);
  });

  it('refuses an unknown command rather than assuming it can detach', () => {
    expect(() => assertDetachable('not a command', undefined)).toThrow(
      /cannot run in the background/i
    );
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

    await expect(client.run('repo status', {}, {}, () => {})).rejects.toThrow(
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

    await expect(client.run('repo status', {}, {}, () => {})).rejects.toThrow(
      ProxyStreamTruncatedError
    );
    await expect(client.run('repo status', {}, {}, () => {})).rejects.toThrow(
      /may still be running/i
    );
  });

  it('re-attaches to a detached job when the command stream drops, deduping on ordinal', async () => {
    const client = clientWith((url) => {
      const u = String(url);
      if (u.includes(PROXY_ROUTES.command)) {
        // Announces the job, streams two ordinal-tagged events, then the
        // connection drops before the result line ever arrives.
        return Promise.resolve(
          ndjson([
            { kind: 'job', jobId: 'j1-deadbeef', sinceLine: 0 },
            { kind: 'event', event: { type: 'output', msg: 'a\n' }, line: 1 },
            { kind: 'event', event: { type: 'output', msg: 'b\n' }, line: 2 },
          ])
        );
      }
      // The re-attach resumes from the last complete line and renet re-sends the
      // boundary line (ordinal 2) it may have only half-delivered, then finishes.
      expect(u).toContain('/v1/jobs/j1-deadbeef/events');
      expect(u).toContain('machine=hostinger');
      expect(u).toContain('sinceLine=2');
      return Promise.resolve(
        ndjson([
          { kind: 'event', event: { type: 'output', msg: 'b\n' }, line: 2 },
          { kind: 'event', event: { type: 'output', msg: 'c\n' }, line: 3 },
          { kind: 'result', result: { success: true, exitCode: 0, durationMs: 3 }, stdout: 'done' },
        ])
      );
    });

    const rendered: string[] = [];
    const outcome = await client.run(
      'repo up',
      { name: 'x' },
      {},
      (event) => {
        if (event.type === 'output' && event.msg) rendered.push(event.msg);
      },
      { machine: 'hostinger' }
    );

    expect(outcome.success).toBe(true);
    // The re-sent boundary line (ordinal 2) is rendered exactly once: a, b, c.
    expect(rendered).toEqual(['a\n', 'b\n', 'c\n']);
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

    const outcome = await client.run('repo status', {}, { ref: 'demo' }, () => {});

    expect(sent).toEqual({
      contractVersion: 'contract-v1',
      pathKey: 'repo status',
      params: {},
      positionals: { ref: 'demo' },
    });
    // No function name, no machine address, no key, no config: the executor
    // derives everything else from the command itself.
    expect(JSON.stringify(sent)).not.toContain('functionName');
    expect(outcome.stdout).toBe('ok');
  });

  it('is pointed at a command the contract actually has', () => {
    // Guards the fixtures above: a rename would otherwise quietly gut this file.
    expect(REPO_CAT).toBeDefined();
  });
});
