/**
 * LocalExecutorService - Direct task execution via renet.
 *
 * This service enables the CLI to work directly with renet
 * over SSH, without any intermediate API.
 *
 * Uses direct SSH to the target machine and runs `renet execute --executor local`
 * which builds and executes the command locally on the machine (no double SSH).
 *
 * Delegates to shared utilities in renet-execution.ts.
 */

import { t } from '../../i18n/index.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { formatDuration } from '../../utils/format.js';
import { startSpinner, stopSpinner } from '../../utils/spinner.js';
import { clusterKubeconfigRemotePath } from '../cluster/cluster-target.js';
import { configService } from '../config/config-resources.js';
import { auditService } from '../core/audit.js';
import { outputService } from '../core/output.js';
import { machineConnections } from '../machine/machine-connection.js';
import {
  acquireRemoteRenet,
  buildLocalVault,
  readOptionalSSHKey,
  readSSHKey,
  verifyMachineSetup,
} from '../renet/renet-execution.js';
import {
  isRepoProvisioningFunction,
  isRestoreLicenseFunction,
  parseRenetLicenseFailure,
  type RenetLicenseFailure,
} from '../renet/renet-license-contract.js';
import { fetchOtlpCredentials } from '../telemetry/otlp-credentials.js';
import { isTelemetryDisabled } from '../telemetry/telemetry.js';
import { runDetachedExecution } from './detached-execution.js';
import { resolveExtraMachines } from './extra-machines.js';
import { createJobOutputCollector } from './job-client.js';
import {
  ensureRepoLicenseForProvisioning,
  ensureRepoLicenseForRestore,
  maybeRefreshRepoIdentity,
  maybeRefreshRepoLicenses,
  needsLicenseRecovery,
  refreshRepoIdentityFor,
  resolveLicenseFailure,
} from './license-recovery.js';
import { createQuietStderrPump, shouldEchoRelayLive } from './output-lines.js';
import { buildRemoteRenetCommand, detectEnvironment, resolveEnvSecrets } from './renet-command.js';
import { renetAccessFor } from './renet-function-access.js';
import {
  buildRenetExitError,
  createStdoutHandler,
  echoRenetFailure,
  extractStepsFromOutput,
  surfaceRenetWarnings,
} from './renet-output.js';
import type { ExecuteOptions, ExecuteResult } from './types.js';
import { loadContextRepositories, loadContextStorages, resolveKnownHosts } from './vault-inputs.js';

// The pieces split out of this module stay importable from it, so no caller had to move.
export { needsLicenseRecovery } from './license-recovery.js';
export { buildRemoteRenetCommand, buildRenetEnvPrefix } from './renet-command.js';
export { parseCapturedJson } from './renet-output.js';
// ExecuteResult only. The other seam types are consumed from executor-factory, which is the entry point to this layer; re-exporting them here as well just gave callers two doors to the same room.
export type { ExecuteResult } from './types.js';

/** Run a step with spinner + timing. Shows "Loading..." then "✓ Loaded (1.2s)" on the same line. */
async function timedStep<T>(
  spinnerText: string,
  successKey: string,
  fn: () => Promise<T>
): Promise<T> {
  const start = Date.now();
  const spinner = startSpinner(spinnerText);
  try {
    const result = await fn();
    const successText = t(successKey, { duration: formatDuration(Date.now() - start) });
    if (spinner) {
      stopSpinner(true, successText);
    } else {
      outputService.info(successText);
    }
    return result;
  } catch (error) {
    if (spinner) stopSpinner(false);
    throw error;
  }
}

/**
 * Service for executing tasks directly via renet subprocess.
 * Runs against a single machine over direct SSH.
 *
 * Uses direct SSH to the target machine and runs `renet execute --executor local`
 * with vault JSON piped via stdin. This avoids double-SSH (CLI→renet→machine).
 */
class LocalExecutorService {
  /**
   * Re-issue a repo license with identity proofs, for callers that ran a
   * create/fork with deferIdentityRefresh.
   */
  refreshIdentityFor(
    functionName: string,
    machineName: string,
    params: Record<string, unknown>
  ): Promise<void> {
    return refreshRepoIdentityFor(functionName, machineName, params);
  }

