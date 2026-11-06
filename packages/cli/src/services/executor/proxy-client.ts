/**
 * The `--proxy` client: run a COMMAND at an `rdc serve` executor.
 *
 * This replaced a client that intercepted at the executor seam, which sits inside
 * each command's action body. That was too deep, and the reason is worth keeping:
 * a command does config work on its way to the seam. `repo up` reads the
 * repository out of local config and writes back a network id before it ever
 * reaches an executor. A proxy client holds no config at all, by design, so it
 * died with "Repository not found in context" before the wire was touched. The
 * seam was invisible to the config the command needed.
 *
 * So interception moved up, to the whole command. The client parses argv, refuses
 * what cannot be proxied, prompts, and renders. Everything else, config included,
 * happens at the executor. That is what the design always claimed the client was,
 * and now it is true: this file holds no config, no SSH key, and no vault.
 *
 * The response is rendered as if the command had run locally, because it is the
 * same event stream: renet's events, forwarded verbatim, through the same
 * timeline helpers a local run uses. An operator should not be able to tell from
 * the output that the work happened somewhere else.
 */

import { randomUUID } from 'node:crypto';
import { getCommand } from '@rediacc/shared/cli-contract';
import { readNdjson } from '@rediacc/shared/cli-contract/ndjson';
import {
  CLI_VERSION_HEADER,
  CONTRACT_VERSION_HEADER,
  type CommandRequest,
  type JobPollResponse,
  JobPollResponseSchema,
  PROXY_ROUTES,
  type ServerInfo,
  type StreamLine,
  StreamLineSchema,
  VersionMismatchSchema,
} from '@rediacc/shared/cli-contract/wire';
import { cekHandoffEncrypt, exportAesKey, fromBase64 } from '@rediacc/shared/config-crypto';
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { VERSION } from '../../version.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { TicketStore } from '../jobs/ticket-store.js';
import { annotatePolled } from './job-span.js';
import {
  emptyOutcome,
  foldJobLine,
  foldResultLine,
  isTerminalState,
  jittered,
  lostOutcome,
  MAX_START_RETRIES,
  nextPollDelayMs,
  POLL_FIRST_DELAY_MS,
  POLL_MAX_LINES,
  PROXY_LOST_BUDGET_MS,
  type ProxyCommandOutcome,
  recoverBrokenStream,
  type StreamState,
  terminalOutcome,
} from './proxy-follow.js';
import { traceProxyRequest } from './proxy-trace.js';

import type { RenetEvent } from './types.js';

/** The waits before start retry 1, 2 and 3: the head of the poll ladder (2 s, then 3 s, then 4.5 s). */
const START_RETRY_DELAYS_MS = [2000, 3000, 4500] as const;

/** The stream state plus the replay guard of a retried start: events with no spool ordinal cannot dedupe by it. */
interface ClientStreamState extends StreamState {
  /** Ordinal-less events rendered so far, across attempts. */
  unorderedSeen: number;
  /** Ordinal-less events of the current attempt still to skip because an earlier attempt rendered them. */
  unorderedSkip: number;
}

export { nextPollDelayMs, type ProxyCommandOutcome };

/** Raised when the executor rejects the client's contract version. */
export class ProxyVersionMismatchError extends Error {
  constructor(
    readonly clientContractVersion: string,
    readonly executorContractVersion: string,
    readonly executorCliVersion: string
  ) {
    super(
      `Proxy executor speaks contract ${executorContractVersion} (rdc ${executorCliVersion}), ` +
        `this client speaks ${clientContractVersion}. Upgrade rdc, or point --proxy at a matching executor.`
    );
    this.name = 'ProxyVersionMismatchError';
  }
}

