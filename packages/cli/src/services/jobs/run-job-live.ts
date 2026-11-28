/**
 * The real, SSH-backed claim behind {@link runJob}'s steps: the `renet job claim` command, its answer parser, the
 * pooled-session exec, and the live step-runner deps for this process's config.
 */

import { hostname } from 'node:os';
import { shellQuote } from '../../utils/shell-quote.js';
import { assertJobId } from '../executor/job-client.js';
import {
  type ClaimAnswer,
  type ClaimExec,
  type ClaimResultKind,
  type ConfigIdentity,
  JOB_NOT_FOUND_EXIT,
  JobGoneError,
  type StepRunnerDeps,
} from './run-job.js';
import type { TicketStore } from './ticket-store.js';

// --- the live claim ----------------------------------------------------------

/** The claim command. Step names are validated by the registry pattern before they reach a shell. */
export function buildJobClaimCommand(params: {
  remoteRenetPath: string;
  jobId: string;
  steps: string[];
  done?: boolean;
  origin: ConfigIdentity;
  host: string;
  pid: number;
}): string {
  for (const name of params.steps) {
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(name)) throw new Error(`Invalid step name: ${name}`);
  }
  const origin = JSON.stringify({
    client: 'rdc',
    ...(params.origin.configName || params.origin.configId
      ? {
          config: {
            ...(params.origin.configName ? { name: params.origin.configName } : {}),
            ...(params.origin.configId ? { id: params.origin.configId } : {}),
          },
        }
      : {}),
  });
  return [
    'sudo',
    shellQuote(params.remoteRenetPath),
    'job claim',
    `--id ${assertJobId(params.jobId)}`,
    `--steps ${params.steps.join(',')}`,
    params.done ? '--done' : '',
    `--origin ${shellQuote(origin)}`,
    `--host ${shellQuote(params.host)}`,
    `--pid ${Math.trunc(params.pid)}`,
  ]
    .filter(Boolean)
    .join(' ');
}

/** Parse `renet job claim` JSON: `{ job_id, steps: [{ name, result }] }`. */
export function parseClaimOutput(stdout: string): ClaimAnswer[] {
  const start = stdout.indexOf('{');
  const parsed = JSON.parse(start >= 0 ? stdout.slice(start) : stdout) as {
    steps?: { name?: unknown; result?: unknown }[];
  };
  const kinds: ClaimResultKind[] = ['claimed', 'reclaimed', 'already-claimed', 'done'];
  return (parsed.steps ?? [])
    .filter(
      (s): s is { name: string; result: ClaimResultKind } =>
        typeof s.name === 'string' && kinds.includes(s.result as ClaimResultKind)
    )
    .map((s) => ({ name: s.name, result: s.result }));
}

/** The real claim: one SSH exec of `renet job claim` per call, on a pooled connection. */
function liveClaimExec(observer: ConfigIdentity): ClaimExec {
  return async (request) => {
    const { connectForJobs } = await import('../executor/job-remote.js');
    const conn = await connectForJobs(request.machine, 'read-only');
    try {
      const sftp = await conn.lease.ensure();
      const command = buildJobClaimCommand({
        remoteRenetPath: conn.remoteRenetPath,
        jobId: request.jobId,
        steps: request.steps,
        done: request.done,
        origin: observer,
        host: hostname(),
        pid: process.pid,
      });
      let stdout = '';
      let stderr = '';
      const exitCode = await sftp.execStreaming(command, {
        onStdout: (data) => {
          stdout += data.toString();
        },
        onStderr: (data) => {
          stderr += data.toString();
        },
      });
      if (exitCode === JOB_NOT_FOUND_EXIT) throw new JobGoneError(request.jobId);
      if (exitCode !== 0) {
        const detail = (stderr || stdout).trim().split('\n')[0] ?? '';
        throw new Error(
          `Failed to claim steps ${request.steps.join(',')} of job ${request.jobId}: ${detail || `renet exited ${exitCode}`}`
        );
      }
      return parseClaimOutput(stdout);
    } finally {
      conn.lease.release();
    }
  };
}

/** The live step-runner deps for this process's config. */
export async function liveStepRunnerDeps(store: TicketStore): Promise<StepRunnerDeps> {
  const [{ configService }, { writeStderr }] = await Promise.all([
    import('../config/config-resources.js'),
    import('../core/request-context.js'),
  ]);
  let configId: string | undefined;
  try {
    configId = (await configService.getCurrent())?.id;
  } catch {
    configId = undefined;
  }
  const observer: ConfigIdentity = { configName: store.config, configId };
  return {
    claim: liveClaimExec(observer),
    observer,
    warn: (line) => writeStderr(`${line}\n`),
    hold: async (machine) => {
      const { machineConnections } = await import('../machine/machine-connection.js');
      const lease = await machineConnections.acquire(machine);
      return () => lease.release();
    },
  };
}
