/**
 * Running an operation as a detached renet job: start it, follow its event
 * stream through the same path `rdc job logs` uses, and map its terminal
 * status onto an ExecuteResult.
 */

import type { SFTPClient } from '../../remote/sftp/index.js';
import { clusterKubeconfigRemotePath } from '../cluster/cluster-target.js';
import type { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { writeStderr, writeStdout } from '../core/request-context.js';
import { machineConnections } from '../machine/machine-connection.js';
import { fetchOtlpCredentials } from '../telemetry/otlp-credentials.js';
import { isTelemetryDisabled } from '../telemetry/telemetry.js';
import {
  backgroundStartedHint,
  buildJobStartCommand,
  createJobOutputCollector,
  isJobCommandUnsupported,
  JobLogCursor,
  JobStartFailedError,
  jobStatusToExecuteResult,
  parseJobHandle,
  resumeHint,
  versionSkewWarning,
} from './job-client.js';
import { followJobLogs, readJobStatus, renderJobEvent } from './job-remote.js';
import { buildRenetEnvPrefix, detectEnvironment, resolveEnvSecrets } from './renet-command.js';
import { capReason } from './renet-output.js';
import type { ExecuteOptions, ExecuteResult } from './types.js';

/** Exit code reported when the operator detaches from a running job with Ctrl-C. */
const EXIT_DETACHED = 130;

/**
 * Run an operation as a DETACHED renet job, so it survives this connection.
 *
 * Three phases: start the job and get its ID back, tail its event stream
 * (reconnecting and resuming if the network drops), then read its terminal
 * status and map that onto the same ExecuteResult a synchronous run produces.
 * The render path is byte-for-byte the same one `runRemoteExecution` uses, so
 * spinners and the step timeline behave identically. Under `follow: false`
 * (`--background`) it returns the moment the job starts, leaving the work
 * running on the machine.
 *
 * Returns null in exactly one case: the renet deployed on the machine is too
 * old to know the `job` command. That is a version-skew signal for the caller
 * to fall back to a synchronous run, and it is safe precisely because cobra
 * rejects an unknown command before running any work.
 */
export async function runDetachedExecution(
  remoteRenetPath: string,
  vault: string,
  options: ExecuteOptions,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string
): Promise<ExecuteResult | null> {
  const startedAt = Date.now();

  // Every phase goes through the lease rather than a captured client, so a connection that dies between phases is transparently re-established.
  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
  try {
    const handle = await startJob(await lease.ensure(), remoteRenetPath, vault, options);
    if (handle === null) return null; // version skew: caller falls back

    // Announce the job the instant it exists, before any event, so a serve route can emit its kind:'job' line and a client can re-attach even if the connection drops before the first event arrives.
    options.onJobStarted?.(handle.job_id);

    if (options.follow === false) {
      // Fire-and-forget (--background): hand back the id and how to catch up, and return success without waiting for the job to finish.
      writeStdout(`${backgroundStartedHint(handle.job_id, options.machineName)}\n`);
      return {
        success: true,
        exitCode: 0,
        durationMs: Date.now() - startedAt,
        jobId: handle.job_id,
      };
    }

    // Follow through the SAME implementation `rdc job logs` uses, so a detached run and a re-attached one render identically and share one reconnect-and-resume path rather than two that can drift apart. The collector captures the output unconditionally (the spool is always NDJSON), independent of whether the caller wants it rendered.
    const cursor = new JobLogCursor();
    const collector = createJobOutputCollector();
    const render = options.onEvent ?? (options.captureOutput ? undefined : renderJobEvent);
    const interrupted = await followJobLogs(
      lease,
      remoteRenetPath,
      handle.job_id,
      {
        onEvent: (event, line) => {
          collector.consume(event);
          render?.(event, line);
        },
        debug: options.debug,
      },
      cursor
    );

    if (interrupted) {
      // The operator stopped WATCHING; the job keeps running. Cancelling here would destroy a half-finished migration because someone hit Ctrl-C on a scrolling log, which is the opposite of what a detached job is for.
      const hint = resumeHint(handle.job_id, options.machineName);
      writeStderr(`\n${hint}\n`);
      return {
        success: false,
        exitCode: EXIT_DETACHED,
        error: hint,
        durationMs: Date.now() - startedAt,
        outputEchoed: true,
      };
    }

    const status = await readJobStatus(await lease.ensure(), remoteRenetPath, handle.job_id);
    return jobStatusToExecuteResult(status, Date.now() - startedAt, collector);
  } finally {
    lease.release();
  }
}

/**
 * Start a detached job. Returns its handle, or null when the machine's renet
 * does not support detached jobs at all.
 *
 * The version-skew check is deliberately narrow: ONLY "unknown command" earns
 * a null. Any other failure throws, because a `job start` that failed AFTER
 * spawning the unit could already be doing the work, and falling back would
 * then run the operation a second time.
 */
async function startJob(
  sftp: SFTPClient,
  remoteRenetPath: string,
  vault: string,
  options: ExecuteOptions
): Promise<{ job_id: string } | null> {
  const otlpCreds = isTelemetryDisabled() ? null : await fetchOtlpCredentials();
  const repoRef =
    typeof options.params?.repository === 'string' ? options.params.repository : undefined;
  const envSecrets = await resolveEnvSecrets(repoRef);
  const kubeconfig = options.kubeCluster
    ? clusterKubeconfigRemotePath(options.kubeCluster)
    : undefined;

  // The env prefix is load-bearing: `job start` snapshots the environment it is handed into the job's spool, so `job run` (which systemd spawns with a clean environment) can re-inject the repo's secrets and the OTLP creds.
  const command = buildJobStartCommand({
    remoteRenetPath,
    envPrefix: buildRenetEnvPrefix({
      isDevelopment: detectEnvironment() === 'development',
      telemetryDisabled: isTelemetryDisabled(),
      otlpCreds,
      envSecrets,
      kubeconfig,
    }),
    timeoutMs: options.timeout,
    debug: options.debug,
  });

  let stdout = '';
  let stderr = '';
  const exitCode = await sftp.execStreaming(command, {
    stdin: vault,
    onStdout: (data) => {
      stdout += data;
    },
    onStderr: (data) => {
      stderr += data;
    },
  });

  if (exitCode !== 0) {
    const combined = stdout + stderr;
    if (isJobCommandUnsupported(combined)) {
      outputService.warn(versionSkewWarning(options.machineName));
      return null;
    }
    throw new JobStartFailedError(options.machineName, capReason((stderr || stdout).trim()));
  }

  return parseJobHandle(stdout);
}
