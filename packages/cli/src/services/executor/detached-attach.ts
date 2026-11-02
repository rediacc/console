/**
 * The `job start --attach` exec of a detached call (see detached-execution.ts):
 * one start attempt, the line reader that classifies its stream, and how a
 * failed start is told apart. The call state it reports into is `AttachRun`.
 */

import type { JobOverlap } from '@rediacc/shared/cli-contract/wire';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { writeStdout } from '../core/request-context.js';
import {
  type buildJobStartCommand,
  handleOverlaps,
  isJobStartUnsupported,
  type JobStatus,
  type PreconditionRefusal,
  parseAttachLine,
  parseJobHandle,
  parseOverlapRefusal,
  parsePreconditionRefusal,
} from './job-client.js';
import { capReason } from './renet-output.js';
import type { RenetEvent } from './types.js';

type Launch = ReturnType<typeof buildJobStartCommand>;

/** What a call exposes to its attach reader. */
export interface AttachRun {
  readonly window: number | undefined;
  readonly state: AttachState;
  announce(jobId: string, overlaps: JobOverlap[], deduped: boolean, networkId?: number): void;
  onEvent(event: RenetEvent, line: number): void;
}

/** What the attach has seen of the job so far. */
export interface AttachState {
  jobId?: string;
  /** Spool lines delivered (events between the handle and the trailer). */
  lines: number;
  overlaps: JobOverlap[];
  deduped: boolean;
  status?: JobStatus;
  /** The network ID the start allocated for a `network_id: "auto"` vault. */
  networkId?: number;
}

export type StartOutcome =
  | { kind: 'trailer' }
  | { kind: 'handle' }
  | { kind: 'dropped'; error: Error }
  | { kind: 'interrupted' }
  | { kind: 'refused'; overlaps: JobOverlap[] }
  | { kind: 'precondition'; refusal: PreconditionRefusal }
  | { kind: 'unsupported' }
  | { kind: 'failed'; detail: string };

/**
 * Reads one `job start --attach` stream line by line: the handle, the events
 * (one per spool line, which is what the cursor counts) and the trailer.
 */
class AttachReader {
  private readonly out: string[] = [];
  private readonly err: string[] = [];
  private trailers = 0;
  private buffered = '';
  private lineNo = 0;
  /** A retried start replays the spool from line 0 (renet dedupes onto the first job), so a line already delivered is not rendered twice. */
  private readonly deliveredBefore: number;

  constructor(
    private readonly run: AttachRun,
    private readonly streaming: boolean
  ) {
    this.deliveredBefore = run.state.lines;
  }

  get stdout(): string {
    return this.out.join('');
  }

  get stderr(): string {
    return this.err.join('');
  }

  /** Whether the status trailer arrived: the stream reached its end. */
  get sawTrailer(): boolean {
    return this.trailers > 0;
  }

  feedErr(text: string): void {
    this.err.push(text);
  }

  feed(text: string): void {
    this.out.push(text);
    if (!this.streaming) return;
    this.buffered += text;
    const lines = this.buffered.split('\n');
    this.buffered = lines.pop() ?? '';
    for (const line of lines) this.consume(line);
  }

  flush(): void {
    if (this.buffered.trim()) this.consume(this.buffered);
    this.buffered = '';
  }

  private consume(raw: string): void {
    const line = raw.trim();
    const parsed = line ? parseAttachLine(line) : ({ kind: 'raw', text: '' } as const);
    if (parsed.kind === 'handle') {
      this.run.announce(parsed.jobId, parsed.overlaps, parsed.deduped, parsed.networkId);
    } else if (parsed.kind === 'status') {
      this.run.state.status = parsed.status;
      if (parsed.overlaps.length > 0) this.run.state.overlaps = parsed.overlaps;
      this.trailers += 1;
    } else if (parsed.kind !== 'refusal' && parsed.kind !== 'precondition') {
      this.spoolLine(parsed);
    }
  }

  private spoolLine(
    parsed: { kind: 'event'; event: RenetEvent } | { kind: 'raw'; text: string }
  ): void {
    this.lineNo += 1;
    if (this.lineNo <= this.deliveredBefore) return;
    this.run.state.lines = this.lineNo;
    if (parsed.kind === 'event') this.run.onEvent(parsed.event, this.lineNo);
    else if (parsed.text) writeStdout(`${parsed.text}\n`);
  }
}

/** One `job start` exec, classifying every line it streams. */
export async function startOnce(
  sftp: SFTPClient,
  launch: Launch,
  vault: string,
  run: AttachRun
): Promise<StartOutcome> {
  const reader = new AttachReader(run, run.window !== 0);
  const interrupt = run.window === undefined ? watchSigint() : undefined;
  const exec = sftp
    .execStreaming(launch.command, {
      stdin: launch.stdinPrefix + vault,
      onStdout: (data) => reader.feed(data.toString()),
      onStderr: (data) => {
        reader.feedErr(data.toString());
      },
    })
    .catch((error: unknown) => (error instanceof Error ? error : new Error(String(error))));

  let raced: number | undefined | Error | 'interrupted';
  try {
    raced = interrupt ? await Promise.race([exec, interrupt.promise]) : await exec;
  } finally {
    interrupt?.dispose();
  }
  if (raced === 'interrupted') return { kind: 'interrupted' };
  if (raced instanceof Error) return { kind: 'dropped', error: raced };
  if (typeof raced !== 'number') {
    return { kind: 'dropped', error: new Error('job start closed without an exit status') };
  }
  if (raced !== 0) return classifyFailedStart(reader, run);
  if (run.window === 0) return readPlainHandle(reader, run);

  reader.flush();
  if (reader.sawTrailer) return { kind: 'trailer' };
  // Exit 0 with no trailer: the stream was cut short. Treat it as a drop.
  return { kind: 'dropped', error: new Error('job start ended without a status trailer') };
}

/** A non-zero `job start`: an overlap or precondition refusal, an old renet, or a failure. */
function classifyFailedStart(reader: AttachReader, run: AttachRun): StartOutcome {
  const refusal = parseOverlapRefusal(reader.stdout);
  if (refusal) return { kind: 'refused', overlaps: refusal };
  const precondition = parsePreconditionRefusal(reader.stdout);
  if (precondition) return { kind: 'precondition', refusal: precondition };
  if (isJobStartUnsupported(reader.stdout + reader.stderr)) return { kind: 'unsupported' };
  const detail = capReason((reader.stderr || reader.stdout).trim());
  // A renet that started the job and then failed to stream it: the job is running, so reattach rather than fail.
  if (run.state.jobId) return { kind: 'dropped', error: new Error(detail) };
  return { kind: 'failed', detail };
}

/** A `-b` start prints the plain handle (no attach stream). */
function readPlainHandle(reader: AttachReader, run: AttachRun): StartOutcome {
  const handle = parseJobHandle(reader.stdout);
  const extra = handleOverlaps(reader.stdout);
  run.announce(handle.job_id, extra.overlaps, extra.deduped, extra.networkId);
  return { kind: 'handle' };
}

/** Ctrl-C while attached detaches (never cancels), as a follow always has. */
function watchSigint(): { promise: Promise<'interrupted'>; dispose: () => void } {
  let dispose = () => {};
  const promise = new Promise<'interrupted'>((resolve) => {
    const fire = () => resolve('interrupted');
    process.once('SIGINT', fire);
    dispose = () => process.removeListener('SIGINT', fire);
  });
  return { promise, dispose };
}
