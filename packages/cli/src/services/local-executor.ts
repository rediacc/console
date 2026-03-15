/* eslint-disable max-lines */
/**
 * LocalExecutorService - Direct task execution without middleware.
 *
 * This service enables Console CLI to work directly with renet bridge
 * without going through middleware API. Used in "local mode" and "s3 mode" contexts.
 *
 * Uses direct SSH to the target machine and runs `renet execute --executor local`
 * which builds and executes the command locally on the machine (no double SSH).
 *
 * Delegates to shared utilities in renet-execution.ts.
 */

import { spawn } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { configService } from './config-resources.js';
import {
  refreshMachineActivation,
  refreshRepoLicenseIdentity,
  refreshRepoLicensesBatch,
} from './license.js';
import { outputService } from './output.js';
import {
  buildLocalVault,
  getLocalRenetPath,
  provisionRenetToRemote,
  readOptionalSSHKey,
  readSSHKey,
  verifyMachineSetup,
} from './renet-execution.js';
import {
  isLicensedRenetFunction,
  parseRenetLicenseFailure,
  RENET_LICENSE_REQUIRED_EXIT_CODE,
  type RenetLicenseFailure,
} from './renet-license-contract.js';
import { getSubscriptionTokenState } from './subscription-auth.js';
import { authorizeSubscriptionViaDeviceCode } from './subscription-device-auth.js';

/** Options for local execution */
interface LocalExecuteOptions {
  /** Function name to execute */
  functionName: string;
  /** Target machine name (must exist in local context) */
  machineName: string;
  /** Parameters to pass to the function */
  params?: Record<string, unknown>;
  /** Extra machines for multi-machine operations (e.g. backup) */
  extraMachines?: Record<string, { ip: string; port?: number; user: string }>;
  /** Timeout in milliseconds (default: 10 minutes) */
  timeout?: number;
  /** Enable debug output */
  debug?: boolean;
  /** Output as JSON */
  json?: boolean;
  /** Skip restarting the rediacc-router service after binary update */
  skipRouterRestart?: boolean;
  /** Capture stdout/stderr instead of streaming them directly */
  captureOutput?: boolean;
}

/** Result of local execution */
export interface LocalExecuteResult {
  /** Whether execution succeeded */
  success: boolean;
  /** Exit code from renet */
  exitCode: number;
  /** Error message if failed */
  error?: string;
  /** Stable machine-readable error code, when available */
  errorCode?: string;
  /** Actionable guidance for operators or automation */
  errorGuidance?: string;
  /** Structured repo-license reason from renet, when available */
  licenseFailureReason?: string;
  /** Execution duration in milliseconds */
  durationMs: number;
  /** Captured stdout, when requested */
  stdout?: string;
  /** Captured stderr, when requested */
  stderr?: string;
}

interface RepoLicenseContext {
  repositoryGuid: string;
  grandGuid?: string;
  kind: 'grand' | 'fork';
  requestedSizeGb: number;
  luksUuid?: string;
  storageFingerprint?: string;
}

async function resolveKnownHosts(machineKnownHosts: string | undefined): Promise<string> {
  const hosts = machineKnownHosts ?? '';
  if (hosts) return hosts;
  const knownHostsPath = path.join(os.homedir(), '.ssh', 'known_hosts');
  return fs.readFile(knownHostsPath, 'utf-8').catch(() => '');
}

async function loadContextStorages(): Promise<
  Record<string, { vaultContent: Record<string, unknown> }> | undefined
> {
  try {
    const storageList = await configService.listStorages();
    if (storageList.length === 0) return undefined;
    const storages: Record<string, { vaultContent: Record<string, unknown> }> = {};
    for (const s of storageList) {
      storages[s.name] = { vaultContent: s.config.vaultContent };
    }
    return storages;
  } catch {
    return undefined;
  }
}

async function loadContextRepositories(): Promise<{
  credentials: Record<string, string> | undefined;
  configs: Record<string, { guid: string; name: string; networkId?: number }> | undefined;
}> {
  try {
    const repoList = await configService.listRepositories();
    if (repoList.length === 0) return { credentials: undefined, configs: undefined };
    const credentials: Record<string, string> = {};
    const configs: Record<string, { guid: string; name: string; networkId?: number }> = {};
    for (const r of repoList) {
      if (r.config.credential) {
        credentials[r.config.repositoryGuid] = r.config.credential;
      }
      configs[r.name] = {
        guid: r.config.repositoryGuid,
        name: r.name,
        networkId: r.config.networkId,
      };
    }
    return { credentials, configs };
  } catch {
    return { credentials: undefined, configs: undefined };
  }
}

