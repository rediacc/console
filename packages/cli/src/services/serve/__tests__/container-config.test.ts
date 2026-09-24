/**
 * Container tier: a session-granted key, a config pulled encrypted, a command run.
 *
 * This is the test that proves the convenience tier is actually functional. It
 * boots the real serve app in container mode, does a genuine X25519 CEK grant
 * over the real HTTP surface, and serves REAL ciphertext from a fake account
 * server, ciphertext produced by the same buildConfigPushPayload the CLI pushes
 * with. Nothing about the crypto is stubbed.
 *
 * What that buys: if the executor could not truly decrypt, it would hold an
 * opaque blob and every assertion here would fail. A test that fed it plaintext
 * would prove nothing about the tier that matters.
 *
 * Lives in its own file rather than loopback.test.ts because that file is being
 * edited concurrently for /v1/command.
 */

import type { AddressInfo } from 'node:net';
import { tmpdir } from 'node:os';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import {
  cekHandoffEncrypt,
  exportAesKey,
  fromBase64,
  generateCek,
  generateSdkMaster,
  sdkDerive,
  toBase64,
} from '@rediacc/shared/config-crypto';
import { buildConfigPushPayload, type RdcConfig } from '@rediacc/shared/config-schema';
import type { PolicyDocument } from '@rediacc/shared/policy';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { configFileStorage } from '../../../adapters/config-file-storage.js';
import { createCli } from '../../../cli.js';
import { configService } from '../../config/config-resources.js';
import {
  createOutputState,
  DispatchExit,
  runInRequestContext,
} from '../../core/request-context.js';
import { resetProxySessions } from '../../executor/proxy-client.js';
import type { ExecuteOptions, ExecuteResult } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { createContainerConfigLoader } from '../container-config.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

/**
 * Extract an ArrayBuffer for the Web Crypto API, exactly as config-crypto's own
 * private `buf()` does. `Uint8Array` is `Uint8Array<ArrayBufferLike>`, which is
 * not a `BufferSource` (that wants `ArrayBufferView<ArrayBuffer>`).
 */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

