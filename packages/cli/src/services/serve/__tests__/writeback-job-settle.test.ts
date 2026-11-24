/**
 * WB7 (agent/plans/PLAN-rmcp-writeback.md Design 7): the job routes run under the
 * same write-capable scope as dispatch, and rehydrate it after an executor restart.
 *
 * A proxied `repo create` registers the repo (pushed to the store) and hands its
 * job back as a ticket. The executor process then restarts: its sessions, keys
 * and decrypted configs are gone. The client grants a key again and polls; the
 * poll that sees the job failed runs the create's rollback step, and that step's
 * config write must reach the store, through a session store the restarted
 * executor pulled afresh from the grant. Before write-back the step's write was
 * refused inside the poll and swallowed, so the registration of a volume that
 * was never made outlived the job.
 */

import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-writeback-job-settle-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

// The poll's only machine seam: the job's status, as `renet job logs --with-status` prints it, and `renet job claim`, which grants every step it is asked for.
const { jobStatus, claimed } = vi.hoisted(() => ({
  jobStatus: { state: 'failed' },
  claimed: [] as string[],
}));
vi.mock('../../executor/job-remote.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  connectForJobs: () =>
    Promise.resolve({
      remoteRenetPath: '/usr/local/bin/renet',
      lease: {
        release: () => {},
        ensure: () =>
          Promise.resolve({
            execStreaming: (command: string, io: { onStdout: (data: Buffer) => void }) => {
              const steps = (/--steps\s+'?([\w,-]+)/.exec(command)?.[1] ?? '').split(',');
              claimed.push(...steps);
              io.onStdout(
                Buffer.from(
                  JSON.stringify({ steps: steps.map((name) => ({ name, result: 'claimed' })) })
                )
              );
              return Promise.resolve(0);
            },
          }),
      },
    }),
  runJobCommand: () =>
    Promise.resolve(
      `${JSON.stringify({
        type: 'job_status',
        state: jobStatus.state,
        exit_code: jobStatus.state === 'succeeded' ? 0 : 1,
        function: 'repository_create',
      })}\n`
    ),
}));

import {
  bootContainerExecutor,
  type ContainerExecutor,
  createFakeConfigStore,
  fakeRenet,
  OPEN_POLICY,
  OWNER_TOKEN,
} from './writeback-harness.js';

const JOB_ID = 'j1a2b-0123abcd';

function storedConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000c7',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: {
      machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
      repositories: {},
    },
    state: {},
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

describe('WB7: a job settled after an executor restart still writes back', () => {
  const running: ContainerExecutor[] = [];

  afterEach(async () => {
    for (const executor of running.splice(0)) await executor.close().catch(() => undefined);
  });

  it('a create job that fails after the restart removes its registration from the store', async () => {
    const store = await createFakeConfigStore(storedConfig(), OPEN_POLICY);
    // The create job outlives its attach window: renet hands back a running ticket.
    const renet = fakeRenet(() => ({
      success: true,
      exitCode: 0,
      durationMs: 1,
      state: 'running',
      jobId: JOB_ID,
    }));

    const first = await bootContainerExecutor(store, renet.executor);
    running.push(first);
    await first.grantKey();
    const created = await first.command(
      'repo create',
      { machine: 'm1', size: '1G' },
      { name: 'fresh' }
    );
    expect(created.result.success).toBe(true);
    expect(renet.calls).toHaveLength(1);
    // The registration was saved before the job ran.
    expect(Object.keys((await store.current()).resources?.repositories ?? {})).toEqual(['fresh']);

    // The executor restarts: a new process holds no session, no key and no config.
    await first.close();
    running.splice(0);
    const second = await bootContainerExecutor(store, renet.executor);
    running.push(second);
    await second.grantKey();

    jobStatus.state = 'failed';
    const poll = await fetch(
      `${second.baseUrl}${PROXY_ROUTES.jobPoll(JOB_ID)}?machine=m1&sinceLine=0`,
      { headers: { authorization: `Bearer ${OWNER_TOKEN}` } }
    );
    expect(poll.status).toBe(200);
    expect(((await poll.json()) as { status: { state: string } }).status.state).toBe('failed');

    // The rollback step ran under the restarted executor's write-capable scope: the store no longer holds the repo.
    expect(claimed).toContain('rollbackCreate');
    expect((await store.current()).resources?.repositories).toEqual({});
    expect(store.puts.map((put) => put.status)).toEqual([200, 200]);
    expect(store.puts[1]?.removedKeys.length).toBeGreaterThan(0);
  });
});
