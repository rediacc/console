/**
 * OpenTofu Executor
 *
 * Runs tofu CLI commands (init, apply, destroy, output) as subprocesses.
 * Each machine gets its own work directory for isolated state management.
 *
 * Engine lookup, first usable wins: `REDIACC_TOFU` (an explicit path, refused rather than skipped when unusable), the pinned OpenTofu in rdc's tools directory (`rdc tools install tofu`), `tofu` on PATH, then `terraform` on PATH. Each candidate must report a version at or above its engine's floor. rdc never installs terraform; one the user installed is accepted as found.
 */

import { type ExecFileOptions, execFile } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { chmod, mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { getCacheDir } from '@rediacc/shared/paths';
import { compareVersions } from '@rediacc/shared/utils';
import { t } from '../../i18n/index.js';
import { writeStderr, writeStdout } from '../core/request-context.js';
import { tofuInstallPath } from '../tools/install.js';
import { findOnPath } from '../tools/path-lookup.js';
import { OPENTOFU_PIN } from '../tools/pins.js';
import { PROVIDER_PINS, type ProviderPin } from './provider-pins.generated.js';
import { generateProviderLock } from './tf-generator.js';

export type TofuEngineName = 'tofu' | 'terraform';
export type TofuSource = 'env' | 'rdc' | 'path';

/**
 * Lowest accepted version per engine. OpenTofu 1.6.0 is its first stable release; Terraform 1.5 is the last MPL line and reads every construct the generators emit (JSON config with `required_providers`).
 */
const ENGINE_FLOORS: Record<TofuEngineName, string> = {
  tofu: '1.6.0',
  terraform: '1.5.0',
};

export interface TofuEngine {
  engine: TofuEngineName;
  version: string;
  path: string;
  source: TofuSource;
}

export type TofuResolution =
  | { ok: true; engine: TofuEngine }
  | { ok: false; reason: 'missing' }
  | { ok: false; reason: 'belowFloor'; engine: TofuEngine }
  | { ok: false; reason: 'overrideUnusable'; path: string };

export interface ResolveTofuDeps {
  env?: NodeJS.ProcessEnv;
  platform?: NodeJS.Platform;
  /** Path of the pinned rdc-managed binary. */
  managedPath?: string;
  findOnPath?: (command: string) => string | null;
  /** Run `<path> version`; resolve its stdout, or null when it does not run. */
  probe?: (path: string) => Promise<string | null>;
}

/** The shared provider plugin cache, one per user, under rdc's cache root. */
export function getPluginCacheDir(): string {
  return join(getCacheDir(), 'tofu-plugin-cache');
}

/** Engine and version from `tofu version` / `terraform version` output. */
export function parseEngineVersion(
  output: string
): { engine: TofuEngineName; version: string } | null {
  const m = /^(OpenTofu|Terraform) v(\d+\.\d+\.\d+)/m.exec(output);
  if (!m) return null;
  return { engine: m[1] === 'OpenTofu' ? 'tofu' : 'terraform', version: m[2] };
}

function defaultProbe(path: string): Promise<string | null> {
  return new Promise((resolve) => {
    execFile(path, ['version'], { timeout: 10_000 }, (error, stdout) =>
      resolve(error ? null : String(stdout))
    );
  });
}

function meetsFloor(engine: TofuEngineName, version: string): boolean {
  return compareVersions(version, ENGINE_FLOORS[engine]) >= 0;
}

async function inspectEngine(
  probe: (path: string) => Promise<string | null>,
  path: string,
  source: TofuSource
): Promise<TofuEngine | null> {
  const out = await probe(path);
  const parsed = out === null ? null : parseEngineVersion(out);
  return parsed ? { ...parsed, path, source } : null;
}

/** An explicit REDIACC_TOFU is used or refused, never skipped for a later candidate. */
async function resolveOverride(
  probe: (path: string) => Promise<string | null>,
  override: string
): Promise<TofuResolution> {
  const engine = await inspectEngine(probe, override, 'env');
  if (!engine) return { ok: false, reason: 'overrideUnusable', path: override };
  if (!meetsFloor(engine.engine, engine.version))
    return { ok: false, reason: 'belowFloor', engine };
  return { ok: true, engine };
}

/** Find the engine to run, without throwing. */
export function resolveTofu(deps: ResolveTofuDeps = {}): Promise<TofuResolution> {
  const env = deps.env ?? process.env;
  const platform = deps.platform ?? process.platform;
  const probe = deps.probe ?? defaultProbe;
  const lookup = deps.findOnPath ?? ((cmd: string) => findOnPath(cmd, { env, platform }));

  if (env.REDIACC_TOFU) return resolveOverride(probe, env.REDIACC_TOFU);

  const managed = deps.managedPath ?? tofuInstallPath(OPENTOFU_PIN.version, { platform });
  const onPath = ['tofu', 'terraform'].map(lookup).filter((p): p is string => p !== null);
  return firstUsable(probe, [
    { path: managed, source: 'rdc' },
    ...onPath.map((path) => ({ path, source: 'path' as const })),
  ]);
}

/** The first candidate at or above its floor; else the first one below it; else missing. */
async function firstUsable(
  probe: (path: string) => Promise<string | null>,
  candidates: { path: string; source: TofuSource }[]
): Promise<TofuResolution> {
  let firstTooOld: TofuEngine | null = null;
  for (const c of candidates) {
    const engine = await inspectEngine(probe, c.path, c.source);
    if (!engine) continue;
    if (meetsFloor(engine.engine, engine.version)) return { ok: true, engine };
    firstTooOld ??= engine;
  }
  return firstTooOld
    ? { ok: false, reason: 'belowFloor', engine: firstTooOld }
    : { ok: false, reason: 'missing' };
}

/** The user-facing message for a failed resolution; every variant names `rdc tools install tofu`. */
export function describeTofuFailure(result: Exclude<TofuResolution, { ok: true }>): string {
  switch (result.reason) {
    case 'missing':
      return t('errors.tofu.notInstalled');
    case 'belowFloor':
      return t('errors.tofu.belowFloor', {
        engine: result.engine.engine,
        version: result.engine.version,
        path: result.engine.path,
        floor: ENGINE_FLOORS[result.engine.engine],
      });
    case 'overrideUnusable':
      return t('errors.tofu.overrideUnusable', { path: result.path });
  }
}

interface ExecOptions {
  debug?: boolean;
  onStdout?: (data: string) => void;
  onStderr?: (data: string) => void;
}

export class TofuExecutor {
  private engine: TofuEngine | null = null;

  constructor(
    private readonly workDir: string,
    /** The provider pins whose lock blocks init writes; a test passes its own. */
    private readonly providerPins: Readonly<Record<string, ProviderPin>> = PROVIDER_PINS
  ) {}

  /**
   * Write main.tf.json to the work directory. The config carries the provider API token and the
   * state tofu writes beside it carries resource secrets, so the directory is 0700 and the file
   * 0600 (chmod as well, since mkdir and writeFile modes apply only on creation, and the umask can narrow them).
   */
  async writeConfig(config: Record<string, unknown>): Promise<void> {
    await mkdir(this.workDir, { recursive: true, mode: 0o700 });
    await chmod(this.workDir, 0o700);
    const file = join(this.workDir, 'main.tf.json');
    // A fresh 0600 file renamed over the old one: the token is never written into a loose file, and a
    // symlink at the target is replaced rather than followed out of the work directory.
    const tmp = join(
      this.workDir,
      `.main.tf.json.${process.pid}.${randomBytes(6).toString('hex')}`
    );
    try {
      await writeFile(tmp, JSON.stringify(config, null, 2), { mode: 0o600, flag: 'wx' });
      await chmod(tmp, 0o600);
      await rename(tmp, file);
    } catch (error) {
      await rm(tmp, { force: true });
      throw error;
    }
  }

  /** Run `tofu init`, after writing the pinned providers' lock file. */
  async init(options?: ExecOptions): Promise<void> {
    await this.writeProviderLock();
    await this.run(['init', '-input=false'], options);
  }

  /**
   * Refuse a work dir without main.tf.json under either engine (init exits 0 on an empty directory, so a
   * provision whose config was never written would otherwise pass it), then, under tofu, write
   * `.terraform.lock.hcl` for the pinned providers main.tf.json requires, replacing any lock already there
   * when one is written, so init refuses a provider package whose hash the pin does not list (from the
   * registry and from the shared plugin cache alike). The pins hash the packages registry.opentofu.org
   * serves, which is where OpenTofu resolves an unqualified source; terraform resolves the same source
   * against its own registry, so under terraform no lock is written and init locks what it fetches. With
   * no pinned provider required, nothing is written and an existing lock is left for tofu to keep or rewrite.
   */
  private async writeProviderLock(): Promise<void> {
    let raw: string;
    try {
      raw = await readFile(join(this.workDir, 'main.tf.json'), 'utf8');
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        throw new Error(t('errors.tofu.noConfig', { path: this.workDir }));
      }
      throw error;
    }
    if ((await this.getEngine()).engine !== 'tofu') return;
    const config = JSON.parse(raw) as {
      terraform?: { required_providers?: Record<string, { source?: string; version?: string }> };
    };
    const lock = generateProviderLock(
      config.terraform?.required_providers ?? {},
      this.providerPins
    );
    if (lock === null) return;
    const file = join(this.workDir, '.terraform.lock.hcl');
    const tmp = join(
      this.workDir,
      `.terraform.lock.hcl.${process.pid}.${randomBytes(6).toString('hex')}`
    );
    try {
      await writeFile(tmp, lock, { mode: 0o600, flag: 'wx' });
      await rename(tmp, file);
    } catch (error) {
      await rm(tmp, { force: true });
      throw error;
    }
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

  /** Resolve which engine to use, through the lookup order of {@link resolveTofu}. */
  private async getEngine(): Promise<TofuEngine> {
    this.engine ??= await TofuExecutor.resolveEngine();
    return this.engine;
  }

  private async getBinary(): Promise<string> {
    return (await this.getEngine()).path;
  }

  /** The engine to run; throws an i18n error naming `rdc tools install tofu`. */
  private static async resolveEngine(): Promise<TofuEngine> {
    const result = await resolveTofu();
    if (!result.ok) throw new Error(describeTofuFailure(result));
    return result.engine;
  }

  /** The absolute path of the engine to run; throws an i18n error naming `rdc tools install tofu`. */
  static async resolveBinary(): Promise<string> {
    return (await TofuExecutor.resolveEngine()).path;
  }

  /** Whether a usable tofu or terraform is available. */
  static async checkInstalled(): Promise<boolean> {
    return (await resolveTofu()).ok;
  }

  /** Environment for the engine: TF_PLUGIN_CACHE_DIR shared across work dirs, created on demand. */
  private async engineEnv(): Promise<NodeJS.ProcessEnv> {
    if (process.env.TF_PLUGIN_CACHE_DIR) return process.env;
    const cache = getPluginCacheDir();
    await mkdir(cache, { recursive: true });
    return { ...process.env, TF_PLUGIN_CACHE_DIR: cache };
  }

  private async run(args: string[], options?: ExecOptions): Promise<void> {
    const bin = await this.getBinary();
    const env = await this.engineEnv();
    return new Promise((resolve, reject) => {
      const execOpts: ExecFileOptions = {
        cwd: this.workDir,
        env,
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
            (options.onStdout ?? writeStdout)(text);
          }
        });
      }

      if (child.stderr) {
        child.stderr.on('data', (data: Buffer) => {
          const text = data.toString();
          (options?.onStderr ?? writeStderr)(text);
        });
      }
    });
  }

  private async runCapture(args: string[]): Promise<string> {
    const bin = await this.getBinary();
    const env = await this.engineEnv();
    return new Promise((resolve, reject) => {
      execFile(
        bin,
        args,
        { cwd: this.workDir, env, timeout: 30_000, maxBuffer: 10 * 1024 * 1024 },
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
