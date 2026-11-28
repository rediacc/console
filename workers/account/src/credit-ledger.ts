import { DurableObject, WorkerEntrypoint } from 'cloudflare:workers';
import {
  type AiPriceTier,
  actualCredits,
  clampMaxTokens,
  estimateInputTokens,
  findPriceRow,
  PRICE_TABLE_VERSION,
  worstCaseCredits,
} from '../../../packages/shared/src/ai-credits/index.js';

/**
 * The per-org AI credit ledger (agent/plans/PLAN-console-ai-credits.md D4 to D6, D9, D10).
 *
 * `CreditLedgerCore` is the whole decision logic over a SQLite-shaped store, with every
 * method synchronous: a Durable Object runs one synchronous stretch without interleaving, so
 * concurrent reservations are decided one after the other against the same balance and can
 * never overdraw it. The class `CreditLedger` binds the core to Durable Object storage and D1
 * (the history rows and the global pause), and `CreditLedgerGate` is the only entrypoint the
 * proxy reaches: `reserve`, `commit` and `release`. Grants, refunds and switches are methods
 * of the Durable Object that only the account Worker's own routes call.
 */

/** Concurrent streams, conversation token cap and loop depth defaults of D5. */
const DEFAULT_MAX_STREAMS = 3;
const DEFAULT_CONVERSATION_TOKEN_CAP = 200_000;
const DEFAULT_LOOP_DEPTH = 40;
/** 20 USD of credit per org per UTC day; D5 names the cap without a number. */
const DEFAULT_DAILY_CREDIT_CAP = 20_000;
/** A reservation uncommitted after this long is committed in full by the alarm (D6). */
export const RESERVATION_TTL_MS = 10 * 60 * 1000;
/** How long after a failed history write the alarm retries the rows still waiting (the outbox). */
export const HISTORY_RETRY_MS = 60 * 1000;
/** Outbox rows retried per flush, so one flush stays inside an invocation's subrequest budget. */
const HISTORY_FLUSH_BATCH = 25;
const HISTORY_FLUSH_MAX_MISSES = 3;
/** How long a read of the global pause (D10) is trusted. */
const PAUSE_CACHE_MS = 30 * 1000;

export interface LedgerLimits {
  maxStreams: number;
  conversationTokenCap: number;
  loopDepth: number;
  dailyCreditCap: number;
}

export const DEFAULT_LIMITS: LedgerLimits = {
  maxStreams: DEFAULT_MAX_STREAMS,
  conversationTokenCap: DEFAULT_CONVERSATION_TOKEN_CAP,
  loopDepth: DEFAULT_LOOP_DEPTH,
  dailyCreditCap: DEFAULT_DAILY_CREDIT_CAP,
};

/** The slice of the Durable Object `SqlStorage` the core uses. */
export interface LedgerSql {
  exec(query: string, ...bindings: unknown[]): { toArray(): Record<string, unknown>[] };
}

type RefusalCode =
  | 'PLAN_NOT_ENTITLED'
  | 'ORG_BLOCKED'
  | 'GLOBAL_PAUSED'
  | 'MODEL_NOT_ALLOWED'
  | 'INSUFFICIENT_CREDITS'
  | 'DAILY_CAP'
  | 'TOO_MANY_STREAMS'
  | 'CONVERSATION_TOKEN_CAP'
  | 'LOOP_DEPTH';

export interface ReserveRequest {
  reservationId: string;
  userId: string;
  conversationId: string;
  model: string;
  bodyBytes: number;
  maxTokens?: number;
}

export type ReserveAnswer =
  | { ok: true; reservationId: string; credits: number; maxTokens: number; priceVersion: number }
  | { ok: false; code: RefusalCode };

export interface TokenCounts {
  promptTokens: number;
  completionTokens: number;
}

/** One committed change, as `ai_credit_ledger` takes it (private/account/src/db/schema.ts). */
export interface HistoryRow {
  kind: 'commit';
  credits: number;
  lotId: string | null;
  reservationId: string;
  userId: string;
  conversationId: string;
  model: string;
  tier: AiPriceTier;
  inputTokens: number;
  outputTokens: number;
  priceVersion: number;
  createdAt: string;
}

export type CommitAnswer =
  | { ok: true; charged: number; balance: number; history: HistoryRow }
  | { ok: false; code: 'RESERVATION_UNKNOWN' };

