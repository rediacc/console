/**
 * Machine Status Service
 *
 * Fetches full machine status by SSHing in and running `renet list all --json`.
 * Returns the parsed ListResult for display by the command layer.
 */

import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { ListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { isListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { configService } from '../config/config-resources.js';
import { buildRenetEnvPrefix } from '../executor/local-executor.js';
import { machineConnections } from './machine-connection.js';
import { fetchOtlpCredentials } from '../telemetry/otlp-credentials.js';
import { outputService } from '../core/output.js';
import { provisionRenetToRemote } from '../renet/renet-execution.js';
import { isTelemetryDisabled } from '../telemetry/telemetry.js';

interface FetchStatusOptions {
  debug?: boolean;
  /** When provided, only gather these renet sections (system,repositories,containers,services,network,block). */
  sections?: string[];
}

/**
 * Build the `renet list all` invocation. Exported for unit testing — the
 * caller-provided sections filter must propagate into `--sections`.
 */
export function buildListCommand(params: {
  envPrefix: string;
  remoteRenetPath: string;
  datastore: string;
  sections?: string[];
}): string {
  const sectionsFlag =
    params.sections && params.sections.length > 0 ? ` --sections ${params.sections.join(',')}` : '';
  return `sudo ${params.envPrefix}${params.remoteRenetPath} list all --datastore ${params.datastore} --json${sectionsFlag}`;
}

/**
 * Fetch full machine status via SSH.
 *
 * Flow:
 * 1. Load machine config from local context
 * 2. Provision renet binary to remote
 * 3. SSH: run `sudo renet list all --datastore <path> --json`
 * 4. Parse JSON output as ListResult
 */
export async function fetchMachineStatus(
  machineName: string,
  options: FetchStatusOptions = {}
): Promise<ListResult> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const lease = await machineConnections.acquire(machineName);

  try {
    // Provision renet binary to remote
    if (options.debug) {
      outputService.info(`Provisioning renet to ${machine.ip}...`);
    }

    // Fetch OTLP creds the same way `rdc run` / `repo up` do via
    // local-executor, so the spawned renet sends its own telemetry to
    // otlp.rediacc.io — keeping `machine query` consistent with other paths
    // that shell out to renet. This is an independent, unauthenticated HTTP
    // round-trip to the account server: it depends on neither the machine
    // nor renet provisioning, so run it concurrently with provisioning
    // rather than sequentially after it. It never throws (default-deny to
    // null), so Promise.all cannot reject on the telemetry branch. Respect
    // the opt-out short-circuit so we skip the fetch entirely when disabled.
    const telemetryOff = isTelemetryDisabled();
    const otlpCredsPromise = telemetryOff ? Promise.resolve(null) : fetchOtlpCredentials();

    const [{ remotePath: remoteRenetPath }, otlpCreds] = await Promise.all([
      provisionRenetToRemote({ renetPath: localConfig.renetPath }, machine, lease.sshPrivateKey, {
        debug: options.debug,
      }),
      otlpCredsPromise,
    ]);

    const envPrefix = buildRenetEnvPrefix({
      isDevelopment: process.env.NODE_ENV !== 'production',
      telemetryDisabled: telemetryOff,
      otlpCreds,
    });
    const cmd = buildListCommand({
      envPrefix,
      remoteRenetPath,
      datastore: machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
      sections: options.sections,
    });

    if (options.debug) {
      outputService.info(`[status] Running: ${cmd}`);
    }

    // Execute over the shared connection
    const sftp = await lease.ensure();

    let stdout = '';
    let stderr = '';

    const exitCode = await sftp.execStreaming(cmd, {
      onStdout: (data) => {
        stdout += data.toString();
      },
      onStderr: (data) => {
        stderr += data.toString();
        if (options.debug) {
          process.stderr.write(data);
        }
      },
    });

    if (exitCode !== 0) {
      throw new Error(`renet list all failed (exit ${exitCode}): ${stderr}`);
    }

    const parsed: unknown = JSON.parse(stdout);
    if (!isListResult(parsed)) {
      throw new Error('Failed to parse renet output: unexpected format');
    }

    return parsed;
  } finally {
    lease.release();
  }
}
