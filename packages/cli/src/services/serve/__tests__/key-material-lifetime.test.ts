/**
 * MU4: `rdc serve --mode container` writes no key material to disk on the dispatch path.
 *
 * Drives `machine status` through the real serve app and the real LocalExecutorService
 * against a fake machine (an in-memory SFTP lease), with every fs write recorded.
 * A private key, a known_hosts entry or config bytes may be written only inside a
 * per-request 0700 directory that is gone again when the request finishes. Today the
 * dispatch path writes none, so the recorded set must hold no such bytes at all.
 */

import { existsSync, statSync } from 'node:fs';
import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

const PRIVATE_KEY =
  '-----BEGIN OPENSSH PRIVATE KEY-----\nMU4-SECRET-KEY-BYTES\n-----END OPENSSH PRIVATE KEY-----\n';
const KNOWN_HOSTS = '10.9.9.9 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5MU4KNOWNHOSTSMARKER';
const CONFIG_MARKER = 'mu4-config-marker-machine';

interface RecordedWrite {
  target: string;
  data: string;
  /** Mode bits of the containing directory when written, if it still existed. */
  dirMode?: number;
}

const { writes, execs, keysSeen } = vi.hoisted(() => ({
  keysSeen: [] as string[],
  writes: [] as { target: string; data: string; dirMode?: number }[],
  execs: [] as { command: string; stdin?: string }[],
}));

vi.mock('node:fs', async (original) => {
  const real = await original<typeof import('node:fs')>();
  const path = await import('node:path');
  const record = (target: unknown, data: unknown) => {
    let dirMode: number | undefined;
    try {
      dirMode = real.statSync(path.dirname(String(target))).mode & 0o777;
    } catch {
      dirMode = undefined;
    }
    writes.push({ target: String(target), data: String(data), dirMode });
  };
  const wrapped = {
    ...real,
    writeFileSync: ((target: never, data: never, ...rest: never[]) => {
      record(target, data);
      return (real.writeFileSync as (...a: unknown[]) => unknown)(target, data, ...rest);
    }) as typeof real.writeFileSync,
    appendFileSync: ((target: never, data: never, ...rest: never[]) => {
      record(target, data);
      return (real.appendFileSync as (...a: unknown[]) => unknown)(target, data, ...rest);
    }) as typeof real.appendFileSync,
  };
  return { ...wrapped, default: wrapped };
});

vi.mock('node:fs/promises', async (original) => {
  const real = await original<typeof import('node:fs/promises')>();
  const path = await import('node:path');
  const record = async (target: unknown, data: unknown) => {
    let dirMode: number | undefined;
    try {
      dirMode = (await real.stat(path.dirname(String(target)))).mode & 0o777;
    } catch {
      dirMode = undefined;
    }
    writes.push({ target: String(target), data: String(data), dirMode });
  };
  const wrapped = {
    ...real,
    writeFile: (async (target: never, data: never, ...rest: never[]) => {
      await record(target, data);
      return (real.writeFile as (...a: unknown[]) => unknown)(target, data, ...rest);
    }) as typeof real.writeFile,
    appendFile: (async (target: never, data: never, ...rest: never[]) => {
      await record(target, data);
      return (real.appendFile as (...a: unknown[]) => unknown)(target, data, ...rest);
    }) as typeof real.appendFile,
  };
  return { ...wrapped, default: wrapped };
});

// The fake machine: an SFTP lease that answers every command with success and records what it was sent.
vi.mock('../../machine/machine-connection.js', async (original) => {
  const real = await original<Record<string, unknown>>();
  const sftp = {
    execStreaming: (
      command: string,
      options?: { stdin?: string; onStdout?: (d: string) => void }
    ) => {
      execs.push({ command, stdin: options?.stdin });
      return Promise.resolve(0);
    },
    exec: (command: string) => {
      execs.push({ command });
      return Promise.resolve('');
    },
  };
  const { configService } = await import('../../config/config-resources.js');
  const acquireFor = (machine: unknown, sshPrivateKey: string) => {
    keysSeen.push(sshPrivateKey);
    return Promise.resolve({
      sftp,
      machine,
      sshPrivateKey,
      release: () => {},
      ensure: () => Promise.resolve(sftp),
    });
  };
  return {
    ...real,
    machineConnections: {
      acquireFor,
      // Resolves exactly as the real manager does: key and machine from the request's config.
      acquire: async (machineName: string) => {
        const config = await configService.getLocalConfig();
        const machine = await configService.getLocalMachine(machineName);
        return acquireFor(machine, config.sshPrivateKey ?? '');
      },
    },
  };
});