  private async executeWithConnectedSftp(
    sftp: SFTPClient,
    options: ExecuteOptions,
    remoteRenetPath: string,
    vault: string,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    startTime: number
  ): Promise<ExecuteResult> {
    let result = await this.runOperation(
      sftp,
      options,
      remoteRenetPath,
      vault,
      machine,
      sshPrivateKey
    );
    const failure: RenetLicenseFailure | null = needsLicenseRecovery(result)
      ? parseRenetLicenseFailure(result.stderr, result.stdout)
      : null;
    if (failure) {
      const recovered = await resolveLicenseFailure(
        result,
        failure,
        options,
        machine,
        sshPrivateKey,
        remoteRenetPath,
        sftp,
        startTime
      );
      if (recovered === null) {
        // Recovery issued a license. Re-run: exit 10 means renet refused BEFORE doing any work, so a second run cannot double-execute even a detached job (a strictly weaker claim than startJob's version-skew fallback).
        result = await this.runOperation(
          sftp,
          options,
          remoteRenetPath,
          vault,
          machine,
          sshPrivateKey
        );
      } else {
        return recovered;
      }
    }

    if (result.success && !options.deferIdentityRefresh) {
      await maybeRefreshRepoIdentity(options, machine, sshPrivateKey, remoteRenetPath, sftp);
    }

    const operationDurationMs = result.operationDurationMs ?? result.durationMs;
    return {
      ...result,
      durationMs: Date.now() - startTime,
      operationDurationMs,
    };
  }

  /**
   * Run the operation once, detached when the caller asked for it and the
   * machine supports it, else synchronously. Both variants flow back through the
   * shared recovery, identity-refresh, and duration tail in
   * executeWithConnectedSftp, so a detached run is no longer a second code path
   * that silently skips license recovery (finding #33).
   */
  private async runOperation(
    sftp: SFTPClient,
    options: ExecuteOptions,
    remoteRenetPath: string,
    vault: string,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string
  ): Promise<ExecuteResult> {
    if (options.detached) {
      const detached = await runDetachedExecution(
        remoteRenetPath,
        vault,
        options,
        machine,
        sshPrivateKey
      );
      // null means the machine's renet has no `job` command: fall back to sync.
      if (detached !== null) return detached;
    }
    return this.runRemoteExecution(sftp, remoteRenetPath, vault, options);
  }

  /**
   * Thin wrapper around `buildRemoteRenetCommand` that pulls the
   * environment-detection logic from the service instance. Kept as a
   * class method so call sites don't need to recompute `isDevelopment`
   * / `isTelemetryDisabled` themselves.
   */
  private buildRemoteCommand(
    remoteRenetPath: string,
    eventsMode?: boolean,
    otlpCreds?: { user: string; pass: string } | null,
    envSecrets?: Record<string, string>,
    kubeconfig?: string
  ): string {
    return buildRemoteRenetCommand({
      remoteRenetPath,
      eventsMode,
      isDevelopment: detectEnvironment() === 'development',
      telemetryDisabled: isTelemetryDisabled(),
      otlpCreds,
      envSecrets,
      kubeconfig,
    });
  }