/** Raised when the executor closes the stream without a terminal result line. */
export class ProxyStreamTruncatedError extends Error {
  constructor(readonly eventsSeen: number) {
    super(
      `The proxy closed the stream after ${eventsSeen} event(s) without reporting a result. ` +
        `The operation may still be running on the machine. Check its status before retrying.`
    );
    this.name = 'ProxyStreamTruncatedError';
  }
}

export interface ProxyClientOptions {
  /** Base URL of the executor, e.g. https://proxy.rediacc.com or http://localhost:8080 */
  baseUrl: string;
  /** Resolves the bearer token presented to the executor. */
  getToken: () => Promise<string>;
  /** Contract version this client was built against. */
  contractVersion: string;
  /** Injectable for tests. */
  fetchImpl?: typeof fetch;
  /** Milliseconds the executor has to answer a request. Defaults to REDIACC_PROXY_TIMEOUT_MS, then 60s. */
  timeoutMs?: number;
  /**
   * Unwraps this device's config key (CEK). Called only when the executor is a
   * CONTAINER, which holds no key of its own and can open the config only with
   * one granted per session. A daemon derives its own and is never sent one.
   */
  getCek?: () => Promise<CryptoKey>;
  /** Test seams: the poll pacing and the ticket store (`null` writes no ticket). */
  sleep?: (ms: number) => Promise<void>;
  random?: () => number;
  /** How long consecutive failed polls are retried before the follow is given up with the ticket kept. */
  lostBudgetMs?: number;
  ticketStore?: TicketStore | null;
}

/**
 * Grants already made by this process, keyed by executor and token, so a
 * process grants once however many commands it sends. Holds the promise, so
 * concurrent callers share one grant rather than racing two sessions.
 */
const grantedSessions = new Map<string, Promise<void>>();

/** Forget every grant this process made. For tests. */
export function resetProxySessions(): void {
  grantedSessions.clear();
}

/** An ArrayBuffer view Web Crypto accepts, from a Uint8Array that may be a slice. */
function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

/** Where to re-attach a dropped stream: the machine the command ran on. */
export interface ReattachTarget {
  machine: string;
}

/**
 * How long the executor has to ANSWER a request (the response headers) before the client gives up.
 *
 * It bounds the request phase only: the clock stops when the headers arrive, so a command that streams for
 * minutes is never cut. A minute covers an executor that does real work (license recovery, a session grant)
 * before it flushes headers, and still turns a stalled one into an error instead of a hang. Override with
 * REDIACC_PROXY_TIMEOUT_MS (milliseconds), or `timeoutMs` in the options.
 */
const DEFAULT_PROXY_REQUEST_TIMEOUT_MS = 60_000;

/** The host of a request URL; an unparseable URL yields its text up to any query or fragment, so the wrapped network error is never replaced by a URL TypeError and a query token is never echoed. */
function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url.split(/[?#]/, 1)[0];
  }
}

/** The request timeout from the environment, or the default when unset or not a positive number. */
function proxyRequestTimeoutMs(): number {
  const raw = Number(process.env.REDIACC_PROXY_TIMEOUT_MS);
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_PROXY_REQUEST_TIMEOUT_MS;
}

/** What went wrong in a failed fetch, from undici's `cause` ("ECONNREFUSED", "ENOTFOUND", ...) when it has one. */
function describeFetchFailure(error: unknown): string {
  const cause = error instanceof Error ? error.cause : undefined;
  const source = cause ?? error;
  if (!(source instanceof Error)) return String(source);
  const code = (source as { code?: unknown }).code;
  if (typeof code !== 'string') return source.message || source.name;
  // An AggregateError (one refusal per resolved address) has an empty message; the code says it all.
  return source.message && source.message !== code ? `${code} (${source.message})` : code;
}

/** Hand a page's events to the renderer, with their 1-based spool ordinals. True when the page ends the job. */
function deliverPage(
  poll: JobPollResponse,
  onEvent: (event: RenetEvent, line?: number) => void
): boolean {
  for (const entry of poll.events) onEvent(entry.event, entry.line + 1);
  return isTerminalState(poll.status.state) && !poll.more;
}

