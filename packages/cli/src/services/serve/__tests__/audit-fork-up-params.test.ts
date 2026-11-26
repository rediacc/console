/**
 * Review 3a102a4c: a served command that makes several machine calls (fork, then up) keeps the
 * image-making call's function and params on its outcome event, so the audit still names the GUID of the
 * image the fork made. A command with no image-making call reports its last call, as before.
 *
 * The real serve app runs; the audit sink and the machine (a fake renet) are faked, and so are the SSH
 * pool and key deployment the fork orchestration leases.
 */

import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

vi.mock('../../machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn(() =>
      Promise.resolve({
        sftp: {},
        machine: { ip: '10.1.1.1', user: 'root' },
        sshPrivateKey: 'team-key',
        ensure: vi.fn(() => Promise.resolve({})),
        release: vi.fn(),
      })
    ),
  },
}));

vi.mock('../../repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn(() => Promise.resolve()),
  removeRepoKeyIfDeployed: vi.fn(() => Promise.resolve()),
}));

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-audit-fork-up-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import type { ExecutorAuditEvent } from '../deps.js';
import {
  bootContainerExecutor,
  type ContainerExecutor,
  createFakeConfigStore,
  fakeRenet,
  OPEN_POLICY,
  OWNER_TOKEN,
} from './writeback-harness.js';

function storedConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000c8',
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
              credential: 'shop-credential',
            },
          },
        },
      },
    },
    state: { repos: { shop: { latest: { networkId: 2816 } } } },
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

describe('the outcome event keeps the image-making call', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    await executor?.close();
    executor = undefined;
  });

  async function run(pathKey: string, params: Record<string, unknown>) {
    const store = await createFakeConfigStore(storedConfig(), OPEN_POLICY);
    const events: ExecutorAuditEvent[] = [];
    const renet = fakeRenet();
    executor = await bootContainerExecutor(store, renet.executor, {
      audit: (event) => {
        events.push(event);
        return Promise.resolve();
      },
    });
    await executor.grantKey();
    const response = await fetch(`${executor.baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey,
        params,
        positionals: { ref: 'shop' },
        requestId: 'req-fork-up.1',
      }),
    });
    await response.text();
    return { events, calls: renet.calls };
  }

  it('a fork followed by up reports the fork call and its GUID param', async () => {
    const { events, calls } = await run('repo fork', { tag: 'try1', checkpoint: true, up: true });
    const names = calls.map((call) => call.functionName);
    expect(names).toContain('repository_fork');
    expect(names.at(-1)).not.toBe('repository_fork');
    const outcome = events.find((event) => event.outcome !== 'started' && event.functionName);
    expect(outcome?.functionName).toBe('repository_fork');
    // The fork's own GUID param: the one the fork call was made with, a fresh GUID, neither the tag name nor the source repo's GUID.
    const forkCall = calls.find((call) => call.functionName === 'repository_fork');
    const madeGuid = forkCall?.params?.tag;
    expect(madeGuid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    expect(madeGuid).not.toBe('11111111-1111-4111-8111-111111111111');
    expect(outcome?.functionParams?.tag).toBe(madeGuid);
  });

  it('control: a command with no image-making call reports its last call', async () => {
    const { events, calls } = await run('repo up', {});
    const last = calls.at(-1)?.functionName;
    expect(last).toBeDefined();
    const outcome = events.find((event) => event.outcome !== 'started' && event.functionName);
    expect(outcome?.functionName).toBe(last);
  });
});
