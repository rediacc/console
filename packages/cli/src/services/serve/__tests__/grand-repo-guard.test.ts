/**
 * S1 and F1: what the executor refuses before a command runs.
 *
 * S1. The CLI's grand-repo guard (utils/command-policy.ts assertCommandPolicy)
 * runs only inside the local action and only for an agent. A proxied command
 * never reaches the local action, and the executor is not an agent, so before
 * this fix an agent using `--proxy` could `repo up` / `repo down` / `repo exec`
 * any grand repo. The executor now computes grand-ness itself, from the config
 * the command will run against, and refuses a grand-repo mutation by default.
 *
 * F1. The executor audits AFTER a command ran. The Phase 1 trial ran with an
 * executor token lacking `audit:write`: the event was rejected (403) and the
 * command had already happened. The executor now checks its own token's scopes
 * BEFORE running, refuses a change it cannot record, and lets a read through
 * with a loud warning.
 *
 * The real Commander tree, the real configService and the real policy code run
 * here; only the machine (a fake executor) and the account server are faked. The
 * config dir is an empty scratch directory, so nothing reads the developer's
 * own config.
 */

import type { AddressInfo } from 'node:net';
import { tmpdir } from 'node:os';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { PolicyDocument } from '@rediacc/shared/policy';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { configFileStorage } from '../../../adapters/config-file-storage.js';
import type { ExecuteOptions, ExecuteResult } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-grand-guard-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

const OWNER_TOKEN = 'rdt_owner';
const EXECUTOR_TOKEN = 'rdt_executor';
const GRAND_GUID = '11111111-1111-4111-8111-111111111111';
const FORK_GUID = '22222222-2222-4222-8222-222222222222';

const OWNER = {
  active: true,
  scopes: ['proxy:exec'],
  orgId: 'org-1',
  teamId: null,
  createdByUserId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
};

function executorIdentity(scopes: string[]) {
  return { ...OWNER, scopes, createdByUserId: 'user-exec', userEmail: 'exec@example.com' };
}

/** `shop` is a grand repo (tag latest); `shop:trial` is a fork of it. */
function fleetConfig(policy?: PolicyDocument): RdcConfig {
  const config: RdcConfig = {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000bb',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: {
      machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
      repositories: {
        shop: {
          grand: 'latest',
          placement: { machine: 'm1' },
          tags: {
            latest: { repositoryGuid: GRAND_GUID },
            trial: { repositoryGuid: FORK_GUID, grandGuid: GRAND_GUID, parentGuid: GRAND_GUID },
          },
        },
      },
      storages: {},
    },
    encryption: { mode: 'plaintext' },
    ...(policy ? { policy } : {}),
  };
  return config;
}

/** An account server that introspects the caller and the executor's own token. */
function fakeAccount(executorScopes: string[] | 'unreachable'): typeof fetch {
  return vi.fn((_url: string | URL, init?: RequestInit) => {
    const { token } = JSON.parse(String(init?.body ?? '{}')) as { token: string };
    if (token !== EXECUTOR_TOKEN) {
      return Promise.resolve(Response.json(token === OWNER_TOKEN ? OWNER : { active: false }));
    }
    if (executorScopes === 'unreachable') return Promise.reject(new TypeError('fetch failed'));
    return Promise.resolve(Response.json(executorIdentity(executorScopes)));
  }) as unknown as typeof fetch;
}

interface RunOutcome {
  status: number;
  error?: string;
  stderr?: string;
  success?: boolean;
}

