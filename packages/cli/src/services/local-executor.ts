/**
 * LocalExecutorService - Direct task execution without middleware.
 *
 * This service enables Console CLI to work directly with renet bridge
 * without going through middleware API. Used in "local mode" contexts.
 */

import { type ChildProcess, spawn } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS, PROCESS_DEFAULTS } from '@rediacc/shared/config';
import { contextService } from './context.js';
import { isSEA } from './embedded-assets.js';
import { outputService } from './output.js';
import { renetProvisioner } from './renet-provisioner.js';
import type { LocalMachineConfig } from '../types/index.js';

/** Options for local execution */
interface LocalExecuteOptions {
  /** Function name to execute */
  functionName: string;
  /** Target machine name (must exist in local context) */
  machineName: string;
  /** Parameters to pass to the function */
  params?: Record<string, unknown>;
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

/**
 * Service for executing tasks directly via renet subprocess.
 * Bypasses middleware for single-machine local deployments.
 */
class LocalExecutorService {
  /**
   * Log debug message if debug mode is enabled.
   */
  private logDebug(options: Pick<LocalExecuteOptions, 'debug'>, message: string): void {
    if (options.debug) {
      outputService.info(message);
    }
  }

  /**
   * Read SSH public key, returning empty string on failure.
   */
  private async readOptionalSSHKey(keyPath: string | undefined): Promise<string> {
    if (!keyPath) {
      return '';
    }
    return this.readSSHKey(keyPath).catch(() => '');
  }

  /**
   * Provision renet binary to remote machine if running as SEA.
   * Returns the remote path to use for execution.
   */
  private async provisionRenetIfNeeded(
    config: { renetPath: string },
    machine: LocalMachineConfig,
    sshPrivateKey: string,
    options: Pick<LocalExecuteOptions, 'debug'>
  ): Promise<string> {
    if (!isSEA()) {
      return config.renetPath;
    }

    const provisionResult = await renetProvisioner.provision({
      host: machine.ip,
      port: machine.port ?? DEFAULTS.SSH.PORT,
      username: machine.user,
      privateKey: sshPrivateKey,
    });

    if (!provisionResult.success) {
      throw new Error(provisionResult.error ?? PROCESS_DEFAULTS.RENET_PROVISION_ERROR);
    }

    if (provisionResult.action === 'uploaded') {
      this.logDebug(
        options,
        `[local] Provisioned renet (${provisionResult.arch}) to ${machine.ip}`
      );
    }

    return provisionResult.remotePath;
  }