function parseSizeToGb(size: string): number {
  const trimmed = size.trim().toUpperCase();
  const match = /^(\d+(?:\.\d+)?)([MGT])$/.exec(trimmed);
  if (!match) throw new Error(`Unsupported repository size: ${size}`);
  const value = Number(match[1]);
  const unit = match[2];
  if (unit === 'T') return Math.ceil(value * 1024);
  if (unit === 'G') return Math.ceil(value);
  return Math.max(1, Math.ceil(value / 1024));
}

async function resolveRepoLicenseContext(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  sftp: SFTPClient
): Promise<RepoLicenseContext | null> {
  const resolved = await resolveRepoLicenseInputs(functionName, machineName, params);
  if (!resolved) return null;
  const { repo, machine } = resolved;

  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const requestedSizeGb = await resolveRequestedSizeGb(
    functionName,
    params,
    repo?.repositoryGuid,
    datastore,
    sftp
  );
  if (requestedSizeGb === null) return null;
  const targetGuid = resolveTargetGuid(functionName, params, repo?.repositoryGuid);
  const identity = await resolveRepoIdentity(functionName, targetGuid, datastore, sftp);

  return buildRepoLicenseContext(functionName, params, repo, requestedSizeGb, identity);
}

async function resolveRepoLicenseInputs(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>
): Promise<{
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>;
  repo: Awaited<ReturnType<typeof configService.getRepository>> | null;
} | null> {
  if (!functionName.startsWith('repository_')) return null;
  const repoName = typeof params.repository === 'string' ? params.repository : '';
  if (!repoName && functionName !== 'repository_fork') return null;
  const [repo, machine] = await Promise.all([
    configService.getRepository(repoName),
    configService.getLocalMachine(machineName),
  ]);
  if (!repo && functionName !== 'repository_fork') return null;
  return { repo, machine };
}

function buildRepoLicenseContext(
  functionName: string,
  params: Record<string, unknown>,
  repo: Awaited<ReturnType<typeof configService.getRepository>> | null,
  requestedSizeGb: number,
  identity: Pick<RepoLicenseContext, 'luksUuid' | 'storageFingerprint'>
): RepoLicenseContext | null {
  if (functionName === 'repository_fork') {
    const forkGuid = typeof params.tag === 'string' ? params.tag : '';
    if (!repo || !forkGuid) return null;
    return {
      repositoryGuid: forkGuid,
      grandGuid: repo.grandGuid ?? repo.repositoryGuid,
      kind: 'fork',
      requestedSizeGb,
      ...identity,
    };
  }
  if (!repo) return null;
  return {
    repositoryGuid: repo.repositoryGuid,
    grandGuid: repo.grandGuid,
    kind: repo.grandGuid && repo.grandGuid !== repo.repositoryGuid ? 'fork' : 'grand',
    requestedSizeGb,
    ...identity,
  };
}

async function resolveRequestedSizeGb(
  functionName: string,
  params: Record<string, unknown>,
  repositoryGuid: string | undefined,
  datastore: string,
  sftp: SFTPClient
): Promise<number | null> {
  if (typeof params.size === 'string' && params.size.trim()) {
    return parseSizeToGb(params.size);
  }
  const statGuid = functionName === 'repository_fork' ? repositoryGuid : repositoryGuid;
  if (!statGuid) return null;
  const bytesOutput = await sftp.exec(
    `stat -c %s '${datastore}/repositories/${statGuid}' 2>/dev/null || echo 0`
  );
  const bytes = Number.parseInt(bytesOutput.trim(), 10);
  return Math.max(1, Math.ceil(bytes / (1024 * 1024 * 1024)));
}

function resolveTargetGuid(
  functionName: string,
  params: Record<string, unknown>,
  repositoryGuid: string | undefined
): string {
  if (functionName === 'repository_fork') {
    return typeof params.tag === 'string' ? params.tag : '';
  }
  return repositoryGuid ?? '';
}

