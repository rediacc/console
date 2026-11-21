import { DurableObject } from 'cloudflare:workers';

import { CONFIG, ingestMaxAgeHours, type OpsHealthConfig } from './config';
import type { Env } from './env';
import type { ProbeResult } from './probes';
import type { TriState } from './targets';

/**
 * The `OpsState` Durable Object of D-record: one SQLite-backed instance (`idFromName("state")`) holding three keys, `alerts`, `ingest` and `targets`. Every read-modify-write runs through one promise chain, so a cron run and an ingest POST that overlap are applied one after the other and neither write is lost. The object does no network I/O; mail is sent by the Worker, which reports back through `markMailed`.
 */

export interface StorageLike {
  get<T>(key: string): Promise<T | undefined>;
  put<T>(key: string, value: T): Promise<void>;
}

export interface ProbeRecord {
  kind: string;
  state: TriState;
  since: string;
  checked_at: string;
  /** How many consecutive runs answered `raw`. */
  consecutive: number;
  raw: TriState;
  detail: string;
  last_mailed_at: string | null;
  /** The state the last mail reported; a confirmed state that differs from it is an unmailed transition. */
  mailed_state: TriState | null;
}

export interface MailLogEntry {
  at: string;
  kind: 'alert' | 'digest';
  probes: string[];
  message_id: string;
}

export interface CtCacheEntry {
  not_after: string | null;
  source: string;
  at: string;
}

export interface AlertsDoc {
  last_cron_at: string | null;
  probes: Record<string, ProbeRecord>;
  mail_log: MailLogEntry[];
  ct_cache: Record<string, CtCacheEntry>;
  last_digest_at: string | null;
  last_mail_error: { at: string; detail: string } | null;
}

export interface IngestRecord {
  state: TriState;
  at: string;
  detail: string;
  received_at: string;
  last_mailed_at: string | null;
  mailed_state: TriState | null;
}

export interface IngestDoc {
  [source: string]: IngestRecord;
}

export interface TargetsDoc {
  sha: string | null;
  probe_count: number;
  loaded_at: string;
}

export interface IngestInput {
  source: string;
  state: TriState;
  detail: string;
  at: string;
}

export type DueReason = 'red' | 'still-red' | 'recovered';

export interface DueItem {
  origin: 'probe' | 'ingest';
  id: string;
  state: TriState;
  reason: DueReason;
  detail: string;
}

export interface RunInput {
  at: string;
  results: ProbeResult[];
  targets: { sha: string | null; probe_count: number };
  ct?: Record<string, CtCacheEntry>;
}

export interface StatusView {
  last_cron_at: string | null;
  targets_sha: string | null;
  probes: Array<{
    probe: string;
    state: TriState;
    since: string;
    checked_at: string;
    detail: string;
  }>;
  ingest: Array<{ source: string; state: TriState; at: string; detail: string }>;
  verdict: TriState;
  mail_log?: MailLogEntry[];
  last_mail_error?: { at: string; detail: string } | null;
}

const HOUR_MS = 3_600_000;

function emptyAlerts(): AlertsDoc {
  return {
    last_cron_at: null,
    probes: {},
    mail_log: [],
    ct_cache: {},
    last_digest_at: null,
    last_mail_error: null,
  };
}

/**
 * One probe's next record under D-mail: red after `to_red` consecutive red runs, back to green after `to_green` green runs; a new probe takes a green or unknown answer at once and still needs `to_red` runs to turn red; any other change needs `to_red` consecutive answers.
 */
/** How many consecutive `raw` answers move a probe out of `prev.state`. */
function runsNeeded(prev: ProbeRecord, raw: TriState, config: OpsHealthConfig): number {
  if (raw !== 'green') return config.transitions.to_red;
  if (prev.state === 'red') return config.transitions.to_green;
  // unknown -> green: at once, unless the last mail said red, which a recovery must earn.
  return prev.mailed_state === 'red' ? config.transitions.to_green : 1;
}

function firstState(raw: TriState, config: OpsHealthConfig): TriState {
  return raw === 'red' && config.transitions.to_red > 1 ? 'unknown' : raw;
}

