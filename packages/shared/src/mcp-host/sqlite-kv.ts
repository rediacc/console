/**
 * A KV namespace over one SQLite table, shaped like the subset of the Workers KV
 * binding that `@cloudflare/workers-oauth-provider` calls: `get` (text or JSON),
 * `put` with `expirationTtl` or `expiration`, `delete`, and `list` by prefix with a
 * cursor. The Node host hands it to the library as `env.OAUTH_KV`, so the library
 * runs unmodified on both hosts (PLAN-rmcp-remote-worker.md Design 11, D53).
 *
 * The database is typed structurally so the module does not import `node:sqlite`
 * and stays loadable wherever `@rediacc/shared` is; `new DatabaseSync(path)` from
 * `node:sqlite` satisfies it, and so does any driver with the same two methods.
 */

/** The two calls the adapter makes on a SQLite connection. */
export interface SqliteKvDatabase {
  exec(sql: string): void;
  prepare(sql: string): SqliteKvStatement;
}

interface SqliteKvStatement {
  run(...params: SqliteKvParam[]): unknown;
  get(...params: SqliteKvParam[]): unknown;
  all(...params: SqliteKvParam[]): unknown[];
}

type SqliteKvParam = string | number | null;

export interface SqliteKvPutOptions {
  /** Seconds from now; Workers KV refuses less than 60, and so does this adapter. */
  expirationTtl?: number;
  /** Absolute expiry in epoch seconds. */
  expiration?: number;
}

export interface SqliteKvListOptions {
  prefix?: string;
  cursor?: string;
  limit?: number;
}

interface SqliteKvListKey {
  name: string;
  expiration?: number;
}

export type SqliteKvListResult =
  | { keys: SqliteKvListKey[]; list_complete: true; cacheStatus: null }
  | {
      keys: SqliteKvListKey[];
      list_complete: false;
      cursor: string;
      cacheStatus: null;
    };

export interface SqliteKvOptions {
  /** Table name; one table per namespace. Letters, digits and underscores only. */
  table?: string;
  /** Clock in milliseconds, injectable so expiry can be tested without waiting. */
  now?: () => number;
}

/** The floor Workers KV puts on a TTL, mirrored so both hosts refuse the same writes. */
const KV_MIN_EXPIRATION_TTL_SECONDS = 60;
const KV_MAX_LIST_LIMIT = 1000;
/** The table a namespace uses when the caller names none. */
const SQLITE_KV_DEFAULT_TABLE = 'mcp_oauth_kv';
const KV_DEFAULT_VALUE_TYPE = 'text';

interface Row {
  key: string;
  value: string;
  expires_at: number | null;
}

export class SqliteKvNamespace {
  private readonly table: string;
  private readonly now: () => number;

  constructor(
    private readonly db: SqliteKvDatabase,
    options: SqliteKvOptions = {}
  ) {
    const table = options.table ?? SQLITE_KV_DEFAULT_TABLE;
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(table)) {
      throw new TypeError(`invalid table name: ${table}`);
    }
    this.table = table;
    this.now = options.now ?? Date.now;
    db.exec(
      `CREATE TABLE IF NOT EXISTS ${table} (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at INTEGER)`
    );
  }

  private nowSeconds(): number {
    return Math.floor(this.now() / 1000);
  }

  private live(row: Row | undefined): Row | undefined {
    if (!row) return undefined;
    if (row.expires_at !== null && row.expires_at <= this.nowSeconds()) {
      this.db.prepare(`DELETE FROM ${this.table} WHERE key = ?`).run(row.key);
      return undefined;
    }
    return row;
  }

  get(key: string, options?: 'text' | { type?: 'text' }): Promise<string | null>;
  get(key: string, options: 'json' | { type: 'json' }): Promise<unknown>;
  get(key: string, options?: 'text' | 'json' | { type?: 'text' | 'json' }): Promise<unknown> {
    const type = typeof options === 'string' ? options : (options?.type ?? KV_DEFAULT_VALUE_TYPE);
    const row = this.live(
      this.db.prepare(`SELECT key, value, expires_at FROM ${this.table} WHERE key = ?`).get(key) as
        | Row
        | undefined
    );
    if (!row) return Promise.resolve(null);
    return Promise.resolve(type === 'json' ? JSON.parse(row.value) : row.value);
  }

  put(key: string, value: string, options: SqliteKvPutOptions = {}): Promise<void> {
    if (typeof value !== 'string') {
      return Promise.reject(new TypeError('SqliteKvNamespace stores string values only'));
    }
    let expiresAt: number | null = null;
    if (options.expirationTtl !== undefined) {
      if (options.expirationTtl < KV_MIN_EXPIRATION_TTL_SECONDS) {
        return Promise.reject(
          new RangeError(
            `expirationTtl must be at least ${KV_MIN_EXPIRATION_TTL_SECONDS} seconds, got ${options.expirationTtl}`
          )
        );
      }
      expiresAt = this.nowSeconds() + Math.floor(options.expirationTtl);
    } else if (options.expiration !== undefined) {
      if (options.expiration - this.nowSeconds() < KV_MIN_EXPIRATION_TTL_SECONDS) {
        return Promise.reject(
          new RangeError(
            `expiration must be at least ${KV_MIN_EXPIRATION_TTL_SECONDS} seconds in the future`
          )
        );
      }
      expiresAt = Math.floor(options.expiration);
    }
    this.db
      .prepare(
        `INSERT INTO ${this.table} (key, value, expires_at) VALUES (?, ?, ?)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at`
      )
      .run(key, value, expiresAt);
    return Promise.resolve();
  }

  delete(key: string): Promise<void> {
    this.db.prepare(`DELETE FROM ${this.table} WHERE key = ?`).run(key);
    return Promise.resolve();
  }

  list(options: SqliteKvListOptions = {}): Promise<SqliteKvListResult> {
    const prefix = options.prefix ?? '';
    const limit = Math.min(Math.max(options.limit ?? KV_MAX_LIST_LIMIT, 1), KV_MAX_LIST_LIMIT);
    const after = options.cursor ?? '';
    const rows = this.db
      .prepare(
        `SELECT key, value, expires_at FROM ${this.table}
         WHERE substr(key, 1, ?) = ? AND key > ? AND (expires_at IS NULL OR expires_at > ?)
         ORDER BY key LIMIT ?`
      )
      .all(prefix.length, prefix, after, this.nowSeconds(), limit + 1) as Row[];
    const page = rows.slice(0, limit);
    const keys = page.map((row) =>
      row.expires_at === null ? { name: row.key } : { name: row.key, expiration: row.expires_at }
    );
    if (rows.length > limit) {
      return Promise.resolve({
        keys,
        list_complete: false,
        cursor: page[page.length - 1]!.key,
        cacheStatus: null,
      });
    }
    return Promise.resolve({ keys, list_complete: true, cacheStatus: null });
  }
}
