import { exec } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { promisify } from 'node:util';
import { getMonorepoRoot } from './renetPath';

const execAsync = promisify(exec);

export interface RenetResolution {
  path: string;
  source: 'env' | 'source-build' | 'path';
  builtNow: boolean;
}

/**
 * Resolves and ensures renet binary availability.
 *
 * Single entry point for all renet binary concerns:
 * - Path resolution (env vars, source build, PATH)
 * - Auto-build from source when needed
 * - Validation that binary works
 */
export class RenetResolver {
  private cachedPath: string | null = null;
  private readonly monorepoRoot: string;

  /**
   * Create a RenetResolver.
   *
   * @param monorepoRoot - Optional monorepo root override. If not provided, auto-detects.
   */
  constructor(monorepoRoot?: string) {
    this.monorepoRoot = monorepoRoot ?? getMonorepoRoot();
  }

  /**
   * Get the renet binary path, building from source if needed.
   * This is the main entry point - call this and you're done.
   *
   * @throws Error if binary cannot be found or built
   */
  async ensureBinary(): Promise<RenetResolution> {
    // 1. Check env vars (CI mode) - no auto-build
    const envPath = this.getEnvPath();
    if (envPath) {
      await this.validateBinary(envPath);
      this.cachedPath = envPath;
      return { path: envPath, source: 'env', builtNow: false };
    }

    // 2. Try source build path, auto-build if needed
    const sourceResult = await this.trySourceBuild();
    if (sourceResult) {
      this.cachedPath = sourceResult.path;
      return sourceResult;
    }

    // 3. Fallback to PATH
    const pathResult = await this.trySystemPath();
    if (pathResult) {
      this.cachedPath = pathResult;
      return { path: pathResult, source: 'path', builtNow: false };
    }

    // Nothing worked
    throw this.buildNotFoundError();
  }

  /** Get cached path (only valid after ensureBinary succeeds) */
  getPath(): string {
    if (!this.cachedPath) {
      throw new Error('Call ensureBinary() first');
    }
    return this.cachedPath;
  }

  /** Get the monorepo root directory */
  getMonorepoRoot(): string {
    return this.monorepoRoot;
  }

  // === Private helpers ===

  private getEnvPath(): string | null {
    return process.env.RENET_BINARY_PATH ?? null;
  }

  private getSourceDir(): string | null {
    const renetDir = path.join(this.monorepoRoot, 'renet');
    const mainFile = path.join(renetDir, 'cmd', 'renet', 'main.go');
    return fs.existsSync(mainFile) ? renetDir : null;
  }

  private getSourceBinaryPath(): string {
    return path.join(this.monorepoRoot, 'renet', 'bin', 'renet');
  }

  private needsBuild(): boolean {
    const sourceDir = this.getSourceDir();
    if (!sourceDir) return false;

    const binaryPath = this.getSourceBinaryPath();
    if (!fs.existsSync(binaryPath)) return true;

    // Check staleness using go.mod
    const goModPath = path.join(sourceDir, 'go.mod');
    if (!fs.existsSync(goModPath)) return false;

    return fs.statSync(goModPath).mtimeMs > fs.statSync(binaryPath).mtimeMs;
  }

  private async trySourceBuild(): Promise<RenetResolution | null> {
    const sourceDir = this.getSourceDir();
    if (!sourceDir) return null;

    const binaryPath = this.getSourceBinaryPath();
    const needsBuild = this.needsBuild();

    if (needsBuild) {
      console.warn('  Building renet from source...');
      try {
        await execAsync('./go dev', { cwd: sourceDir, timeout: 120000 });
        console.warn('  ✓ Renet built successfully');
      } catch (err) {
        const error = err as { stderr?: string; message?: string };
        throw new Error(
          `Renet build failed: ${error.stderr ?? error.message}\n` +
            `Try manually: cd renet && ./go dev`
        );
      }
    }

    if (fs.existsSync(binaryPath)) {
      await this.validateBinary(binaryPath);
      return { path: binaryPath, source: 'source-build', builtNow: needsBuild };
    }

    return null;
  }

  private async trySystemPath(): Promise<string | null> {
    try {
      await execAsync('renet version', { timeout: 5000 });
      return 'renet';
    } catch {
      return null;
    }
  }

  private async validateBinary(binaryPath: string): Promise<void> {
    try {
      await execAsync(`${binaryPath} version`, { timeout: 5000 });
    } catch {
      throw new Error(`Renet binary at ${binaryPath} is not working`);
    }
  }

  private buildNotFoundError(): Error {
    const sourceDir = this.getSourceDir();
    if (sourceDir) {
      return new Error('Renet source found but build failed.\n' + 'Try: cd renet && ./go dev');
    }
    return new Error(
      'Renet binary not found.\n' +
        'Options:\n' +
        '  1. Clone submodule: git submodule update --init renet\n' +
        '  2. Set RENET_BINARY_PATH environment variable'
    );
  }
}

// Singleton for convenience
let defaultResolver: RenetResolver | null = null;

/**
 * Get the default singleton RenetResolver instance.
 */
export function getRenetResolver(): RenetResolver {
  defaultResolver ??= new RenetResolver();
  return defaultResolver;
}

/**
 * Create a new RenetResolver with custom monorepo root.
 */
export function createRenetResolver(monorepoRoot?: string): RenetResolver {
  return new RenetResolver(monorepoRoot);
}
