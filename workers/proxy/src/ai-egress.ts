/**
 * The container's road to Rediacc-provided AI, metered against the org's credit ledger
 * (agent/plans/PLAN-console-ai-credits.md D1, D5 to D7).
 *
 * The loop host calls `http://ai.internal/compat/chat/completions`, which `OrgExecutor` routes here (`interceptOutboundHttp`, to the `AiEgress` entrypoint). The container holds no key and names no org: `orgId` comes from the per-instance props, cross-checked against the instance's own Durable Object id exactly as `AccountEgress` does.
 *
 * One call runs in this order, and every step before the forward answers without touching the gateway:
 *
 *   1. only `POST /compat/chat/completions` with no query is admitted (403 `route-not-allowed`);
 *   2. an unconfigured Worker (no `CREDITS` binding, `AI_GATEWAY_TOKEN`, `AI_GATEWAY_ID` or `AI_GATEWAY_ACCOUNT_ID`) answers 503 `ai-unconfigured`;
 *   3. the body is read to at most `MAX_AI_BODY_BYTES` (413 `body-too-large`) and must be a JSON object naming a string `model` and a `messages` array (400 `invalid-request`);
 *   4. a model absent from the price table is 403 `model-not-allowed` before any reservation (D2);
 *   5. `reserve` on the org's ledger holds the worst case; a refusal is answered with its ledger code (D5), and a ledger that cannot answer is 503 `ledger-unavailable` (fail closed);
 *   6. the forwarded body carries the token limit it named (`max_tokens` or `max_completion_tokens`) clamped in place and, for a stream, `stream_options.include_usage` forced on, so the final chunk always reports usage;
 *   7. the call leaves for the region's AI Gateway OpenAI-compatible endpoint with `cf-aig-authorization` from the Worker secret and `cf-aig-metadata` carrying `org_id`, `user_id`, `conversation_id`, `reservation_id` and `price_version` (D7), and nothing else of the container's headers.
 *
 * The response streams back untouched while its usage is read on the way. When the body closes, errors or is cancelled (the container's abort cancels the upstream fetch too, D6), the reservation is committed once with the usage seen, or in full when none was seen; the ledger's own alarm commits a reservation this Worker never settled. An upstream that never answered, or answered a non-2xx status, consumed nothing, so its reservation is released.
 */

import { WorkerEntrypoint } from 'cloudflare:workers';
import {
  type AiPriceRow,
  findPriceRow,
  PRICE_TABLE_VERSION,
} from '../../../packages/shared/src/ai-credits/index.js';
import type { ExecutorEgressProps } from './org-executor-support';
import { executorName, placementOf } from './placement';
import { activeSpan } from './span';

/** The only path the container may call. */
export const AI_COMPAT_PATH = '/compat/chat/completions';

/** The most of a request body read; a longer one is refused 413 before any reservation. */
export const MAX_AI_BODY_BYTES = 2 * 1024 * 1024;

/** The most of a non-stream response buffered to read its usage; a larger one is committed in full. */
const MAX_USAGE_BUFFER_BYTES = 4 * 1024 * 1024;

/** Headers the loop host sets for the ledger's per-user and per-conversation caps. Values are shape-checked and never trusted for the org. */
export const AI_USER_HEADER = 'x-rediacc-ai-user';
export const AI_CONVERSATION_HEADER = 'x-rediacc-ai-conversation';

const ID_RE = /^[A-Za-z0-9_.:-]{1,128}$/;

/** The ledger's reserve refusal codes (workers/account/src/credit-ledger.ts `RefusalCode`). */
type CreditRefusalCode =
  | 'PLAN_NOT_ENTITLED'
  | 'ORG_BLOCKED'
  | 'GLOBAL_PAUSED'
  | 'MODEL_NOT_ALLOWED'
  | 'INSUFFICIENT_CREDITS'
  | 'DAILY_CAP'
  | 'TOO_MANY_STREAMS'
  | 'CONVERSATION_TOKEN_CAP'
  | 'LOOP_DEPTH';

export interface CreditReserveRequest {
  reservationId: string;
  userId: string;
  conversationId: string;
  model: string;
  bodyBytes: number;
  maxTokens?: number;
}

export type CreditReserveAnswer =
  | { ok: true; reservationId: string; credits: number; maxTokens: number; priceVersion: number }
  | { ok: false; code: CreditRefusalCode };

export interface CreditTokenCounts {
  promptTokens: number;
  completionTokens: number;
}

