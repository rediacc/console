/**
 * The executor's audit trail.
 *
 * This is where the proxy earns the claim that it is a MORE trustworthy audit
 * source than the CLI, which is the whole enterprise pitch. Three differences
 * from the CLI's own best-effort audit, and each one closes a real gap:
 *
 *   1. SYNCHRONOUS. One event per command, awaited before the caller is told the
 *      outcome. The CLI flushes at process exit, so a killed process loses its
 *      events silently. An executor that cannot record what it did must not
 *      pretend it did nothing.
 *
 *   2. SERVER-VERIFIED ACTOR. The event is attributed to the user the ACCOUNT
 *      server resolved from the presented token, never to an identity the client
 *      asserted. `onBehalfOfTokenId` carries that token so the server can
 *      re-derive the same answer independently.
 *
 *   3. IDEMPOTENT. Every event carries a key, so a retry after a network blip
 *      records the command once rather than twice, and a job's terminal event
 *      carries a key derived from the job id, so a restarted executor that
 *      ships it again is recorded once too. An audit log that double-counts is
 *      not evidence of anything.
 */

import { createHash, randomUUID } from 'node:crypto';
import { type AuditEvent, functionNameToEventType } from '@rediacc/shared';
import { isValidGuid } from '@rediacc/shared/validation';
import { VERSION } from '../../version.js';
import { deadlineFetch, describeFetchError } from './account-fetch.js';
import type { ExecutorAuditEvent } from './deps.js';

export interface ExecutorAuditOptions {
  /** Account server base URL. */
  accountUrl: string;
  /** The executor's own token, which must carry the audit:write scope. */
  executorToken: string;
  fetchImpl?: typeof fetch;
  /** Called when an event cannot be delivered, so the failure is visible. */
  onFailure?: (error: unknown, event: ExecutorAuditEvent) => void;
}

/** The job outcomes that end a job: the event that records one is the job's terminal event. */
const TERMINAL_OUTCOMES: ReadonlySet<string> = new Set(['succeeded', 'failed', 'cancelled']);

/** The UUIDv5 namespace of the executor's derived audit keys (a fixed random UUID; changing it re-keys every terminal event). */
const AUDIT_KEY_NAMESPACE = '6f1d7c2e-3b4a-4e8f-9c05-1a2b3c4d5e6f';