export class ProxyClient {
  private readonly baseUrl: string;
  private readonly getToken: () => Promise<string>;
  private readonly contractVersion: string;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  private readonly getCek: (() => Promise<CryptoKey>) | undefined;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly random: () => number;
  private readonly lostBudgetMs: number;
  private readonly ticketStore: TicketStore | null | undefined;

  constructor(options: ProxyClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.getToken = options.getToken;
    this.contractVersion = options.contractVersion;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
    this.timeoutMs = options.timeoutMs ?? proxyRequestTimeoutMs();
    this.getCek = options.getCek;
    this.sleep = options.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    this.random = options.random ?? Math.random;
    this.lostBudgetMs = options.lostBudgetMs ?? PROXY_LOST_BUDGET_MS;
    this.ticketStore = options.ticketStore;
  }

  /**
   * Make sure a CONTAINER executor holds this caller's config key, once per
   * process.
   *
   * A container starts with no key and answers every command "This session has
   * no config key yet" until the caller grants one. So: ask the executor what it
   * is; if it is a container, open a session (it mints an X25519 keypair and
   * returns the public half), unwrap the local CEK from the `config remote`
   * enrollment, seal it to that public key, and post the sealed blob. The key
   * never crosses the wire in the clear, and a daemon, which derives its own
   * key, is never sent it at all.
   */
  async ensureSession(): Promise<void> {
    // A client with no key to give (a test harness, a caller that manages its own sessions) leaves the grant to whoever holds one.
    if (!this.getCek) return;
    const key = `${this.baseUrl}\u0000${await this.getToken()}`;
    let grant = grantedSessions.get(key);
    if (!grant) {
      grant = this.grantSession();
      grantedSessions.set(key, grant);
      // A failed grant must not be remembered as done: the next command retries it.
      grant.catch(() => grantedSessions.delete(key));
    }
    return grant;
  }

  private async grantSession(): Promise<void> {
    const info = await this.serverInfo();
    if (info.mode !== 'container') return;

    const getCek = this.getCek;
    if (!getCek) return;

    const opened = await this.post(PROXY_ROUTES.session, {});
    if (!opened.ok) throw new Error(await this.describeFailure(opened));
    const { sessionId, publicKey } = (await opened.json()) as {
      sessionId: string;
      publicKey: string;
    };

    const executorKey = await crypto.subtle.importKey(
      'spki',
      toArrayBuffer(fromBase64(publicKey)),
      { name: 'X25519' },
      false,
      []
    );
    const sealed = await cekHandoffEncrypt(await exportAesKey(await getCek()), executorKey);

    const granted = await this.post(PROXY_ROUTES.sessionCek(sessionId), sealed);
    if (!granted.ok) throw new Error(await this.describeFailure(granted));
  }

  /**
   * Run one command at the executor, forwarding its events as they arrive.
   *
   * The request is the operator's intent and nothing else: a command path and
   * its options. No function name (the executor derives it), no machine address,
   * no key, no config.
   */
  async run(
    pathKey: string,
    params: Record<string, unknown>,
    positionals: Record<string, unknown>,
    onEvent: (event: RenetEvent) => void,
    reattach?: ReattachTarget,
    options: { background?: boolean } = {}
  ): Promise<ProxyCommandOutcome> {
    await this.ensureSession();

    // One id for the invocation: a POST that dropped before the job line is retried with it, so the executor attaches to the job the first one started instead of starting a second.
    const requestId = randomUUID();
    const request: CommandRequest = {
      contractVersion: this.contractVersion,
      pathKey,
      params,
      positionals,
      requestId,
      ...(options.background ? { background: true } : {}),
    };
    traceProxyRequest('sent', request);

    const state: ClientStreamState = {
      eventsSeen: 0,
      highestLine: 0,
      unorderedSeen: 0,
      unorderedSkip: 0,
    };
    await this.startCommand(request, onEvent, state, reattach?.machine);
    return this.finishOrPoll(pathKey, requestId, onEvent, state, reattach, options.background);
  }

