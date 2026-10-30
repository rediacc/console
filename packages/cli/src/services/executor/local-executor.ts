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
import { SshConnectError } from '../../remote/sftp/connect-error.js';
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
import {
  CONVERGE_FUNCTION,
  parseConvergeReport,
  routerRefreshAfterPass,
} from '../renet/runtime-converge.js';
import { fetchOtlpCredentials } from '../telemetry/otlp-credentials.js';
import { isTelemetryDisabled } from '../telemetry/telemetry.js';
import { runJobExecution, runsOutsideJob } from './detached-execution.js';
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
import {
  buildRemoteRenetCommand,
  detectEnvironment,
  resolveEnvSecrets,
  resolveRenetTimeoutMs,
} from './renet-command.js';
import { renetAccessFor } from './renet-function-access.js';
import type { RenetLaunch } from './renet-launch.js';
import {
  createStdoutHandler,
  echoRenetFailure,
  extractStepsFromOutput,
  surfaceRenetWarnings,
} from './renet-output.js';
import { settleRenetRun } from './renet-settle.js';
import { prepareSessionVault, sessionConvergeDeps } from './session-converge.js';
import type { ExecuteOptions, ExecuteResult } from './types.js';
import { loadContextRepositories, resolveKnownHosts } from './vault-inputs.js';

// The pieces split out of this module stay importable from it, so no caller had to move.
export { needsLicenseRecovery } from './license-recovery.js';
export { buildRemoteRenetCommand, buildRenetEnv } from './renet-command.js';
export { parseCapturedJson } from './renet-output.js';
export { mergeEventsStderr, settleRenetRun } from './renet-settle.js';
// ExecuteResult only. The other seam types are consumed from executor-factory, which is the entry point to this layer; re-exporting them here as well just gave callers two doors to the same room.
export type { ExecuteResult } from './types.js';

/** What `buildLocalVault` reads besides the function and its params, kept to build a second vault (the converge pass) in the same session. */
type VaultInputs = Omit<Parameters<typeof buildLocalVault>[0], 'functionName' | 'params'>;

/** The network_id value that asks `job start` to allocate the ID (private/renet/pkg/functions/network_auto.go). */
const NETWORK_ID_AUTO = 'auto';

function isPositiveId(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0;
}

/**
 * Write the call's start directives into a built vault (agent/plans/PLAN-detached-jobs.md
 * section 14), on the job path only: `renet execute` evaluates neither, and refuses an
 * unresolved "auto".
 *
 *   - `expect` lands at the vault root, where `job start` checks it before any unit exists.
 *   - `network_id: "auto"` (asked by `networkIdAuto`, or by a caller's `params.network_id`)
 *     lands on the task repository's entry when that entry has no ID, with every ID the
 *     caller's config holds as `network_id_exclude`: the machine cannot see the IDs this
 *     config placed on other machines. An entry that already has an ID keeps it, and a
 *     params "auto" beside it is replaced by that ID, which renet would otherwise refuse.
 */
