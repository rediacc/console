/**
 * What one `rdc --proxy` run learned about an executor, kept for the next run.
 *
 * Each run used to repeat server-info, a session open and a CEK unwrap and grant
 * before its one command. The executor keeps a granted session for its idle TTL
 * (30 minutes, sliding on use: packages/cli/src/services/serve/sessions.ts), so a
 * run inside that window can name the session it granted last time and skip all
 * three (Design 7 of PLAN-rmcp-executor-hardening). If the executor no longer
 * holds the session (a redeploy, an eviction), it answers 404
 * EXECUTOR_SESSION_UNKNOWN and the client re-grants once.
 *
 * The file sits beside the config tokens (`<config dir>/.tokens/`, 0600) and
 * holds no secret: a session id is useless without the bearer that granted it,
 * and the entry is keyed by a hash of (executor URL, bearer), never the bearer.
 */

import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';

/** The executor's idle session TTL; an entry older than this is never used. */
export const PROXY_SESSION_TTL_MS = 30 * 60 * 1000;

export interface ProxySessionEntry {
  /** What the executor said it is; a daemon holds its own key and is never granted one. */
  mode: 'container' | 'daemon';
  /** The session this caller granted its key through (container only). */
  sessionId?: string;
  /** Epoch ms past which the entry is stale. Slides on each command that used it. */
  expiresAt: number;
}

type CacheFile = Record<string, ProxySessionEntry>;

export interface ProxySessionCacheOptions {
  /** Defaults to `<config dir>/.tokens`. */
  dir?: string;
  now?: () => number;
}

export class ProxySessionCache {
  private readonly path: string;
  private readonly dir: string;
  private readonly now: () => number;

  constructor(options: ProxySessionCacheOptions = {}) {
    this.dir = options.dir ?? join(getConfigDir(), '.tokens');
    this.path = join(this.dir, 'proxy-sessions.json');
    this.now = options.now ?? Date.now;
  }

  /** The live entry for this executor and bearer, or undefined; a file that cannot be read is no entry. */
  async get(baseUrl: string, token: string): Promise<ProxySessionEntry | undefined> {
    const file = await this.read().catch(() => ({}) as CacheFile);
    const entry = file[keyOf(baseUrl, token)];
    return entry && entry.expiresAt > this.now() ? entry : undefined;
  }

  /**
   * Record what this run learned; the entry lives one session TTL from now. The cache only saves a
   * grant, so a file that cannot be read or written (an unwritable config dir) costs the next run a
   * fresh grant and never fails the command that already ran.
   */
  async set(baseUrl: string, token: string, entry: Omit<ProxySessionEntry, 'expiresAt'>) {
    try {
      await this.store(baseUrl, token, entry);
    } catch {
      // Best effort by design.
    }
  }

  private async store(
    baseUrl: string,
    token: string,
    entry: Omit<ProxySessionEntry, 'expiresAt'>
  ): Promise<void> {
    const file = await this.read();
    const now = this.now();
    // Stale entries are dropped on every write, so the file holds only live sessions.
    for (const [key, value] of Object.entries(file)) {
      if (value.expiresAt <= now) delete file[key];
    }
    file[keyOf(baseUrl, token)] = { ...entry, expiresAt: now + PROXY_SESSION_TTL_MS };
    await this.write(file);
  }

  /** Forget this executor and bearer's entry (the executor no longer holds the session). */
  async delete(baseUrl: string, token: string): Promise<void> {
    try {
      const file = await this.read();
      const key = keyOf(baseUrl, token);
      if (!(key in file)) return;
      delete file[key];
      await this.write(file);
    } catch {
      // Best effort: an entry that cannot be dropped expires with its TTL.
    }
  }

  private async read(): Promise<CacheFile> {
    let text: string;
    try {
      text = await fs.readFile(this.path, 'utf8');
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return {};
      throw error;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      // A torn or hand-edited file costs one fresh grant, never a failed command; the next write replaces it.
      return {};
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const file: CacheFile = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (isEntry(value)) file[key] = value;
    }
    return file;
  }

  private async write(file: CacheFile): Promise<void> {
    await fs.mkdir(this.dir, { recursive: true, mode: 0o700 });
    // Write-then-rename, so a concurrent reader never sees half a file.
    const temporary = `${this.path}.${process.pid}.${this.now()}.tmp`;
    await fs.writeFile(temporary, JSON.stringify(file), { mode: 0o600 });
    await fs.rename(temporary, this.path);
  }
}

function keyOf(baseUrl: string, token: string): string {
  return createHash('sha256').update(`${baseUrl}\u0000${token}`).digest('hex');
}

function isEntry(value: unknown): value is ProxySessionEntry {
  if (!value || typeof value !== 'object') return false;
  const entry = value as Record<string, unknown>;
  return (
    (entry.mode === 'container' || entry.mode === 'daemon') &&
    typeof entry.expiresAt === 'number' &&
    (entry.sessionId === undefined || typeof entry.sessionId === 'string')
  );
}