  /**
   * Execute a function on a machine in local mode.
   * Spawns renet execute subprocess with vault JSON.
   */
  async execute(options: LocalExecuteOptions): Promise<LocalExecuteResult> {
    const startTime = Date.now();

    try {
      // Get local config from context
      const config = await contextService.getLocalConfig();
      const machine = await contextService.getLocalMachine(options.machineName);

      this.logDebug(
        options,
        `[local] Executing '${options.functionName}' on ${options.machineName}`
      );

      // Read SSH keys
      const sshPrivateKey = await this.readSSHKey(config.ssh.privateKeyPath);
      const sshPublicKey = await this.readOptionalSSHKey(config.ssh.publicKeyPath);

      // Read known_hosts from system (fallback to empty if not found)
      const knownHostsPath = path.join(os.homedir(), '.ssh', 'known_hosts');
      const sshKnownHosts = await fs.readFile(knownHostsPath, 'utf-8').catch(() => '');

      // Build vault JSON for renet execute
      const vault = this.buildLocalVault({
        functionName: options.functionName,
        machineName: options.machineName,
        machine,
        sshPrivateKey,
        sshPublicKey,
        sshKnownHosts,
        params: options.params ?? {},
      });

      // Provision renet to remote if running as SEA
      const renetPath = await this.provisionRenetIfNeeded(config, machine, sshPrivateKey, options);

      // Spawn renet execute
      const result = await this.spawnRenet(renetPath, vault, options);

      return {
        success: result.exitCode === 0,
        exitCode: result.exitCode,
        error: result.exitCode === 0 ? undefined : `renet exited with code ${result.exitCode}`,
        durationMs: Date.now() - startTime,
      };
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
   * Build QueueVaultV2 structure for local execution.
   * This is a simplified vault without organization/team context.
   */
  private buildLocalVault(opts: {
    functionName: string;
    machineName: string;
    machine: LocalMachineConfig;
    sshPrivateKey: string;
    sshPublicKey: string;
    sshKnownHosts: string;
    params: Record<string, unknown>;
  }): string {
    const vault = {
      $schema: 'queue-vault-v2',
      version: '2.0',
      task: {
        function: opts.functionName,
        machine: opts.machineName,
        team: 'local',
        repository: (opts.params.repository ?? '') as string,
      },
      ssh: {
        private_key: opts.sshPrivateKey,
        public_key: opts.sshPublicKey,
        known_hosts: opts.sshKnownHosts,
        password: '',
      },
      machine: {
        ip: opts.machine.ip,
        user: opts.machine.user,
        port: opts.machine.port ?? DEFAULTS.SSH.PORT,
        datastore: opts.machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
        known_hosts: '',
      },
      params: opts.params,
      extra_machines: {},
      storage_systems: {},
      repository_credentials: {},
      repositories: {},
      context: {
        organization_id: '',
        api_url: '',
        universal_user_id: '7111',
        universal_user_name: 'rediacc',
      },
    };

    return JSON.stringify(vault);
  }

  /**
   * Spawn renet execute process and stream output.
   */
  private async spawnRenet(
    renetPath: string,
    vault: string,
    options: LocalExecuteOptions
  ): Promise<{ exitCode: number }> {
    return new Promise((resolve, reject) => {
      const args = ['execute', '--vault', vault];

      if (options.debug) {
        args.push('--debug');
      }
      if (options.json) {
        args.push('--json');
      }

      const timeout = options.timeout ?? 10 * 60 * 1000; // 10 minutes default

      if (options.debug) {
        outputService.info(`[local] Spawning: ${renetPath} execute ...`);
      }

      const child: ChildProcess = spawn(renetPath, args, {
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env },
      });

      // Set timeout
      const timeoutId = setTimeout(() => {
        child.kill('SIGTERM');
        reject(new Error(`Execution timed out after ${timeout}ms`));
      }, timeout);

      // Stream stdout
      child.stdout?.on('data', (data: Buffer) => {
        const text = data.toString();
        // Output each line
        text.split('\n').forEach((line) => {
          if (line.trim()) {
            // eslint-disable-next-line no-console
            console.log(line);
          }
        });
      });

      // Stream stderr
      child.stderr?.on('data', (data: Buffer) => {
        const text = data.toString();
        text.split('\n').forEach((line) => {
          if (line.trim()) {
            console.error(line);
          }
        });
      });

      child.on('close', (code) => {
        clearTimeout(timeoutId);
        resolve({ exitCode: code ?? 1 });
      });

      child.on('error', (err) => {
        clearTimeout(timeoutId);
        reject(new Error(`Failed to spawn renet: ${err.message}`));
      });
    });
  }

  /**
   * Read SSH key from filesystem.
   * Expands ~ to home directory.
   */
  private async readSSHKey(keyPath: string): Promise<string> {
    const expandedPath = keyPath.startsWith('~')
      ? path.join(os.homedir(), keyPath.slice(1))
      : keyPath;

    try {
      const content = await fs.readFile(expandedPath, 'utf-8');
      return content;
    } catch (error) {
      throw new Error(`Failed to read SSH key from ${expandedPath}: ${error}`);
    }
  }

  /**
   * Check if renet binary is available.
   */
  async checkRenetAvailable(): Promise<boolean> {
    try {
      const config = await contextService.getLocalConfig();
      return new Promise((resolve) => {
        const child = spawn(config.renetPath, ['version'], {
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
