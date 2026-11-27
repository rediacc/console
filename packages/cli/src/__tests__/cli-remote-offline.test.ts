/**
 * A remote config with its server unreachable, driven through the whole CLI (the root preAction
 * judge, then the action): a read is served from the offline cache with the staleness warning and
 * exit 0, and a write refuses naming the config and saying the change was NOT saved
 * (CLAUDE.md *Config Storage*; `./run.sh drill transfer` phases 2 and 3).
 *
 * vm:check A2.2 (2026-11-27): the root judge opened the remote session (`/configs/session`) before
 * the action ran, so with the server gone every command, read or write, died with "Config server
 * … is unreachable" (exit 6) and the cache was never consulted. The session's principal and policy
 * are now kept in the token file when they are opened, and judged with while the server is
 * unreachable.
 *
 * Only the config server transport is faked (it refuses the connection); the config file, the
 * token file, the adapter, the judge and the offline cache are the real ones, in this file's
 * throwaway config home (isolate-config-home.ts).
 */

import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { serverFetch } = vi.hoisted(() => ({ serverFetch: vi.fn() }));

vi.mock('../services/config/config-server-client.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/config/config-server-client.js')>()),
  configServerFetch: serverFetch,
}));

class ExitCalled extends Error {
  constructor(readonly code: number) {
    super(`exit ${code}`);
  }
}

const CONFIG = 'offline-drill';
const SERVER = 'http://127.0.0.1:9';
const STORE = randomUUID();
const CONFIG_ID = randomUUID();

const configDir = () => getConfigDir();
const configFile = () => join(configDir(), `${CONFIG}.json`);

/** The cache a pull left: version 2 of the server copy, one machine. */
function writeCachedConfig(): void {
  mkdirSync(configDir(), { recursive: true });
  const doc = {
    schemaVersion: 3,
    id: randomUUID(),
    version: 2,
    resources: { machines: { 'cached-box': { ip: '10.9.8.7', user: 'ops' } } },
    remote: {
      apiUrl: SERVER,
      storeId: STORE,
      configId: CONFIG_ID,
      storageKeyId: 'drill-key',
      cachedVersion: 2,
      cachedAt: new Date(Date.now() - 60_000).toISOString(),
    },
  };
  writeFileSync(configFile(), `${JSON.stringify(doc, null, 2)}\n`);
}

/** The token file an online run left, with the session context it judged with when `kept`. */
function writeTokenFile(kept: unknown): void {
  const dir = join(configDir(), '.tokens');
  mkdirSync(dir, { recursive: true });
  const sync = {
    binding: `${STORE}/${CONFIG_ID}/`,
    highWater: 2,
    envelopeVersion: 4,
    fckSalt: 'salt',
    ...(kept === undefined ? {} : { policyContext: kept }),
  };
  writeFileSync(
    join(dir, `${CONFIG}.json`),
    JSON.stringify({ token: 'config-token', wrappedCek: 'wrapped', sync }),
    { mode: 0o600 }
  );
}

/** An admin the server named online, under an org with no policy record (admins may act). */
const ADMIN_CONTEXT = {
  principal: { orgRole: 'admin', userEmail: 'admin@example.com' },
  policy: { locked: [], ignoredLocked: [] },
};

/** A member under no policy record: the missing-policy default refuses members everything. */
const MEMBER_CONTEXT = {
  principal: { orgRole: 'member', userEmail: 'member@example.com' },
  policy: { locked: [], ignoredLocked: [] },
};

function refusedConnection(): Error {
  return new TypeError('fetch failed', {
    cause: Object.assign(new Error('connect ECONNREFUSED 127.0.0.1:9'), { code: 'ECONNREFUSED' }),
  });
}

interface Run {
  code: number;
  warnings: string;
  errors: string;
  stdout: string;
}

