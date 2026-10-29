/**
 * The env prefix and command line the CLI runs over SSH to start renet, and
 * the environment and per-repo secrets that go into it. Secrets ride stdin,
 * never argv.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { isDevBuild } from '../../utils/platform.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { configService } from '../config/config-resources.js';
import { type RenetEnv, type RenetLaunch, sudoRenet } from './renet-launch.js';

/** The settings a renet launch carries, split by whether they may ride argv. */
export interface RenetEnvParams {
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
  /**
   * Remote KUBECONFIG path when the target is a cluster, the k8s analog of
   * DOCKER_HOST. The `renet kube` wrapper reads it to talk to the cluster.
   */
  kubeconfig?: string;
}

/**
 * Compose the environment that carries telemetry state and per-repo secrets
 * into a renet subprocess launched over SSH. Shared by the `renet execute`
 * path (buildRemoteRenetCommand), the detached `renet job start` path and the
 * `renet list all` path (machine-status.ts), so every invocation gets the same
 * telemetry handling: spans/metrics/logs when OTLP creds were fetched, or
 * default-deny when the user opted out via CI / REDIACC_TELEMETRY_DISABLED.
 */
export function buildRenetEnv(params: RenetEnvParams): RenetEnv {
  const { isDevelopment, telemetryDisabled, otlpCreds, envSecrets, kubeconfig } = params;
  const envParts: string[] = [];
  const secrets: Record<string, string> = {};
  if (isDevelopment) {
    // REMOTE plane: this REDIACC_ENVIRONMENT travels to the renet process on the machine, a different plane from the local CLI's dev signal. Keep the name; the env-tombstone test allowlists this one literal.
    envParts.push('REDIACC_ENVIRONMENT=development');
  }
  if (kubeconfig) {
    envParts.push(`KUBECONFIG=${shellQuote(kubeconfig)}`);
  }
  if (telemetryDisabled) {
    // Propagate the opt-out to renet. When set, renet skips its OTel SDK setup entirely (see pkg/telemetry/telemetry.go:disabled). We deliberately do NOT pass OTLP creds in this branch, even if the caller passed `otlpCreds`, ignoring them here matches the user's intent to send zero telemetry from any process.
    envParts.push('REDIACC_TELEMETRY_DISABLED=1');
  } else if (otlpCreds) {
    secrets.REDIACC_OTLP_USER = otlpCreds.user;
    secrets.REDIACC_OTLP_PASS = otlpCreds.pass;
  }
  if (envSecrets) {
    Object.assign(secrets, envSecrets);
  }
  return { prefix: envParts.length > 0 ? `env ${envParts.join(' ')} ` : '', secrets };
}

/**
 * Build the sudo `renet execute ...` launch that the CLI executes over SSH
 * on the target machine; its `stdinPrefix` goes ahead of the vault.
 *
 * Exported as a pure function so unit tests can exercise all combinations
 * of (telemetry disabled, OTLP creds present, events mode, dev environment)
 * without constructing a full LocalExecutorService with SFTP mocks.
 *
 * When `telemetryDisabled` is true, `REDIACC_TELEMETRY_DISABLED=1` is
 * injected INSTEAD OF OTLP credentials, the user's opt-out takes
 * precedence over any credentials the caller may have pre-fetched.
 */
export function buildRemoteRenetCommand(
  params: RenetEnvParams & { remoteRenetPath: string; eventsMode?: boolean; timeoutMs?: number }
): RenetLaunch {
  const { remoteRenetPath, eventsMode, timeoutMs, ...envParams } = params;
  const eventsFlag = eventsMode ? ' --events' : '';
  const timeoutFlag = timeoutMs ? ` --timeout ${timeoutMs}ms` : '';
  return sudoRenet(
    buildRenetEnv(envParams),
    `${shellQuote(remoteRenetPath)} execute --executor local${eventsFlag}${timeoutFlag}`
  );
}

/** The ceiling for a verb whose run time grows with the data it moves. */
export const DATA_TRANSFER_TIMEOUT_MS = 24 * 60 * 60 * 1000;

const DATA_TRANSFER_FUNCTIONS = new Set([
  'backup_snapshot',
  'backup_push',
  'backup_pull',
  'backup_restore',
  'backup_restore_path',
  'backup_verify',
]);

/**
 * The `--timeout` a renet run carries. Both `renet execute` and `renet job start` cancel at 10 minutes when none is passed, which killed the hostinger seed's foreground snapshot of mautic at duration_ms=600019 with `signal: terminated` (2026-10-29), mid-upload under a 100 Mbps cap. A data-moving backup verb gets a ceiling sized for the transfer instead: a 200 GB repo at 12.5 MB/s needs about 4.5 hours, and 24 hours leaves room for a slower link. The cost is that a stalled transfer is cancelled only at that ceiling, which `rdc job cancel` or Ctrl-C ends sooner. An explicit caller value always wins.
 */
export function resolveRenetTimeoutMs(
  functionName: string,
  explicitMs: number | undefined
): number | undefined {
  if (explicitMs) return explicitMs;
  return DATA_TRANSFER_FUNCTIONS.has(functionName) ? DATA_TRANSFER_TIMEOUT_MS : undefined;
}

/**
 * Resolve env-mode per-repo secrets for the focal repository, prefixed
 * `REDIACC_SECRET_<NAME>`. Returns undefined when no repo is targeted.
 * File-mode secrets ride inside the vault; env-mode secrets ride the stdin
 * prefix that `sudoRenet` puts ahead of it. Neither appears in `ps`.
 */
export async function resolveEnvSecrets(
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

/**
 * Detect whether CLI is running in development (tsx) or production.
 */
export function detectEnvironment(): string {
  const execArgs = process.execArgv.join(' ');
  if (
    execArgs.includes('tsx') ||
    execArgs.includes('ts-node') ||
    process.argv[1]?.endsWith('.ts')
  ) {
    return 'development';
  }
  return isDevBuild() ? 'development' : DEFAULTS.TELEMETRY.ENVIRONMENT;
}
