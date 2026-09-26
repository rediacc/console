/**
 * `rdc --proxy repo cat` returns the file's exact bytes and the command's exit code.
 *
 * repo cat wrote the decoded file with process.stdout.write and reported failure
 * with process.exitCode. Inside an executor dispatch both bypass the request:
 * the bytes landed on the EXECUTOR's stdout, and the client got empty output
 * and exit 0. A binary file also cannot travel as the stream's text `stdout`,
 * which is a JSON string: anything that is not valid UTF-8 would be replaced.
 *
 * Real serve app over real HTTP, real Commander tree, real configService, and
 * the real client (ProxyClient) decoding the stream; only the account server
 * and the machine are faked.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

// The executor never runs under an AI agent, and the agent path exits early with the renet code, which hid
// both defects these tests pin from any agent-driven run. Pin the production (non-agent) path.
vi.mock('../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));
import type { ExecuteResult } from '../../services/executor/types.js';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-repo-cat-proxied-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { Command } from 'commander';
import {
  type CommandRequestContext,
  createOutputState,
  DispatchExit,
  runInRequestContext,
} from '../../services/core/request-context.js';
import { ProxyClient } from '../../services/executor/proxy-client.js';
import { runCommandThroughProxy } from '../../services/executor/proxy-command.js';
import { AuthVerifier } from '../../services/serve/auth.js';
import { serveCrypto } from '../../services/serve/crypto.js';
import type { ServeDeps } from '../../services/serve/deps.js';
import { authorize } from '../../services/serve/policy.js';
import { createServeApp } from '../../services/serve/server.js';
import { SessionStore } from '../../services/serve/sessions.js';

const OWNER_TOKEN = 'rdt_owner';
const IDENTITY = {
  active: true,
  scopes: ['proxy:exec', 'audit:write'],
  orgId: 'org-1',
  teamId: null,
  createdByUserId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
};

const CONFIG = {
  schemaVersion: 3,
  id: '00000000-0000-4000-8000-0000000000ef',
  version: 1,
  credentials: { ssh: { privateKey: 'KEY' } },
  resources: {
    machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
    repositories: {
      shop: {
        grand: 'latest',
        placement: { machine: 'm1' },
        tags: {
          latest: {
            repositoryGuid: '11111111-1111-4111-8111-111111111111',
            networkId: 2816,
          },
        },
      },
    },
    storages: {},
  },
  encryption: { mode: 'plaintext' },
} as unknown as RdcConfig;

/** Bytes no UTF-8 decoder round-trips: a PNG header, a lone 0xff, NUL, 0x80. */
const BINARY = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0xff, 0x00, 0x80]);

describe('repo cat through the executor', () => {
  let server: ReturnType<typeof serve> | undefined;

  afterEach(async () => {
    const running = server;
    server = undefined;
    if (running) await new Promise<void>((resolve) => running.close(() => resolve()));
    vi.restoreAllMocks();
  });

  let baseUrl = '';

  function start(machine: ExecuteResult): ProxyClient {
    const deps: ServeDeps = {
      mode: 'container',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        fetchImpl: () => Promise.resolve(Response.json(IDENTITY)),
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      executor: { execute: () => Promise.resolve(machine) },
      loadConfig: () => Promise.resolve(CONFIG),
      authorize,
      audit: () => Promise.resolve(),
      detach: () => false,
    };
    server = serve({ fetch: createServeApp(deps).fetch, port: 0 });
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    return new ProxyClient({
      baseUrl,
      getToken: () => Promise.resolve(OWNER_TOKEN),
      contractVersion: CLI_CONTRACT_VERSION,
    });
  }

  const cat = (client: ProxyClient) =>
    client.run('repo cat', { 'remote-file': 'logo.png' }, { ref: 'shop' }, () => {});

  it('delivers the exact bytes, non-UTF-8 included, and never to the executor stdout', async () => {
    const client = start({
      success: true,
      exitCode: 0,
      durationMs: 1,
      stdout: `RDC_CAT_B64:${Buffer.from(BINARY).toString('base64')}\n`,
    });
    const executorStdout = vi.spyOn(process.stdout, 'write');

    const outcome = await cat(client);

    expect(outcome.exitCode).toBe(0);
    expect(outcome.stdoutBytes).toBeDefined();
    expect(Buffer.from(outcome.stdoutBytes ?? new Uint8Array()).equals(Buffer.from(BINARY))).toBe(
      true
    );
    const leaked = executorStdout.mock.calls.filter(([chunk]) => chunk instanceof Uint8Array);
    expect(leaked).toHaveLength(0);
  });

  it('returns exit 1 when the machine answered without a payload', async () => {
    const client = start({ success: true, exitCode: 0, durationMs: 1, stdout: 'no marker here' });
    const outcome = await cat(client);
    expect(outcome.exitCode).toBe(1);
    expect(outcome.success).toBe(false);
  });

  it("returns renet's exit code when the read itself failed", async () => {
    const client = start({
      success: false,
      exitCode: 4,
      durationMs: 1,
      error: 'no such file',
      stderr: 'Error: open logo.png: no such file or directory',
    });
    const outcome = await cat(client);
    expect(outcome.exitCode).toBe(4);
    expect(outcome.stdoutBytes).toBeUndefined();
  });

  it('the client writes those bytes out verbatim, with no newline added, and exits 0', async () => {
    start({
      success: true,
      exitCode: 0,
      durationMs: 1,
      stdout: `RDC_CAT_B64:${Buffer.from(BINARY).toString('base64')}\n`,
    });
    // The operator's side: `rdc --proxy repo cat shop --remote-file logo.png`, its action command parsed by Commander.
    let action: Command | undefined;
    const program = new Command();
    program
      .command('cat')
      .argument('<ref>')
      .option('--remote-file <path>')
      .action((_ref, _options, command: Command) => {
        action = command;
      });
    program.parse(['cat', 'shop', '--remote-file', 'logo.png'], { from: 'user' });
    if (!action) throw new Error('the action command was not parsed');
    const parsed = action;

    // Captured through a request context, which also turns the final exit into a throw.
    const captured: CommandRequestContext = { output: createOutputState(), stdout: [], stderr: [] };
    const cek = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, [
      'encrypt',
      'decrypt',
    ]);
    const exit = await runInRequestContext(captured, () =>
      runCommandThroughProxy('repo cat', parsed, {
        baseUrl,
        getToken: () => Promise.resolve(OWNER_TOKEN),
        contractVersion: CLI_CONTRACT_VERSION,
        getCek: () => Promise.resolve(cek),
      })
    ).catch((error: unknown) => error);

    expect(exit).toBeInstanceOf(DispatchExit);
    expect((exit as DispatchExit).code).toBe(0);
    const written = captured.stdout.filter((chunk) => typeof chunk !== 'string' || chunk !== '');
    expect(written).toHaveLength(1);
    expect(Buffer.from(written[0] as Uint8Array).equals(Buffer.from(BINARY))).toBe(true);
  });
});
