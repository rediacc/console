import { connect } from 'cloudflare:sockets';

import { CONFIG } from './config';
import type { Env } from './env';
import { alertBody, alertSubject, digestBody, digestSubject, mailerState, sendSes } from './mail';
import { type ConnectFn, type CtAnswer, lookupCt, type ProbeResult, runProbes } from './probes';
import type { CtCacheEntry, IngestInput } from './state';
import { loadTargets, regionEndpoints, type TriState } from './targets';

export { OpsState } from './state';

/**
 * The off-box ops-health alerter (agent/plans/PLAN-health-checks-local.md D-runner). Every 10 minutes it runs the generic probes against the deploy-time targets and the regions.json health endpoints, applies the D-mail dedupe in the `OpsState` Durable Object and mails transitions through SES. It only reads and alerts; nothing here fixes anything (E3).
 */

export interface Runtime {
  fetch: typeof fetch;
  connect: ConnectFn;
  now: () => number;
}

const SOURCE_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const STATES: readonly TriState[] = ['green', 'red', 'unknown'];
const DETAIL_MAX = 2000;
const HOUR_MS = 3_600_000;

function stateStub(env: Env) {
  return env.OPS_STATE.get(env.OPS_STATE.idFromName('state'));
}

/** Is a Monday-digest send due at `at`: the configured weekday, at or after the configured hour, and none sent that day yet. */
export function digestDue(at: string, lastDigestAt: string | null): boolean {
  const now = new Date(at);
  const { weekday_utc, hour_utc } = CONFIG.worker.digest;
  if (now.getUTCDay() !== weekday_utc || now.getUTCHours() < hour_utc) return false;
  return lastDigestAt === null || lastDigestAt.slice(0, 10) !== at.slice(0, 10);
}

/** One cron run: probe, apply, mail the due transitions, then the digest when due. A failed send leaves its transitions unmailed. */
export async function runCron(env: Env, rt: Runtime): Promise<void> {
  const at = new Date(rt.now()).toISOString();
  const stub = stateStub(env);
  const loaded = loadTargets(env.OPS_HEALTH_TARGETS);
  const cache = await stub.ctCache();
  const fresh: Record<string, CtCacheEntry> = {};

  // CT answers are cached for ct_cache_hours: certspotter's unauthenticated quota is small, and an expiry date moves only on a new issuance.
  const ct = async (host: string, issuer?: string): Promise<CtAnswer> => {
    const key = issuer ? `${host}|${issuer}` : host;
    const hit = cache[key];
    if (
      hit &&
      hit.not_after !== null &&
      rt.now() - Date.parse(hit.at) < CONFIG.worker.ct_cache_hours * HOUR_MS
    ) {
      return { notAfter: hit.not_after, source: 'cache' };
    }
    const answer = await lookupCt(host, { fetch: rt.fetch }, issuer);
    fresh[key] = { not_after: answer.notAfter, source: answer.source, at };
    return answer;
  };

  const results: ProbeResult[] = await runProbes([...regionEndpoints(), ...loaded.probes], {
    fetch: rt.fetch,
    connect: rt.connect,
    now: rt.now,
    ct,
    spamhausKey: env.SPAMHAUS_DQS_KEY,
  });
  results.push({ id: 'targets', kind: 'targets', ...loaded.status });
  results.push({ id: 'mailer', kind: 'mailer', ...mailerState(env) });

  const due = await stub.applyRun({
    at,
    results,
    targets: { sha: env.OPS_HEALTH_TARGETS_SHA ?? null, probe_count: loaded.probeCount },
    ct: fresh,
  });

  if (due.length > 0) {
    const sent = await sendSes(env, rt.fetch, {
      subject: alertSubject(due),
      text: alertBody(due, at),
    });
    if (sent.ok) await stub.markMailed(due, at, sent.messageId, 'alert');
    else await stub.recordMailError(at, sent.detail);
  }

  if (digestDue(at, await stub.lastDigestAt())) {
    const view = await stub.status(at, false);
    const sent = await sendSes(env, rt.fetch, {
      subject: digestSubject(view),
      text: digestBody(view, at),
    });
    if (sent.ok) await stub.markMailed([], at, sent.messageId, 'digest');
    else await stub.recordMailError(at, sent.detail);
  }
}