// NO configService mock. The dispatched command reads its config through the REAL configService and configFileStorage, which in container mode must serve the config decrypted for the session (B3). The config dir points at an empty scratch directory, so a dispatch that fell through to the disk would find no machine and no repo, and the developer's own config is never read.
await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const scratch = mkdtempSync(`${tmpdir()}/rdc-container-config-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
});

// The re-attach route's only machine seam. The fake resolves the machine exactly as the real connectForJobs does (configService.getLocalMachine), records what it saw, and stops before any SSH.
const { reattachResolved } = vi.hoisted(() => ({ reattachResolved: [] as string[] }));
vi.mock('../../executor/job-remote.js', async (original) => {
  const { configService: service } = await import('../../config/config-resources.js');
  return {
    ...(await original<Record<string, unknown>>()),
    connectForJobs: async (machineName: string) => {
      const machine = await service.getLocalMachine(machineName);
      reattachResolved.push(machine.ip);
      throw new Error('stopped before SSH');
    },
  };
});

// The loopback variant drives the REAL `rdc --proxy` CLI, which needs a login token and its enrollment's CEK. The token comes from the account login; the CEK unwrap talks to config storage, so the adapter hands back the test's CEK (the enrollment's one real network dependency) and everything around it, the pointer read and the seal, is production code.
const { enrolledCek } = vi.hoisted(() => ({
  enrolledCek: { keys: [] as Awaited<ReturnType<typeof generateCek>>[] },
}));
vi.mock('../../account/subscription-auth.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  getSubscriptionTokenState: () => ({ kind: 'ready', token: { token: 'rdt_owner' } }),
}));
vi.mock('../../../adapters/remote-config-adapter.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  RemoteConfigAdapter: class {
    unwrapCek(): Promise<CryptoKey> {
      const [key] = enrolledCek.keys;
      if (!key) throw new Error('no enrolled CEK in this test');
      return Promise.resolve(key);
    }
    pull() {
      return Promise.resolve({
        config: {
          schemaVersion: 3,
          id: CLIENT_CONFIG_ID,
          version: 1,
          encryption: { mode: 'plaintext' },
        },
        version: 1,
        sdkEpoch: 1,
      });
    }
  },
}));

// Telemetry would otherwise try the network on every dispatched command.
process.env.REDIACC_TELEMETRY_DISABLED = '1';

const OWNER_TOKEN = 'rdt_owner';
const CLIENT_CONFIG_ID = '00000000-0000-4000-8000-0000000000cc';
const OTHER_TOKEN = 'rdt_other';
const EXECUTOR_TOKEN = 'rdt_executor';
const CONFIG_ID = '00000000-0000-0000-0000-0000000000aa';
/** A real, non-destructive contract command the executor will authorize. */
const COMMAND_PATH = 'repo status';

const PRINCIPALS: Record<string, unknown> = {
  // The executor's own token: it may record audit events.
  [EXECUTOR_TOKEN]: {
    active: true,
    scopes: ['proxy:exec', 'audit:write'],
    orgId: 'org-1',
    teamId: null,
    createdByUserId: 'user-executor',
    userEmail: 'executor@example.com',
    orgRole: 'admin',
  },
  [OWNER_TOKEN]: {
    active: true,
    scopes: ['proxy:exec'],
    orgId: 'org-1',
    teamId: null,
    createdByUserId: 'user-owner',
    userEmail: 'owner@example.com',
    orgRole: 'owner',
  },
  // A second real user in the same org, who never grants a key.
  [OTHER_TOKEN]: {
    active: true,
    scopes: ['proxy:exec'],
    orgId: 'org-1',
    teamId: null,
    createdByUserId: 'user-other',
    userEmail: 'other@example.com',
    orgRole: 'owner',
  },
};

/**
 * The config that only ever exists encrypted, until the executor opens it.
 *
 * The optional policy document is the point of the deny test below: the RULES
 * ride inside the ciphertext, so if the executor cannot decrypt them it silently
 * falls back to the missing-document default and enforces nothing.
 */
function secretConfig(policy?: PolicyDocument): RdcConfig {
  const config: RdcConfig = {
    schemaVersion: 3,
    id: CONFIG_ID,
    version: 4,
    credentials: { ssh: { privateKey: 'THE-SSH-KEY' } },
    resources: {
      machines: { 'prod-1': { ip: '10.9.9.9', user: 'deploy', port: 22 } },
      // `demo` exists ONLY in the ciphertext, placed on prod-1, so `repo status demo` can derive its machine from nothing but the decrypted config.
      repositories: {
        demo: {
          grand: 'latest',
          placement: { machine: 'prod-1' },
          tags: { latest: { repositoryGuid: '11111111-1111-4111-8111-111111111111' } },
        },
      },
      storages: {},
    },
    encryption: { mode: 'plaintext' },
    ...(policy === undefined ? {} : { policy }),
  };
  return config;
}

describe('container-tier config loading', () => {
  let server: ReturnType<typeof serve>;
  let baseUrl: string;
  let sessions: SessionStore;
  let cek: CryptoKey;
  let executed: ExecuteOptions[];
  /** What the execution seam resolved for each call, read the way LocalExecutorService reads it. */
  let resolvedAtExecution: { ip: string; user: string; sshPrivateKey?: string }[];
  /** Configs that reached policy. Proves what the executor actually decrypted. */
  let authorizedAgainst: RdcConfig[];
  let accountCalls: string[];

  async function boot(config: RdcConfig): Promise<void> {
    cek = await generateCek();
    executed = [];
    resolvedAtExecution = [];
    authorizedAgainst = [];
    accountCalls = [];

    // Real ciphertext, built exactly as a CLI push builds it.
    const sdkEpoch = 12345;
    const sdkDerived = await sdkDerive(generateSdkMaster(), sdkEpoch);
    const payload = await buildConfigPushPayload(config, {
      version: 4,
      sdkEpoch,
      sdkDerived,
      cek,
    });
    const sdkDerivedB64 = toBase64(await exportAesKey(sdkDerived));

    const accountFetch = vi.fn((url: string | URL, init?: RequestInit) => {
      const href = String(url);
      accountCalls.push(href);

      if (href.includes('/proxy/introspect')) {
        const body = JSON.parse(init?.body as string) as { token: string };
        return json(PRINCIPALS[body.token] ?? { active: false });
      }

      // Checked BEFORE the generic /configs/ pull: the literal path is a prefix match.
      if (href.includes('/configs/executor-token')) {
        expect(init?.headers).toMatchObject({ authorization: `Bearer ${EXECUTOR_TOKEN}` });
        return json({
          token: 'rct_executor_scoped',
          storeId: 'store-1',
          serverSecret: toBase64(new Uint8Array(32)),
          configs: [{ configId: CONFIG_ID, teamId: null, version: 4 }],
        });
      }

      if (href.includes('/configs/')) {
        // The executor must present the token it was just minted, not its own.
        expect((init?.headers as Record<string, string>)['X-Config-Token']).toBe(
          'rct_executor_scoped'
        );
        return json({
          newServerToken: 'rct_rotated',
          sdk_derived: sdkDerivedB64,
          configData: payload.encryptedBlob,
          envelope: payload.envelope,
          hmac: payload.hmac,
        });
      }

      throw new Error(`unexpected account call: ${href}`);
    }) as unknown as typeof fetch;

    sessions = new SessionStore();

    const deps: ServeDeps = {
      mode: 'container',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: EXECUTOR_TOKEN,
        fetchImpl: accountFetch,
      }),
      sessions,
      crypto: serveCrypto,
      executor: {
        async execute(options: ExecuteOptions): Promise<ExecuteResult> {
          executed.push(options);
          // Exactly the calls LocalExecutorService makes to find the host and key it SSHes with (local-executor.ts resolveRepoLicenseInputs / getLocalConfig). Run at the seam, inside the dispatch, so they see whatever config the dispatch really runs against.
          const machine = await configService.getLocalMachine(options.machineName);
          const local = await configService.getLocalConfig();
          resolvedAtExecution.push({
            ip: machine.ip,
            user: machine.user,
            sshPrivateKey: local.sshPrivateKey,
          });
          return { success: true, exitCode: 0, durationMs: 1, stdout: 'ok' };
        },
      },
      loadConfig: createContainerConfigLoader({
        accountUrl: 'https://account.test',
        executorToken: EXECUTOR_TOKEN,
        sessions,
        fetchImpl: accountFetch,
      }),
      authorize: (args) => {
        authorizedAgainst.push(args.config);
        return authorize(args);
      },
      audit: async () => {},
    };

    const app = createServeApp(deps);
    server = serve({ fetch: app.fetch, port: 0 });
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  }

  beforeEach(async () => {
    await boot(secretConfig());
  });

  afterEach(() => {
    server.close();
  });

  function json(body: unknown): Response {
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  }

  /** Open a session and seal the CEK to the executor's ephemeral key, for real. */
  async function grantKey(token = OWNER_TOKEN): Promise<string> {
    const opened = await fetch(`${baseUrl}/v1/session`, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}` },
    });
    const { sessionId, publicKey } = (await opened.json()) as {
      sessionId: string;
      publicKey: string;
    };

    const executorPublicKey = await crypto.subtle.importKey(
      'spki',
      buf(fromBase64(publicKey)),
      { name: 'X25519' },
      false,
      []
    );
    const blob = await cekHandoffEncrypt(await exportAesKey(cek), executorPublicKey);

    const granted = await fetch(`${baseUrl}/v1/session/${sessionId}/cek`, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
      body: JSON.stringify(blob),
    });
    expect(granted.status).toBe(200);
    return sessionId;
  }

  function runCommand(
    token = OWNER_TOKEN,
    extraHeaders: Record<string, string> = {}
  ): Promise<Response> {
    return fetch(`${baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${token}`,
        'content-type': 'application/json',
        ...extraHeaders,
      },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: COMMAND_PATH,
        positionals: { ref: 'demo' },
      }),
    });
  }

  // ── The property that matters ────────────────────────────────────────

  it('decrypts the remote config with the granted key and runs against it', async () => {
    await grantKey();

    const response = await runCommand();
    expect(response.status).toBe(200);
    await response.text();

    expect(executed).toHaveLength(1);

    // The config policy ran against is the DECRYPTED one. If the executor had failed to open the blob, these fields could not exist.
    expect(authorizedAgainst).toHaveLength(1);
    const config = authorizedAgainst[0];
    expect(config.resources?.machines).toEqual({
      'prod-1': { ip: '10.9.9.9', user: 'deploy', port: 22 },
    });
    expect(config.credentials?.ssh?.privateKey).toBe('THE-SSH-KEY');

    // B3: and EXECUTION ran against it too, not just policy. The machine was derived from the decrypted placement, and the host and key the executor would SSH with are the decrypted ones. Before the fix the dispatch read the container's empty disk and the command died with "not in this config".
    expect(executed[0].machineName).toBe('prod-1');
    expect(resolvedAtExecution).toEqual([
      { ip: '10.9.9.9', user: 'deploy', sshPrivateKey: 'THE-SSH-KEY' },
    ]);
  });

  it('re-attaches to a job against the decrypted config too', async () => {
    reattachResolved.length = 0;
    await grantKey();

    const response = await fetch(
      `${baseUrl}${PROXY_ROUTES.jobEvents('j1a2b-0123abcd')}?machine=prod-1&sinceLine=0`,
      { headers: { authorization: `Bearer ${OWNER_TOKEN}` } }
    );
    expect(response.status).toBe(200);
    const body = await response.text();

    // B3, re-attach route: the machine was looked up in the session's decrypted config (10.9.9.9). Before the fix the lookup read the empty container disk and failed with "has no machines configured".
    expect(reattachResolved).toEqual(['10.9.9.9']);
    expect(body).toContain('stopped before SSH');
  });

  // ── B4: the real CLI completes the grant itself (missing test 3, loopback) ──

  it('lets a real `rdc --proxy` grant its enrolled key and run against the decrypted config', async () => {
    resetProxySessions();
    enrolledCek.keys = [cek];
    // The CLIENT's own config: only an enrollment pointer, no machines, no repos.
    expect(configFileStorage.getConfigDir().startsWith(tmpdir())).toBe(true);
    await configFileStorage.save(
      {
        schemaVersion: 3,
        id: CLIENT_CONFIG_ID,
        version: 1,
        encryption: { mode: 'plaintext' },
        remote: {
          apiUrl: 'https://account.test',
          storeId: '00000000-0000-4000-8000-0000000000dd',
          configId: '00000000-0000-4000-8000-0000000000aa',
          storageKeyId: 'rediacc:test-slot',
        },
      },
      'rediacc'
    );

    const context = { output: createOutputState(), stdout: [] as string[], stderr: [] as string[] };
    const exitCode = await runInRequestContext(context, async () => {
      try {
        await createCli().parseAsync(['--proxy', baseUrl, 'repo', 'status', 'demo'], {
          from: 'user',
        });
        return 0;
      } catch (error) {
        if (error instanceof DispatchExit) return error.code;
        throw error;
      }
    });

    const stderr = context.stderr.join('');
    expect(stderr).not.toMatch(/no config key/);
    expect(exitCode).toBe(0);
    // Nothing but the client's own grant could have given this container a key (see "refuses to run before the key grant"), so a command that ran against the decrypted config proves the client completed it.
    expect(executed).toHaveLength(1);
    expect(resolvedAtExecution).toEqual([
      { ip: '10.9.9.9', user: 'deploy', sshPrivateKey: 'THE-SSH-KEY' },
    ]);
  });

  // ── The rules must actually reach the executor ───────────────────────

  it('enforces a deny rule that exists ONLY inside the encrypted config', async () => {
    // The policy document rides in the ciphertext and nowhere else. The account server cannot read it, the wire does not carry it, and the executor has no local copy: the ONLY way this rule can bind is if the executor genuinely decrypted the config it was handed.
    server.close();
    await boot(
      secretConfig({
        version: 1,
        defaults: { commands: { allow: ['*'], deny: [COMMAND_PATH] } },
      })
    );

    await grantKey(OWNER_TOKEN);
    const response = await runCommand(OWNER_TOKEN);

    // BEFORE THE FIX THIS WAS A 200. The policy was dropped on push, so the executor saw no document, fell back to MISSING_POLICY_DEFAULT, and an owner sailed straight through a rule that explicitly forbade the command.
    expect(response.status).toBe(403);
    expect(((await response.json()) as { error: string }).error).toMatch(/denies/);
    expect(executed).toHaveLength(0);

    // And the rule really came out of the blob: policy reached authorize().
    expect(authorizedAgainst).toHaveLength(1);
    expect(authorizedAgainst[0].policy).toEqual({
      version: 1,
      defaults: { commands: { allow: ['*'], deny: [COMMAND_PATH] } },
    });
  });

  it('still allows what the encrypted rules permit', async () => {
    server.close();
    await boot(
      secretConfig({
        version: 1,
        defaults: { commands: { allow: ['repo *'], deny: ['repo delete'] } },
      })
    );

    await grantKey(OWNER_TOKEN);
    const response = await runCommand(OWNER_TOKEN);

    expect(response.status).toBe(200);
    await response.text();
    expect(executed).toHaveLength(1);
  });

  it('mints its OWN config token rather than using the executor account token', async () => {
    await grantKey();
    await (await runCommand()).text();

    // The pull asserted X-Config-Token === the minted token (see accountFetch),
    // and the mint asserted the executor's own bearer. Both were exercised.
    expect(accountCalls.some((u) => u.includes('/configs/executor-token'))).toBe(true);
    expect(accountCalls.some((u) => u.includes(`/configs/${CONFIG_ID}`))).toBe(true);
  });

  // ── Without a grant there is nothing to run against ──────────────────

  it('refuses to run before the key grant, naming the fix', async () => {
    const response = await runCommand();

    expect(response.status).toBeGreaterThanOrEqual(400);
    const body = (await response.json()) as { error: string };
    expect(body.error).toMatch(/Complete the key grant before running commands/);
    expect(executed).toHaveLength(0);

    // And it never even tried to fetch a config it could not have opened.
    expect(accountCalls.some((u) => u.includes('/configs/'))).toBe(false);
  });

  it('does not lend one user the key another user granted', async () => {
    await grantKey(OWNER_TOKEN);

    // A different real user in the same org, with no grant of their own.
    const response = await runCommand(OTHER_TOKEN);

    expect(response.status).toBeGreaterThanOrEqual(400);
    const body = (await response.json()) as { error: string };
    expect(body.error).toMatch(/Complete the key grant before running commands/);
    expect(executed).toHaveLength(0);
  });

  // ── Warm-container economics ─────────────────────────────────────────

  it('caches the decrypted config per session: the second command pulls nothing', async () => {
    await grantKey();

    await (await runCommand()).text();
    const afterFirst = accountCalls.filter((u) => u.includes('/configs/')).length;

    await (await runCommand()).text();
    const afterSecond = accountCalls.filter((u) => u.includes('/configs/')).length;

    expect(executed).toHaveLength(2);
    // Exactly one mint + one pull, for two commands.
    expect(afterFirst).toBe(2);
    expect(afterSecond).toBe(2);
  });

  it('drops the decrypted config when the session goes, so it never outlives its key', async () => {
    const sessionId = await grantKey();
    await (await runCommand()).text();
    expect(accountCalls.filter((u) => u.includes('/configs/'))).toHaveLength(2);

    // The session dies. The config it decrypted must die with it.
    sessions.close(sessionId);

    const response = await runCommand();
    expect(response.status).toBeGreaterThanOrEqual(400);
    expect(((await response.json()) as { error: string }).error).toMatch(/Complete the key grant/);

    // A fresh grant re-pulls rather than serving the dead session's plaintext.
    await grantKey();
    await (await runCommand()).text();
    expect(accountCalls.filter((u) => u.includes('/configs/'))).toHaveLength(4);
  });

  // ── X-Config-Session: the console names the session it granted through ──

  it('runs under the session the X-Config-Session header names', async () => {
    const sessionId = await grantKey();

    const response = await runCommand(OWNER_TOKEN, { 'X-Config-Session': sessionId });
    expect(response.status).toBe(200);
    await response.text();

    // The command genuinely ran against the config that session's key opened.
    expect(executed).toHaveLength(1);
    expect(authorizedAgainst[0].credentials?.ssh?.privateKey).toBe('THE-SSH-KEY');
  });

  it('draws the key from the NAMED session, not the latest-grant index', async () => {
    // Two live grants by the same user: the index points at the second, but the request names the first. The per-session config cache makes the selection observable: repeating the named-session request must pull NOTHING new,
    // while the headerless fallback (the second session) pays its own pull.
    const first = await grantKey();
    await grantKey();

    await (await runCommand(OWNER_TOKEN, { 'X-Config-Session': first })).text();
    await (await runCommand(OWNER_TOKEN, { 'X-Config-Session': first })).text();
    expect(accountCalls.filter((u) => u.includes('/configs/'))).toHaveLength(2);

    await (await runCommand(OWNER_TOKEN)).text();
    expect(accountCalls.filter((u) => u.includes('/configs/'))).toHaveLength(4);
    expect(executed).toHaveLength(3);
  });

  it('refuses a header naming a session someone ELSE granted (principal mismatch)', async () => {
    const sessionId = await grantKey(OWNER_TOKEN);

    // A different real user in the same org names the owner's session. Same ownership rule as the grant itself: refused, and indistinguishable from a session that does not exist.
    const response = await runCommand(OTHER_TOKEN, { 'X-Config-Session': sessionId });

    expect(response.status).toBe(404);
    expect(((await response.json()) as { error: string }).error).toMatch(/unknown or expired/i);
    expect(executed).toHaveLength(0);
  });

  it('refuses a header naming a session that does not exist', async () => {
    await grantKey(OWNER_TOKEN);

    const response = await runCommand(OWNER_TOKEN, {
      'X-Config-Session': '33333333-3333-3333-3333-333333333333',
    });

    expect(response.status).toBe(404);
    expect(executed).toHaveLength(0);
  });

  it('keeps the headerless CLI fallback intact alongside header-named sessions', async () => {
    await grantKey(OWNER_TOKEN);

    // No header: exactly the pre-header behavior, found via sessionFor().
    const response = await runCommand(OWNER_TOKEN);
    expect(response.status).toBe(200);
    await response.text();
    expect(executed).toHaveLength(1);
  });
});