export function step(
  prev: ProbeRecord | undefined,
  result: ProbeResult,
  at: string,
  config: OpsHealthConfig = CONFIG
): ProbeRecord {
  const raw = result.state;
  if (!prev) {
    const state = firstState(raw, config);
    return {
      kind: result.kind,
      state,
      since: at,
      checked_at: at,
      consecutive: 1,
      raw,
      detail: result.detail,
      last_mailed_at: null,
      mailed_state: null,
    };
  }
  const consecutive = prev.raw === raw ? prev.consecutive + 1 : 1;
  const moves = raw !== prev.state && consecutive >= runsNeeded(prev, raw, config);
  const state = moves ? raw : prev.state;
  return {
    ...prev,
    kind: result.kind,
    state,
    since: moves ? at : prev.since,
    checked_at: at,
    consecutive,
    raw,
    detail: result.detail,
  };
}

function dueReason(
  state: TriState,
  mailed: TriState | null,
  lastMailedAt: string | null,
  now: number,
  config: OpsHealthConfig
): DueReason | null {
  if (state === 'red') {
    if (mailed !== 'red') return 'red';
    const last = lastMailedAt ? Date.parse(lastMailedAt) : 0;
    return now - last >= config.transitions.remail_hours * HOUR_MS ? 'still-red' : null;
  }
  if (state === 'green' && mailed === 'red') return 'recovered';
  return null;
}

function ingestFresh(
  source: string,
  record: IngestRecord,
  now: number,
  config: OpsHealthConfig
): boolean {
  const at = Date.parse(record.at);
  return !Number.isNaN(at) && now - at <= ingestMaxAgeHours(source, config) * HOUR_MS;
}

export class OpsStateCore {
  private chain: Promise<unknown> = Promise.resolve();

  constructor(
    private readonly storage: StorageLike,
    private readonly config: OpsHealthConfig = CONFIG
  ) {}

