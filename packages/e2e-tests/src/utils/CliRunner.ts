import { execFile } from 'node:child_process';
import path from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

/**
 * CliRunner — the e2e harness's FIRST rdc-driving surface.
 *
 * Every existing suite goes through BridgeTestRunner (SSH → `sudo renet …`). The
 * two-VM `repo migrate` routing family, however, is CLI logic (config placement
 * rewrite, `config reconcile`) that renet-side tests structurally cannot cover
 * (07 §1-9). CliRunner shells the real `rdc` binary so suite 23 can drive it; it
 * is also the interface point the future examples program (07 §1-5) reuses.
 *
 * Config isolation (07 §2, the verified footgun): every invocation carries
 * `--config e2e-cli` so nothing ever touches the developer's real default config
 * (`config init` WITHOUT a name merges into ~/.config/rediacc/rediacc.json).
 */
export interface CliResult {
  code: number;
  stdout: string;
  stderr: string;
}

/** The isolated e2e config namespace — NEVER the user's default config. */
export const E2E_CLI_CONFIG = 'e2e-cli';

export class CliRunner {
  private constructor(
    private readonly bin: string,
    private readonly binPrefixArgs: string[],
    private readonly env: NodeJS.ProcessEnv
  ) {}

  /**
   * Resolve the CLI. CI installs it globally (install-cli-global.sh runs in
   * every e2e job), so prefer `rdc` on PATH there; locally fall back to the
   * built bundle via node. `E2E_CLI_BIN` overrides both.
   */
  static create(): CliRunner {
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      // License-less ops VMs (07 §2). CI shells have no agent ancestor, so the
      // REDIACC_ALLOW_* ancestry checks never trigger (07 §6).
      REDIACC_SKIP_MACHINE_ACTIVATION: '1',
      // Non-interactive: never prompt for confirmation or the master password.
      REDIACC_YES: '1',
      REDIACC_MASTER_PASSWORD: process.env.REDIACC_MASTER_PASSWORD ?? 'e2e-cli-master',
    };

    if (process.env.E2E_CLI_BIN) {
      return new CliRunner(process.env.E2E_CLI_BIN, [], env);
    }
    if (process.env.CI) {
      return new CliRunner('rdc', [], env);
    }
    // packages/e2e-tests/src/utils -> packages/cli/dist/cli-bundle.cjs
    const bundle = path.resolve(__dirname, '../../../cli/dist/cli-bundle.cjs');
    return new CliRunner(process.execPath, [bundle], env);
  }

  /** Spawn the CLI with the given argv verbatim (no --config injected). */
  private async exec(args: string[]): Promise<CliResult> {
    try {
      const { stdout, stderr } = await execFileAsync(this.bin, [...this.binPrefixArgs, ...args], {
        env: this.env,
        maxBuffer: 32 * 1024 * 1024,
      });
      return { code: 0, stdout, stderr };
    } catch (err) {
      const e = err as { code?: number; stdout?: string; stderr?: string };
      return {
        code: typeof e.code === 'number' ? e.code : 1,
        stdout: e.stdout ?? '',
        stderr: e.stderr ?? '',
      };
    }
  }

  /** Run `rdc --config e2e-cli <args>`. */
  async run(args: string[]): Promise<CliResult> {
    return this.exec(['--config', E2E_CLI_CONFIG, ...args]);
  }

  /** Run with the global `-o json` output format and JSON.parse stdout. */
  async runJson<T = unknown>(args: string[]): Promise<{ result: CliResult; json: T | undefined }> {
    const result = await this.run(['-o', 'json', ...args]);
    let json: T | undefined;
    try {
      json = JSON.parse(result.stdout.trim()) as T;
    } catch {
      json = undefined;
    }
    return { result, json };
  }

  /**
   * Create the isolated e2e-cli config (positional name — `config init` takes a
   * positional, NOT --name). Idempotent-ish: a second init on an existing named
   * config errors, which callers treat as already-initialised.
   */
  async initConfig(sshKeyPath: string): Promise<CliResult> {
    return this.exec(['config', 'init', E2E_CLI_CONFIG, '--ssh-key', sshKeyPath]);
  }

  /** Register a machine in the e2e-cli config (`machine add <name> --ip --user`). */
  async addMachine(name: string, ip: string, user: string, port = '22'): Promise<CliResult> {
    return this.run(['machine', 'add', name, '--ip', ip, '--user', user, '--port', port]);
  }
}
