import { spawn } from 'node:child_process';
import type { CommandResult } from '../types';

/**
 * OpsCommandRunner - Executes renet ops commands
 *
 * Handles command execution with proper output streaming and timeout handling.
 */
export class OpsCommandRunner {
  constructor(
    private readonly renetBin: string,
    private readonly renetDir: string
  ) {}

  /**
   * Run a renet ops command
   */
  async run(
    subcommands: string[],
    args: string[] = [],
    timeoutMs = 300000
  ): Promise<CommandResult> {
    return this.runWithEnv(subcommands, args, {}, timeoutMs);
  }

  /**
   * Run a renet ops command with additional environment variables
   */
  async runWithEnv(
    subcommands: string[],
    args: string[] = [],
    extraEnv: Record<string, string> = {},
    timeoutMs = 300000
  ): Promise<CommandResult> {
    return new Promise((resolve) => {
      const allArgs = ['ops', ...subcommands, ...args];
      const fullCommand = `${this.renetBin} ${allArgs.join(' ')}`.trim();
      console.warn(`[OpsCommandRunner] Running: ${fullCommand}`);

      const childProcess = spawn(this.renetBin, allArgs, {
        cwd: this.renetDir,
        shell: false,
        env: { ...process.env, ...extraEnv },
      });

      let stdout = '';
      let stderr = '';

      childProcess.stdout.on('data', (data: Buffer) => {
        stdout += data.toString();
        console.error(`[renet] ${data.toString().trim()}`);
      });

      childProcess.stderr.on('data', (data: Buffer) => {
        stderr += data.toString();
        console.error(`[renet:err] ${data.toString().trim()}`);
      });

      const timeout = setTimeout(() => {
        // SIGTERM here is not the end of the story on the renet side: `ops up`
        // cancels its root context on SIGTERM (cmd/renet/ops_up.go), and every
        // ssh/scp it has in flight is an exec.CommandContext, which Go kills
        // with SIGKILL. The operator-visible wreckage is therefore an
        // unrelated-looking "ssh command failed: signal: killed" deep inside
        // whatever step happened to be running. Say plainly, here, that WE
        // killed it and after how long.
        childProcess.kill('SIGTERM');
        resolve({
          stdout,
          stderr: `${stderr}\nTimeout exceeded: killed after ${(timeoutMs / 1000).toFixed(0)}s`,
          code: -1,
          timedOut: true,
        });
      }, timeoutMs);

      childProcess.on('close', (code: number | null) => {
        clearTimeout(timeout);
        resolve({ stdout, stderr, code: code ?? 0 });
      });

      childProcess.on('error', (err: Error) => {
        clearTimeout(timeout);
        resolve({ stdout, stderr: err.message, code: -1 });
      });
    });
  }
}