  /**
   * POST the command and read its stream into `state`. A POST that dropped, or a stream that
   * broke before the job line, is retried with the same request id (the executor attaches to
   * the job the first one started); after the job line the polls recover the job.
   */
  private async startCommand(
    request: CommandRequest,
    onEvent: (event: RenetEvent) => void,
    state: ClientStreamState,
    fallbackMachine: string | undefined
  ): Promise<void> {
    for (let attempt = 0; ; attempt++) {
      const step = await this.tryStart(
        request,
        onEvent,
        state,
        fallbackMachine,
        attempt < MAX_START_RETRIES
      );
      if (step === 'done') return;
      // The retry waits on the poll ladder (Design 5): 2 s, then 3 s, then 4.5 s.
      await this.sleep(
        jittered(START_RETRY_DELAYS_MS[Math.min(attempt, MAX_START_RETRIES - 1)], this.random)
      );
    }
  }

  private async tryStart(
    request: CommandRequest,
    onEvent: (event: RenetEvent) => void,
    state: ClientStreamState,
    fallbackMachine: string | undefined,
    retriable: boolean
  ): Promise<'done' | 'retry'> {
    let response: Response;
    try {
      response = await this.post(PROXY_ROUTES.command, request);
    } catch (error) {
      if (retriable) return 'retry';
      throw error;
    }
    const body = await this.commandBody(response);
    // A retried attempt replays from the start: what an earlier attempt rendered without an ordinal is skipped.
    state.unorderedSkip = state.unorderedSeen;
    try {
      await this.pumpStream(body, onEvent, state);
      // A clean close with neither a job line, a result nor any output (heartbeats only) dropped before the start was announced: a detachable command is retried like a broken stream. One that printed may have run a command the request id does not dedupe, so it is not re-sent.
      const silentStart = !state.jobId && !state.outcome && state.eventsSeen === 0;
      // The request id dedupes machine job starts only, so another command that ran silently is never sent twice.
      return silentStart && retriable && getCommand(request.pathKey)?.detachable ? 'retry' : 'done';
    } catch (error) {
      return recoverBrokenStream(error, state, fallbackMachine, retriable);
    }
  }

  /** The command response's body, or the refusal it carried. */
  private async commandBody(response: Response): Promise<ReadableStream<Uint8Array>> {
    if (response.status === 409) await this.throwVersionMismatch(response);
    if (!response.ok) throw new Error(await this.describeFailure(response));
    if (!response.body) throw new ProxyStreamTruncatedError(0);
    return response.body;
  }

  /** Probe the executor. Used by `--proxy` startup checks and the loopback harness. */
  async serverInfo(): Promise<ServerInfo> {
    const response = await this.request(`${this.baseUrl}${PROXY_ROUTES.serverInfo}`, {
      headers: await this.headers(),
    });
    if (!response.ok) {
      throw new Error(await this.describeFailure(response));
    }
    return (await response.json()) as ServerInfo;
  }