  private async runRemoteExecution(
    sftp: SFTPClient,
    remoteRenetPath: string,
    vault: string,
    options: ExecuteOptions
  ): Promise<ExecuteResult> {
    // Fetch OTLP credentials so renet inherits them as env vars and its telemetry init picks them up. Skip the fetch entirely when telemetry is opted out, no wasted network round-trip, no credentials in memory to accidentally propagate downstream. `buildRemoteCommand`
    // still injects `REDIACC_TELEMETRY_DISABLED=1` for the remote end.
    const otlpCreds = isTelemetryDisabled() ? null : await fetchOtlpCredentials();
    const repoRef =
      typeof options.params?.repository === 'string' ? options.params.repository : undefined;
    const envSecrets = await resolveEnvSecrets(repoRef);
    const kubeconfig = options.kubeCluster
      ? clusterKubeconfigRemotePath(options.kubeCluster)
      : undefined;
    const command = this.buildRemoteCommand(
      remoteRenetPath,
      options.eventsMode,
      otlpCreds,
      envSecrets,
      kubeconfig
    );
    // Events mode streams NDJSON, not text. Reconstruct the real stdout from the events (below) instead of accumulating the raw stream: handing an event stream straight to parseCapturedJson is the pre-existing --proxy bug (#31).
    const collector = options.eventsMode ? createJobOutputCollector() : undefined;
    let stdout = '';
    let stderr = '';
    const stdoutHandler = createStdoutHandler(options, collector);
    // Renet routes diagnostics (lifecycle brackets, relayed sub-command stderr) to ITS stderr so they can never interleave with parseable stdout. Echo them live in interactive text mode, to OUR stderr, same "stdout belongs to the command" rule as createStdoutHandler.
    const echoStderrLive = Boolean(!options.captureOutput && !options.eventsMode);
    // Quiet logrus lines are WITHHELD from the live terminal and replayed only if the command fails. They were 227-358 columns wide and wrapped into garbage in every tutorial recording; dropping them outright is worse and was tried (see daemon/client.ts), because a failing child explains itself at info level. REDIACC_DEBUG restores the old firehose.
    //
    // This USES the shared pump rather than restating it: an inline copy lived here first, and it was a byte-for-byte duplicate of createQuietStderrPump whose only lasting effect was to push this function past the complexity gate. Two copies of a withhold-and-replay buffer is exactly how the two drift apart while both keep passing. BOTH the env var and the `--debug` FLAG. This
    // read only the env var, so `rdc repo up --debug` withheld renet's info-level lines anyway and a flag named --debug did not enable debug output. It cost a CI test: the concurrent-fork-isolation suite greps its `--debug` log for renet's "restored from checkpoint" (emitted with log.Infof), found nothing, and blamed console#440 for a regression that had not happened. The two
    // sibling call sites already pass options.debug; this one reached past it.
    const stderrPump = createQuietStderrPump({ echoAll: shouldEchoRelayLive(options) });
    const execStart = Date.now();
    const exitCode = await sftp.execStreaming(command, {
      stdin: vault,
      onStdout: (data) => {
        // Events mode reconstructs stdout from the parsed events (below), so the raw NDJSON is only fed to the handler, never accumulated as text.
        if (!collector) stdout += data;
        stdoutHandler(data);
      },
      onStderr: (data) => {
        stderr += data;
        if (echoStderrLive) stderrPump.write(String(data));
      },
    });
    // Emit any final line that arrived without a trailing newline.
    stdoutHandler.flush?.();
    // The command failed, so what we withheld is exactly what explains it.
    if (echoStderrLive) stderrPump.flush(exitCode !== 0);

    if (collector) stdout = collector.stdout;

    const combined = stdout + stderr;
    const renetDurationMatch = /operation completed.*?duration_ms=(\d+)/.exec(combined);
    const operationMs = renetDurationMatch
      ? Number.parseInt(renetDurationMatch[1], 10)
      : Date.now() - execStart;

    surfaceRenetWarnings(exitCode, combined, options);

    return {
      success: exitCode === 0,
      exitCode,
      error: exitCode === 0 ? undefined : buildRenetExitError(exitCode, stderr, stdout),
      durationMs: operationMs,
      stdout,
      stderr,
      outputEchoed: echoRenetFailure(exitCode, combined, options),
      steps: extractStepsFromOutput(combined),
    };
  }

