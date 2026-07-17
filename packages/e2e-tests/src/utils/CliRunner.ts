import { execFile } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { getRenetBinaryPath } from './renetPath';

const execFileAsync = promisify(execFile);

/**
 * Resolve the dev renet binary the CLI should deploy to the fleet, robustly.
 * The pin MUST land or the CLI resolves the host's production /usr/bin/renet
 * and deploys it fleet-wide, stripping the bridge surfaces (functions/kube/
 * ops) the very suite then queries — a bug that hid behind three different
 * failed resolution attempts (__dirname under Playwright's transform, a PATH
 * prepend the spawned CLI never honored, and the provisioning resolver's
 * fallback which points one directory too shallow). So try every channel and
 * verify the file exists:
 *   1. the harness's own resolver (correct when its singleton is initialized);
 *   2. an explicit RENET_BINARY_PATH (rdc.sh / CI export);
 *   3. walk up from cwd AND __dirname to <root>/private/renet/bin/renet.
 * Returns undefined only when none exist (CI / SEA), where the pin is moot.
 */
function resolveDevRenet(): string | undefined {
  const candidates: string[] = [];
  try {
    candidates.push(getRenetBinaryPath());
  } catch {
    // resolver not initialized in this process — fall through
  }
  if (process.env.RENET_BINARY_PATH) candidates.push(process.env.RENET_BINARY_PATH);
  for (const start of [process.cwd(), __dirname]) {
    let dir = start;
    for (let i = 0; i < 8; i++) {
      candidates.push(path.join(dir, 'private', 'renet', 'bin', 'renet'));
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  return candidates.find((c) => c && existsSync(c));
}

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
const E2E_CLI_CONFIG = 'e2e-cli';

export class CliRunner {
  private constructor(
    private readonly bin: string,
    private readonly binPrefixArgs: string[],
    private readonly env: NodeJS.ProcessEnv,
    /** Absolute dev renet to pin into the config (undefined in CI / SEA). */
    private readonly devRenetPath?: string
  ) {}

  /** Path of the isolated e2e-cli config file. */
  private static configFilePath(): string {
    return path.join(os.homedir(), '.config', 'rediacc', `${E2E_CLI_CONFIG}.json`);
  }

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
    // Pin the DEV renet for the CLI's REMOTE provisioning. The CLI resolves
    // its local renet from config.renetPath (default the bare name `renet`,
    // which becomes a PATH lookup). On a dev box PATH finds /usr/bin/renet —
    // the HOST'S installed PRODUCTION build — and the CLI's first machine
    // connection DEPLOYS that into the fleet's install slot, silently
    // replacing the dev renet the harness setup put there and breaking every
    // bridge surface the production build lacks (found live: `functions`
    // vanished fleet-wide right after suite 23's own preflight; both binaries
    // report 0.0.0-dev so the version guard never rejects the downgrade).
    //
    // The pin is an ABSOLUTE config.renetPath (written by initConfig below):
    // resolveRenetPath uses an absolute existing path DIRECTLY, with no PATH
    // lookup to lose. PATH prepend is belt-and-suspenders for any CLI path
    // that still guesses.
    const devRenetPath = resolveDevRenet();
    if (devRenetPath) {
      env.PATH = `${path.dirname(devRenetPath)}${path.delimiter}${env.PATH ?? ''}`;
    }
    return new CliRunner(process.execPath, [bundle], env, devRenetPath);
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
   * Delete the isolated e2e-cli config file. The config is FLEET-scoped, not
   * immortal: machine entries record the fleet's SSH host keys at add time, and
   * an `ops down`/`ops up` re-mints them — a config surviving the reset makes
   * every later connection fail host-key verification (found live: suite 23's
   * preflight red while the bridge-side probes were green). Callers recreate
   * from scratch each run; registration is cheap.
   */
  static async resetConfig(): Promise<void> {
    await rm(path.join(os.homedir(), '.config', 'rediacc', `${E2E_CLI_CONFIG}.json`), {
      force: true,
    });
  }

  /**
   * Create the isolated e2e-cli config (positional name — `config init` takes a
   * positional, NOT --name). Idempotent-ish: a second init on an existing named
   * config errors, which callers treat as already-initialised — but see
   * resetConfig(): a config outliving the fleet is stale, not reusable.
   */
  async initConfig(sshKeyPath: string): Promise<CliResult> {
    const result = await this.exec(['config', 'init', E2E_CLI_CONFIG, '--ssh-key', sshKeyPath]);
    // Pin the dev renet as an ABSOLUTE top-level renetPath (host-local field,
    // unencrypted per config sensitivity rules) so the CLI never PATH-guesses
    // and downgrades the fleet to the host's production binary. See create().
    if (this.devRenetPath) {
      const file = CliRunner.configFilePath();
      const cfg = JSON.parse(readFileSync(file, 'utf8')) as { renetPath?: string };
      cfg.renetPath = this.devRenetPath;
      writeFileSync(file, `${JSON.stringify(cfg, null, 2)}\n`);
    }
    return result;
  }

  /** Register a machine in the e2e-cli config (`machine add <name> --ip --user`). */
  async addMachine(name: string, ip: string, user: string, port = '22'): Promise<CliResult> {
    return this.run(['machine', 'add', name, '--ip', ip, '--user', user, '--port', port]);
  }
}