  /**
   * Return the outcome, or follow the job by polls.
   *
   * A result line that says the job finished is done. A `running` result, or a
   * stream that ended with a job line but no result (the request dropped), means
   * the job outlived the attach window: the client writes the ticket (`via:
   * proxy`) and follows with short polls until a terminal state. A stream with
   * neither a result nor a job is a truncation, surfaced as before.
   */
  private async finishOrPoll(
    pathKey: string,
    requestId: string,
    onEvent: (event: RenetEvent) => void,
    state: StreamState,
    reattach: ReattachTarget | undefined,
    background = false
  ): Promise<ProxyCommandOutcome> {
    const machine = state.machine ?? reattach?.machine;
    if (state.outcome && !state.running) {
      return state.outcome;
    }
    if (!(state.jobId && machine)) {
      if (state.outcome) return state.outcome;
      throw new ProxyStreamTruncatedError(state.eventsSeen);
    }

    const ticket = this.openTicket();
    this.record(ticket, 'started', requestId, {
      jobId: state.jobId,
      machine,
      verb: pathKey,
      state: 'running',
      via: { kind: 'proxy', url: this.baseUrl },
    });
    // `-b`: the ticket is the answer. The job keeps running at the executor, and `rdc job wait <id>` follows it through the proxy later.
    if (background) {
      return { ...(state.outcome ?? emptyOutcome()), jobId: state.jobId, running: true, machine };
    }
    const outcome = await this.followByPolls(
      machine,
      state.jobId,
      onEvent,
      state,
      requestId,
      ticket
    );
    return outcome;
  }

  /**
   * Follow a job this client started earlier (a `-b` ticket with `via: proxy`) by
   * short polls until it is terminal, from `fromLine`. Returns undefined when
   * `signal` aborts first, or when the executor stays unreachable past the lost
   * budget; the job keeps running either way.
   */
  async followJob(
    machine: string,
    jobId: string,
    fromLine: number,
    onEvent: (event: RenetEvent, line?: number) => void,
    signal?: AbortSignal
  ): Promise<JobPollResponse['status'] | undefined> {
    await this.ensureSession();
    const pace = { delay: POLL_FIRST_DELAY_MS };
    const failing: { since?: number } = {};
    let nextLine = fromLine;
    while (!signal?.aborted) {
      const poll = await this.fetchPoll(machine, jobId, nextLine);
      if (!poll) {
        if (await this.retryLostPoll(pace, failing)) continue;
        return undefined;
      }
      failing.since = undefined;
      nextLine = poll.nextLine;
      const done = deliverPage(poll, onEvent);
      if (done) return poll.status;
      await this.pausePoll(pace, poll);
    }
    return undefined;
  }

  /** Wait out one failed poll on the ladder. False once failures have lasted the lost budget. */
  private async retryLostPoll(
    pace: { delay: number },
    failing: { since?: number }
  ): Promise<boolean> {
    failing.since ??= Date.now();
    if (Date.now() - failing.since >= this.lostBudgetMs) return false;
    await this.sleep(jittered(pace.delay, this.random));
    pace.delay = nextPollDelayMs(pace.delay);
    return true;
  }

  private openTicket(): TicketStore | undefined {
    if (this.ticketStore !== undefined) return this.ticketStore ?? undefined;
    try {
      return new TicketStore(getEffectiveConfigName());
    } catch {
      return undefined;
    }
  }

  /** A ticket that cannot be written never fails the command: the job runs on regardless. */
  private record(
    ticket: TicketStore | undefined,
    kind: Parameters<TicketStore['append']>[0],
    requestId: string,
    input: Parameters<TicketStore['append']>[2]
  ): void {
    try {
      ticket?.append(kind, requestId, input);
    } catch {
      // Left as is.
    }
  }

  /**
   * Read one NDJSON stream into `state`, forwarding every renet event.
   *
   * Dedupes on the per-event spool-line ordinal: a resume re-sends the boundary
   * line renet only half-delivered, and skipping any ordinal already seen keeps
   * the reconstruction exactly-once. A `kind:'job'` line records where to
   * re-attach and the offset to resume from.
   */
  private async pumpStream(
    body: ReadableStream<Uint8Array>,
    onEvent: (event: RenetEvent) => void,
    state: ClientStreamState
  ): Promise<void> {
    for await (const raw of readNdjson<unknown>(body, (line) => {
      // Renet occasionally writes unstructured output to the same stream. A stray line must not kill a healthy operation, so surface it as a log event and keep reading.
      onEvent({ type: 'log', level: 'debug', msg: line });
    })) {
      const parsed = StreamLineSchema.safeParse(raw);
      if (parsed.success) this.foldStreamLine(parsed.data, onEvent, state);
    }
  }

