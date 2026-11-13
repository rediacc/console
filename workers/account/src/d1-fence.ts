import { writesFrozenError } from '../../../private/account/src/errors.js';

/**
 * The D1 write fence (agent/plans/PLAN-d1-eu-jurisdiction.md, Design 2).
 *
 * While table `_write_fence` (private/account/drizzle/0086_write_fence.sql) holds
 * its one row, the D1 handle this module wraps refuses every statement but a read
 * with 503 WRITES_FROZEN. The fence lives in the database itself, so every Worker
 * version still bound to that database refuses writes too. An isolate trusts its
 * last lookup for FENCE_TTL_MS, so one that read "unfenced" just before the row was
 * inserted can still commit for up to FENCE_TTL_MS: a copy misses nothing once
 * FENCE_TTL_MS has passed since the fence went up. Reads (`SELECT`, `WITH ... SELECT`, `VALUES`, `EXPLAIN`,
 * a read-only `PRAGMA`) pass without a lookup; a write looks the fence up, cached
 * per isolate for FENCE_TTL_MS. A database without the table (the migration not yet
 * applied) counts as unfenced. Every entry of workers/account wraps `env.DB` here:
 * fetch, the two named entrypoints, scheduled and queue in index.ts, and the
 * BackupReplicator constructor in backup-replicator.ts.
 */

/** How long one isolate trusts a fence lookup. */
export const FENCE_TTL_MS = 10_000;

/** How far a BackupReplicator alarm that found the fence up moves itself. */
export const FENCE_ALARM_DELAY_MS = 300_000;

const FENCE_PROBE = 'SELECT 1 AS fenced FROM _write_fence LIMIT 1';

/** PRAGMAs that may take a parenthesised argument and still only read. */
const READING_PRAGMA_CALLS = new Set([
  'TABLE_INFO',
  'TABLE_XINFO',
  'TABLE_LIST',
  'INDEX_LIST',
  'INDEX_INFO',
  'INDEX_XINFO',
  'FOREIGN_KEY_LIST',
  'FOREIGN_KEY_CHECK',
  'INTEGRITY_CHECK',
  'QUICK_CHECK',
]);

/** PRAGMAs that write even without an `=` argument. */
const WRITING_PRAGMAS = new Set([
  'OPTIMIZE',
  'INCREMENTAL_VACUUM',
  'WAL_CHECKPOINT',
  'SHRINK_MEMORY',
]);

/** The main-statement keywords that can follow a WITH clause. */
const MAIN_KEYWORDS = new Set(['SELECT', 'VALUES', 'INSERT', 'UPDATE', 'DELETE', 'REPLACE']);

const PAREN_DEPTH: Record<string, number> = { '(': 1, ')': -1 };

const QUOTE_CLOSERS: Record<string, string> = { "'": "'", '"': '"', '`': '`', '[': ']' };

/** The index just past the comment opening at `i`, or -1 when none opens there. */
function skipComment(sql: string, i: number): number {
  if (sql.startsWith('--', i)) {
    const end = sql.indexOf('\n', i);
    return end === -1 ? sql.length : end + 1;
  }
  if (sql.startsWith('/*', i)) {
    const end = sql.indexOf('*/', i + 2);
    return end === -1 ? sql.length : end + 2;
  }
  return -1;
}

/** The index just past the quoted string or identifier opening at `i`. */
function skipQuoted(sql: string, i: number, close: string): number {
  let j = i + 1;
  while (j < sql.length) {
    if (sql[j] !== close) j++;
    // A doubled quote is an escaped quote inside the literal.
    else if (close !== ']' && sql[j + 1] === close) j += 2;
    else break;
  }
  return j + 1;
}

/** The index just past the word starting at `i`. */
function skipWord(sql: string, i: number): number {
  let j = i + 1;
  while (j < sql.length && /[A-Za-z0-9_$]/.test(sql[j] as string)) j++;
  return j;
}