export interface GrantLot {
  id: string;
  credits: number;
  expiresAt: string;
  paymentReference: string;
}

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS lots (id TEXT PRIMARY KEY, credits_granted INTEGER NOT NULL, credits_remaining INTEGER NOT NULL, expires_at TEXT NOT NULL, payment_reference TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, credits INTEGER NOT NULL, user_id TEXT NOT NULL, conversation_id TEXT NOT NULL, model TEXT NOT NULL, tier TEXT NOT NULL, est_tokens INTEGER NOT NULL, price_version INTEGER NOT NULL, created_ms INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS daily (day TEXT PRIMARY KEY, credits INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, tokens INTEGER NOT NULL, calls INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS history_outbox (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, row_json TEXT NOT NULL)`,
] as const;

function validUsage(usage: TokenCounts | undefined): usage is TokenCounts {
  return (
    usage !== undefined &&
    Number.isInteger(usage.promptTokens) &&
    Number.isInteger(usage.completionTokens) &&
    usage.promptTokens >= 0 &&
    usage.completionTokens >= 0
  );
}

function num(value: unknown): number {
  return typeof value === 'number' ? value : Number(value ?? 0);
}

export class CreditLedgerCore {
  constructor(
    private readonly sql: LedgerSql,
    private readonly limits: LedgerLimits = DEFAULT_LIMITS
  ) {
    for (const statement of SCHEMA) this.sql.exec(statement);
    // Lots written before grant() normalised expiry may hold a raw '...:00Z'; rewrite them to the toISOString form the string comparison needs.
    this.sql.exec(
      "UPDATE lots SET expires_at = strftime('%Y-%m-%dT%H:%M:%fZ', expires_at) WHERE expires_at NOT GLOB '*.[0-9][0-9][0-9]Z' AND strftime('%Y-%m-%dT%H:%M:%fZ', expires_at) IS NOT NULL"
    );
  }

  private one(query: string, ...bindings: unknown[]): Record<string, unknown> | undefined {
    return this.sql.exec(query, ...bindings).toArray()[0];
  }

  private flag(key: string): boolean {
    return this.one('SELECT value FROM meta WHERE key = ?', key)?.value === '1';
  }

  private setFlag(key: string, on: boolean): void {
    this.sql.exec('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', key, on ? '1' : '0');
  }

  setEntitled(on: boolean): void {
    this.setFlag('entitled', on);
  }

  setBlocked(on: boolean): void {
    this.setFlag('blocked', on);
  }

  /** Credits of unexpired lots, before open reservations. */
  private lotCredits(nowIso: string): number {
    return num(
      this.one(
        'SELECT COALESCE(SUM(credits_remaining), 0) AS c FROM lots WHERE expires_at > ?',
        nowIso
      )?.c
    );
  }

  private reservedCredits(): number {
    return num(this.one('SELECT COALESCE(SUM(credits), 0) AS c FROM reservations')?.c);
  }

  /** Available balance: unexpired lots minus open reservations. */
  balance(nowIso: string): number {
    return Math.max(0, this.lotCredits(nowIso) - this.reservedCredits());
  }

  /** Adds a lot; a repeated id changes nothing, so a retried grant never doubles. */
  grant(lot: GrantLot): void {
    if (!Number.isInteger(lot.credits) || lot.credits < 1) {
      throw new RangeError(
        `a lot grants a whole number of credits of at least 1, got ${lot.credits}`
      );
    }
    // Expiry is compared as a string against toISOString() output, so it is stored in that one form: '...:00Z' without milliseconds would sort after the same-second now.
    const expires = new Date(lot.expiresAt);
    if (Number.isNaN(expires.getTime())) {
      throw new RangeError(`a lot expires at a valid timestamp, got ${lot.expiresAt}`);
    }
    this.sql.exec(
      'INSERT OR IGNORE INTO lots (id, credits_granted, credits_remaining, expires_at, payment_reference) VALUES (?, ?, ?, ?, ?)',
      lot.id,
      lot.credits,
      lot.credits,
      expires.toISOString(),
      lot.paymentReference
    );
  }

  /**
   * Zeroes the unused part of an unexpired lot and returns it. Refused with null when the lot is
   * unknown or expired, or when open reservations hold part of the balance it would take.
   */
  refundLot(lotId: string, nowIso: string): number | null {
    const lot = this.one(
      'SELECT credits_remaining AS r, expires_at AS e FROM lots WHERE id = ?',
      lotId
    );
    if (!lot || String(lot.e) <= nowIso) return null;
    const unused = num(lot.r);
    if (this.balance(nowIso) < unused) return null;
    this.sql.exec('UPDATE lots SET credits_remaining = 0 WHERE id = ?', lotId);
    return unused;
  }

  /**
   * Adds `credits` back to an unexpired lot (the reconcile's correction toward the gateway's real
   * cost) and returns the credits applied: 0 for an unknown or expired lot or a non-positive or
   * fractional amount, which the reconcile reads as definitive. The amount is not keyed, so the
   * caller owns once-only delivery; a repeated call adds again.
   */
  adjustLot(lotId: string, credits: number, nowIso: string): number {
    if (!Number.isInteger(credits) || credits < 1) return 0;
    const lot = this.one('SELECT expires_at AS e FROM lots WHERE id = ?', lotId);
    if (!lot || String(lot.e) <= nowIso) return 0;
    this.sql.exec(
      'UPDATE lots SET credits_remaining = credits_remaining + ? WHERE id = ?',
      credits,
      lotId
    );
    return credits;
  }

  /**
   * Zeroes the unused credits of a lapsed (expired) lot and returns what it held. Idempotent: a
   * second call finds nothing and returns 0, and an unknown lot or one still unexpired returns 0
   * and changes nothing.
   */
  lapseLot(lotId: string, nowIso: string): number {
    const lot = this.one(
      'SELECT credits_remaining AS r, expires_at AS e FROM lots WHERE id = ?',
      lotId
    );
    if (!lot || String(lot.e) > nowIso) return 0;
    const held = num(lot.r);
    if (held > 0) this.sql.exec('UPDATE lots SET credits_remaining = 0 WHERE id = ?', lotId);
    return held;
  }

  reserve(req: ReserveRequest, nowMs: number, globalPaused: boolean): ReserveAnswer {
    const nowIso = new Date(nowMs).toISOString();
    if (!this.flag('entitled')) return { ok: false, code: 'PLAN_NOT_ENTITLED' };
    if (this.flag('blocked')) return { ok: false, code: 'ORG_BLOCKED' };
    if (globalPaused) return { ok: false, code: 'GLOBAL_PAUSED' };
    const row = findPriceRow(req.model);
    if (!row) return { ok: false, code: 'MODEL_NOT_ALLOWED' };

    const maxTokens = clampMaxTokens(req.maxTokens);
    const credits = worstCaseCredits(row, req.bodyBytes, req.maxTokens);
    const estTokens = estimateInputTokens(req.bodyBytes) + maxTokens;

    const conversation = this.one(
      'SELECT tokens, calls FROM conversations WHERE id = ?',
      req.conversationId
    );
    const convTokens = num(conversation?.tokens);
    const convCalls = num(conversation?.calls);
    if (convCalls >= this.limits.loopDepth) return { ok: false, code: 'LOOP_DEPTH' };
    if (convTokens + estTokens > this.limits.conversationTokenCap) {
      return { ok: false, code: 'CONVERSATION_TOKEN_CAP' };
    }
    const open = num(this.one('SELECT COUNT(*) AS c FROM reservations')?.c);
    if (open >= this.limits.maxStreams) return { ok: false, code: 'TOO_MANY_STREAMS' };
    const today = num(
      this.one('SELECT credits FROM daily WHERE day = ?', nowIso.slice(0, 10))?.credits
    );
    if (today + this.reservedCredits() + credits > this.limits.dailyCreditCap) {
      return { ok: false, code: 'DAILY_CAP' };
    }
    if (this.balance(nowIso) < credits) return { ok: false, code: 'INSUFFICIENT_CREDITS' };

    this.sql.exec(
      'INSERT INTO reservations (id, credits, user_id, conversation_id, model, tier, est_tokens, price_version, created_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
      req.reservationId,
      credits,
      req.userId,
      req.conversationId,
      req.model,
      row.tier,
      estTokens,
      PRICE_TABLE_VERSION,
      nowMs
    );
    this.sql.exec(
      'INSERT INTO conversations (id, tokens, calls) VALUES (?, 0, 1) ON CONFLICT(id) DO UPDATE SET calls = calls + 1',
      req.conversationId
    );
    return {
      ok: true,
      reservationId: req.reservationId,
      credits,
      maxTokens,
      priceVersion: PRICE_TABLE_VERSION,
    };
  }

  /** Frees a reservation without charging, for a call that never reached the provider. */
  release(reservationId: string): boolean {
    const found = this.one(
      'SELECT id, conversation_id AS c FROM reservations WHERE id = ?',
      reservationId
    );
    if (!found) return false;
    this.sql.exec('DELETE FROM reservations WHERE id = ?', reservationId);
    this.sql.exec(
      'UPDATE conversations SET calls = MAX(calls - 1, 0) WHERE id = ?',
      String(found.c)
    );
    return true;
  }

  /**
   * Charges the usage the stream reported, or the whole reservation when it reported none, and
   * frees the rest. Lots are consumed earliest expiry first and never below zero: what the
   * unexpired lots cannot cover is not charged.
   */
  commit(reservationId: string, usage: TokenCounts | undefined, nowMs: number): CommitAnswer {
    const nowIso = new Date(nowMs).toISOString();
    const res = this.one('SELECT * FROM reservations WHERE id = ?', reservationId);
    if (!res) return { ok: false, code: 'RESERVATION_UNKNOWN' };
    const model = String(res.model);
    const row = findPriceRow(model);
    const reserved = num(res.credits);
    // Usage the stream reported is trusted only as whole non-negative counts: a negative or fractional count would charge a negative amount and credit the daily counter back, so such a report is charged as no report, in full.
    const reported = validUsage(usage) ? usage : undefined;
    const want = reported && row ? actualCredits(row, reported) : reserved;
    this.sql.exec('DELETE FROM reservations WHERE id = ?', reservationId);

    let left = Math.min(want, this.lotCredits(nowIso));
    const charged = left;
    let firstLot: string | null = null;
    const lots = this.sql
      .exec(
        'SELECT id, credits_remaining AS r FROM lots WHERE expires_at > ? AND credits_remaining > 0 ORDER BY expires_at ASC, id ASC',
        nowIso
      )
      .toArray();
    for (const lot of lots) {
      if (left <= 0) break;
      const take = Math.min(left, num(lot.r));
      this.sql.exec(
        'UPDATE lots SET credits_remaining = credits_remaining - ? WHERE id = ?',
        take,
        String(lot.id)
      );
      firstLot ??= String(lot.id);
      left -= take;
    }

    const inputTokens = reported?.promptTokens ?? 0;
    const outputTokens = reported?.completionTokens ?? 0;
    const convTokens = reported ? inputTokens + outputTokens : num(res.est_tokens);
    this.sql.exec(
      'INSERT INTO daily (day, credits) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET credits = credits + ?',
      nowIso.slice(0, 10),
      charged,
      charged
    );
    this.sql.exec(
      'UPDATE conversations SET tokens = tokens + ? WHERE id = ?',
      convTokens,
      String(res.conversation_id)
    );
    return {
      ok: true,
      charged,
      balance: this.balance(nowIso),
      history: {
        kind: 'commit',
        credits: -charged,
        lotId: firstLot,
        reservationId,
        userId: String(res.user_id),
        conversationId: String(res.conversation_id),
        model,
        tier: String(res.tier) as AiPriceTier,
        inputTokens,
        outputTokens,
        priceVersion: num(res.price_version),
        createdAt: nowIso,
      },
    };
  }

  /** Commits in full every reservation older than the TTL (D6) and returns their history rows. */
  expireReservations(nowMs: number): HistoryRow[] {
    const stale = this.sql
      .exec('SELECT id FROM reservations WHERE created_ms <= ?', nowMs - RESERVATION_TTL_MS)
      .toArray();
    const rows: HistoryRow[] = [];
    for (const { id } of stale) {
      const answer = this.commit(String(id), undefined, nowMs);
      if (answer.ok) rows.push(answer.history);
    }
    return rows;
  }

  /** Keeps a history row whose D1 write failed, under the id it will be written with, until a retry lands it. */
  queueHistory(id: string, orgId: string, row: HistoryRow): void {
    this.sql.exec(
      'INSERT OR REPLACE INTO history_outbox (id, org_id, row_json) VALUES (?, ?, ?)',
      id,
      orgId,
      JSON.stringify(row)
    );
  }

  /** The oldest rows still waiting for their D1 write. */
  pendingHistory(limit: number): { id: string; orgId: string; row: HistoryRow }[] {
    return this.sql
      .exec('SELECT id, org_id, row_json FROM history_outbox ORDER BY rowid ASC LIMIT ?', limit)
      .toArray()
      .map((r) => ({
        id: String(r.id),
        orgId: String(r.org_id),
        row: JSON.parse(String(r.row_json)) as HistoryRow,
      }));
  }

  hasPendingHistory(): boolean {
    return this.one('SELECT 1 AS x FROM history_outbox LIMIT 1') !== undefined;
  }

  dropHistory(id: string): void {
    this.sql.exec('DELETE FROM history_outbox WHERE id = ?', id);
  }

  /** When the alarm should next fire: the oldest open reservation's expiry, or null with none open. */
  nextExpiryMs(): number | null {
    const oldest = this.one('SELECT MIN(created_ms) AS m FROM reservations')?.m;
    return oldest === null || oldest === undefined ? null : num(oldest) + RESERVATION_TTL_MS;
  }
}

export interface CreditLedgerEnv {
  DB: D1Database;
  REGION?: string;
  CREDIT_LEDGER?: DurableObjectNamespace<CreditLedger>;
}

/** The Durable Object of one org (`idFromName(orgId)`), SQLite-backed. */
export class CreditLedger extends DurableObject<CreditLedgerEnv> {
  private readonly core: CreditLedgerCore;
  private pauseCache: { at: number; paused: boolean } | undefined;

  constructor(ctx: DurableObjectState, env: CreditLedgerEnv) {
    super(ctx, env);
    this.core = new CreditLedgerCore(ctx.storage.sql as unknown as LedgerSql);
  }

  /** The global pause (D10), read from D1 with a 30 second cache. A failed read refuses: the ledger is the hard stop. */
  private async paused(nowMs: number): Promise<boolean> {
    if (this.pauseCache && nowMs - this.pauseCache.at < PAUSE_CACHE_MS)
      return this.pauseCache.paused;
    let paused = true;
    try {
      const row = await this.env.DB.prepare(
        'SELECT paused_at AS p FROM ai_credit_control WHERE id = 1'
      ).first<{
        p: string | null;
      }>();
      paused = row?.p != null;
    } catch (error) {
      console.error(`[credit-ledger] the pause lookup failed, calls refused: ${String(error)}`);
    }
    this.pauseCache = { at: nowMs, paused };
    return paused;
  }

  /** One history row into D1; false when the write failed. The id is the row's own, and an id already there is left alone, so a retry after an unseen success never doubles. */
  private async insertHistory(id: string, orgId: string, row: HistoryRow): Promise<boolean> {
    try {
      await this.env.DB.prepare(
        'INSERT OR IGNORE INTO ai_credit_ledger (id, org_id, kind, credits, lot_id, reservation_id, user_id, conversation_id, model, tier, input_tokens, output_tokens, price_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
      )
        .bind(
          id,
          orgId,
          row.kind,
          row.credits,
          row.lotId,
          row.reservationId,
          row.userId,
          row.conversationId,
          row.model,
          row.tier,
          row.inputTokens,
          row.outputTokens,
          row.priceVersion,
          row.createdAt
        )
        .run();
      return true;
    } catch (error) {
      console.error(
        `[credit-ledger] history row for ${row.reservationId} not written, kept for retry: ${String(error)}`
      );
      return false;
    }
  }

  /**
   * Retries the rows a failed write left in the outbox, oldest first. A row that fails again goes to the back of the queue, so one row D1 rejects for good cannot hold the rows behind it; the pass stops after HISTORY_FLUSH_MAX_MISSES failures in a row, which is an outage rather than a bad row.
   */
  private async flushHistory(): Promise<void> {
    let misses = 0;
    for (const { id, orgId, row } of this.core.pendingHistory(HISTORY_FLUSH_BATCH)) {
      if (await this.insertHistory(id, orgId, row)) {
        misses = 0;
        this.core.dropHistory(id);
        continue;
      }
      this.core.queueHistory(id, orgId, row);
      if (++misses >= HISTORY_FLUSH_MAX_MISSES) return;
    }
  }

  /** A charge is already applied when its row is written, so a failed write is kept in the outbox and the alarm retries it. */
  private async record(orgId: string, rows: HistoryRow[]): Promise<void> {
    await this.flushHistory();
    for (const row of rows) {
      const id = crypto.randomUUID();
      if (!(await this.insertHistory(id, orgId, row))) this.core.queueHistory(id, orgId, row);
    }
    if (this.core.hasPendingHistory()) {
      const at = Date.now() + HISTORY_RETRY_MS;
      const armed = await this.ctx.storage.getAlarm();
      if (armed === null || armed > at) await this.ctx.storage.setAlarm(at);
    }
  }

  async reserve(req: ReserveRequest): Promise<ReserveAnswer> {
    const paused = await this.paused(Date.now());
    // Synchronous from here: no other call interleaves between the checks and the insert.
    const answer = this.core.reserve(req, Date.now(), paused);
    if (answer.ok && (await this.ctx.storage.getAlarm()) === null) {
      await this.ctx.storage.setAlarm(Date.now() + RESERVATION_TTL_MS);
    }
    return answer;
  }

  async commit(orgId: string, reservationId: string, usage?: TokenCounts): Promise<CommitAnswer> {
    const answer = this.core.commit(reservationId, usage, Date.now());
    if (answer.ok) await this.record(orgId, [answer.history]);
    return answer;
  }

  release(reservationId: string): boolean {
    return this.core.release(reservationId);
  }

  grant(lot: GrantLot): void {
    this.core.grant(lot);
  }

  refundLot(lotId: string): number | null {
    return this.core.refundLot(lotId, new Date().toISOString());
  }

  adjustLot(lotId: string, credits: number): number {
    return this.core.adjustLot(lotId, credits, new Date().toISOString());
  }

  lapseLot(lotId: string): number {
    return this.core.lapseLot(lotId, new Date().toISOString());
  }

  setEntitled(on: boolean): void {
    this.core.setEntitled(on);
  }

  /** Pushed at once by the account routes when the org switch changes (D10). */
  setBlocked(on: boolean): void {
    this.core.setBlocked(on);
  }

  balance(): number {
    return this.core.balance(new Date().toISOString());
  }

  override async alarm(): Promise<void> {
    const orgId = this.ctx.id.name;
    const rows = this.core.expireReservations(Date.now());
    if (orgId) await this.record(orgId, rows);
    else await this.flushHistory();
    const expiry = this.core.nextExpiryMs();
    const retry = this.core.hasPendingHistory() ? Date.now() + HISTORY_RETRY_MS : null;
    const next = expiry !== null && retry !== null ? Math.min(expiry, retry) : (expiry ?? retry);
    if (next !== null) await this.ctx.storage.setAlarm(next);
  }
}

/** The stub of one org's ledger. An EU region keeps the object inside the EU jurisdiction, as its D1 is. */
function creditLedgerStub(env: CreditLedgerEnv, orgId: string): DurableObjectStub<CreditLedger> {
  const namespace = env.CREDIT_LEDGER;
  if (!namespace) throw new Error('CREDIT_LEDGER is not bound on this Worker');
  const scoped = env.REGION === 'eu' ? namespace.jurisdiction('eu') : namespace;
  return scoped.get(scoped.idFromName(orgId));
}

/**
 * The credit ledger as the proxy Worker reaches it, through a service binding that names
 * `entrypoint = "CreditLedgerGate"`: `reserve`, `commit` and `release`, and nothing that grants,
 * refunds or switches. The org id is the caller's pinned one (the proxy's `AiEgress` props), never
 * a request value.
 */
export class CreditLedgerGate extends WorkerEntrypoint<CreditLedgerEnv> {
  reserve(orgId: string, req: ReserveRequest): Promise<ReserveAnswer> {
    return creditLedgerStub(this.env, orgId).reserve(req);
  }

  commit(orgId: string, reservationId: string, usage?: TokenCounts): Promise<CommitAnswer> {
    return creditLedgerStub(this.env, orgId).commit(orgId, reservationId, usage);
  }

  release(orgId: string, reservationId: string): Promise<boolean> {
    return creditLedgerStub(this.env, orgId).release(reservationId);
  }
}