async function resolveRepoIdentity(
  functionName: string,
  targetGuid: string,
  datastore: string,
  sftp: SFTPClient
): Promise<Pick<RepoLicenseContext, 'luksUuid' | 'storageFingerprint'>> {
  if (!targetGuid || functionName === 'repository_create' || functionName === 'repository_fork') {
    return {};
  }
  const identityOutput = await sftp.exec(
    `sudo sh -lc 'p="${datastore}/repositories/${targetGuid}"; if cryptsetup luksUUID "$p" >/dev/null 2>&1; then cryptsetup luksUUID "$p"; else stat -c "%F:%d:%i:%s:%Y" "$p" 2>/dev/null || true; fi'`
  );
  const trimmed = identityOutput.trim();
  if (!trimmed) {
    return {};
  }
  return /^[0-9a-f-]{36}$/i.test(trimmed) ? { luksUuid: trimmed } : { storageFingerprint: trimmed };
}

/**
 * Service for executing tasks directly via renet subprocess.
 * Bypasses middleware for single-machine local deployments.
 *
 * Uses direct SSH to the target machine and runs `renet execute --executor local`
 * with vault JSON piped via stdin. This avoids double-SSH (CLI→renet→machine).
 */
class LocalExecutorService {
  private async resolveLicenseFailure(
    result: LocalExecuteResult,
    failure: RenetLicenseFailure,
    options: LocalExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp: SFTPClient,
    startTime: number
  ): Promise<LocalExecuteResult | null> {
    const guidance = this.resolveLicenseRecoveryGuidance(failure, options.machineName);
    if (guidance.failFastMessage) {
      return this.buildRecoveryFailureResult(
        result,
        guidance,
        guidance.failFastMessage,
        failure.reason,
        startTime
      );
    }
    try {
      await this.maybeOnboardSubscription(failure.reason);
    } catch (error) {
      return this.buildRecoveryFailureResult(
        result,
        guidance,
        error instanceof Error ? error.message : String(error),
        failure.reason,
        startTime
      );
    }
    const issued = await this.maybeIssueLicense(
      options,
      machine,
      sshPrivateKey,
      remoteRenetPath,
      sftp
    );
    if (issued) {
      return null;
    }
    if (!guidance.recoveryFailedMessage) {
      return result;
    }
    return this.buildRecoveryFailureResult(
      result,
      guidance,
      guidance.recoveryFailedMessage,
      failure.reason,
      startTime
    );
  }

  private buildRecoveryFailureResult(
    result: LocalExecuteResult,
    guidance: ReturnType<LocalExecutorService['resolveLicenseRecoveryGuidance']>,
    error: string,
    failureReason: string,
    startTime: number
  ): LocalExecuteResult {
    return {
      ...result,
      errorCode: guidance.errorCode,
      error,
      errorGuidance: guidance.guidance,
      licenseFailureReason: failureReason,
      durationMs: Date.now() - startTime,
    };
  }

  private async executeWithConnectedSftp(
    sftp: SFTPClient,
    options: LocalExecuteOptions,
    remoteRenetPath: string,
    vault: string,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    startTime: number
  ): Promise<LocalExecuteResult> {
    try {
      let result = await this.runRemoteExecution(sftp, remoteRenetPath, vault, options);
      let failure: RenetLicenseFailure | null = null;
      if (!result.success && result.exitCode === RENET_LICENSE_REQUIRED_EXIT_CODE) {
        failure = parseRenetLicenseFailure(result.stderr, result.stdout);
      }
      if (failure) {
        const recovered = await this.resolveLicenseFailure(
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
          result = await this.runRemoteExecution(sftp, remoteRenetPath, vault, options);
        } else {
          return recovered;
        }
      }

      if (result.success) {
        await this.maybeRefreshRepoIdentity(options, machine, sshPrivateKey, remoteRenetPath, sftp);
      }

      return {
        ...result,
        durationMs: Date.now() - startTime,
      };
    } finally {
      sftp.close();
    }
  }

  private async maybeIssueLicense(
    options: LocalExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    _sftp: SFTPClient
  ): Promise<boolean> {
    if (!isLicensedRenetFunction(options.functionName)) {
      return false;
    }
    // Unified path: machine activation + batch refresh for all licensed functions
    const machineIssued = await refreshMachineActivation(
      machine,
      sshPrivateKey,
      remoteRenetPath
    ).catch(() => false);
    const batchResult = await refreshRepoLicensesBatch(
      machine,
      sshPrivateKey,
      remoteRenetPath
    ).catch(() => null);
    return machineIssued || Boolean(batchResult && batchResult.valid > 0);
  }