describe('executor pre-run refusals', () => {
  let server: ReturnType<typeof serve> | undefined;
  let baseUrl: string;
  let executed: ExecuteOptions[];
  let audited: unknown[];

  function boot(options: {
    config?: RdcConfig;
    mode?: 'container' | 'daemon';
    executorScopes?: string[] | 'unreachable';
  }): void {
    executed = [];
    audited = [];
    const config = options.config ?? fleetConfig();
    const scopes = options.executorScopes ?? ['proxy:exec', 'audit:write'];

    const accountFetch = fakeAccount(scopes);

    const deps: ServeDeps = {
      mode: options.mode ?? 'container',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: EXECUTOR_TOKEN,
        fetchImpl: accountFetch,
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      executor: {
        execute(call: ExecuteOptions): Promise<ExecuteResult> {
          executed.push(call);
          return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' });
        },
      },
      loadConfig: () => Promise.resolve(config),
      authorize,
      audit: (event) => {
        audited.push(event);
        return Promise.resolve();
      },
      // The fake executor has no job spool.
      detach: () => false,
    };

    const app = createServeApp(deps);
    server = serve({ fetch: app.fetch, port: 0 });
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  }

  afterEach(async () => {
    const running = server;
    server = undefined;
    if (running) await new Promise<void>((resolve) => running.close(() => resolve()));
  });

  async function run(pathKey: string, positionals: Record<string, unknown>): Promise<RunOutcome> {
    const response = await fetch(`${baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({ contractVersion: CLI_CONTRACT_VERSION, pathKey, positionals }),
    });
    if (response.status !== 200) {
      const body = (await response.json()) as { error: string };
      return { status: response.status, error: body.error };
    }
    const lines = (await response.text())
      .split('\n')
      .filter(Boolean)
      .map(
        (line) =>
          JSON.parse(line) as {
            kind: string;
            stderr?: string;
            stdout?: string;
            result?: { success: boolean; error?: string };
          }
      );
    const result = lines.find((line) => line.kind === 'result');
    return {
      status: 200,
      stderr: result?.stderr,
      success: result?.result?.success,
      error: result?.result?.error ?? result?.stdout,
    };
  }

  // ── S1: missing test 7 ─────────────────────────────────────────────────

  describe('grand-repo guard (S1)', () => {
    it.each([
      ['repo up', { ref: 'shop' }],
      ['repo up', { ref: 'shop@m1' }],
      ['repo down', { ref: 'shop' }],
      ['repo exec', { ref: 'shop', cmd: ['ls'] }],
      ['repo delete', { ref: 'shop' }],
    ])(
      'refuses "%s" on a grand repo by default, even for an owner (%o)',
      async (pathKey, positionals) => {
        boot({});
        const { status, error } = await run(pathKey, positionals);

        expect(status).toBe(403);
        expect(error).toMatch(/grand repo/);
        expect(error).toMatch(/rdc repo fork/);
        expect(executed).toHaveLength(0);
      }
    );

    it('runs the same mutation on a fork', async () => {
      boot({});
      const { status, success } = await run('repo up', { ref: 'shop:trial' });

      expect(status).toBe(200);
      expect(success).toBe(true);
      expect(executed.length).toBeGreaterThan(0);
      expect(executed.every((call) => call.machineName === 'm1')).toBe(true);
    });

    it('still allows a read of a grand repo', async () => {
      boot({});
      const { status, success } = await run('repo status', { ref: 'shop' });

      expect(status).toBe(200);
      expect(success).toBe(true);
      expect(executed).toHaveLength(1);
    });

    it('fails closed on a ref it cannot identify', async () => {
      boot({});
      const { status } = await run('repo up', { ref: 'nosuchrepo' });

      expect(status).toBe(403);
      expect(executed).toHaveLength(0);
    });

    it('treats repo promote as a grand mutation even though its ref names a fork', async () => {
      boot({});
      const { status, error } = await run('repo promote', { 'fork-ref': 'shop:trial' });

      expect(status).toBe(403);
      expect(error).toMatch(/grand repo/);
      expect(executed).toHaveLength(0);
    });

    it('lets a policy that sets allowGrandRepos opt in', async () => {
      boot({
        config: fleetConfig({
          version: 1,
          defaults: { commands: { allow: ['*'] }, allowGrandRepos: true },
        }),
      });
      const { status } = await run('repo up', { ref: 'shop' });

      expect(status).toBe(200);
      expect(executed).toHaveLength(1);
    });

    it('refuses under a policy that allows the command but not grand repos', async () => {
      boot({ config: fleetConfig({ version: 1, defaults: { commands: { allow: ['repo *'] } } }) });
      const { status, error } = await run('repo up', { ref: 'shop' });

      expect(status).toBe(403);
      expect(error).toMatch(/allowGrandRepos/);
      expect(executed).toHaveLength(0);
    });

    it('applies on a daemon too, reading its enrolled config file', async () => {
      // Never write outside the scratch dir: this save would otherwise replace a real rediacc.json.
      expect(configFileStorage.getConfigDir().startsWith(tmpdir())).toBe(true);
      await configFileStorage.save(fleetConfig(), 'rediacc');
      boot({ mode: 'daemon' });

      expect((await run('repo up', { ref: 'shop' })).status).toBe(403);
      expect(executed).toHaveLength(0);
      const fork = await run('repo up', { ref: 'shop:trial' });
      expect(fork.status).toBe(200);
      expect(executed.length).toBeGreaterThan(0);
    });
  });

  // ── F1: an executor that cannot audit ──────────────────────────────────

  describe('audit capability (F1)', () => {
    it('refuses a change when the executor token lacks audit:write', async () => {
      boot({ executorScopes: ['proxy:exec'] });
      const { status, error } = await run('repo up', { ref: 'shop:trial' });

      expect(status).toBe(503);
      expect(error).toMatch(/audit:write/);
      expect(executed).toHaveLength(0);
      expect(audited).toHaveLength(0);
    });

    it('refuses a change when the scopes cannot be learned at all', async () => {
      boot({ executorScopes: 'unreachable' });
      const { status } = await run('repo up', { ref: 'shop:trial' });

      expect(status).toBe(503);
      expect(executed).toHaveLength(0);
    });

    it('runs a read anyway, with a loud warning in its output', async () => {
      boot({ executorScopes: ['proxy:exec'] });
      const { status, success, stderr } = await run('repo status', { ref: 'shop' });

      expect(status).toBe(200);
      expect(success).toBe(true);
      expect(executed).toHaveLength(1);
      expect(stderr).toMatch(/WITHOUT an audit record/);
    });

    it('runs a change, audited and without a warning, when the token can audit', async () => {
      boot({});
      const { status, stderr } = await run('repo up', { ref: 'shop:trial' });

      expect(status).toBe(200);
      expect(executed.length).toBeGreaterThan(0);
      expect(audited).toHaveLength(1);
      expect(stderr ?? '').not.toMatch(/audit record/);
    });
  });
});
