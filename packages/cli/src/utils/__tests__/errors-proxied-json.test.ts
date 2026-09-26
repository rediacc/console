/**
 * Finding (b), PLAN-cloudflare-proxy.md "Writer B status": a proxied command's
 * JSON error envelope never reached the client.
 *
 * The executor forces `--output json` on every dispatched command
 * (command-dispatch.ts), so a failing command ends in handleError's
 * outputJsonError. That wrote with process.stdout.write, straight to the
 * EXECUTOR's own stdout, instead of writeStdout, which a dispatch captures into
 * the request. The client got only "The command exited with code N" and the
 * executor's log got someone else's error.
 *
 * Real serve app over real HTTP, real Commander tree, real configService and
 * real error path; only the account server and the machine are faked.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthVerifier } from '../../services/serve/auth.js';
import { serveCrypto } from '../../services/serve/crypto.js';
import type { ServeDeps } from '../../services/serve/deps.js';
import { authorize } from '../../services/serve/policy.js';
import { createServeApp } from '../../services/serve/server.js';
import { SessionStore } from '../../services/serve/sessions.js';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-errors-proxied-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

const OWNER_TOKEN = 'rdt_owner';
const EXECUTOR_TOKEN = 'rdt_executor';
const IDENTITY = {
  active: true,
  scopes: ['proxy:exec', 'audit:write'],
  orgId: 'org-1',
  teamId: null,
  createdByUserId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
};

const CONFIG: RdcConfig = {
  schemaVersion: 3,
  id: '00000000-0000-4000-8000-0000000000ee',
  version: 1,
  credentials: { ssh: { privateKey: 'KEY' } },
  resources: {
    machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
    repositories: {},
    storages: {},
  },
  encryption: { mode: 'plaintext' },
};

describe('a proxied command that fails', () => {
  let server: ReturnType<typeof serve> | undefined;

  afterEach(async () => {
    const running = server;
    server = undefined;
    if (running) await new Promise<void>((resolve) => running.close(() => resolve()));
    vi.restoreAllMocks();
  });

  it('carries its JSON error envelope to the client, not to the executor stdout', async () => {
    const executed: unknown[] = [];
    const deps: ServeDeps = {
      mode: 'container',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: EXECUTOR_TOKEN,
        fetchImpl: () => Promise.resolve(Response.json(IDENTITY)),
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      executor: {
        execute(call) {
          executed.push(call);
          return Promise.resolve({ success: true, exitCode: 0, durationMs: 1 });
        },
      },
      loadConfig: () => Promise.resolve(CONFIG),
      authorize,
      audit: () => Promise.resolve(),
      detach: () => false,
    };
    const app = createServeApp(deps);
    server = serve({ fetch: app.fetch, port: 0 });
    const baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

    const executorStdout = vi.spyOn(process.stdout, 'write');

    const response = await fetch(`${baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo status',
        positionals: { ref: 'nothere' },
      }),
    });
    expect(response.status).toBe(200);

    const lines = (await response.text())
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line) as { kind: string; stdout?: string; result?: unknown });
    const result = lines.find((line) => line.kind === 'result');

    expect(executed).toHaveLength(0);
    expect(result?.result).toMatchObject({ success: false });
    // The client receives the command's own envelope, naming the repo it could not find.
    expect(result?.stdout ?? '').toMatch(/nothere/);
    const envelope = JSON.parse(result?.stdout ?? '{}') as {
      success?: boolean;
      errors?: { message: string }[];
    };
    expect(envelope.success).toBe(false);
    expect(envelope.errors?.[0]?.message).toMatch(/nothere/);
    // And the executor's own stdout never saw it.
    const leaked = executorStdout.mock.calls.map(([chunk]) => String(chunk)).join('');
    expect(leaked).not.toMatch(/nothere/);
  });
});
