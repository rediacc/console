/**
 * WB11 (agent/plans/PLAN-rmcp-writeback.md): a create job's rollback survives the
 * container's throwaway disk. The executor keeps its job tickets (and the rollback
 * step each carries) on that disk, so a sleep between dispatch and settle loses them.
 * The poll then rebuilds the rollback from the machine's own record of the job.
 *
 * Setup as in WB7 (writeback-job-settle.test.ts): a proxied `repo create` registers the repo
 * (pushed to the store) and hands its job back as a ticket; the executor then restarts and the
 * client polls under a key granted again. Here the ticket is gone too, and no step is claimed on
 * the machine: the registration of a volume that was never made must still leave the store.
 */

import { existsSync, readdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
  assertAgentRepoCreate: async () => undefined,
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
const { jobStatus, claimed, jobRecord } = vi.hoisted(() => ({
  jobStatus: { state: 'failed' },
  claimed: [] as string[],
  jobRecord: { repoGuid: undefined as string | undefined },
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
        repo_guid: jobRecord.repoGuid,
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

describe('WB11: a create job settled after the container disk was dropped still rolls back', () => {
  const running: ContainerExecutor[] = [];

  afterEach(async () => {
    for (const executor of running.splice(0)) await executor.close().catch(() => undefined);
  });

  it('a create job that fails after a sleep wiped the ticket removes its registration from the store', async () => {
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

    // The machine's status file names the repository the job creates.
    const family = Object.values((await store.current()).resources?.repositories ?? {})[0];
    jobRecord.repoGuid = family?.tags[family.grand]?.repositoryGuid;
    expect(jobRecord.repoGuid).toBeTruthy();

    // The container sleeps: its disk, and the ticket on it, is gone, together with the process's sessions and keys.
    const jobsDir = join(process.env.XDG_CONFIG_HOME ?? '', 'rediacc', 'jobs');
    expect(existsSync(jobsDir) && readdirSync(jobsDir).length > 0).toBe(true);
    rmSync(jobsDir, { recursive: true, force: true });
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

    // The ticket was gone, so no step was claimed on the machine; the rollback ran from the job record under the write-capable scope.
    expect(claimed).toEqual([]);
    expect((await store.current()).resources?.repositories).toEqual({});
    expect(store.puts.map((put) => put.status)).toEqual([200, 200]);
    expect(store.puts[1]?.removedKeys.length).toBeGreaterThan(0);
  });
});