/** One lexical step at `i`: where the next one starts, the token read, and the depth change. */
function scanAt(sql: string, i: number): { next: number; token: string | null; depth: number } {
  const ch = sql[i] as string;
  const afterComment = skipComment(sql, i);
  if (afterComment !== -1) return { next: afterComment, token: null, depth: 0 };
  const close = QUOTE_CLOSERS[ch];
  if (close !== undefined) return { next: skipQuoted(sql, i, close), token: 'LIT', depth: 0 };
  if (/[A-Za-z_]/.test(ch)) {
    const next = skipWord(sql, i);
    return { next, token: sql.slice(i, next).toUpperCase(), depth: 0 };
  }
  if (ch === ';' || ch === '=') return { next: i + 1, token: ch, depth: 0 };
  return { next: i + 1, token: null, depth: PAREN_DEPTH[ch] ?? 0 };
}

/**
 * The tokens of `sql` outside parentheses: upper-cased words, `;`, `=` and a `(` that opens at the top level.
 * Comments are dropped; a quoted string or identifier becomes one `LIT` token.
 */
function topLevelTokens(sql: string): string[] {
  const tokens: string[] = [];
  let depth = 0;
  let i = 0;
  while (i < sql.length) {
    const step = scanAt(sql, i);
    depth = Math.max(0, depth + step.depth);
    if (step.token !== null && depth === 0) tokens.push(step.token);
    // A parenthesis opening at the top level is kept as a token: `PRAGMA name(value)` sets as `PRAGMA name = value` does.
    if (step.depth > 0 && depth === step.depth) tokens.push('(');
    i = step.next;
  }
  return tokens;
}

/** Whether a tokenised PRAGMA only reads: no `=`, no writing name, and a parenthesised argument only on an inspection pragma. */
function pragmaReads(tokens: string[]): boolean {
  if (tokens.includes('=') || tokens.some((t) => WRITING_PRAGMAS.has(t))) return false;
  // `PRAGMA name(value)` is the other spelling of a set.
  return !tokens.includes('(') || READING_PRAGMA_CALLS.has(tokens[1] ?? '');
}

/**
 * True when `sql` cannot write: one `SELECT`, `VALUES`, `EXPLAIN`, a `WITH` whose
 * main statement is a SELECT or VALUES, or a `PRAGMA` with no `=` that is not one
 * of the writing ones. Anything else, several statements included, is a write.
 */
export function isReadOnlySql(sql: string): boolean {
  const tokens = topLevelTokens(sql);
  while (tokens.at(-1) === ';') tokens.pop();
  if (tokens.length === 0 || tokens.includes(';')) return false;
  const first = tokens[0];
  if (first === 'SELECT' || first === 'VALUES' || first === 'EXPLAIN') return true;
  if (first === 'WITH') {
    const main = tokens.slice(1).find((t) => MAIN_KEYWORDS.has(t));
    return main === 'SELECT' || main === 'VALUES';
  }
  if (first === 'PRAGMA') return pragmaReads(tokens);
  return false;
}

/** Whether `db` holds the fence row; a database without the table has no fence. */
async function probeFence(db: D1Database): Promise<boolean> {
  try {
    const { results } = await db.prepare(FENCE_PROBE).all();
    return results.length > 0;
  } catch (error) {
    // A database the fence migration has not reached yet has no fence.
    if (/no such table/i.test(error instanceof Error ? error.message : String(error))) return false;
    throw error;
  }
}

interface FenceState {
  frozen: boolean;
  checkedAt: number;
  pending: Promise<boolean> | null;
}

/** The statement shapes the wrapper passes through; a D1PreparedStatement satisfies it. */
type Statement = D1PreparedStatement;

/**
 * One isolate's view of the fence. `wrap` hands out a D1Database that refuses
 * writes while the fence is up; `frozen` and `assertWritable` answer for the
 * entries that must decide before they start (cron, queue, alarm).
 */
export class D1Fence {
  private readonly states = new WeakMap<object, FenceState>();
  private readonly raw = new WeakMap<object, D1Database>();
  /** Each handed-out statement: the driver's statement behind it, and whether it writes. */
  private readonly statements = new WeakMap<object, { inner: Statement; write: boolean }>();

  constructor(
    private readonly ttlMs: number = FENCE_TTL_MS,
    private readonly now: () => number = () => Date.now()
  ) {}