export function applyVaultDirectives(
  vault: string,
  options: Pick<ExecuteOptions, 'functionName' | 'params' | 'expect' | 'networkIdAuto'>,
  repositoryConfigs: Record<string, { networkId?: number }> | undefined
): string {
  const paramsAuto = options.params?.network_id === NETWORK_ID_AUTO;
  if (runsOutsideJob(options) || (!options.expect && !options.networkIdAuto && !paramsAuto)) {
    return vault;
  }
  const parsed = JSON.parse(vault) as {
    expect?: string;
    task?: { repository?: string };
    params?: Record<string, unknown>;
    repositories?: Record<string, Record<string, unknown>>;
  };
  if (options.expect) parsed.expect = options.expect;
  if (options.networkIdAuto || paramsAuto) {
    const entry = parsed.repositories?.[parsed.task?.repository ?? ''];
    if (entry && isPositiveId(entry.network_id)) {
      if (paramsAuto && parsed.params) parsed.params.network_id = entry.network_id;
    } else if (entry) {
      entry.network_id = NETWORK_ID_AUTO;
      entry.network_id_exclude = [
        ...new Set(
          Object.values(repositoryConfigs ?? {})
            .map((config) => config.networkId)
            .filter(isPositiveId)
        ),
      ].sort((a, b) => a - b);
    }
  }
  return JSON.stringify(parsed);
}

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
        // Recovery issued a license. Re-run: exit 10 means renet refused BEFORE doing any work, so a second run cannot double-execute. The re-run is a NEW job, so it carries a new request id: the first one would dedupe onto the job that refused.
        result = await this.runOperation(
          sftp,
          options.requestId ? { ...options, requestId: `${options.requestId}:r` } : options,
          remoteRenetPath,
          vault,
          machine,
          sshPrivateKey
        );
      } else {
        return recovered;
      }
    }

    // A job still running past its window may already have created repos, but the identity refresh needs the finished repo on disk. The `identityRefresh` plan step (packages/cli/src/services/jobs/plans.ts) is meant to run it when the job is seen to finish; the step runner is not wired to repo verbs until PLAN-detached-jobs J16, so until then a backgrounded create refreshes no identity.
    if (result.success && result.state !== 'running' && !options.deferIdentityRefresh) {
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
   * Run the operation once, as a machine job (agent/plans/PLAN-detached-jobs.md
   * section 14). Only the section 24 exemptions (`runsOutsideJob`: an
   * interactive TTY exec, a log follow) stay on `renet execute`. There is no
   * synchronous fallback: a renet too old for jobs refuses with the upgrade
   * command (Design 11). Both paths flow back through the shared recovery,
   * identity-refresh, and duration tail in executeWithConnectedSftp (finding #33).
   */
  private runOperation(
    sftp: SFTPClient,
    options: ExecuteOptions,
    remoteRenetPath: string,
    vault: string,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string
  ): Promise<ExecuteResult> {
    if (runsOutsideJob(options)) {
      return this.runRemoteExecution(sftp, remoteRenetPath, vault, options);
    }
    return runJobExecution(remoteRenetPath, vault, options, machine, sshPrivateKey);
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
    kubeconfig?: string,
    timeoutMs?: number
  ): RenetLaunch {
    return buildRemoteRenetCommand({
      remoteRenetPath,
      eventsMode,
      timeoutMs,
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
    const { command, stdinPrefix } = this.buildRemoteCommand(
      remoteRenetPath,
      options.eventsMode,
      otlpCreds,
      envSecrets,
      kubeconfig,
      resolveRenetTimeoutMs(options.functionName, options.timeout)
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
      stdin: stdinPrefix + vault,
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

    const settled = settleRenetRun({
      exitCode,
      stdout,
      stderr,
      collector,
      machineName: options.machineName,
    });
    stdout = settled.stdout;
    stderr = settled.stderr;
    const combined = settled.combined;
    const renetDurationMatch = /operation completed.*?duration_ms=(\d+)/.exec(combined);
    const operationMs = renetDurationMatch
      ? Number.parseInt(renetDurationMatch[1], 10)
      : Date.now() - execStart;

    surfaceRenetWarnings(exitCode, combined, options);

    return {
      success: exitCode === 0,
      exitCode,
      error: settled.error,
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
  ): Promise<{ remoteRenetPath: string; renetUploaded: boolean; routerRefreshDue: boolean }> {
    const provStart = Date.now();
    // The dispatched function decides whether this run may replace the machine's renet (RENET_FUNCTION_ACCESS).
    const access = renetAccessFor(options.functionName, options.params);
    const provisionFn = () =>
      acquireRemoteRenet(
        access,
        config,
        machine,
        sshPrivateKey,
        {
          debug: options.debug,
          skipRouterRestart: options.skipRouterRestart,
          // The router refresh waits for the runtime converge pass (executeSession).
          deferRouterRefresh: true,
          machineName: options.machineName,
        },
        sftp
      );
    const {
      remotePath: remoteRenetPath,
      uploaded: renetUploaded,
      routerRefreshDue,
    } = quiet
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
      // first, then license: a DR restore or chunk-store browse (backup_restore, backup_browse_at) is not a path where a second of wall clock is worth an interleaving hazard.
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

    return { remoteRenetPath, renetUploaded, routerRefreshDue: routerRefreshDue === true };
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
    const { credentials: repositoryCredentials, configs: repositoryConfigs } =
      await loadContextRepositories();

    // Peer machines (backup push/pull targets) are resolved HERE, from params, against the executor's own config. Callers may still pass them explicitly (tests do), but no command should: a proxy client holds no config and so cannot resolve a peer's IP. Deriving executor-side keeps one code path.
    const params = options.params ?? {};
    const extraMachines = options.extraMachines ?? (await resolveExtraMachines(params));

    const vaultInputs: VaultInputs = {
      machineName: options.machineName,
      // #74: a caller that KNOWS the repo's placement declares its datastore here, and it must land in the MACHINE VAULT, that is the only datastore renet ever reads (`p.Datastore()` -> `machineDatastore`, set by WithMachineVault). A `datastore` PARAM would not do it: `repository_create` resolves the datastore through AddDatastore, which reads the vault, not the params bag. The
      // fallback below is untouched and still correct: a machine with no named datastore keeps its own default. This only lets a caller stop staying silent.
      machine: options.datastore ? { ...machine, datastore: options.datastore } : machine,
      sshPrivateKey,
      sshPublicKey,
      sshKnownHosts,
      extraMachines,
      repositoryCredentials,
      repositoryConfigs,
    };
    const vault = applyVaultDirectives(
      buildLocalVault({ ...vaultInputs, functionName: options.functionName, params }),
      options,
      repositoryConfigs
    );
    cliSteps.push({ name: 'config', duration_ms: Date.now() - startTime, startedAtMs: startTime });
    return { config, machine, sshPrivateKey, vault, vaultInputs };
  }

  private async executeSession(
    sftp: SFTPClient,
    config: Awaited<ReturnType<typeof configService.getLocalConfig>>,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    built: { vault: string; vaultInputs: VaultInputs },
    options: ExecuteOptions,
    cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[],
    quiet: boolean,
    startTime: number
  ): Promise<ExecuteResult> {
    const { remoteRenetPath, renetUploaded, routerRefreshDue } = await this.provisionAndVerify(
      config,
      machine,
      sshPrivateKey,
      options,
      sftp,
      cliSteps,
      quiet
    );

    const deps = sessionConvergeDeps({
      sftp,
      remoteRenetPath,
      machine,
      options,
      buildVault: (params) =>
        buildLocalVault({ ...built.vaultInputs, functionName: CONVERGE_FUNCTION, params }),
      runRemote: (vault, runOptions) =>
        this.runRemoteExecution(sftp, remoteRenetPath, vault, runOptions),
    });
    const isConverge = options.functionName === CONVERGE_FUNCTION;
    const vault = await prepareSessionVault(sftp, deps, options, built.vault, {
      renetUploaded,
      routerRefreshDue,
    });

    const result = await this.executeWithConnectedSftp(
      sftp,
      options,
      remoteRenetPath,
      vault,
      machine,
      sshPrivateKey,
      startTime
    );
    if (isConverge) {
      const refresh = routerRefreshAfterPass({
        due: routerRefreshDue,
        dryRun: options.params?.dry_run === true,
        summary: parseConvergeReport(result.stdout)?.summary ?? null,
        skipRouterRestart: options.skipRouterRestart,
      });
      if (refresh) await deps.refreshRouter();
    }
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
      const { config, machine, sshPrivateKey, vault, vaultInputs } =
        await this.loadConfigAndBuildVault(options, startTime, cliSteps);
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
          { vault, vaultInputs },
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
      this.recordAudit(options, {
        success: false,
        exitCode: error instanceof SshConnectError ? error.exitCode : 1,
        durationMs,
        error: errorMessage,
      });
      // A CliExitError is a deliberate REFUSAL carrying its own exit code, its retryable flag and its next-actions. Flattening it into a generic
      // {exitCode: 1} result throws all of that away: a BUSY provisioning-lock
      // timeout (exit 15, retryable, "here is the pid holding it") arrived at the user as an anonymous exit 1. Let it through untouched.
      if (error instanceof CliExitError) throw error;
      // A named connect failure keeps its code, exit code and guidance, so the console can tell an unreachable machine from a crash. An unanswered connect (EGRESS_UNREACHABLE) also carries its address, which `rdc serve` names in the egress report for the proxy to probe.
      if (error instanceof SshConnectError) {
        const connectTarget = { host: error.host, port: error.port };
        return {
          success: false,
          exitCode: error.exitCode,
          error: errorMessage,
          ...(error.errorCode ? { errorCode: error.errorCode } : {}),
          ...(error.guidance ? { errorGuidance: error.guidance } : {}),
          ...(error.kind === 'unreachable' ? { connectTarget } : {}),
          durationMs,
        };
      }
      return { success: false, exitCode: 1, error: errorMessage, durationMs };
    }
  }
}

export const localExecutorService = new LocalExecutorService();
