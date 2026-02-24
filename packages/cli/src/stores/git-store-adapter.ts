import { execFile } from 'node:child_process';
import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { DEFAULTS } from '@rediacc/shared/config';
import type { IStoreAdapter, PullResult, PushResult } from './types.js';
import type { RdcConfig } from '../types/index.js';
import type { StoreEntry } from '../types/store.js';

const execFileAsync = promisify(execFile);

/**
 * Git store adapter. Stores config files in a git repository.
 * Each push/pull does a shallow clone, read/write, commit, push.
 */
export class GitStoreAdapter implements IStoreAdapter {
  private readonly gitUrl: string;
  private readonly branch: string;
  private readonly gitPath: string;

  constructor(entry: StoreEntry) {
    if (!entry.gitUrl) {
      throw new Error('Git store requires a gitUrl');
    }
    this.gitUrl = entry.gitUrl;
    this.branch = entry.gitBranch ?? DEFAULTS.STORE.GIT_BRANCH;
    this.gitPath = entry.gitPath ?? DEFAULTS.STORE.GIT_PATH;
  }

  private async withClone<T>(operation: (repoDir: string) => Promise<T>): Promise<T> {
    const workDir = await fs.mkdtemp(join(tmpdir(), 'rdc-git-store-'));
    try {
      try {
        await execFileAsync(
          'git',
          ['clone', '--depth', '1', '--branch', this.branch, this.gitUrl, workDir],
          {
            timeout: 60000,
          }
        );
      } catch {
        // Branch or repo may be empty — initialize a fresh repo with the remote
        await execFileAsync('git', ['init', '-b', this.branch, workDir], { timeout: 10000 });
        await this.git(workDir, ['remote', 'add', 'origin', this.gitUrl]);
      }
      return await operation(workDir);
    } finally {
      await fs.rm(workDir, { recursive: true, force: true }).catch(() => {});
    }
  }

  private configPath(repoDir: string, configName: string): string {
    return join(repoDir, this.gitPath, `${configName}.json`);
  }

  private async git(cwd: string, args: string[]): Promise<string> {
    const { stdout } = await execFileAsync('git', args, { cwd, timeout: 30000 });
    return stdout.trim();
  }

  async push(config: RdcConfig, configName: string): Promise<PushResult> {
    return this.withClone(async (repoDir) => {
      const filePath = this.configPath(repoDir, configName);

      // Check remote for conflict
      try {
        const content = await fs.readFile(filePath, 'utf-8');
        const remote = JSON.parse(content) as RdcConfig;
        if (remote.id !== config.id) {
          return {
            success: false,
            error: `GUID mismatch: local config id "${config.id}" does not match remote "${remote.id}".`,
          };
        }
        if (remote.version > config.version) {
          return {
            success: false,
            error: `Version conflict: remote version ${remote.version} is newer than local version ${config.version}. Run "rdc store pull" first.`,
          };
        }
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
      }

      await fs.mkdir(join(repoDir, this.gitPath), { recursive: true });
      await fs.writeFile(filePath, JSON.stringify(config, null, 2));
      await this.git(repoDir, ['add', filePath]);
      await this.git(repoDir, ['commit', '-m', `Update config ${configName} v${config.version}`]);
      await this.git(repoDir, ['push', 'origin', this.branch]);

      return { success: true, remoteVersion: config.version };
    });
  }

  async pull(configName: string): Promise<PullResult> {
    return this.withClone(async (repoDir) => {
      const filePath = this.configPath(repoDir, configName);
      try {
        const content = await fs.readFile(filePath, 'utf-8');
        const config = JSON.parse(content) as RdcConfig;
        return { success: true, config };
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
          return { success: false, error: `Config "${configName}" not found in git store` };
        }
        throw error;
      }
    });
  }

  async list(): Promise<string[]> {
    return this.withClone(async (repoDir) => {
      const configDir = join(repoDir, this.gitPath);
      try {
        const files = await fs.readdir(configDir);
        return files
          .filter((f) => f.endsWith('.json'))
          .map((f) => f.replace(/\.json$/, ''))
          .sort();
      } catch {
        return [];
      }
    });
  }

  async delete(configName: string): Promise<PushResult> {
    return this.withClone(async (repoDir) => {
      const filePath = this.configPath(repoDir, configName);
      try {
        await fs.unlink(filePath);
        await this.git(repoDir, ['add', filePath]);
        await this.git(repoDir, ['commit', '-m', `Delete config ${configName}`]);
        await this.git(repoDir, ['push', 'origin', this.branch]);
        return { success: true };
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
          return { success: false, error: `Config "${configName}" not found in git store` };
        }
        throw error;
      }
    });
  }

  async verify(): Promise<boolean> {
    try {
      // ls-remote without --exit-code succeeds even for empty repos
      await execFileAsync('git', ['ls-remote', this.gitUrl], { timeout: 15000 });
      return true;
    } catch {
      return false;
    }
  }
}
