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
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { DEFAULTS } from '@rediacc/shared/config';
import { contextService } from './context.js';
import { outputService } from './output.js';
import {
  buildLocalVault,
  getLocalRenetPath,
  provisionRenetToRemote,
  readOptionalSSHKey,
  readSSHKey,
  verifyMachineSetup,
} from './renet-execution.js';

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
}

/** Result of local execution */
interface LocalExecuteResult {
  /** Whether execution succeeded */
  success: boolean;
  /** Exit code from renet */
  exitCode: number;
  /** Error message if failed */
  error?: string;
  /** Execution duration in milliseconds */
  durationMs: number;
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
    const storageList = await contextService.listLocalStorages();
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
    const repoList = await contextService.listLocalRepositories();
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

/**
 * Service for executing tasks directly via renet subprocess.
 * Bypasses middleware for single-machine local deployments.
 *
 * Uses direct SSH to the target machine and runs `renet execute --executor local`
 * with vault JSON piped via stdin. This avoids double-SSH (CLI→renet→machine).
 */
class LocalExecutorService {
  /**
   * Execute a function on a machine via direct SSH.
   * SSHes to the machine and runs `renet execute --executor local` with vault via stdin.
   */
  async execute(options: LocalExecuteOptions): Promise<LocalExecuteResult> {
    const startTime = Date.now();

    try {
      const config = await contextService.getLocalConfig();
      const machine = await contextService.getLocalMachine(options.machineName);

      if (options.debug) {
        outputService.info(`[local] Executing '${options.functionName}' on ${options.machineName}`);
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

      await provisionRenetToRemote(config, machine, sshPrivateKey, options);
      await verifyMachineSetup(machine, sshPrivateKey, options);

      if (options.debug) {
        outputService.info(`[local] Direct SSH to ${machine.ip}, executor=local`);
      }

      const sftp = new SFTPClient({
        host: machine.ip,
        port: machine.port ?? DEFAULTS.SSH.PORT,
        username: machine.user,
        privateKey: sshPrivateKey,
      });
      await sftp.connect();

      try {
        const exitCode = await sftp.execStreaming('renet execute --executor local', {
          stdin: vault,
          onStdout: (data) => {
            process.stdout.write(data);
          },
          onStderr: (data) => {
            process.stderr.write(data);
          },
        });

        return {
          success: exitCode === 0,
          exitCode,
          error: exitCode === 0 ? undefined : `renet exited with code ${exitCode}`,
          durationMs: Date.now() - startTime,
        };
      } finally {
        sftp.close();
      }
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
   * Check if renet binary is available.
   */
  async checkRenetAvailable(): Promise<boolean> {
    try {
      const config = await contextService.getLocalConfig();
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
