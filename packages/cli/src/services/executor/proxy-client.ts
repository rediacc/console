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

import { readNdjson } from '@rediacc/shared/cli-contract/ndjson';
import {
  CLI_VERSION_HEADER,
  CONTRACT_VERSION_HEADER,
  type CommandRequest,
  PROXY_ROUTES,
  type ServerInfo,
  type StreamLine,
  StreamLineSchema,
  VersionMismatchSchema,
} from '@rediacc/shared/cli-contract/wire';
import { cekHandoffEncrypt, exportAesKey, fromBase64 } from '@rediacc/shared/config-crypto';
import { VERSION } from '../../version.js';
import type { RenetEvent } from './types.js';

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
  /**
   * Unwraps this device's config key (CEK). Called only when the executor is a
   * CONTAINER, which holds no key of its own and can open the config only with
   * one granted per session. A daemon derives its own and is never sent one.
   */
  getCek?: () => Promise<CryptoKey>;
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

/** What the executor reported: how it ended, and what the command printed. */
export interface ProxyCommandOutcome {
  success: boolean;
  exitCode: number;
  error?: string;
  /** What the command rendered: its envelope, its table. Printed verbatim. */
  stdout: string;
  /** Raw bytes the command wrote instead (`repo cat` of a binary file). Written verbatim. */
  stdoutBytes?: Uint8Array;
  stderr: string;
  /**
   * Renet's own output, captured at the executor.
   *
   * Normally already seen: in events mode renet's output arrives as `output`
   * events and is rendered live, exactly as it streams to the terminal on a
   * laptop. This is the same bytes, kept for the run that emitted no output
   * events at all, so the operator is never left staring at a command that
   * printed nothing.
   */
  renetStdout: string;
  /** True when at least one `output` event was rendered live. */
  renderedLiveOutput: boolean;
}

/** Where to re-attach a dropped stream: the machine the command ran on. */
export interface ReattachTarget {
  machine: string;
}

/** How many times a dropped proxy stream is re-attached before giving up. */
const MAX_REATTACHES = 5;

/** Build the outcome from a result line. renderedLiveOutput is filled in by the reader. */
function toOutcome(line: Extract<StreamLine, { kind: 'result' }>): ProxyCommandOutcome {
  return {
    success: line.result.success,
    exitCode: line.result.exitCode,
    error: line.result.error,
    stdout: line.stdout ?? '',
    ...(line.stdoutBase64 === undefined
      ? {}
      : { stdoutBytes: new Uint8Array(Buffer.from(line.stdoutBase64, 'base64')) }),
    stderr: line.stderr ?? '',
    renetStdout: line.result.stdout ?? '',
    renderedLiveOutput: false,
  };
}

/** What a stream read so far, carried across a re-attach so a resume dedupes correctly. */
interface StreamState {
  eventsSeen: number;
  renderedLiveOutput: boolean;
  /** The detached job the executor handed the work to, once it announced one. */
  jobId?: string;
  /** The highest spool-line ordinal delivered, so a resume skips what it already has. */
  highestLine: number;
  /** The terminal result, once it lands. */
  outcome?: ProxyCommandOutcome;
}

export class ProxyClient {
  private readonly baseUrl: string;
  private readonly getToken: () => Promise<string>;
  private readonly contractVersion: string;
  private readonly fetchImpl: typeof fetch;
  private readonly getCek: (() => Promise<CryptoKey>) | undefined;

  constructor(options: ProxyClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.getToken = options.getToken;
    this.contractVersion = options.contractVersion;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
    this.getCek = options.getCek;
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
    reattach?: ReattachTarget
  ): Promise<ProxyCommandOutcome> {
    await this.ensureSession();

    const request: CommandRequest = {
      contractVersion: this.contractVersion,
      pathKey,
      params,
      positionals,
    };

    const response = await this.post(PROXY_ROUTES.command, request);

    if (response.status === 409) {
      await this.throwVersionMismatch(response);
    }
    if (!response.ok) {
      throw new Error(await this.describeFailure(response));
    }
    if (!response.body) {
      throw new ProxyStreamTruncatedError(0);
    }

    const state: StreamState = { eventsSeen: 0, renderedLiveOutput: false, highestLine: 0 };
    try {
      await this.pumpStream(response.body, onEvent, state);
    } catch (error) {
      // A transport error mid-stream is exactly what re-attach exists to recover. Fall through when the executor announced a job and we know the
      // machine; otherwise the failure is genuine and propagates.
      if (!(state.jobId && reattach)) throw error;
    }

    return this.finishOrReattach(onEvent, state, reattach);
  }