  /** The unwrapped handle behind `db` (itself when it was never wrapped). */
  unwrap(db: D1Database): D1Database {
    return this.raw.get(db) ?? db;
  }

  /** Whether the fence row is present, from the isolate cache when fresh. */
  frozen(db: D1Database): Promise<boolean> {
    const target = this.unwrap(db);
    let state = this.states.get(target);
    if (!state) {
      state = { frozen: false, checkedAt: Number.NEGATIVE_INFINITY, pending: null };
      this.states.set(target, state);
    }
    const current = state;
    if (this.now() - current.checkedAt < this.ttlMs) return Promise.resolve(current.frozen);
    if (current.pending !== null) return current.pending;
    const pending: Promise<boolean> = probeFence(target)
      .then((frozen) => {
        current.frozen = frozen;
        current.checkedAt = this.now();
        return frozen;
      })
      .finally(() => {
        if (current.pending === pending) current.pending = null;
      });
    current.pending = pending;
    return pending;
  }

  /** Throws 503 WRITES_FROZEN when the fence is up. */
  async assertWritable(db: D1Database): Promise<void> {
    if (await this.frozen(db)) throw writesFrozenError();
  }

  /** A D1Database over `db` that refuses writes while the fence is up. */
  wrap(db: D1Database): D1Database {
    if (this.raw.has(db)) return db;
    const wrapped = {
      ...this.preparer(db, db),
      exec: async (query: string) => {
        if (!isReadOnlySql(query)) await this.assertWritable(db);
        return db.exec(query);
      },
      dump: () => db.dump(),
      withSession: (constraint?: string) => {
        const session = db.withSession(constraint as never);
        return {
          ...this.preparer(db, session),
          getBookmark: () => session.getBookmark(),
        };
      },
    } as unknown as D1Database;
    this.raw.set(wrapped, db);
    return wrapped;
  }

  /** `prepare` and `batch` over `target`, fenced by the fence row of `db`. */
  private preparer(
    db: D1Database,
    target: Pick<D1Database, 'prepare' | 'batch'>
  ): Pick<D1Database, 'prepare' | 'batch'> {
    return {
      prepare: (query: string) =>
        this.fencedStatement(db, target.prepare(query), !isReadOnlySql(query)),
      batch: async <T = unknown>(statements: Statement[]): Promise<D1Result<T>[]> => {
        const known = statements.map((s) => this.statements.get(s));
        // A statement this wrapper never handed out counts as a write.
        if (known.some((k) => k === undefined || k.write)) await this.assertWritable(db);
        return target.batch<T>(statements.map((s, i) => known[i]?.inner ?? s));
      },
    };
  }

  private fencedStatement(db: D1Database, statement: Statement, write: boolean): Statement {
    const guard = async () => {
      if (write) await this.assertWritable(db);
    };
    const fenced = {
      bind: (...values: unknown[]) => this.fencedStatement(db, statement.bind(...values), write),
      first: async (column?: string) => {
        await guard();
        return column === undefined ? statement.first() : statement.first(column);
      },
      run: async () => {
        await guard();
        return statement.run();
      },
      all: async () => {
        await guard();
        return statement.all();
      },
      raw: async (options?: { columnNames?: boolean }) => {
        await guard();
        return statement.raw(options as never);
      },
    } as unknown as Statement;
    this.statements.set(fenced, { inner: statement, write });
    return fenced;
  }
}

/** The fence of this isolate. */
export const fence = new D1Fence();

const fencedEnvs = new WeakMap<object, object>();

/** `env` with its DB wrapped by `fence`, the same object for the same env. */
export function fencedEnv<E extends { DB: D1Database }>(env: E, using: D1Fence = fence): E {
  // An env with no DB binding has nothing to fence.
  if (!env.DB) return env;
  const known = fencedEnvs.get(env);
  if (known) return known as E;
  const wrapped = { ...env, DB: using.wrap(env.DB) };
  fencedEnvs.set(env, wrapped);
  fencedEnvs.set(wrapped, wrapped);
  return wrapped;
}