async function digest(value: string): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)));
}

/** A constant-time bearer check. An unset expected token never authorizes. */
export async function bearerOk(request: Request, expected: string | undefined): Promise<boolean> {
  if (!expected) return false;
  const header = request.headers.get('authorization') ?? '';
  if (!header.startsWith('Bearer ')) return false;
  const [a, b] = await Promise.all([digest(header.slice(7)), digest(expected)]);
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a[i] ^ b[i];
  return diff === 0;
}

function json(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

/** The first reason an ingest body is refused, or null when every field is valid. */
function ingestProblem(fields: Record<string, unknown>): string | null {
  const { source, state, detail, at } = fields;
  const checks: [boolean, string][] = [
    [typeof source === 'string' && SOURCE_RE.test(source), `source must match ${SOURCE_RE.source}`],
    [
      typeof state === 'string' && STATES.includes(state as TriState),
      'state must be green, red or unknown',
    ],
    [detail === undefined || typeof detail === 'string', 'detail must be a string'],
    [typeof at === 'string' && !Number.isNaN(Date.parse(at)), 'at must be an ISO 8601 time'],
  ];
  const failed = checks.find(([ok]) => !ok);
  return failed ? failed[1] : null;
}

/** Validates an ingest body: `{source, state, detail, at}`. Answers the entry or the reason it is refused. */
export function parseIngest(body: unknown): IngestInput | string {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return 'the body is not an object';
  }
  const fields = body as Record<string, unknown>;
  const problem = ingestProblem(fields);
  if (problem) return problem;
  return {
    source: fields.source as string,
    state: fields.state as TriState,
    detail: ((fields.detail as string | undefined) ?? '').slice(0, DETAIL_MAX),
    at: new Date(Date.parse(fields.at as string)).toISOString(),
  };
}

/** OPS_HEALTH_SECRET_DIGESTS (`NAME=hex,NAME=hex`, written by the deploy) as an object; anything unreadable is empty, which makes the next deploy re-put every secret. */
export function deployedDigests(env: Env): Record<string, string> {
  const out: Record<string, string> = {};
  for (const pair of (env.OPS_HEALTH_SECRET_DIGESTS ?? '').split(',')) {
    const match = /^([A-Z0-9_]+)=([0-9a-f]+)$/.exec(pair.trim());
    if (match) out[match[1]] = match[2];
  }
  return out;
}

async function handleStatus(request: Request, env: Env, url: URL, at: string): Promise<Response> {
  if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405);
  if (!(await bearerOk(request, env.OPS_HEALTH_READ_TOKEN))) {
    return json({ error: 'unauthorized' }, 401);
  }
  const view = await stateStub(env).status(at, url.searchParams.get('mail') === '1');
  return json({
    ...view,
    targets_sha: env.OPS_HEALTH_TARGETS_SHA ?? view.targets_sha,
    deploy: { code_sha: env.OPS_HEALTH_CODE_SHA ?? null, secret_digests: deployedDigests(env) },
  });
}

async function handleIngest(request: Request, env: Env, at: string): Promise<Response> {
  if (request.method !== 'POST') return json({ error: 'method not allowed' }, 405);
  if (!(await bearerOk(request, env.OPS_HEALTH_INGEST_TOKEN))) {
    return json({ error: 'unauthorized' }, 401);
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'the body is not JSON' }, 400);
  }
  const entry = parseIngest(body);
  if (typeof entry === 'string') return json({ error: entry }, 400);
  const { transition } = await stateStub(env).ingest(entry, at);
  return json({ ok: true, transition });
}

export function handleFetch(request: Request, env: Env, rt: Runtime): Promise<Response> {
  const url = new URL(request.url);
  const at = new Date(rt.now()).toISOString();
  if (url.pathname === '/v1/status') return handleStatus(request, env, url, at);
  if (url.pathname === '/v1/ingest') return handleIngest(request, env, at);
  return Promise.resolve(json({ error: 'not found' }, 404));
}

function runtime(now: () => number = Date.now): Runtime {
  return { fetch: (input, init) => fetch(input, init), connect, now };
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handleFetch(request, env, runtime());
  },
  scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): void {
    ctx.waitUntil(runCron(env, runtime()));
  },
} satisfies ExportedHandler<Env>;
