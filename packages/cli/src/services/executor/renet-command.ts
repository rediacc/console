/**
 * The env prefix and command line the CLI runs over SSH to start renet, and
 * the environment and per-repo secrets that go into it.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { isDevBuild } from '../../utils/platform.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { configService } from '../config/config-resources.js';

/**
 * Build the `env K=V K=V ` prefix that carries telemetry state into a
 * renet subprocess launched over SSH. Shared by the `renet execute`
 * path (buildRemoteRenetCommand) and the `renet list all` path
 * (machine-status.ts) so both invocations get the same telemetry
 * handling, emit spans/metrics/logs when OTLP creds were fetched, or
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
  /**
   * Remote KUBECONFIG path when the target is a cluster, the k8s analog of
   * DOCKER_HOST. The `renet kube` wrapper reads it to talk to the cluster.
   */
  kubeconfig?: string;
}): string {
  const { isDevelopment, telemetryDisabled, otlpCreds, envSecrets, kubeconfig } = params;
  const envParts: string[] = [];
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
 * injected INSTEAD OF OTLP credentials, the user's opt-out takes
 * precedence over any credentials the caller may have pre-fetched.
 */
export function buildRemoteRenetCommand(params: {
  remoteRenetPath: string;
  eventsMode?: boolean;
  isDevelopment: boolean;
  telemetryDisabled: boolean;
  otlpCreds?: { user: string; pass: string } | null;
  envSecrets?: Record<string, string>;
  kubeconfig?: string;
}): string {
  const { remoteRenetPath, eventsMode, ...envParams } = params;
  const eventsFlag = eventsMode ? ' --events' : '';
  const envPrefix = buildRenetEnvPrefix(envParams);
  return `sudo ${envPrefix}${remoteRenetPath} execute --executor local${eventsFlag}`;
}

/**
 * Resolve env-mode per-repo secrets for the focal repository, prefixed
 * `REDIACC_SECRET_<NAME>`. Returns undefined when no repo is targeted.
 * File-mode secrets are out of band, they ride the vault stdin (Step 6),
 * not the shell prefix, so they never appear in `ps`.
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