/** One CLI process: fresh modules, so no config, adapter or judgement is memoized from another run. */
async function rdc(...argv: string[]): Promise<Run> {
  vi.resetModules();
  const { createCli } = await import('../cli.js');
  const { outputService } = await import('../services/core/output.js');
  const warn = vi.spyOn(outputService, 'warn');
  const errorSpy = vi.spyOn(outputService, 'error');
  const stdout: string[] = [];
  const stderr: string[] = [];
  vi.spyOn(process.stdout, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stdout.push(String(chunk));
    return true;
  });
  vi.spyOn(process.stderr, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stderr.push(String(chunk));
    return true;
  });
  vi.spyOn(console, 'log').mockImplementation((...a: unknown[]) => {
    stdout.push(`${a.join(' ')}\n`);
  });
  vi.spyOn(console, 'error').mockImplementation((...a: unknown[]) => {
    stderr.push(`${a.join(' ')}\n`);
  });
  vi.spyOn(console, 'warn').mockImplementation((...a: unknown[]) => {
    stderr.push(`${a.join(' ')}\n`);
  });
  vi.spyOn(process, 'exit').mockImplementation(((code?: number) => {
    throw new ExitCalled(code ?? 0);
  }) as never);
  let code = 0;
  try {
    await createCli().parseAsync(['node', 'rdc', ...argv]);
  } catch (error) {
    if (!(error instanceof ExitCalled)) throw error;
    code = error.code;
  }
  const said = (spy: typeof warn) => spy.mock.calls.map((c) => String(c[0])).join('\n');
  return {
    code,
    warnings: `${said(warn)}\n${stderr.join('')}`,
    errors: `${said(errorSpy)}\n${stderr.join('')}`,
    stdout: stdout.join(''),
  };
}

describe('a remote config whose server is unreachable', () => {
  const saved = { ...process.env };
  beforeEach(() => {
    process.env.REDIACC_CONFIG = CONFIG;
    process.env.REDIACC_TELEMETRY_DISABLED = '1';
    process.env.REDIACC_DEFAULT_OUTPUT = 'table';
    delete process.env.REDIACC_TOKEN;
    serverFetch.mockReset().mockRejectedValue(refusedConnection());
    writeCachedConfig();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    process.env = { ...saved };
  });

  it('serves a read from the offline cache with the staleness warning and exit 0', async () => {
    writeTokenFile(ADMIN_CONTEXT);
    const run = await rdc('machine', 'list');
    expect(run.code).toBe(0);
    expect(run.warnings).toContain('is unreachable; serving config');
    expect(run.warnings).toContain('from the offline cache');
    expect(run.warnings).toContain('Changes cannot be saved until the server is reachable.');
    expect(run.stdout).toContain('cached-box');
    expect(run.stdout).not.toContain('offline cache');
  });

  it('refuses a write naming the config, and says the change was NOT saved', async () => {
    writeTokenFile(ADMIN_CONTEXT);
    const keyFile = join(configDir(), 'id_ed25519_b');
    writeFileSync(
      keyFile,
      '-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----\n',
      { mode: 0o600 }
    );
    const before = readFileSync(configFile(), 'utf8');
    const run = await rdc('config', 'ssh', 'set', '--key', keyFile);
    expect(run.code).toBe(6);
    expect(run.errors).toContain(`Cannot save: config "${CONFIG}"`);
    expect(run.errors).toContain(SERVER);
    expect(run.errors).toContain('The change was NOT saved.');
    expect(readFileSync(configFile(), 'utf8')).toBe(before);
  });

  it('control: with no session kept from an online run, the read is refused, never judged as the owner', async () => {
    writeTokenFile(undefined);
    const run = await rdc('machine', 'list');
    expect(run.code).toBe(6);
    expect(run.errors).toContain(`Config server ${SERVER} is unreachable`);
    expect(run.stdout).not.toContain('cached-box');
  });

  it('control: a kept member session is judged as that member offline, so the read is refused by policy', async () => {
    writeTokenFile(MEMBER_CONTEXT);
    const run = await rdc('machine', 'list');
    expect(run.code).not.toBe(0);
    expect(run.errors).toContain('POLICY_DENIED');
    expect(run.stdout).not.toContain('cached-box');
  });
});