  /**
   * Provision renet, verify machine setup, and handle pre-flight licensing.
   * Returns the remote renet path and whether the binary was uploaded.
   */
  private async provisionAndVerify(
    config: Awaited<ReturnType<typeof configService.getLocalConfig>>,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    options: ExecuteOptions,
    sftp: SFTPClient,
    cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[],
    quiet: boolean
  ): Promise<{ remoteRenetPath: string; renetUploaded: boolean }> {
    const provStart = Date.now();
    // The dispatched function decides whether this run may replace the machine's renet (RENET_FUNCTION_ACCESS).
    const access = renetAccessFor(options.functionName);
    const provisionFn = () =>
      acquireRemoteRenet(
        access,
        config,
        machine,
        sshPrivateKey,
        {
          debug: options.debug,
          skipRouterRestart: options.skipRouterRestart,
          machineName: options.machineName,
        },
        sftp
      );
    const { remotePath: remoteRenetPath, uploaded: renetUploaded } = quiet
      ? await provisionFn()
      : await timedStep(t('timing.step.provisioning'), 'timing.step.renetProvisioned', provisionFn);
    cliSteps.push({
      name: 'renet_provision',
      duration_ms: Date.now() - provStart,
      startedAtMs: provStart,
    });

    const verifyFn = () =>
      verifyMachineSetup(
        machine,
        sshPrivateKey,
        { ...options, functionName: options.functionName },
        sftp
      );
    const runVerify = async () => {
      const verifyStart = Date.now();
      if (quiet) {
        await verifyFn();
      } else {
        await timedStep(t('timing.step.verifying'), 'timing.step.machineVerified', verifyFn);
      }
      cliSteps.push({
        name: 'machine_verify',
        duration_ms: Date.now() - verifyStart,
        startedAtMs: verifyStart,
      });
    };

    if (isRepoProvisioningFunction(options.functionName)) {
      // License issuance only needs the provisioned renet binary, not the verified machine setup, run it concurrently with verification.
      const runLicense = async () => {
        const licStart = Date.now();
        await timedStep(t('timing.step.activating'), 'timing.step.licenseActivated', () =>
          ensureRepoLicenseForProvisioning(options, machine, sshPrivateKey, remoteRenetPath, sftp)
        );
        cliSteps.push({
          name: 'license',
          duration_ms: Date.now() - licStart,
          startedAtMs: licStart,
        });
      };
      await Promise.all([runVerify(), runLicense()]);
    } else if (isRestoreLicenseFunction(options.functionName)) {
      // Sequential, unlike the provisioning arm above, and the difference is not stylistic. That arm's concurrency is safe because its pre-flight only needs the renet binary; this one runs a licence SCAN on the target (the skip probe) over the same shared SFTP session `verifyMachineSetup` is using, and a restore target is by construction a machine nobody has verified yet. Verify
      // first, then license: a DR restore is not a path where a second of wall clock is worth an interleaving hazard.
      await runVerify();
      const licStart = Date.now();
      await timedStep(t('timing.step.activating'), 'timing.step.licenseActivated', () =>
        ensureRepoLicenseForRestore(options, machine, sshPrivateKey, remoteRenetPath, sftp)
      );
      cliSteps.push({ name: 'license', duration_ms: Date.now() - licStart, startedAtMs: licStart });
    } else {
      await runVerify();
    }

    await maybeRefreshRepoLicenses(
      machine,
      options.machineName,
      sshPrivateKey,
      remoteRenetPath,
      sftp
    );

    return { remoteRenetPath, renetUploaded };
  }

  /**
   * Execute a function on a machine via direct SSH.
   * SSHes to the machine and runs `renet execute --executor local` with vault via stdin.
   */
  private async loadConfigAndBuildVault(
    options: ExecuteOptions,
    startTime: number,
    cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[]
  ) {
    const config = await configService.getLocalConfig();
    const machine = await configService.getLocalMachine(options.machineName);

    if (options.debug) {
      outputService.info(`Executing '${options.functionName}' on ${options.machineName}`);
    }

    const sshPrivateKey = config.sshPrivateKey ?? (await readSSHKey(config.ssh.privateKeyPath));
    const sshPublicKey =
      config.sshPublicKey ?? (await readOptionalSSHKey(config.ssh.publicKeyPath));
    const sshKnownHosts = await resolveKnownHosts(machine.knownHosts);
    const storages = await loadContextStorages();
    const { credentials: repositoryCredentials, configs: repositoryConfigs } =
      await loadContextRepositories();

    // Peer machines (backup push/pull targets) are resolved HERE, from params, against the executor's own config. Callers may still pass them explicitly (tests do), but no command should: a proxy client holds no config and so cannot resolve a peer's IP. Deriving executor-side keeps one code path.
    const params = options.params ?? {};
    const extraMachines = options.extraMachines ?? (await resolveExtraMachines(params));

    const vault = buildLocalVault({
      functionName: options.functionName,
      machineName: options.machineName,
      // #74: a caller that KNOWS the repo's placement declares its datastore here, and it must land in the MACHINE VAULT, that is the only datastore renet ever reads (`p.Datastore()` -> `machineDatastore`, set by WithMachineVault). A `datastore` PARAM would not do it: `repository_create` resolves the datastore through AddDatastore, which reads the vault, not the params bag. The
      // fallback below is untouched and still correct: a machine with no named datastore keeps its own default. This only lets a caller stop staying silent.
      machine: options.datastore ? { ...machine, datastore: options.datastore } : machine,
      sshPrivateKey,
      sshPublicKey,
      sshKnownHosts,
      params,
      extraMachines,
      storages,
      repositoryCredentials,
      repositoryConfigs,
    });
    cliSteps.push({ name: 'config', duration_ms: Date.now() - startTime, startedAtMs: startTime });
    return { config, machine, sshPrivateKey, vault };
  }