/** The RFC 9562 version-5 UUID of `name` in `namespace`: the same name always maps to the same UUID. */
export function uuidV5(namespace: string, name: string): string {
  const hash = createHash('sha1')
    .update(Buffer.from(namespace.replaceAll('-', ''), 'hex'))
    .update(name, 'utf8')
    .digest();
  hash[6] = (hash[6] & 0x0f) | 0x50;
  hash[8] = (hash[8] & 0x3f) | 0x80;
  const hex = hash.subarray(0, 16).toString('hex');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * The idempotency key of an event (PLAN-rmcp-writeback.md Design 9).
 *
 * A job's terminal event is keyed by the name `job:<jobId>:terminal`, the same in
 * every process: the in-memory ledger that ships it once per job is lost on every
 * container sleep, and a restarted executor's poll ships it again under the same
 * key, which the account server keeps once (routes/license.ts). Whether the
 * terminal outcome arrived with the dispatch (the job finished inside the attach
 * window) or with a poll, it is one record. The wire schema takes a UUID, so the
 * key is that name's version-5 UUID. Every other event is one occurrence of its
 * own and gets a fresh key, shared only by that event's retries.
 */
export function auditIdempotencyKey(event: ExecutorAuditEvent): string {
  if (event.jobId && event.outcome && TERMINAL_OUTCOMES.has(event.outcome)) {
    return uuidV5(AUDIT_KEY_NAMESPACE, `job:${event.jobId}:terminal`);
  }
  return randomUUID();
}

/**
 * The wire event for one executed command, in the shape the account server's
 * AuditEventsRequestSchema accepts.
 *
 * A command whose function maps to an event type records under that type, so
 * a proxied `repo up` and a local one land in the same SIEM bucket. Every other
 * command (one that reached no renet function, or whose function maps to no
 * type, or that resolved no machine) records as `cli.command`, keyed by its
 * path: the one-event-per-command guarantee does not depend on the mapping.
 *
 * Params are NOT shipped: they can carry a secret value on a `repo secret set`.
 * The audit trail records WHAT ran and WHO ran it, not the payload. The one
 * exception is the repository identity of a function-mapped event, read out of
 * the observed call's params (repositoryIdentity): the repository it acted on,
 * as the CLI's own emitter records it, and the GUID of the image a create or
 * fork made, which is how an orphaned image is traced back to its event.
 */
function buildExecutorAuditEvent(
  event: ExecutorAuditEvent,
  idempotencyKey: string = auditIdempotencyKey(event)
): AuditEvent {
  const envelope = {
    idempotencyKey,
    ...(event.principal.tokenId ? { onBehalfOfTokenId: event.principal.tokenId } : {}),
  };
  const outcome = {
    success: event.success,
    exitCode: event.exitCode,
    durationMs: Math.max(0, Math.round(event.durationMs)),
    cliVersion: VERSION,
    commandPath: event.commandPath,
    destructive: event.destructive,
    ...(event.jobId ? { jobId: event.jobId } : {}),
    ...(event.outcome ? { outcome: event.outcome } : {}),
    ...(event.requestId ? { requestId: event.requestId } : {}),
  };

  const { functionName, machineName } = event;
  const mapped = functionName ? functionNameToEventType(functionName) : null;
  if (mapped && functionName && machineName) {
    return mappedEvent(
      mapped,
      {
        functionName,
        machineName,
        ...repositoryIdentity(functionName, event.functionParams),
        ...outcome,
      },
      envelope
    );
  }

  return {
    type: 'cli.command',
    data: {
      ...(functionName ? { functionName } : {}),
      ...(machineName ? { machineName } : {}),
      ...outcome,
    },
    ...envelope,
  };
}

/** The param that carries the GUID of the image each image-making function creates (repo-create-delete.ts, repo-fork.ts buildForkParams). */
const MADE_GUID_PARAM: Readonly<Record<string, string>> = {
  repository_create: 'guid',
  repository_fork: 'tag',
};

/** The longest repoName the audit schema accepts (event-schema.ts baseData). */
const REPO_NAME_MAX = 200;

/**
 * The repository identity of one observed renet call: `repoName` from its
 * `repository` param, and for `repository_create` / `repository_fork` the `guid`
 * of the image it made. A value the audit schema would refuse is left out, so a
 * malformed param never costs the event.
 */
export function repositoryIdentity(
  functionName: string,
  params: Record<string, unknown> | undefined
): { repoName?: string; guid?: string } {
  if (!params) return {};
  const repo = params.repository;
  const guidParam = MADE_GUID_PARAM[functionName];
  const guid = guidParam ? params[guidParam] : undefined;
  return {
    ...(typeof repo === 'string' && repo !== '' && repo.length <= REPO_NAME_MAX
      ? { repoName: repo }
      : {}),
    ...(typeof guid === 'string' && isValidGuid(guid) ? { guid: guid.toLowerCase() } : {}),
  };
}

type MappedType = NonNullable<ReturnType<typeof functionNameToEventType>>;
/** The plain baseData every function-mapped branch accepts (the machine-op branch's data). */
type MappedData = Exclude<
  AuditEvent,
  { type: 'cli.command' | 'cli.sync.upload' | 'cli.sync.download' | 'cli.term.session' }
>['data'];

// The same data for every branch; the split only narrows `type` to one discriminated-union member, which TypeScript cannot do for the whole union at once.
function mappedEvent(
  type: MappedType,
  data: MappedData,
  envelope: Pick<AuditEvent, 'idempotencyKey' | 'onBehalfOfTokenId'>
): AuditEvent {
  if (type === 'cli.sync.upload' || type === 'cli.sync.download')
    return { type, data, ...envelope };
  if (type === 'cli.term.session') return { type, data, ...envelope };
  return { type, data, ...envelope };
}

/** The served result's error code for a mutating command refused because its audit record could not be delivered. */
export const AUDIT_UNAVAILABLE = 'AUDIT_UNAVAILABLE';

/** Deliveries per event: the first attempt and one retry, both under the event's one idempotency key. */
export const AUDIT_DELIVERY_ATTEMPTS = 2;

/** An audit event the account server did not accept after the retry. */
export class AuditUnavailableError extends Error {
  readonly code = AUDIT_UNAVAILABLE;
  /** `reason` is why the last attempt failed; it is the whole message, so a caller can frame it. */
  constructor(reason: string) {
    super(reason);
    this.name = 'AuditUnavailableError';
  }
}

/**
 * Ship one audit event, retrying once.
 *
 * The event is built once, so the retry carries the same idempotency key and the
 * account server records it once however many attempts reach it. A refusal the
 * server answers with (a 4xx other than 429) is not retried: it would refuse the
 * same body again. An event still undelivered after the retry is reported to
 * `onFailure` and thrown as AuditUnavailableError, and the caller decides
 * (agent/plans/PLAN-rmcp-writeback.md Design 8): before dispatch a mutating
 * command is refused, after dispatch the result says the record is missing.
 */
export function createExecutorAudit(
  options: ExecutorAuditOptions
): (event: ExecutorAuditEvent) => Promise<void> {
  const fetchImpl = deadlineFetch(options.fetchImpl ?? globalThis.fetch);
  const accountUrl = options.accountUrl.replace(/\/+$/, '');

  /** One delivery: undefined when accepted, else why not and whether a retry could help. */
  const deliver = async (body: string): Promise<{ reason: string; retry: boolean } | undefined> => {
    try {
      const response = await fetchImpl(`${accountUrl}/account/api/v1/licenses/audit-events`, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${options.executorToken}`,
          'content-type': 'application/json',
        },
        body,
      });
      if (response.ok) return undefined;
      return {
        reason: `the account server rejected the audit event (${response.status})`,
        retry: response.status >= 500 || response.status === 429,
      };
    } catch (error) {
      return { reason: describeFetchError(error), retry: true };
    }
  };

  /** Build and deliver one event: undefined when accepted, else why not. An event that cannot be built is undelivered like any other, so the caller refuses or warns instead of the raw error ending its stream. */
  const ship = async (
    event: ExecutorAuditEvent
  ): Promise<{ reason: string; retry: boolean } | undefined> => {
    let body: string;
    try {
      body = JSON.stringify({ events: [buildExecutorAuditEvent(event)] });
    } catch (error) {
      const why = error instanceof Error ? error.message : String(error);
      return { reason: `the audit event could not be built (${why})`, retry: false };
    }
    let failed: { reason: string; retry: boolean } | undefined;
    for (let attempt = 1; attempt <= AUDIT_DELIVERY_ATTEMPTS; attempt++) {
      failed = await deliver(body);
      if (!failed?.retry) break;
    }
    return failed;
  };

  return async (event: ExecutorAuditEvent): Promise<void> => {
    const failed = await ship(event);
    if (!failed) return;
    const failure = new AuditUnavailableError(failed.reason);
    options.onFailure?.(failure, event);
    throw failure;
  };
}
