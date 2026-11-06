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
import { ProxyClient } from '../proxy-client.js';
import { ProxyStreamTruncatedError, ProxyVersionMismatchError } from '../proxy-client-support.js';
import {
  assertDetachable,
  assertProxyCapable,
  BACKGROUND_UNSAFE,
  paramsFromCommand,
  proxyUrlFor,
} from '../proxy-command.js';

/**
 * Parse argv with a throwaway Commander tree and hand back the action command.
 * Modelled on `repo cat <ref>`, after the §2.3 reshape the repo verbs derive
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

    // Commander stores --skip-router-restart as `skipRouterRestart`. The executor validates against the contract, which knows it as `skip-router-restart`.
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

    // The command carries a value the contract does not know about. Only declared options are read, so it cannot travel.
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

describe('proxyUrlFor', () => {
  const URL = 'https://proxy.example.test';

  it('never routes `subscription proxy-token` through the proxy, from the env or the flag', () => {
    expect(proxyUrlFor('subscription proxy-token', undefined, URL)).toBeUndefined();
    expect(proxyUrlFor('subscription proxy-token', URL, URL)).toBeUndefined();
  });

  it('routes every other command by the flag first, then the env', () => {
    expect(proxyUrlFor('repo up', undefined, URL)).toBe(URL);
    expect(proxyUrlFor('repo up', 'https://flag.example.test', URL)).toBe(
      'https://flag.example.test'
    );
    expect(proxyUrlFor('repo up', undefined, undefined)).toBeUndefined();
  });
});

describe('assertDetachable', () => {
  it('allows a detachable command through', () => {
    const entry = getCommand('repo down');
    expect(entry?.detachable).toBe(true);
    expect(() => assertDetachable('repo down', entry)).not.toThrow();
  });

  it('refuses a detachable verb that is unsafe with --background, naming why', () => {
    // Iterates the table itself: a renamed verb (getCommand undefined) or one the contract stops marking detachable fails here instead of silently leaving the table. Empty once every J0 verb is converted (PLAN-detached-jobs J22).
    for (const verb of Object.keys(BACKGROUND_UNSAFE)) {
      const entry = getCommand(verb);
      expect(entry?.detachable, verb).toBe(true);
      expect(() => assertDetachable(verb, entry), verb).toThrow(/cannot run with --background yet/);
    }
  });

  it('accepts a verb whose conversion landed (PLAN-detached-jobs J4): it runs as one job with its steps on the ticket', () => {
    for (const verb of ['repo up', 'repo migrate', 'backup restore']) {
      expect(BACKGROUND_UNSAFE[verb], verb).toBeUndefined();
      expect(() => assertDetachable(verb, getCommand(verb)), verb).not.toThrow();
    }
  });

  it('refuses a job command with a circular-detach message', () => {
    const entry = getCommand('job logs');
    expect(entry?.detachable).toBe(false);
    expect(() => assertDetachable('job logs', entry)).toThrow(/manages detached jobs/i);
  });

  it('refuses a non-detachable command with its proxy-blocked reason', () => {
    const entry = getCommand('term connect');
    expect(entry?.detachable).toBe(false);
    // term connect is not proxyable (interactive), so it is not detachable either, and the message is the same reason the proxy would give.
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
    // The executor died mid-operation: events arrived, a result never did. The work may still be running on the machine, so reporting success here would be the worst possible lie.
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

  it('follows a job by polls when the command stream drops after the job line', async () => {
    const client = new ProxyClient({
      baseUrl: 'https://executor.test',
      getToken: () => Promise.resolve('rdt_token'),
      contractVersion: 'contract-v1',
      ticketStore: null,
      sleep: () => Promise.resolve(),
      fetchImpl: ((url: string | URL) => {
        const u = String(url);
        if (u.includes(PROXY_ROUTES.command)) {
          // Announces the job and one event, then the connection ends before any result line.
          return Promise.resolve(
            ndjson([
              { kind: 'job', jobId: 'j1-deadbeef', machine: 'prod-1', sinceLine: 0 },
              { kind: 'event', event: { type: 'output', msg: 'a\n' }, line: 1 },
            ])
          );
        }
        expect(u).toContain('/v1/jobs/j1-deadbeef/poll');
        // The machine comes from the job line, not from the caller's guess.
        expect(u).toContain('machine=prod-1');
        return Promise.resolve(
          Response.json({
            events: [{ line: 0, event: { type: 'output', msg: 'b\n' } }],
            nextLine: 1,
            more: false,
            status: { state: 'succeeded', exitCode: 0, function: 'repository_up' },
          })
        );
      }) as typeof fetch,
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
    expect(rendered).toEqual(['a\n', 'b\n']);
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
      requestId: expect.stringMatching(/^[0-9a-f-]{36}$/),
    });
    // No function name, no machine address, no key, no config: the executor derives everything else from the command itself.
    expect(JSON.stringify(sent)).not.toContain('functionName');
    expect(outcome.stdout).toBe('ok');
  });

  it('is pointed at a command the contract actually has', () => {
    // Guards the fixtures above: a rename would otherwise quietly gut this file.
    expect(REPO_CAT).toBeDefined();
  });
});
