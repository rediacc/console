/**
 * OpenTofu Executor
 *
 * Runs tofu CLI commands (init, apply, destroy, output) as subprocesses.
 * Each machine gets its own work directory for isolated state management.
 */

import { type ExecFileOptions, execFile } from 'node:child_process';
import { mkdir, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

interface ExecOptions {
  debug?: boolean;
  onStdout?: (data: string) => void;
  onStderr?: (data: string) => void;
}

export class TofuExecutor {
  private binary: string | null = null;

  constructor(private readonly workDir: string) {}

  /** Write main.tf.json to the work directory. */
  async writeConfig(config: Record<string, unknown>): Promise<void> {
    await mkdir(this.workDir, { recursive: true });
    await writeFile(join(this.workDir, 'main.tf.json'), JSON.stringify(config, null, 2));
  }

  /** Run `tofu init`. */
  async init(options?: ExecOptions): Promise<void> {
    await this.run(['init', '-input=false'], options);
  }

  /** Run `tofu apply -auto-approve -input=false`. */
  async apply(options?: ExecOptions): Promise<void> {
    await this.run(['apply', '-auto-approve', '-input=false'], options);
  }

  /** Run `tofu destroy -auto-approve -input=false`. */
  async destroy(options?: ExecOptions): Promise<void> {
    await this.run(['destroy', '-auto-approve', '-input=false'], options);
  }

  /** Run `tofu output -json` and return parsed result. */
  async getOutputs(): Promise<Record<string, { value: unknown }>> {
    const stdout = await this.runCapture(['output', '-json']);
    return JSON.parse(stdout) as Record<string, { value: unknown }>;
  }

  /** Remove the work directory (cleanup after destroy). */
  async cleanup(): Promise<void> {
    await rm(this.workDir, { recursive: true, force: true });
  }

  /** Get the work directory path. */
  getWorkDir(): string {
    return this.workDir;
  }

  /** Resolve which binary to use: tofu (preferred) or terraform (fallback). */
  private async getBinary(): Promise<string> {
    if (this.binary) return this.binary;
    this.binary = await TofuExecutor.resolveBinary();
    return this.binary;
  }

  /** Check if tofu or terraform is available on PATH. Returns the binary name or null. */
  static async resolveBinary(): Promise<string> {
    for (const bin of ['tofu', 'terraform']) {
      const found = await new Promise<boolean>((resolve) => {
        execFile(bin, ['version'], { timeout: 10_000 }, (error) => resolve(!error));
      });
      if (found) return bin;
    }
    throw new Error(
      'Neither OpenTofu (tofu) nor Terraform (terraform) is installed. Install from: https://opentofu.org/docs/intro/install/'
    );
  }

  /** Check if tofu or terraform is available on PATH. */
  static async checkInstalled(): Promise<boolean> {
    try {
      await TofuExecutor.resolveBinary();
      return true;
    } catch {
      return false;
    }
  }

  private async run(args: string[], options?: ExecOptions): Promise<void> {
    const bin = await this.getBinary();
    return new Promise((resolve, reject) => {
      const execOpts: ExecFileOptions = {
        cwd: this.workDir,
        timeout: 600_000, // 10 minutes
        maxBuffer: 10 * 1024 * 1024,
      };

      const child = execFile(bin, args, execOpts, (error) => {
        if (error) {
          reject(new Error(`${bin} ${args[0]} failed: ${error.message}`));
        } else {
          resolve();
        }
      });

      if (child.stdout) {
        child.stdout.on('data', (data: Buffer) => {
          const text = data.toString();
          if (options?.debug) {
            (options.onStdout ?? process.stdout.write.bind(process.stdout))(text);
          }
        });
      }

      if (child.stderr) {
        child.stderr.on('data', (data: Buffer) => {
          const text = data.toString();
          (options?.onStderr ?? process.stderr.write.bind(process.stderr))(text);
        });
      }
    });
  }

  private async runCapture(args: string[]): Promise<string> {
    const bin = await this.getBinary();
    return new Promise((resolve, reject) => {
      execFile(
        bin,
        args,
        { cwd: this.workDir, timeout: 30_000, maxBuffer: 10 * 1024 * 1024 },
        (error, stdout) => {
          if (error) {
            reject(new Error(`${bin} ${args[0]} failed: ${error.message}`));
          } else {
            resolve(stdout);
          }
        }
      );
    });
  }
}
