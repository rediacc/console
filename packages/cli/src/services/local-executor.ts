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
import type { RepositoryConfig } from '../types/index.js';
import type { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { t } from '../i18n/index.js';
import { isAgentEnvironment } from '../utils/agent-guard.js';
import { ValidationError } from '../utils/errors.js';
import { formatDuration } from '../utils/format.js';
import { startSpinner, stopSpinner } from '../utils/spinner.js';
import { auditService } from './audit.js';
import { configService } from './config-resources.js';
import { machineConnections } from './machine-connection.js';
import {
  issueRepoLicense,
  refreshRepoLicenseIdentity,
  refreshRepoLicensesBatch,
  type RepoBatchRecoveryFailureMode,
} from './license.js';
import { fetchOtlpCredentials } from './otlp-credentials.js';
import { outputService } from './output.js';
import { isTelemetryDisabled, telemetryService } from './telemetry.js';
import { getActiveLabel, getDoneLabel, formatStepDuration } from '../utils/timeline.js';
import {
  buildLocalVault,
  getLocalRenetPath,
  provisionRenetToRemote,
  readOptionalSSHKey,
  readSSHKey,
  verifyMachineSetup,
} from './renet-execution.js';
import {
  parseRenetLicenseFailure,
  RENET_LICENSE_REQUIRED_EXIT_CODE,
  type RenetLicenseFailure,
} from './renet-license-contract.js';

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

import { getSubscriptionTokenState } from './subscription-auth.js';
import { authorizeSubscriptionViaDeviceCode } from './subscription-device-auth.js';

/** Options for local execution */
export interface LocalExecuteOptions {
  /** Function name to execute */
  functionName: string;
  /** Target machine name (must exist in local context) */
  machineName: string;
  /** Parameters to pass to the function */
  params?: Record<string, unknown>;
  /** Extra machines for multi-machine operations (e.g. backup) */
  extraMachines?: Record<string, { ip: string; port?: number; user: string; datastore?: string }>;
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
  /** Enable NDJSON events mode — renet emits structured events instead of text */
  eventsMode?: boolean;
  /** Callback for handling NDJSON events in real-time */
  onEvent?: (event: RenetEvent) => void;
  /** Suppress CLI step spinners (steps still recorded for timeline) */
  quietSpinners?: boolean;
  /**
   * Skip the post-success repo-identity license refresh for create/fork.
   * Callers that defer must invoke refreshIdentityFor() themselves once the
   * repository is in its final state (e.g. compound fork --up flows).
   */
  deferIdentityRefresh?: boolean;
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
  /** Total execution duration in milliseconds (includes SSH, provisioning, etc.) */
  durationMs: number;
  /** Renet operation duration in milliseconds (just the remote function execution) */
  operationDurationMs?: number;
  /** Captured stdout, when requested */
  stdout?: string;
  /** Captured stderr, when requested */
  stderr?: string;
  /** True when the full renet output was already echoed to the terminal
   * (non-capture failure path), so failure renderers must not repeat it */
  outputEchoed?: boolean;
  /** Step timing from renet (parsed from JSON output) */
  steps?: { name: string; duration_ms: number; detail?: string }[];
  /** CLI-side step timing (config, SSH connect, provision, verify, license) */
  cliSteps?: { name: string; duration_ms: number; startedAtMs?: number }[];
  /** All steps combined (CLI overhead + renet execution) */
  allSteps?: { name: string; duration_ms: number; detail?: string }[];
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

interface LoadedRepoEntry {
  guid: string;
  name: string;
  networkId?: number;
  secretFiles?: { name: string; value: string }[];
}

/**
 * Build a single LoadedRepoEntry. Extracts file-mode secrets only;
 * env-mode rides the shell prefix (resolveEnvSecrets), not the vault.
 */
function buildLoadedRepoEntry(name: string, config: RepositoryConfig): LoadedRepoEntry {
  const secretFiles: { name: string; value: string }[] = [];
  for (const [secretName, entry] of Object.entries(config.secrets ?? {})) {
    if (entry.mode === 'file') secretFiles.push({ name: secretName, value: entry.value });
  }
  return {
    guid: config.repositoryGuid,
    name,
    networkId: config.networkId,
    ...(secretFiles.length > 0 ? { secretFiles } : {}),
  };
}

async function loadContextRepositories(): Promise<{
  credentials: Record<string, string> | undefined;
  configs: Record<string, LoadedRepoEntry> | undefined;
}> {
  try {
    const repoList = await configService.listRepositories();
    if (repoList.length === 0) return { credentials: undefined, configs: undefined };
    const credentials: Record<string, string> = {};
    const configs: Record<string, LoadedRepoEntry> = {};
    for (const r of repoList) {
      if (r.config.credential) {
        credentials[r.config.repositoryGuid] = r.config.credential;
      }
      const entry = buildLoadedRepoEntry(r.name, r.config);
      configs[r.name] = entry;
      // Also add bare name alias for :latest repos so lookups by bare name work.
      // NOTE: Only handles the default ":latest" tag. If custom tags for grand repos
      // are supported in the future, commands should pass explicit guid/network_id
      // in params (which buildSingleRepoEntry uses as fallback).
      if (r.name.endsWith(':latest')) {
        const bareName = r.name.slice(0, -7);
        if (!(bareName in configs)) {
          configs[bareName] = entry;
        }
      }
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
  // Try bare name first, then composite key (e.g., "my-app" → "my-app:latest")
  let repo = await configService.getRepository(repoName);
  if (!repo && !repoName.includes(':')) {
    repo = await configService.getRepository(`${repoName}:latest`);
  }
  const machine = await configService.getLocalMachine(machineName);
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
/** Structured event from renet's NDJSON events protocol. */
export interface RenetEvent {
  type: 'log' | 'step_start' | 'step_done' | 'output' | 'result';
  ts?: string;
  name?: string;
  msg?: string;
  level?: string;
  duration_ms?: number;
  detail?: string;
  data?: unknown;
}

type StepEntry = { name: string; duration_ms: number; detail?: string };

/** Try to extract steps from a single parsed JSON object. */
function collectStepsFromParsed(parsed: Record<string, unknown>, steps: StepEntry[]): void {
  if (parsed.step_done && typeof parsed.step_done === 'object') {
    const step = parsed.step_done as StepEntry;
    if (step.name && typeof step.duration_ms === 'number') {
      steps.push(step);
    }
  }
  if (Array.isArray(parsed.steps) && parsed.steps.length > 0) {
    steps.push(...(parsed.steps as StepEntry[]));
  }
}

/** Extract step timing from renet's combined stdout+stderr output. */
function extractStepsFromOutput(output: string): StepEntry[] | undefined {
  const steps: StepEntry[] = [];

  for (const rawLine of output.split('\n')) {
    const line = rawLine.trim();
    const jsonStart = line.indexOf('{');
    if (jsonStart < 0) continue;
    try {
      const parsed = JSON.parse(line.slice(jsonStart)) as Record<string, unknown>;
      collectStepsFromParsed(parsed, steps);
    } catch {
      // Not valid JSON, continue
    }
  }

  return steps.length > 0 ? steps : undefined;
}

const MAX_FAILURE_REASON_CHARS = 300;

/**
 * Build the non-zero-exit error message, including renet's actual failure
 * reason when one is available. Without this the operator only sees
 * "renet exited with code 1" while the real cause ("repository X is not
 * mounted") sits unprinted in the captured output. The bridge relays the
 * inner command's streams into stdout (with a `[function] ` prefix) while
 * its own logrus noise lands in stderr, so the cobra "Error: ..." line is
 * searched across BOTH streams before any last-line fallback.
 */
function buildRenetExitError(exitCode: number, stderr: string, stdout: string): string {
  const base = `renet exited with code ${exitCode}`;
  const reason =
    extractErrorLine(stderr) ??
    extractErrorLine(stdout) ??
    lastInformativeLine(stderr) ??
    lastInformativeLine(stdout);
  return reason ? `${base}: ${capReason(reason)}` : base;
}

/** Strip bridge `[function] ` prefixes and drop empty lines and JSON
 * fragments (multi-line JSON yields lines starting with braces, brackets, or
 * quoted keys). */
function cleanOutputLines(output: string): string[] {
  return output
    .split('\n')
    .map((line) => line.replace(/^\s*\[[^\]]+\]\s?/, '').trim())
    .filter((line) => line.length > 0 && !/^[{}\][",]/.test(line));
}

/** The last cobra-style "Error: ..." line, without the prefix. */
function extractErrorLine(output: string): string | undefined {
  return cleanOutputLines(output)
    .filter((line) => /^Error: /.test(line))
    .at(-1)
    ?.replace(/^Error:\s*/, '');
}

/** The last line that isn't structured-log noise (`time="..." level=...`). */
function lastInformativeLine(output: string): string | undefined {
  return cleanOutputLines(output)
    .filter((line) => !/^time="/.test(line))
    .at(-1);
}

function capReason(reason: string): string {
  return reason.length > MAX_FAILURE_REASON_CHARS
    ? `${reason.slice(0, MAX_FAILURE_REASON_CHARS)}…`
    : reason;
}

type StdoutHandler = (data: Buffer) => void;

/** Handle NDJSON events from renet in events mode. */
function handleEventsStdout(onEvent: (event: RenetEvent) => void): StdoutHandler {
  let lineBuffer = '';
  return (data: Buffer) => {
    lineBuffer += data.toString();
    const lines = lineBuffer.split('\n');
    lineBuffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const event = JSON.parse(trimmed) as RenetEvent;
        onEvent(event);
      } catch {
        process.stdout.write(`${line}\n`);
      }
    }
  };
}

/** Render real-time step events from a single parsed JSON object. */
function renderStepEvent(parsed: Record<string, unknown>): void {
  if (parsed.step_start && typeof parsed.step_start === 'object') {
    const s = parsed.step_start as { name?: string };
    if (s.name) process.stdout.write(`⠋ ${getActiveLabel(s.name)}...`);
  } else if (parsed.step_done && typeof parsed.step_done === 'object') {
    const s = parsed.step_done as { name?: string; duration_ms?: number };
    if (s.name && s.duration_ms != null) {
      process.stdout.write(`\r✔ ${getDoneLabel(s.name)} (${formatStepDuration(s.duration_ms)})\n`);
    }
  }
}

/** Handle stdout in non-events, non-capture mode: detect step events and render them. */
function handleStepDetectionStdout(): StdoutHandler {
  let stepLineBuffer = '';
  return (data: Buffer) => {
    stepLineBuffer += data.toString();
    const stepLines = stepLineBuffer.split('\n');
    stepLineBuffer = stepLines.pop() ?? '';
    for (const sl of stepLines) {
      const trimmed = sl.trim();
      const jsonIdx = trimmed.indexOf('{');
      if (jsonIdx < 0) continue;
      try {
        const p = JSON.parse(trimmed.slice(jsonIdx)) as Record<string, unknown>;
        renderStepEvent(p);
      } catch {
        /* not JSON, ignore */
      }
    }
  };
}

/** Create the appropriate stdout handler based on execution options. */
function createStdoutHandler(options: LocalExecuteOptions): StdoutHandler {
  if (options.eventsMode && options.onEvent) {
    return handleEventsStdout(options.onEvent);
  }
  if (options.captureOutput) {
    return () => {};
  }
  if (options.debug) {
    return (data: Buffer) => process.stdout.write(data);
  }
  return handleStepDetectionStdout();
}

/**
 * POSIX single-quote a string for safe use as an argument inside a remote
 * shell command. Wraps in `'...'` and escapes embedded single quotes. Used
 * by `buildRemoteCommand` to inject OTLP credentials as env vars.
 */
function shellQuote(s: string): string {
  return `'${s.replaceAll("'", `'\\''`)}'`;
}

/**
 * Build the `env K=V K=V ` prefix that carries telemetry state into a
 * renet subprocess launched over SSH. Shared by the `renet execute`
 * path (buildRemoteRenetCommand) and the `renet list all` path
 * (machine-status.ts) so both invocations get the same telemetry
 * handling — emit spans/metrics/logs when OTLP creds were fetched, or
 * go default-deny when the user opted out via CI / REDIACC_TELEMETRY_DISABLED.
 *
 * Returns a trailing-space string ready to splice into the command, or
 * an empty string when nothing needs to be injected.
 */
export function buildRenetEnvPrefix(params: {
  isDevelopment: boolean;
  telemetryDisabled: boolean;
  otlpCreds?: { user: string; pass: string } | null;
  /**
   * Per-repo env-mode secrets, already prefixed `REDIACC_SECRET_<NAME>`.
   * Renet's `propagateDevEnvVars` forwards this prefix into the bash
   * preamble, and the `renet compose --` wrapper interpolates them into
   * `${REDIACC_SECRET_*}` references in the user's compose YAML.
   */
  envSecrets?: Record<string, string>;
}): string {
  const { isDevelopment, telemetryDisabled, otlpCreds, envSecrets } = params;
  const envParts: string[] = [];
  if (isDevelopment) {
    envParts.push('REDIACC_ENVIRONMENT=development');
  }
  if (telemetryDisabled) {
    // Propagate the opt-out to renet. When set, renet skips its OTel SDK
    // setup entirely (see pkg/telemetry/telemetry.go:disabled). We
    // deliberately do NOT pass OTLP creds in this branch — even if the
    // caller passed `otlpCreds`, ignoring them here matches the user's
    // intent to send zero telemetry from any process.
    envParts.push('REDIACC_TELEMETRY_DISABLED=1');
  } else if (otlpCreds) {
    envParts.push(`REDIACC_OTLP_USER=${shellQuote(otlpCreds.user)}`);
    envParts.push(`REDIACC_OTLP_PASS=${shellQuote(otlpCreds.pass)}`);
  }
  if (envSecrets) {
    for (const [k, v] of Object.entries(envSecrets)) {
      envParts.push(`${k}=${shellQuote(v)}`);
    }
  }
  return envParts.length > 0 ? `env ${envParts.join(' ')} ` : '';
}

/**
 * Build the `sudo env ... renet execute ...` command string that the CLI
 * executes over SSH on the target machine.
 *
 * Exported as a pure function so unit tests can exercise all combinations
 * of (telemetry disabled, OTLP creds present, events mode, dev environment)
 * without constructing a full LocalExecutorService with SFTP mocks.
 *
 * When `telemetryDisabled` is true, `REDIACC_TELEMETRY_DISABLED=1` is
 * injected INSTEAD OF OTLP credentials — the user's opt-out takes
 * precedence over any credentials the caller may have pre-fetched.
 */
export function buildRemoteRenetCommand(params: {
  remoteRenetPath: string;
  eventsMode?: boolean;
  isDevelopment: boolean;
  telemetryDisabled: boolean;
  otlpCreds?: { user: string; pass: string } | null;
  envSecrets?: Record<string, string>;
}): string {
  const { remoteRenetPath, eventsMode, ...envParams } = params;
  const eventsFlag = eventsMode ? ' --events' : '';
  const envPrefix = buildRenetEnvPrefix(envParams);
  return `sudo ${envPrefix}${remoteRenetPath} execute --executor local${eventsFlag}`;
}

type LicenseIssuanceOutcome =
  | { kind: 'success' }
  | { kind: 'failure'; failureMode: RepoBatchRecoveryFailureMode; serverErrorSample?: string };

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
    const outcome = await this.maybeIssueLicense(
      options,
      machine,
      sshPrivateKey,
      remoteRenetPath,
      sftp
    );
    if (outcome.kind === 'success') {
      return null;
    }
    telemetryService.trackEvent('license_recovery_failed', {
      licenseRecoveryFailureMode: String(outcome.failureMode),
    });
    const recoveryGuidance = this.resolveLicenseRecoveryGuidance(
      failure,
      options.machineName,
      outcome
    );
    const recoveryFailedMsg = recoveryGuidance.recoveryFailedMessage;
    if (!recoveryFailedMsg) {
      return result;
    }
    return this.buildRecoveryFailureResult(
      result,
      recoveryGuidance,
      recoveryFailedMsg,
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
    let result = await this.runRemoteExecution(sftp, remoteRenetPath, vault, options);
    let failure: RenetLicenseFailure | null = null;
    if (
      !result.success &&
      result.exitCode === RENET_LICENSE_REQUIRED_EXIT_CODE &&
      process.env.REDIACC_SKIP_MACHINE_ACTIVATION !== '1'
    ) {
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

    if (result.success && !options.deferIdentityRefresh) {
      await this.maybeRefreshRepoIdentity(options, machine, sshPrivateKey, remoteRenetPath, sftp);
    }

    const operationDurationMs = result.durationMs;
    return {
      ...result,
      durationMs: Date.now() - startTime,
      operationDurationMs,
    };
  }

  private async maybeIssueLicense(
    options: LocalExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp: SFTPClient
  ): Promise<LicenseIssuanceOutcome> {
    // NOTE: we intentionally do NOT gate on isLicensedRenetFunction here.
    // That deny-list (repository_up/down/delete) governs PRE-FLIGHT issuance —
    // those operate-tier ops don't issue a license before running. But this
    // method runs during RECOVERY, after renet has already reported
    // LICENSE_REQUIRED (reason=missing) for the repo on the target machine.
    // The repo image exists on disk there, so refreshRepoLicensesBatch can
    // scan it and issue. Skipping recovery for deny-listed functions is the
    // root cause of rediacc/console#482: `repo push --up` to a fresh machine
    // fails because the license was issued for the source, not the destination,
    // and the destination's repository_up recovery never tried to issue.

    // For create/fork, re-issue the pre-provisioning repo license
    if (
      options.functionName === 'repository_create' ||
      options.functionName === 'repository_fork'
    ) {
      try {
        await this.ensureRepoLicenseForProvisioning(
          options,
          machine,
          sshPrivateKey,
          remoteRenetPath,
          sftp
        );
        return { kind: 'success' };
      } catch (err) {
        telemetryService.trackError(err, { operation: 'executor.repo_license_recovery' });
        return {
          kind: 'failure',
          failureMode: 'server_rejected_all',
          serverErrorSample: err instanceof Error ? err.message : String(err),
        };
      }
    }
    // For all other licensed operations, batch refresh existing repo licenses
    const batchResult = await refreshRepoLicensesBatch(
      machine,
      sshPrivateKey,
      remoteRenetPath,
      sftp
    ).catch((err: unknown) => {
      telemetryService.trackError(err, { operation: 'executor.batch_refresh' });
      return {
        kind: 'failure' as const,
        failureMode: 'server_rejected_all' as const,
        serverErrorSample: String(err),
      };
    });
    if ('kind' in batchResult) {
      return batchResult;
    }
    if (batchResult.recoveryFailureMode === null) return { kind: 'success' };
    return {
      kind: 'failure',
      failureMode: batchResult.recoveryFailureMode,
      serverErrorSample: batchResult.serverErrorSample,
    };
  }

  private async maybeRefreshInvalidSignatures(
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp: SFTPClient
  ): Promise<void> {
    if (getSubscriptionTokenState().kind !== 'ready') return;

    try {
      const result = await refreshRepoLicensesBatch(machine, sshPrivateKey, remoteRenetPath, sftp);
      if (result.invalidSignatureDetected > 0) {
        const refreshed = result.issued + result.refreshed;
        if (refreshed > 0) {
          outputService.info(t('warnings.licenseSignatureRefreshed', { count: refreshed }));
        } else {
          outputService.warn(
            t('warnings.licenseSignatureRefreshFailed', {
              count: result.invalidSignatureDetected,
            })
          );
        }
      }
    } catch {
      // Non-blocking: license check failure should not prevent command execution
    }
  }

  private async maybeOnboardSubscription(reason: string): Promise<boolean> {
    if (reason !== 'missing') {
      return false;
    }
    const tokenState = getSubscriptionTokenState();
    if (tokenState.kind === 'ready') {
      return false;
    }
    if (isAgentEnvironment()) {
      throw new ValidationError(t('errors.subscription.tokenRequired'));
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
   * and pre-issue a repo license (without identity proofs since the repo
   * doesn't exist yet). The server enforces machine slot limits during
   * issuance. After creation, maybeRefreshRepoIdentity re-issues the
   * license with identity proofs.
   */
  private async ensureRepoLicenseForProvisioning(
    options: LocalExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp?: SFTPClient
  ): Promise<void> {
    // Allow bypassing activation for nolicense/CI builds where no subscription server exists
    if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') {
      return;
    }

    const tokenState = getSubscriptionTokenState();
    if (tokenState.kind !== 'ready') {
      if (isAgentEnvironment()) {
        throw new ValidationError(t('errors.subscription.tokenRequired'));
      }
      await authorizeSubscriptionViaDeviceCode(undefined, {
        interactive: process.stdin.isTTY && process.stdout.isTTY,
        announceIntro: true,
      });
    }

    const repoLicenseCtx = await resolveRepoLicenseContext(
      options.functionName,
      options.machineName,
      options.params ?? {},
      sftp!
    );
    if (!repoLicenseCtx) {
      throw new Error(t('errors.subscription.activationFailed'));
    }

    const issued = await issueRepoLicense(
      machine,
      sshPrivateKey,
      {
        repositoryGuid: repoLicenseCtx.repositoryGuid,
        grandGuid: repoLicenseCtx.grandGuid,
        kind: repoLicenseCtx.kind,
        requestedSizeGb: repoLicenseCtx.requestedSizeGb,
      },
      remoteRenetPath,
      sftp
    );
    if (!issued) {
      throw new Error(t('errors.subscription.activationFailed'));
    }
  }

  private buildMissingLicenseMessage(
    outcome: { failureMode: RepoBatchRecoveryFailureMode; serverErrorSample?: string } | undefined,
    machineName: string
  ): string {
    switch (outcome?.failureMode) {
      case 'token_not_ready':
        return t('errors.license.recoveryFailedTokenNotReady');
      case 'no_known_repos':
        return t('errors.license.recoveryFailedNoKnownRepos', { machine: machineName });
      case 'server_rejected_all': {
        const errorDetail = outcome.serverErrorSample ?? '';
        return t('errors.license.recoveryFailedServerRejected', {
          error: errorDetail,
          machine: machineName,
        });
      }
      default:
        return (
          `A repo license is required for this operation, and automatic issuance did not succeed. ` +
          `Run: rdc subscription refresh -m ${machineName}`
        );
    }
  }

  private resolveLicenseRecoveryGuidance(
    failure: RenetLicenseFailure,
    machineName: string,
    outcome?: { failureMode: RepoBatchRecoveryFailureMode; serverErrorSample?: string }
  ): {
    errorCode?: string;
    guidance?: string;
    failFastMessage?: string;
    recoveryFailedMessage?: string;
  } {
    switch (failure.reason) {
      case 'missing': {
        const recoveryFailedMessage = this.buildMissingLicenseMessage(outcome, machineName);
        return {
          errorCode: 'REPO_LICENSE_ISSUANCE_REQUIRED',
          guidance: `Issue repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
          recoveryFailedMessage,
        };
      }
      case 'expired':
        return {
          errorCode: 'REPO_LICENSE_REFRESH_REQUIRED',
          guidance: `Refresh repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
          recoveryFailedMessage:
            `The installed repo license must be refreshed before this operation can continue. ` +
            `Run: rdc subscription refresh -m ${machineName}`,
        };
      case 'machine_mismatch':
        return {
          errorCode: 'REPO_LICENSE_MACHINE_MISMATCH',
          guidance: `Reissue repo licenses from this machine context with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The installed repo license belongs to a different machine. ` +
            `Reissue it from this machine context with: rdc subscription refresh -m ${machineName}`,
        };
      case 'repository_mismatch':
        return {
          errorCode: 'REPO_LICENSE_REPOSITORY_MISMATCH',
          guidance: `Refresh repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The installed repo license does not match the target repository. ` +
            `Refresh repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
        };
      case 'sequence_regression':
        return {
          errorCode: 'REPO_LICENSE_INTEGRITY_ERROR',
          guidance: `Replace the installed repo license with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The installed repo license is older than the latest accepted sequence. ` +
            `Replace it with a newer repo license using: rdc subscription refresh -m ${machineName}`,
        };
      case 'invalid_signature':
        return {
          errorCode: 'REPO_LICENSE_INTEGRITY_ERROR',
          guidance: `Replace the installed repo license with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The installed repo license could not be trusted. ` +
            `Replace it with a newly issued repo license using: rdc subscription refresh -m ${machineName}`,
        };
      case 'identity_mismatch':
        return {
          errorCode: 'REPO_LICENSE_IDENTITY_MISMATCH',
          guidance: `Reissue repo licenses with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The repository identity does not match the installed repo license. ` +
            `Reissue repo licenses with: rdc subscription refresh -m ${machineName}`,
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
    if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') return;
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
      await refreshRepoLicenseIdentity(machine, sshPrivateKey, repoLicense, remoteRenetPath, sftp);
    }
  }

  /**
   * Re-issue a repo license with identity proofs, for callers that ran a
   * create/fork with deferIdentityRefresh. Resolves the machine and SSH key
   * from the active config, reuses a pooled connection, and shares the SFTP
   * session with license issuance.
   */
  async refreshIdentityFor(
    functionName: string,
    machineName: string,
    params: Record<string, unknown>
  ): Promise<void> {
    if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') return;
    const lease = await machineConnections.acquire(machineName);
    try {
      const repoLicense = await resolveRepoLicenseContext(
        functionName,
        machineName,
        params,
        lease.sftp
      );
      if (repoLicense) {
        await refreshRepoLicenseIdentity(
          lease.machine,
          lease.sshPrivateKey,
          repoLicense,
          undefined,
          lease.sftp
        );
      }
    } finally {
      lease.release();
    }
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
    envSecrets?: Record<string, string>
  ): string {
    return buildRemoteRenetCommand({
      remoteRenetPath,
      eventsMode,
      isDevelopment: this.detectEnvironment() === 'development',
      telemetryDisabled: isTelemetryDisabled(),
      otlpCreds,
      envSecrets,
    });
  }

  /**
   * Resolve env-mode per-repo secrets for the focal repository, prefixed
   * `REDIACC_SECRET_<NAME>`. Returns undefined when no repo is targeted.
   * File-mode secrets are out of band — they ride the vault stdin (Step 6),
   * not the shell prefix, so they never appear in `ps`.
   */
  private async resolveEnvSecrets(
    repoRef: string | undefined
  ): Promise<Record<string, string> | undefined> {
    if (!repoRef) return undefined;
    try {
      const repoConfig = await configService.getRepository(repoRef);
      const secrets = repoConfig?.secrets;
      if (!secrets) return undefined;
      const out: Record<string, string> = {};
      for (const [name, entry] of Object.entries(secrets)) {
        if (entry.mode === 'env') out[`REDIACC_SECRET_${name}`] = entry.value;
      }
      return Object.keys(out).length > 0 ? out : undefined;
    } catch {
      return undefined;
    }
  }

  private async runRemoteExecution(
    sftp: SFTPClient,
    remoteRenetPath: string,
    vault: string,
    options: LocalExecuteOptions
  ): Promise<LocalExecuteResult> {
    // Fetch OTLP credentials so renet inherits them as env vars and its
    // telemetry init picks them up. Skip the fetch entirely when telemetry
    // is opted out — no wasted network round-trip, no credentials in
    // memory to accidentally propagate downstream. `buildRemoteCommand`
    // still injects `REDIACC_TELEMETRY_DISABLED=1` for the remote end.
    const otlpCreds = isTelemetryDisabled() ? null : await fetchOtlpCredentials();
    const repoRef =
      typeof options.params?.repository === 'string' ? options.params.repository : undefined;
    const envSecrets = await this.resolveEnvSecrets(repoRef);
    const command = this.buildRemoteCommand(
      remoteRenetPath,
      options.eventsMode,
      otlpCreds,
      envSecrets
    );
    let stdout = '';
    let stderr = '';
    const stdoutHandler = createStdoutHandler(options);
    const execStart = Date.now();
    const exitCode = await sftp.execStreaming(command, {
      stdin: vault,
      onStdout: (data) => {
        stdout += data;
        stdoutHandler(data);
      },
      onStderr: (data) => {
        stderr += data;
        if (options.debug && !options.captureOutput && !options.eventsMode) {
          process.stderr.write(data);
        }
      },
    });

    const combined = stdout + stderr;
    const renetDurationMatch = /operation completed.*?duration_ms=(\d+)/.exec(combined);
    const operationMs = renetDurationMatch
      ? Number.parseInt(renetDurationMatch[1], 10)
      : Date.now() - execStart;

    const steps = extractStepsFromOutput(combined);

    let outputEchoed = false;
    if (exitCode !== 0 && !options.debug && !options.captureOutput) {
      const output = combined.trim();
      if (output) {
        process.stderr.write(`\n--- renet output (exit code ${exitCode}) ---\n`);
        process.stderr.write(`${output}\n`);
        process.stderr.write('---\n\n');
        outputEchoed = true;
      }
    }

    return {
      success: exitCode === 0,
      exitCode,
      error: exitCode === 0 ? undefined : buildRenetExitError(exitCode, stderr, stdout),
      durationMs: operationMs,
      stdout,
      stderr,
      outputEchoed,
      steps,
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
    options: LocalExecuteOptions,
    sftp: SFTPClient,
    cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[],
    quiet: boolean
  ): Promise<{ remoteRenetPath: string; renetUploaded: boolean }> {
    const provStart = Date.now();
    const provisionFn = () => provisionRenetToRemote(config, machine, sshPrivateKey, options, sftp);
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

    if (
      options.functionName === 'repository_create' ||
      options.functionName === 'repository_fork'
    ) {
      // License issuance only needs the provisioned renet binary, not the
      // verified machine setup — run it concurrently with verification.
      const runLicense = async () => {
        const licStart = Date.now();
        await timedStep(t('timing.step.activating'), 'timing.step.licenseActivated', () =>
          this.ensureRepoLicenseForProvisioning(
            options,
            machine,
            sshPrivateKey,
            remoteRenetPath,
            sftp
          )
        );
        cliSteps.push({
          name: 'license',
          duration_ms: Date.now() - licStart,
          startedAtMs: licStart,
        });
      };
      await Promise.all([runVerify(), runLicense()]);
    } else {
      await runVerify();
    }

    if (renetUploaded) {
      await this.maybeRefreshInvalidSignatures(machine, sshPrivateKey, remoteRenetPath, sftp);
    }

    return { remoteRenetPath, renetUploaded };
  }

  /**
   * Execute a function on a machine via direct SSH.
   * SSHes to the machine and runs `renet execute --executor local` with vault via stdin.
   */
  private async loadConfigAndBuildVault(
    options: LocalExecuteOptions,
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
    cliSteps.push({ name: 'config', duration_ms: Date.now() - startTime, startedAtMs: startTime });
    return { config, machine, sshPrivateKey, vault };
  }

  private async executeSession(
    sftp: SFTPClient,
    config: Awaited<ReturnType<typeof configService.getLocalConfig>>,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    vault: ReturnType<typeof buildLocalVault>,
    options: LocalExecuteOptions,
    cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[],
    quiet: boolean,
    startTime: number
  ): Promise<LocalExecuteResult> {
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
    options: LocalExecuteOptions,
    result: Pick<LocalExecuteResult, 'success' | 'exitCode' | 'durationMs' | 'error'>
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

  async execute(options: LocalExecuteOptions): Promise<LocalExecuteResult> {
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
      return { success: false, exitCode: 1, error: errorMessage, durationMs };
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