  /** Fold one parsed stream line into `state`, forwarding an event to `onEvent`. */
  private foldStreamLine(
    line: StreamLine,
    onEvent: (event: RenetEvent) => void,
    state: ClientStreamState
  ): void {
    if (line.kind === 'job') {
      foldJobLine(line, state);
      return;
    }
    if (line.kind === 'result') {
      foldResultLine(line, state);
      return;
    }
    // A heartbeat only keeps a quiet attach window's connection alive.
    if (line.kind === 'heartbeat') return;
    // An event. Dedupe on the spool-line ordinal so a resumed boundary line renders exactly once.
    if (line.line != null && line.line <= state.highestLine) return;
    if (line.line == null) {
      if (state.unorderedSkip > 0) {
        state.unorderedSkip -= 1;
        return;
      }
      state.unorderedSeen += 1;
    } else {
      state.highestLine = line.line;
    }
    state.eventsSeen += 1;
    // No cast needed: the wire event and RenetEvent are the same shape by construction, which is the point of forwarding renet's events verbatim.
    onEvent(line.event);
  }

  /**
   * Follow a job by short polls (Design 4 and 5): each poll returns the lines past
   * `sinceLine` and the job's status. A page with `more` is followed at once;
   * an empty page waits 2 s, then 3, 4.5 ... up to 30 s (jitter +-20 %); a page
   * with lines resets the pacing. A transport failure or a 5xx is retried on the
   * same offset for up to the lost budget, then the follow is given up with the
   * ticket kept: FOLLOW_LOST. A 4xx (policy, unknown job) is final.
   */
  private async followByPolls(
    machine: string,
    jobId: string,
    onEvent: (event: RenetEvent) => void,
    state: StreamState,
    requestId: string,
    ticket: TicketStore | undefined
  ): Promise<ProxyCommandOutcome> {
    const first = state.outcome;
    const pace = { delay: POLL_FIRST_DELAY_MS };
    let nextLine = 0;
    let failingSince: number | undefined;
    let polls = 0;
    let fn = '';
    for (;;) {
      const poll = await this.fetchPoll(machine, jobId, nextLine);
      polls += 1;
      if (!poll) {
        failingSince ??= Date.now();
        if (Date.now() - failingSince >= this.lostBudgetMs) {
          annotatePolled(jobId, fn, undefined, polls);
          return lostOutcome(jobId, machine, first);
        }
        await this.sleep(jittered(pace.delay, this.random));
        pace.delay = nextPollDelayMs(pace.delay);
        continue;
      }
      failingSince = undefined;
      fn = poll.status.function;
      this.deliver(poll, onEvent, state, ticket, requestId);
      nextLine = poll.nextLine;
      if (isTerminalState(poll.status.state) && !poll.more) {
        this.recordFinished(ticket, requestId, poll.status);
        annotatePolled(jobId, fn, poll.status.state, polls);
        return terminalOutcome(poll.status, jobId, first);
      }
      await this.pausePoll(pace, poll);
    }
  }

  /** Hand a page's events to the renderer and note the offset on the ticket. */
  private deliver(
    poll: JobPollResponse,
    onEvent: (event: RenetEvent) => void,
    state: StreamState,
    ticket: TicketStore | undefined,
    requestId: string
  ): void {
    for (const entry of poll.events) {
      state.eventsSeen += 1;
      onEvent(entry.event);
    }
    this.record(ticket, 'seen', requestId, { lastSeenLine: poll.nextLine });
  }