  /** Probe the executor. Used by `--proxy` startup checks and the loopback harness. */
  async serverInfo(): Promise<ServerInfo> {
    const response = await this.fetchImpl(`${this.baseUrl}${PROXY_ROUTES.serverInfo}`, {
      headers: await this.headers(),
    });
    if (!response.ok) {
      throw new Error(await this.describeFailure(response));
    }
    return (await response.json()) as ServerInfo;
  }

  /**
   * Return the outcome, or re-attach to the detached job and resume.
   *
   * A stream that ended with a result line is done. One that ended WITHOUT a
   * result but that announced a job (`kind:'job'`) means the connection dropped
   * before the work finished; if we know the machine, we re-attach to the job's
   * spool and resume from the last complete line rather than reporting a failure
   * for work that is still running. Only when there is nothing to resume to is
   * the truncation surfaced, exactly as before.
   */
  private async finishOrReattach(
    onEvent: (event: RenetEvent) => void,
    state: StreamState,
    reattach: ReattachTarget | undefined
  ): Promise<ProxyCommandOutcome> {
    if (state.outcome) {
      state.outcome.renderedLiveOutput = state.renderedLiveOutput;
      return state.outcome;
    }

    if (state.jobId && reattach) {
      const resumed = await this.reattachToJob(reattach.machine, state.jobId, onEvent, state);
      if (resumed) {
        resumed.renderedLiveOutput = state.renderedLiveOutput;
        return resumed;
      }
    }

    throw new ProxyStreamTruncatedError(state.eventsSeen);
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
    state: StreamState
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
    state: StreamState
  ): void {
    if (line.kind === 'job') {
      state.jobId = line.jobId;
      if (line.sinceLine > state.highestLine) state.highestLine = line.sinceLine;
      return;
    }
    if (line.kind === 'result') {
      state.outcome = toOutcome(line);
      return;
    }
    // An event. Dedupe on the spool-line ordinal so a resumed boundary line renders exactly once.
    if (line.line != null && line.line <= state.highestLine) return;
    if (line.line != null) state.highestLine = line.line;
    state.eventsSeen += 1;
    if (line.event.type === 'output') state.renderedLiveOutput = true;
    // No cast needed: the wire event and RenetEvent are the same shape by construction, which is the point of forwarding renet's events verbatim.
    onEvent(line.event);
  }

  /**
   * Re-attach to a detached job and resume its stream from the last line seen.
   *
   * Reconnecting is cheap and safe: the job runs on the machine regardless, so a
   * resume only changes what we can SEE of it. Each attempt resumes from the
   * current high-water line, so a stream that drops again simply reconnects
   * without losing or repeating a line. Returns undefined when every attempt is
   * exhausted, leaving the caller to surface the truncation.
   */
  private async reattachToJob(
    machine: string,
    jobId: string,
    onEvent: (event: RenetEvent) => void,
    state: StreamState
  ): Promise<ProxyCommandOutcome | undefined> {
    for (let attempt = 0; attempt < MAX_REATTACHES; attempt++) {
      const query = `machine=${encodeURIComponent(machine)}&sinceLine=${state.highestLine}`;
      const url = `${this.baseUrl}${PROXY_ROUTES.jobEvents(jobId)}?${query}`;

      let response: Response;
      try {
        response = await this.fetchImpl(url, { headers: await this.headers() });
      } catch {
        continue; // network blip; resume from the same offset
      }
      if (!response.ok || !response.body) continue;

      try {
        await this.pumpStream(response.body, onEvent, state);
      } catch {
        continue; // stream dropped again; the loop resumes from highestLine
      }
      if (state.outcome) return state.outcome;
    }
    return undefined;
  }

  private async post(path: string, body: unknown): Promise<Response> {
    return this.fetchImpl(`${this.baseUrl}${path}`, {
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