  private async maybeOnboardSubscription(reason: string): Promise<boolean> {
    if (reason !== 'missing') {
      return false;
    }
    const tokenState = getSubscriptionTokenState();
    if (tokenState.kind === 'ready') {
      return false;
    }
    await authorizeSubscriptionViaDeviceCode(undefined, {
      interactive: process.stdin.isTTY && process.stdout.isTTY,
      announceIntro: true,
    });
    return true;
  }

  /**
   * Pre-flight for repository_create / repository_fork:
   * Ensure subscription token exists (trigger device-code auth if needed)
   * and call refreshMachineActivation (which writes the blob to disk).
   */
  private async ensureMachineActivationForProvisioning(
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string
  ): Promise<void> {
    const tokenState = getSubscriptionTokenState();
    if (tokenState.kind !== 'ready') {
      await authorizeSubscriptionViaDeviceCode(undefined, {
        interactive: process.stdin.isTTY && process.stdout.isTTY,
        announceIntro: true,
      });
    }
    const activated = await refreshMachineActivation(machine, sshPrivateKey, remoteRenetPath);
    if (!activated) {
      throw new Error(
        'Machine activation failed. Ensure your subscription is active and the machine slot is available.'
      );
    }
  }

  private resolveLicenseRecoveryGuidance(
    failure: RenetLicenseFailure,
    machineName: string
  ): {
    errorCode?: string;
    guidance?: string;
    failFastMessage?: string;
    recoveryFailedMessage?: string;
  } {
    switch (failure.reason) {
      case 'missing':
        return {
          errorCode: 'REPO_LICENSE_ISSUANCE_REQUIRED',
          guidance: `Issue repo licenses explicitly with: rdc subscription refresh-repos -m ${machineName}`,
          recoveryFailedMessage:
            `A repo license is required for this operation, and automatic issuance did not succeed. ` +
            `Run: rdc subscription refresh-repos -m ${machineName}`,
        };
      case 'expired':
        return {
          errorCode: 'REPO_LICENSE_REFRESH_REQUIRED',
          guidance: `Refresh repo licenses explicitly with: rdc subscription refresh-repos -m ${machineName}`,
          recoveryFailedMessage:
            `The installed repo license must be refreshed before this operation can continue. ` +
            `Run: rdc subscription refresh-repos -m ${machineName}`,
        };
      case 'machine_mismatch':
        return {
          errorCode: 'REPO_LICENSE_MACHINE_MISMATCH',
          guidance: `Reissue repo licenses from this machine context with: rdc subscription refresh-repos -m ${machineName}`,
          failFastMessage:
            `The installed repo license belongs to a different machine. ` +
            `Reissue it from this machine context with: rdc subscription refresh-repos -m ${machineName}`,
        };
      case 'repository_mismatch':
        return {
          errorCode: 'REPO_LICENSE_REPOSITORY_MISMATCH',
          guidance: `Refresh repo licenses explicitly with: rdc subscription refresh-repos -m ${machineName}`,
          failFastMessage:
            `The installed repo license does not match the target repository. ` +
            `Refresh repo licenses explicitly with: rdc subscription refresh-repos -m ${machineName}`,
        };
      case 'sequence_regression':
        return {
          errorCode: 'REPO_LICENSE_INTEGRITY_ERROR',
          guidance: `Replace the installed repo license with: rdc subscription refresh-repos -m ${machineName}`,
          failFastMessage:
            `The installed repo license is older than the latest accepted sequence. ` +
            `Replace it with a newer repo license using: rdc subscription refresh-repos -m ${machineName}`,
        };
      case 'invalid_signature':
        return {
          errorCode: 'REPO_LICENSE_INTEGRITY_ERROR',
          guidance: `Replace the installed repo license with: rdc subscription refresh-repos -m ${machineName}`,
          failFastMessage:
            `The installed repo license could not be trusted. ` +
            `Replace it with a newly issued repo license using: rdc subscription refresh-repos -m ${machineName}`,
        };
      case 'identity_mismatch':
        return {
          errorCode: 'REPO_LICENSE_IDENTITY_MISMATCH',
          guidance: `Reissue repo licenses with: rdc subscription refresh-repos -m ${machineName}`,
          failFastMessage:
            `The repository identity does not match the installed repo license. ` +
            `Reissue repo licenses with: rdc subscription refresh-repos -m ${machineName}`,
        };
      default:
        return {};
    }
  }