/** The `CreditLedgerGate` entrypoint as the `CREDITS` service binding exposes it: reserve, commit and release, and nothing that grants. */
export interface CreditsRpc extends Rpc.WorkerEntrypointBranded {
  reserve(orgId: string, request: CreditReserveRequest): Promise<CreditReserveAnswer>;
  commit(orgId: string, reservationId: string, usage?: CreditTokenCounts): Promise<unknown>;
  release(orgId: string, reservationId: string): Promise<boolean>;
}

/** The env slice `AiEgress` reads. */
export interface AiEgressEnv {
  ORG_EXECUTOR: {
    idFromName(name: string): { toString(): string };
  };
  CREDITS?: Service<CreditsRpc>;
  /** Secret: a gateway-scoped Cloudflare token (`cf-aig-authorization`), never a provider key. */
  AI_GATEWAY_TOKEN?: string;
  /** Var: the region's gateway id, `rediacc-<region>`. */
  AI_GATEWAY_ID?: string;
  /** Var: the Cloudflare account that owns the gateway. */
  AI_GATEWAY_ACCOUNT_ID?: string;
}

/** The status of a refusal code the map does not name: forbidden, never a pass. */
const DEFAULT_REFUSAL_STATUS = 403;

/** The HTTP status each ledger refusal is answered with. */
const REFUSAL_STATUS: Record<CreditRefusalCode, number> = {
  PLAN_NOT_ENTITLED: 403,
  ORG_BLOCKED: 403,
  GLOBAL_PAUSED: 403,
  MODEL_NOT_ALLOWED: 403,
  INSUFFICIENT_CREDITS: 402,
  DAILY_CAP: 429,
  TOO_MANY_STREAMS: 429,
  CONVERSATION_TOKEN_CAP: 429,
  LOOP_DEPTH: 429,
};

function refuseAi(code: string, status: number, method: string, url: URL): Response {
  console.warn(`proxy: ai egress refused: ${code} ${method} ${url.pathname.slice(0, 200)}`);
  return Response.json({ error: { code, message: code }, code }, { status });
}

/** The gateway's OpenAI-compatible chat completions URL for the region. */
export function gatewayUrl(accountId: string, gatewayId: string): string {
  return `https://gateway.ai.cloudflare.com/v1/${encodeURIComponent(accountId)}/${encodeURIComponent(gatewayId)}/compat/chat/completions`;
}

/** The `cf-aig-metadata` value of D7: five entries, the join key of the reconcile. */
function aiMetadata(entries: {
  orgId: string;
  userId: string;
  conversationId: string;
  reservationId: string;
}): string {
  return JSON.stringify({
    org_id: entries.orgId,
    user_id: entries.userId,
    conversation_id: entries.conversationId,
    reservation_id: entries.reservationId,
    price_version: PRICE_TABLE_VERSION,
  });
}

/** The request body as text, or undefined once it passes `max` bytes. */
async function boundedBody(request: Request, max: number): Promise<string | undefined> {
  const declared = Number(request.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > max) return undefined;
  if (request.body === null) return '';
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) {
      await reader.cancel().catch(() => undefined);
      return undefined;
    }
    chunks.push(value);
  }
  const joined = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    joined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(joined);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** A parsed, admitted call: the body object, its model's price row and the requested output cap. */
interface AdmittedCall {
  body: Record<string, unknown>;
  row: AiPriceRow;
  requestedMax: number | undefined;
}

/** The output cap the request names (`max_completion_tokens` wins over `max_tokens`), undefined when it names none, or null when it is not a number of at least 1. */
function requestedMaxTokens(body: Record<string, unknown>): number | undefined | null {
  const value = body.max_completion_tokens ?? body.max_tokens;
  if (value === undefined || value === null) return undefined;
  return typeof value === 'number' && Number.isFinite(value) && value >= 1 ? value : null;
}

/** The admitted call, or the refusal response. */
function admitCall(text: string, method: string, url: URL): AdmittedCall | Response {
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return refuseAi('invalid-request', 400, method, url);
  }
  if (!isRecord(body) || typeof body.model !== 'string' || !Array.isArray(body.messages)) {
    return refuseAi('invalid-request', 400, method, url);
  }
  const requestedMax = requestedMaxTokens(body);
  if (requestedMax === null) return refuseAi('invalid-request', 400, method, url);
  const row = findPriceRow(body.model);
  if (row === undefined) return refuseAi('model-not-allowed', 403, method, url);
  return { body, row, requestedMax };
}

