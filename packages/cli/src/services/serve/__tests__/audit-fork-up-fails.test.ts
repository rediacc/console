/**
 * Review 1b7e16f7.1: a served fork whose later up fails keeps the fork call on the outcome event, and the
 * event stays the command's own: its path and its failure are the command's, the function names the image.
 * Its own file, because a second fork in the file that tests the success path never reaches its up.
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
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-audit-fork-up-fails-`);
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
    id: '00000000-0000-4000-8000-0000000000cb',
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

describe('a fork whose up fails', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    await executor?.close();
    executor = undefined;
  });

  it('stays attributed to the command, with the fork GUID param (review 1b7e16f7.1)', async () => {
    const store = await createFakeConfigStore(storedConfig(), OPEN_POLICY);
    const events: ExecutorAuditEvent[] = [];
    const renet = fakeRenet((options) =>
      options.functionName === 'repository_up'
        ? { success: false, exitCode: 7, durationMs: 1, stdout: '', error: 'up failed' }
        : { success: true, exitCode: 0, durationMs: 1, stdout: '' }
    );
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
        pathKey: 'repo fork',
        params: { tag: 'try1', checkpoint: true, up: true },
        positionals: { ref: 'shop' },
        requestId: 'req-fork-up-fails.1',
      }),
    });
    await response.text();

    const names = renet.calls.map((call) => call.functionName);
    expect(names).toContain('repository_fork');
    expect(names.at(-1)).toBe('repository_up');
    const outcome = events.find((event) => event.outcome !== 'started' && event.functionName);
    expect(outcome).toMatchObject({
      commandPath: 'repo fork',
      success: false,
      functionName: 'repository_fork',
    });
    expect(outcome?.functionParams?.tag).toEqual(expect.any(String));
  });
});