  private async maybeRefreshRepoIdentity(
    options: LocalExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp: SFTPClient
  ): Promise<void> {
    if (
      options.functionName !== 'repository_create' &&
      options.functionName !== 'repository_fork'
    ) {
      return;
    }
    const repoLicense = await resolveRepoLicenseContext(
      options.functionName,
      options.machineName,
      options.params ?? {},
      sftp
    );
    if (repoLicense) {
      await refreshRepoLicenseIdentity(machine, sshPrivateKey, repoLicense, remoteRenetPath);
    }
  }

  private async runRemoteExecution(
    sftp: SFTPClient,
    remoteRenetPath: string,
    vault: string,
    options: LocalExecuteOptions
  ): Promise<LocalExecuteResult> {
    const command =
      this.detectEnvironment() === 'development'
        ? `sudo env REDIACC_ENVIRONMENT=development ${remoteRenetPath} execute --executor local`
        : `sudo ${remoteRenetPath} execute --executor local`;
    let stdout = '';
    let stderr = '';
    const exitCode = await sftp.execStreaming(command, {
      stdin: vault,
      onStdout: (data) => {
        stdout += data;
        if (!options.captureOutput) {
          process.stdout.write(data);
        }
      },
      onStderr: (data) => {
        stderr += data;
        if (!options.captureOutput) {
          process.stderr.write(data);
        }
      },
    });

    return {
      success: exitCode === 0,
      exitCode,
      error: exitCode === 0 ? undefined : `renet exited with code ${exitCode}`,
      durationMs: 0,
      stdout,
      stderr,
    };
  }

  /**
   * Execute a function on a machine via direct SSH.
   * SSHes to the machine and runs `renet execute --executor local` with vault via stdin.
   */
  async execute(options: LocalExecuteOptions): Promise<LocalExecuteResult> {
    const startTime = Date.now();

    try {
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

      const vault = buildLocalVault({
        functionName: options.functionName,
        machineName: options.machineName,
        machine,
        sshPrivateKey,
        sshPublicKey,
        sshKnownHosts,
        params: options.params ?? {},
        extraMachines: options.extraMachines,
        storages,
        repositoryCredentials,
        repositoryConfigs,
      });

      const remoteRenetPath = await provisionRenetToRemote(config, machine, sshPrivateKey, options);
      await verifyMachineSetup(machine, sshPrivateKey, {
        ...options,
        functionName: options.functionName,
      });

      // Pre-flight for create/fork: ensure machine activation (writes machine license to disk)
      if (
        options.functionName === 'repository_create' ||
        options.functionName === 'repository_fork'
      ) {
        await this.ensureMachineActivationForProvisioning(machine, sshPrivateKey, remoteRenetPath);
      }

      if (options.debug) {
        outputService.info(`Direct SSH to ${machine.ip}, executor=local`);
      }

      const sftp = new SFTPClient({
        host: machine.ip,
        port: machine.port ?? DEFAULTS.SSH.PORT,
        username: machine.user,
        privateKey: sshPrivateKey,
      });
      await sftp.connect();

      return await this.executeWithConnectedSftp(
        sftp,
        options,
        remoteRenetPath,
        vault,
        machine,
        sshPrivateKey,
        startTime
      );
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        exitCode: 1,
        error: errorMessage,
        durationMs: Date.now() - startTime,
      };
    }
  }

  /**
   * Detect whether CLI is running in development (tsx) or production.
   */
  private detectEnvironment(): string {
    const execArgs = process.execArgv.join(' ');
    if (
      execArgs.includes('tsx') ||
      execArgs.includes('ts-node') ||
      process.argv[1]?.endsWith('.ts')
    ) {
      return 'development';
    }
    return process.env.REDIACC_ENVIRONMENT ?? DEFAULTS.TELEMETRY.ENVIRONMENT;
  }

  /**
   * Check if renet binary is available.
   */
  async checkRenetAvailable(): Promise<boolean> {
    try {
      const config = await configService.getLocalConfig();
      const renetPath = await getLocalRenetPath(config);
      return new Promise((resolve) => {
        const child = spawn(renetPath, ['version'], {
          stdio: ['ignore', 'pipe', 'pipe'],
        });
        child.on('close', (code) => resolve(code === 0));
        child.on('error', () => resolve(false));
      });
    } catch {
      return false;
    }
  }
}

export const localExecutorService = new LocalExecutorService();