  /** Runs `fn` after every earlier call has finished, so read-modify-writes never interleave. */
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.chain.then(fn, fn);
    this.chain = run.catch(() => undefined);
    return run;
  }

  private async alerts(): Promise<AlertsDoc> {
    return { ...emptyAlerts(), ...((await this.storage.get<AlertsDoc>('alerts')) ?? {}) };
  }

  private async ingestDoc(): Promise<IngestDoc> {
    return (await this.storage.get<IngestDoc>('ingest')) ?? {};
  }

  /** Applies one cron run's results and answers the transitions that are due a mail now. Probes absent from the run (a removed target) are dropped. */
  applyRun(input: RunInput): Promise<DueItem[]> {
    return this.serial(async () => {
      const alerts = await this.alerts();
      const probes: Record<string, ProbeRecord> = {};
      for (const result of input.results) {
        probes[result.id] = step(alerts.probes[result.id], result, input.at, this.config);
      }
      alerts.probes = probes;
      alerts.last_cron_at = input.at;
      if (input.ct) alerts.ct_cache = { ...alerts.ct_cache, ...input.ct };
      await this.storage.put('alerts', alerts);
      await this.storage.put<TargetsDoc>('targets', {
        sha: input.targets.sha,
        probe_count: input.targets.probe_count,
        loaded_at: input.at,
      });
      return this.due(alerts, await this.ingestDoc(), Date.parse(input.at));
    });
  }

  private due(alerts: AlertsDoc, ingest: IngestDoc, now: number): DueItem[] {
    const out: DueItem[] = [];
    for (const [id, record] of Object.entries(alerts.probes)) {
      const reason = dueReason(
        record.state,
        record.mailed_state,
        record.last_mailed_at,
        now,
        this.config
      );
      if (reason)
        out.push({ origin: 'probe', id, state: record.state, reason, detail: record.detail });
    }
    for (const [source, record] of Object.entries(ingest)) {
      if (record.state === 'red' && !ingestFresh(source, record, now, this.config)) continue;
      const reason = dueReason(
        record.state,
        record.mailed_state,
        record.last_mailed_at,
        now,
        this.config
      );
      if (reason)
        out.push({
          origin: 'ingest',
          id: source,
          state: record.state,
          reason,
          detail: record.detail,
        });
    }
    return out;
  }

  /** Records a sent mail: each item's state becomes its mailed state, and the send is logged with its SES MessageId. */
  markMailed(
    items: DueItem[],
    at: string,
    messageId: string,
    kind: 'alert' | 'digest'
  ): Promise<void> {
    return this.serial(async () => {
      const alerts = await this.alerts();
      const ingest = await this.ingestDoc();
      for (const item of items) {
        const record = item.origin === 'probe' ? alerts.probes[item.id] : ingest[item.id];
        if (!record) continue;
        record.mailed_state = item.state;
        record.last_mailed_at = at;
      }
      if (kind === 'digest') alerts.last_digest_at = at;
      alerts.last_mail_error = null;
      alerts.mail_log = [
        ...alerts.mail_log,
        { at, kind, probes: items.map((item) => item.id), message_id: messageId },
      ].slice(-this.config.worker.mail_log_size);
      await this.storage.put('alerts', alerts);
      await this.storage.put('ingest', ingest);
    });
  }

  /** Records a failed send; nothing is marked mailed, so the next run retries it. */
  recordMailError(at: string, detail: string): Promise<void> {
    return this.serial(async () => {
      const alerts = await this.alerts();
      alerts.last_mail_error = { at, detail };
      await this.storage.put('alerts', alerts);
    });
  }

  /** One ingest entry; it transitions on first receipt (D-ingest). Answers whether the state changed. */
  ingest(entry: IngestInput, receivedAt: string): Promise<{ transition: boolean }> {
    return this.serial(async () => {
      const doc = await this.ingestDoc();
      const prev = doc[entry.source];
      doc[entry.source] = {
        state: entry.state,
        at: entry.at,
        detail: entry.detail,
        received_at: receivedAt,
        last_mailed_at: prev?.last_mailed_at ?? null,
        mailed_state: prev?.mailed_state ?? null,
      };
      await this.storage.put('ingest', doc);
      return { transition: prev?.state !== entry.state };
    });
  }

  ctCache(): Promise<Record<string, CtCacheEntry>> {
    return this.serial(async () => (await this.alerts()).ct_cache);
  }

  lastDigestAt(): Promise<string | null> {
    return this.serial(async () => (await this.alerts()).last_digest_at);
  }

  /** The `/v1/status` body of D-record. */
  status(at: string, withMail: boolean): Promise<StatusView> {
    return this.serial(async () => {
      const alerts = await this.alerts();
      const ingest = await this.ingestDoc();
      const targets = await this.storage.get<TargetsDoc>('targets');
      const now = Date.parse(at);
      const probes = Object.entries(alerts.probes)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([probe, r]) => ({
          probe,
          state: r.state,
          since: r.since,
          checked_at: r.checked_at,
          detail: r.detail,
        }));
      const ingestRows = Object.entries(ingest)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([source, r]) => ({ source, state: r.state, at: r.at, detail: r.detail }));
      const view: StatusView = {
        last_cron_at: alerts.last_cron_at,
        targets_sha: targets?.sha ?? null,
        probes,
        ingest: ingestRows,
        verdict: this.verdict(alerts, ingest, now),
      };
      if (withMail) {
        view.mail_log = alerts.mail_log;
        view.last_mail_error = alerts.last_mail_error;
      }
      return view;
    });
  }

  /** Red when any probe is red or a fresh ingest entry is red; unknown when no cron has run, the last one is stale, or any probe is unknown; green otherwise. */
  private verdict(alerts: AlertsDoc, ingest: IngestDoc, now: number): TriState {
    const records = Object.values(alerts.probes);
    if (records.some((r) => r.state === 'red')) return 'red';
    if (
      Object.entries(ingest).some(
        ([s, r]) => r.state === 'red' && ingestFresh(s, r, now, this.config)
      )
    ) {
      return 'red';
    }
    if (!alerts.last_cron_at) return 'unknown';
    if (now - Date.parse(alerts.last_cron_at) > this.config.stale.last_cron_minutes * 60_000)
      return 'unknown';
    if (records.length === 0 || records.some((r) => r.state === 'unknown')) return 'unknown';
    return 'green';
  }
}

export class OpsState extends DurableObject<Env> {
  private readonly core: OpsStateCore;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.core = new OpsStateCore(ctx.storage);
  }

  applyRun(input: RunInput): Promise<DueItem[]> {
    return this.core.applyRun(input);
  }

  markMailed(
    items: DueItem[],
    at: string,
    messageId: string,
    kind: 'alert' | 'digest'
  ): Promise<void> {
    return this.core.markMailed(items, at, messageId, kind);
  }

  recordMailError(at: string, detail: string): Promise<void> {
    return this.core.recordMailError(at, detail);
  }

  ingest(entry: IngestInput, receivedAt: string): Promise<{ transition: boolean }> {
    return this.core.ingest(entry, receivedAt);
  }

  ctCache(): Promise<Record<string, CtCacheEntry>> {
    return this.core.ctCache();
  }

  lastDigestAt(): Promise<string | null> {
    return this.core.lastDigestAt();
  }

  status(at: string, withMail: boolean): Promise<StatusView> {
    return this.core.status(at, withMail);
  }
}