/** The body forwarded: output caps clamped to the reservation's, and usage reporting forced on for a stream. */
function clampedBody(body: Record<string, unknown>, maxTokens: number): string {
  const out: Record<string, unknown> = { ...body };
  if ('max_completion_tokens' in out) out.max_completion_tokens = maxTokens;
  if ('max_tokens' in out || !('max_completion_tokens' in out)) out.max_tokens = maxTokens;
  if (out.stream === true) {
    const options = isRecord(out.stream_options) ? out.stream_options : {};
    out.stream_options = { ...options, include_usage: true };
  }
  return JSON.stringify(out);
}

/** The usage a response body reported, or undefined when it reported none. */
function usageOf(value: unknown): CreditTokenCounts | undefined {
  if (!isRecord(value) || !isRecord(value.usage)) return undefined;
  const { prompt_tokens: promptTokens, completion_tokens: completionTokens } = value.usage;
  if (
    typeof promptTokens !== 'number' ||
    typeof completionTokens !== 'number' ||
    !Number.isFinite(promptTokens) ||
    !Number.isFinite(completionTokens) ||
    promptTokens < 0 ||
    completionTokens < 0
  ) {
    return undefined;
  }
  return { promptTokens, completionTokens };
}

/** The last usage object carried by the `data:` lines of an event stream. */
function lastStreamUsage(lines: string[], previous: CreditTokenCounts | undefined) {
  let found = previous;
  for (const line of lines) {
    if (!line.startsWith('data:')) continue;
    const data = line.slice(5).trim();
    if (data === '' || data === '[DONE]') continue;
    try {
      found = usageOf(JSON.parse(data)) ?? found;
    } catch {
      // A partial or non-JSON line carries no usage.
    }
  }
  return found;
}

/**
 * The response body, byte for byte, with `settle` called exactly once when it closes, errors or is cancelled, carrying the usage read on the way (undefined when none was seen). An event stream is read line by line for the last chunk's usage; a JSON body is buffered up to MAX_USAGE_BUFFER_BYTES and read at the end.
 */
function meterBody(
  response: Response,
  settle: (usage: CreditTokenCounts | undefined) => void
): Response {
  if (response.body === null) {
    settle(undefined);
    return response;
  }
  const streaming = (response.headers.get('content-type') ?? '').includes('text/event-stream');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let buffered = '';
  let overflow = false;
  let usage: CreditTokenCounts | undefined;
  let settled = false;
  const finish = () => {
    if (settled) return;
    settled = true;
    if (streaming) {
      usage = lastStreamUsage([pending], usage);
    } else if (!overflow) {
      try {
        usage = usageOf(JSON.parse(buffered));
      } catch {
        usage = undefined;
      }
    }
    settle(usage);
  };
  const observe = (chunk: Uint8Array) => {
    const text = decoder.decode(chunk, { stream: true });
    if (streaming) {
      const lines = (pending + text).split('\n');
      pending = lines.pop() ?? '';
      usage = lastStreamUsage(lines, usage);
    } else if (!overflow) {
      buffered += text;
      if (buffered.length > MAX_USAGE_BUFFER_BYTES) overflow = true;
    }
  };
  const body = new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const chunk = await reader.read();
        if (chunk.done) {
          finish();
          controller.close();
        } else {
          observe(chunk.value);
          controller.enqueue(chunk.value);
        }
      } catch (error) {
        finish();
        controller.error(error);
      }
    },
    cancel(reason) {
      finish();
      return reader.cancel(reason);
    },
  });
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

/** The identifier a header carries, or undefined when it is absent or not an identifier. */
function idHeader(request: Request, name: string): string | undefined {
  const value = request.headers.get(name);
  return value !== null && ID_RE.test(value) ? value : undefined;
}

/** A request admitted before any reservation: the parsed call, the caller's ids and the body size. */
interface AdmittedRequest {
  admitted: AdmittedCall;
  userId: string;
  conversationId: string;
  bodyBytes: number;
}

/** The body, the model and the ids of a request, or the refusal response. */
async function admitRequest(request: Request, url: URL): Promise<AdmittedRequest | Response> {
  const { method } = request;
  const text = await boundedBody(request, MAX_AI_BODY_BYTES);
  if (text === undefined) return refuseAi('body-too-large', 413, method, url);
  const admitted = admitCall(text, method, url);
  if (admitted instanceof Response) return admitted;
  const userId = idHeader(request, AI_USER_HEADER);
  const conversationId = idHeader(request, AI_CONVERSATION_HEADER);
  if (userId === undefined || conversationId === undefined) {
    return refuseAi('invalid-request', 400, method, url);
  }
  return {
    admitted,
    userId,
    conversationId,
    bodyBytes: new TextEncoder().encode(text).byteLength,
  };
}