process.env.REDIACC_TELEMETRY_DISABLED = '1';

import { localExecutorService } from '../../executor/local-executor.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

const CONFIG = {
  schemaVersion: 3,
  id: '00000000-0000-4000-8000-0000000000dd',
  version: 1,
  credentials: { ssh: { privateKey: PRIVATE_KEY } },
  resources: {
    machines: {
      [CONFIG_MARKER]: { ip: '10.9.9.9', user: 'deploy', port: 22, knownHosts: KNOWN_HOSTS },
    },
    repositories: {},
  },
  encryption: { mode: 'plaintext' },
} as unknown as RdcConfig;

describe('MU4: key material lifetime on the dispatch path', () => {
  let server: ReturnType<typeof serve> | undefined;

  afterEach(() => {
    server?.close();
    server = undefined;
    writes.length = 0;
    execs.length = 0;
    keysSeen.length = 0;
  });

  function runMachineStatus(): Promise<Response> {
    const deps: ServeDeps = {
      mode: 'container',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        pinnedOrgId: 'org-1',
        fetchImpl: (() =>
          Promise.resolve(
            Response.json({
              active: true,
              scopes: ['proxy:exec', 'audit:write'],
              orgId: 'org-1',
              teamId: null,
              createdByUserId: 'user-owner',
              userEmail: 'owner@example.com',
              orgRole: 'owner',
            })
          )) as unknown as typeof fetch,
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      executor: localExecutorService,
      loadConfig: () => Promise.resolve(CONFIG),
      authorize,
      audit: () => Promise.resolve(),
      detach: () => false,
    };
    server = serve({ fetch: createServeApp(deps).fetch, port: 0 });
    const baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    return fetch(`${baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: 'Bearer rdt_owner', 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'machine status',
        positionals: { name: CONFIG_MARKER },
      }),
    });
  }

  const carriesSecret = (write: RecordedWrite): boolean =>
    [PRIVATE_KEY.trim(), 'MU4-SECRET-KEY-BYTES', 'MU4KNOWNHOSTSMARKER', CONFIG_MARKER].some(
      (marker) => write.data.includes(marker)
    );

  /** A write is allowed only inside a per-request directory that is 0700 and gone now. */
  const allowed = (write: RecordedWrite): boolean =>
    write.dirMode === 0o700 && !existsSync(write.target.replace(/[^/]+$/, ''));

  it('sends the key to the machine in memory and writes none of it to disk', async () => {
    const response = await runMachineStatus();
    const body = await response.text();
    expect(response.status, body).toBe(200);

    // Non-vacuity: the command really went through the executor and the key travelled the in-memory vault.
    expect(keysSeen.some((key) => key.includes('MU4-SECRET-KEY-BYTES'))).toBe(true);
    expect(execs.length).toBeGreaterThan(0);

    const leaked = writes.filter((write) => carriesSecret(write) && !allowed(write));
    expect(leaked).toEqual([]);
  });

  it('the spy sees a write of key bytes (control)', async () => {
    const { writeFileSync, rmSync, mkdtempSync } = await import('node:fs');
    const { tmpdir } = await import('node:os');
    const dir = mkdtempSync(`${tmpdir()}/mu4-control-`);
    try {
      writeFileSync(`${dir}/k`, PRIVATE_KEY);
      expect(statSync(dir).isDirectory()).toBe(true);
      expect(writes.filter(carriesSecret)).toHaveLength(1);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