  private async executeSession(
    sftp: SFTPClient,
    config: Awaited<ReturnType<typeof configService.getLocalConfig>>,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    vault: ReturnType<typeof buildLocalVault>,
    options: ExecuteOptions,
    cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[],
    quiet: boolean,
    startTime: number
  ): Promise<ExecuteResult> {
    const { remoteRenetPath } = await this.provisionAndVerify(
      config,
      machine,
      sshPrivateKey,
      options,
      sftp,
      cliSteps,
      quiet
    );

    const result = await this.executeWithConnectedSftp(
      sftp,
      options,
      remoteRenetPath,
      vault,
      machine,
      sshPrivateKey,
      startTime
    );
    result.cliSteps = [...cliSteps];
    result.allSteps = [...cliSteps, ...(result.steps ?? [])];

    if (result.success) {
      outputService.setOperationDuration(result.operationDurationMs ?? result.durationMs);
    }
    return result;
  }

  private recordAudit(
    options: ExecuteOptions,
    result: Pick<ExecuteResult, 'success' | 'exitCode' | 'durationMs' | 'error'>
  ) {
    auditService.recordOperation({
      functionName: options.functionName,
      machineName: options.machineName,
      repoName:
        typeof options.params?.repository === 'string' ? options.params.repository : undefined,
      success: result.success,
      exitCode: result.exitCode,
      durationMs: result.durationMs,
      error: result.success ? undefined : result.error,
    });
  }

  async execute(options: ExecuteOptions): Promise<ExecuteResult> {
    // BUG #46 (ruling: the executor injects KUBECONFIG WITHOUT rerouting the machine). `kubeCluster` used to ALSO overwrite `machineName` with the cluster's control node here. That was defensible while kubeCluster could only come from an explicit `--cluster` flag ("run this against the cluster"), but the reshape DERIVES it from placement, so the override silently sent every verb
    // on a k8s-placed repo to the control node - including volume-level operations (trim, diff, commit, merge, and repo up's LUKS mount) that MUST run on the machine which actually mounts the datastore (state.datastores[D].attachedTo).
    //
    // KUBECONFIG is the k8s analog of DOCKER_HOST, and DOCKER_HOST never reroutes the machine either: it is still injected from options.kubeCluster in runRemoteExecution. The caller's derived machineName now stands, and a verb that genuinely must run FROM the control node resolves that machine
    // explicitly at its call site (resolveExecutionTarget({ cluster })) rather
    // than relying on an ambient rewrite.
    const startTime = Date.now();
    const configSpinner = options.quietSpinners ? null : startSpinner(t('timing.step.loading'));
    const cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[] = [];

    try {
      const { config, machine, sshPrivateKey, vault } = await this.loadConfigAndBuildVault(
        options,
        startTime,
        cliSteps
      );
      const configText = t('timing.step.configLoaded', {
        duration: formatDuration(cliSteps[0].duration_ms),
      });
      if (configSpinner) stopSpinner(true, configText);
      else if (!options.quietSpinners) outputService.info(configText);

      const quiet = options.quietSpinners ?? false;
      const sshStart = Date.now();
      const acquireFn = () => machineConnections.acquireFor(machine, sshPrivateKey);
      const lease = quiet
        ? await acquireFn()
        : await timedStep(t('timing.step.connecting'), 'timing.step.connected', acquireFn);
      cliSteps.push({
        name: 'ssh_connect',
        duration_ms: Date.now() - sshStart,
        startedAtMs: sshStart,
      });

      try {
        const result = await this.executeSession(
          lease.sftp,
          config,
          machine,
          sshPrivateKey,
          vault,
          options,
          cliSteps,
          quiet,
          startTime
        );
        this.recordAudit(options, result);
        return result;
      } finally {
        lease.release();
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      const durationMs = Date.now() - startTime;
      this.recordAudit(options, { success: false, exitCode: 1, durationMs, error: errorMessage });
      // A CliExitError is a deliberate REFUSAL carrying its own exit code, its retryable flag and its next-actions. Flattening it into a generic
      // {exitCode: 1} result throws all of that away: a BUSY provisioning-lock
      // timeout (exit 15, retryable, "here is the pid holding it") arrived at the user as an anonymous exit 1. Let it through untouched.
      if (error instanceof CliExitError) throw error;
      return { success: false, exitCode: 1, error: errorMessage, durationMs };
    }
  }
}

export const localExecutorService = new LocalExecutorService();