/**
 * The AI egress entrypoint: `OrgExecutor` binds it through `ctx.exports.AiEgress({ props: { orgId, placement, containerId } })` and `interceptOutboundHttp` routes `ai.internal` to that stub. Not bound in any wrangler config: it is reached only through `ctx.exports`.
 */
export class AiEgress extends WorkerEntrypoint<AiEgressEnv, Partial<ExecutorEgressProps>> {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const { method } = request;
    const { orgId, placement, containerId } = this.ctx.props ?? {};
    const valid = placementOf(placement);
    if (
      typeof orgId !== 'string' ||
      orgId === '' ||
      valid === undefined ||
      typeof containerId !== 'string'
    ) {
      return refuseAi('org-param-missing', 403, method, url);
    }
    if (containerId !== this.env.ORG_EXECUTOR.idFromName(executorName(orgId, valid)).toString()) {
      return refuseAi('container-org-mismatch', 403, method, url);
    }
    if (method !== 'POST' || url.pathname !== AI_COMPAT_PATH || url.search !== '') {
      return refuseAi('route-not-allowed', 403, method, url);
    }
    const span = activeSpan(this.ctx);
    const response = await this.meter(request, orgId, url);
    span?.setAttribute('rediacc.proxy.ai_status', response.status);
    return response;
  }

  /** Admit, reserve, forward and meter one call. */
  private async meter(request: Request, orgId: string, url: URL): Promise<Response> {
    const { CREDITS, AI_GATEWAY_TOKEN, AI_GATEWAY_ID, AI_GATEWAY_ACCOUNT_ID } = this.env;
    const { method } = request;
    if (!(CREDITS && AI_GATEWAY_TOKEN && AI_GATEWAY_ID && AI_GATEWAY_ACCOUNT_ID)) {
      return refuseAi('ai-unconfigured', 503, method, url);
    }
    const call = await admitRequest(request, url);
    if (call instanceof Response) return call;
    const { admitted, userId, conversationId, bodyBytes } = call;

    const reservationId = crypto.randomUUID();
    let reserved: CreditReserveAnswer;
    try {
      reserved = await CREDITS.reserve(orgId, {
        reservationId,
        userId,
        conversationId,
        model: admitted.row.model,
        bodyBytes,
        ...(admitted.requestedMax === undefined ? {} : { maxTokens: admitted.requestedMax }),
      });
    } catch {
      return refuseAi('ledger-unavailable', 503, method, url);
    }
    if (!reserved.ok) {
      return refuseAi(
        reserved.code,
        REFUSAL_STATUS[reserved.code] ?? DEFAULT_REFUSAL_STATUS,
        method,
        url
      );
    }

    const release = () => this.ctx.waitUntil(releaseQuietly(CREDITS, orgId, reservationId));
    let upstream: Response;
    try {
      upstream = await fetch(gatewayUrl(AI_GATEWAY_ACCOUNT_ID, AI_GATEWAY_ID), {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'cf-aig-authorization': `Bearer ${AI_GATEWAY_TOKEN}`,
          'cf-aig-metadata': aiMetadata({ orgId, userId, conversationId, reservationId }),
        },
        body: clampedBody(admitted.body, reserved.maxTokens),
        signal: request.signal,
      });
    } catch {
      release();
      return refuseAi('upstream-unreachable', 502, method, url);
    }
    if (!upstream.ok) {
      release();
      return upstream;
    }
    return meterBody(upstream, (usage) => {
      this.ctx.waitUntil(commitQuietly(CREDITS, orgId, reservationId, usage));
    });
  }
}

/** Commit once; a failure is logged, and the ledger's alarm commits the reservation in full after its TTL. */
async function commitQuietly(
  credits: Service<CreditsRpc>,
  orgId: string,
  reservationId: string,
  usage: CreditTokenCounts | undefined
): Promise<void> {
  try {
    await credits.commit(orgId, reservationId, usage);
  } catch {
    console.warn('proxy: ai egress commit failed; the ledger alarm settles it');
  }
}

async function releaseQuietly(
  credits: Service<CreditsRpc>,
  orgId: string,
  reservationId: string
): Promise<void> {
  try {
    await credits.release(orgId, reservationId);
  } catch {
    console.warn('proxy: ai egress release failed; the ledger alarm settles it');
  }
}
