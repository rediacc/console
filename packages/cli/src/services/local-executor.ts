/**
 * LocalExecutorService - Direct task execution without middleware.
 *
 * This service enables Console CLI to work directly with renet bridge
 * without going through middleware API. Used in "local mode" and "s3 mode" contexts.
 *
 * Delegates to shared utilities in renet-execution.ts.
 */

import { spawn } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { contextService } from './context.js';
import { outputService } from './output.js';
import {
  buildLocalVault,
  getLocalRenetPath,
  provisionRenetToRemote,
  readOptionalSSHKey,
  readSSHKey,
  spawnRenet,
} from './renet-execution.js';

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
   * Execute a function on a machine in local mode.
   * Spawns renet execute subprocess with vault JSON.
   */
  async execute(options: LocalExecuteOptions): Promise<LocalExecuteResult> {
    const startTime = Date.now();

    try {
      // Get local config from context
      const config = await contextService.getLocalConfig();
      const machine = await contextService.getLocalMachine(options.machineName);

      if (options.debug) {
        outputService.info(`[local] Executing '${options.functionName}' on ${options.machineName}`);
      }

      // Read SSH keys
      const sshPrivateKey = await readSSHKey(config.ssh.privateKeyPath);
      const sshPublicKey = await readOptionalSSHKey(config.ssh.publicKeyPath);

      // Read known_hosts from system (fallback to empty if not found)
      const knownHostsPath = path.join(os.homedir(), '.ssh', 'known_hosts');
      const sshKnownHosts = await fs.readFile(knownHostsPath, 'utf-8').catch(() => '');

      // Build vault JSON for renet execute
      const vault = buildLocalVault({
        functionName: options.functionName,
        machineName: options.machineName,
        machine,
        sshPrivateKey,
        sshPublicKey,
        sshKnownHosts,
        params: options.params ?? {},
      });

      // Get local renet path (dev: from config, SEA: extract to temp)
      const renetPath = await getLocalRenetPath(config);

      // Provision renet to remote machine (/usr/bin/renet)
      await provisionRenetToRemote(config, machine, sshPrivateKey, options);

      // Spawn renet execute locally
      const result = await spawnRenet(renetPath, vault, options);

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