  /** One poll: the page, or undefined for a failure worth retrying (transport, 5xx, a body that is not a poll). A 4xx is final. */
  private async fetchPoll(
    machine: string,
    jobId: string,
    sinceLine: number
  ): Promise<JobPollResponse | undefined> {
    const query = `machine=${encodeURIComponent(machine)}&sinceLine=${sinceLine}&maxLines=${POLL_MAX_LINES}`;
    let response: Response;
    try {
      response = await this.request(`${this.baseUrl}${PROXY_ROUTES.jobPoll(jobId)}?${query}`, {
        headers: await this.headers(),
      });
    } catch {
      return undefined;
    }
    if (!response.ok) {
      if (response.status < 500) throw new Error(await this.describeFailure(response));
      return undefined;
    }
    const parsed = JobPollResponseSchema.safeParse(await response.json().catch(() => undefined));
    return parsed.success ? parsed.data : undefined;
  }

  /** Wait before the next poll: none after a page that says more, the first delay after a page with lines, and a growing one after an empty page. */
  private async pausePoll(pace: { delay: number }, poll: JobPollResponse): Promise<void> {
    if (poll.more) {
      pace.delay = POLL_FIRST_DELAY_MS;
      return;
    }
    if (poll.events.length > 0) pace.delay = POLL_FIRST_DELAY_MS;
    await this.sleep(jittered(pace.delay, this.random));
    if (poll.events.length === 0) pace.delay = nextPollDelayMs(pace.delay);
  }

  private recordFinished(
    ticket: TicketStore | undefined,
    requestId: string,
    status: JobPollResponse['status']
  ): void {
    this.record(ticket, 'finished', requestId, {
      state: status.state,
      ...(status.exitCode === undefined ? {} : { exitCode: status.exitCode }),
      ...(status.finishedAt ? { finishedAt: status.finishedAt } : {}),
    });
  }

  /**
   * fetch with a deadline on the RESPONSE HEADERS and a readable failure.
   *
   * The timer is cleared once fetch resolves, so it never reaches into the body stream. A rejection is
   * rethrown as a NETWORK_ERROR naming the executor host and undici's cause, which fetch itself drops
   * behind a bare "fetch failed".
   */
  private async request(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.timeoutMs);
    try {
      return await this.fetchImpl(url, { ...init, signal: controller.signal });
    } catch (error) {
      const host = hostOf(url);
      const message = timedOut
        ? t('errors.proxy.timeout', { host, seconds: Math.ceil(this.timeoutMs / 1000) })
        : t('errors.proxy.unreachable', { host, reason: describeFetchFailure(error) });
      const failure = new CliExitError(ERROR_CODES.NETWORK_ERROR, message, { retryable: true });
      failure.cause = error;
      throw failure;
    } finally {
      clearTimeout(timer);
    }
  }

  private async post(path: string, body: unknown): Promise<Response> {
    return this.request(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { ...(await this.headers()), 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  private async headers(): Promise<Record<string, string>> {
    return {
      authorization: `Bearer ${await this.getToken()}`,
      accept: 'application/x-ndjson',
      [CLI_VERSION_HEADER]: VERSION,
      [CONTRACT_VERSION_HEADER]: this.contractVersion,
    };
  }

  private async throwVersionMismatch(response: Response): Promise<never> {
    const body = VersionMismatchSchema.safeParse(await response.json().catch(() => ({})));
    if (body.success) {
      throw new ProxyVersionMismatchError(
        body.data.clientContractVersion,
        body.data.executorContractVersion,
        body.data.executorCliVersion
      );
    }
    throw new ProxyVersionMismatchError(this.contractVersion, 'unknown', 'unknown');
  }

  /** Turn a non-OK response into an operator-readable message. */
  private async describeFailure(response: Response): Promise<string> {
    const text = await response.text().catch(() => '');
    const detail = text.slice(0, 500);

    if (response.status === 401 || response.status === 403) {
      return `Proxy rejected this request (${response.status}). The token may be expired, or policy may not allow this command. ${detail}`;
    }
    return `Proxy request failed (${response.status} ${response.statusText}). ${detail}`;
  }
}
