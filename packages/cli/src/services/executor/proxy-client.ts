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
}

/** What the executor reported: how it ended, and what the command printed. */
export interface ProxyCommandOutcome {
  success: boolean;
  exitCode: number;
  error?: string;
  /** What the command rendered: its envelope, its table. Printed verbatim. */
  stdout: string;
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

/** Build the outcome from a result line. renderedLiveOutput is filled in by the reader. */
function toOutcome(line: Extract<StreamLine, { kind: 'result' }>): ProxyCommandOutcome {
  return {
    success: line.result.success,
    exitCode: line.result.exitCode,
    error: line.result.error,
    stdout: line.stdout ?? '',
    stderr: line.stderr ?? '',
    renetStdout: line.result.stdout ?? '',
    renderedLiveOutput: false,
  };
}

export class ProxyClient {
  private readonly baseUrl: string;
  private readonly getToken: () => Promise<string>;
  private readonly contractVersion: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ProxyClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.getToken = options.getToken;
    this.contractVersion = options.contractVersion;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
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
    onEvent: (event: RenetEvent) => void
  ): Promise<ProxyCommandOutcome> {
    const request: CommandRequest = {
      contractVersion: this.contractVersion,
      pathKey,
      params,
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

    return this.consumeStream(response.body, onEvent);
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
   * Read the NDJSON response: forward every renet event as it arrives, and
   * return the terminal result.
   */
  private async consumeStream(
    body: ReadableStream<Uint8Array>,
    onEvent: (event: RenetEvent) => void
  ): Promise<ProxyCommandOutcome> {
    let outcome: ProxyCommandOutcome | undefined;
    let eventsSeen = 0;
    let renderedLiveOutput = false;

    for await (const raw of readNdjson<unknown>(body, (line) => {
      // Renet occasionally writes unstructured output to the same stream. A
      // stray line must not kill a healthy operation, so surface it as a log
      // event and keep reading.
      onEvent({ type: 'log', level: 'debug', msg: line });
    })) {
      const parsed = StreamLineSchema.safeParse(raw);
      if (!parsed.success) continue;

      const line: StreamLine = parsed.data;
      if (line.kind === 'event') {
        eventsSeen += 1;
        if (line.event.type === 'output') renderedLiveOutput = true;
        // No cast needed: the wire event and RenetEvent are the same shape by
        // construction, which is the point of forwarding renet's events verbatim.
        onEvent(line.event);
      } else if (line.kind === 'result') {
        outcome = toOutcome(line);
      }
    }

    if (!outcome) {
      throw new ProxyStreamTruncatedError(eventsSeen);
    }
    // Set last: whether output was rendered live is only known once the whole
    // stream has been read.
    outcome.renderedLiveOutput = renderedLiveOutput;
    return outcome;
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
