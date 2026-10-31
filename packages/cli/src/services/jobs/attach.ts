/**
 * The hybrid attach (agent/plans/PLAN-detached-jobs.md sections 15-17): how long
 * an entry point stays attached to the machine job it starts, the request id
 * that makes a retried start attach to the same job, and the origin a job
 * records about who started it.
 *
 * One knob decides between a direct result and a ticket: the attach window,
 * set by the entry point and never by the verb. No table of long and short
 * verbs exists anywhere; duration alone decides.
 *
 * | Entry point             | Window                  |
 * |-------------------------|-------------------------|
 * | direct SSH (terminal)   | unlimited (`undefined`) |
 * | `--proxy`, web console  | JOB_ATTACH_WINDOW_MS    |
 * | MCP tool (child `rdc`)  | JOB_ATTACH_WINDOW_MS    |
 * | `-b` / `--background`   | 0 (ticket at once)      |
 */

import { randomUUID } from 'node:crypto';

/** The attach window of the proxy, the web console and MCP (operator ruling, fourth round). */
export const JOB_ATTACH_WINDOW_MS = 20_000;

/** Test-only override of JOB_ATTACH_WINDOW_MS, in milliseconds. */
export const JOB_ATTACH_WINDOW_ENV = 'REDIACC_JOB_ATTACH_WINDOW_MS';

/**
 * Names the client kind of this `rdc` process when it is not a plain terminal
 * run: the MCP server sets `mcp` on the child `rdc` it spawns (J8), so the
 * child attaches for the MCP window and records `client: mcp` as its origin.
 */
export const JOB_CLIENT_ENV = 'REDIACC_JOB_CLIENT';

/** How long a dropped direct attach keeps trying to reattach before it gives up with the ticket kept (section 16). */
export const REATTACH_BUDGET_MS = 120_000;

/** Who starts a job, as renet records it in `origin.client`. */
export type JobClientKind = 'rdc' | 'proxy' | 'mcp' | 'console' | 'scheduler';

const CLIENT_KINDS: readonly JobClientKind[] = [
  'rdc',
  'proxy',
  'mcp',
  'console',
  'scheduler',
] as const;

/** The client kind named by JOB_CLIENT_ENV, else `rdc`. */
export function clientKindFromEnv(env: NodeJS.ProcessEnv = process.env): JobClientKind {
  const raw = env[JOB_CLIENT_ENV];
  return CLIENT_KINDS.includes(raw as JobClientKind) ? (raw as JobClientKind) : 'rdc';
}

/** JOB_ATTACH_WINDOW_MS, or its test override when set to a non-negative integer. */
function jobAttachWindowMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = env[JOB_ATTACH_WINDOW_ENV];
  if (raw !== undefined && /^\d+$/.test(raw)) return Number.parseInt(raw, 10);
  return JOB_ATTACH_WINDOW_MS;
}

/** What the executor seam knows about the entry point of a call. */
export interface AttachEntry {
  /** `-b` / `--background` was given. */
  background: boolean;
  /** The call runs inside a served dispatch (the proxy or the web console). */
  served: boolean;
  /** The client kind of this process (JOB_CLIENT_ENV). */
  client: JobClientKind;
}

/**
 * The attach window for an entry point, in milliseconds. `undefined` is
 * unlimited: the call stays attached for the whole run. 0 returns the ticket
 * the moment the job starts.
 */
export function attachWindowMs(
  entry: AttachEntry,
  env: NodeJS.ProcessEnv = process.env
): number | undefined {
  if (entry.background) return 0;
  if (entry.served || entry.client === 'mcp') return jobAttachWindowMs(env);
  return undefined;
}

/**
 * The `--attach` flag value for a window, as a Go duration. `undefined`
 * (unlimited) is `0s`, renet's "until the job is terminal". A window of 0 never
 * reaches renet as `--attach`: a `-b` start prints the handle and returns.
 */
export function attachFlagValue(windowMs: number | undefined): string {
  return windowMs === undefined ? '0s' : `${windowMs}ms`;
}

// --- request ids -------------------------------------------------------------

/** renet's request-id grammar (private/renet/pkg/jobs/jobs.go requestIDPattern). */
const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:@-]{0,199}$/;

/** Whether renet accepts this request id. */
export function isValidRequestId(id: string): boolean {
  return REQUEST_ID_PATTERN.test(id);
}

/**
 * One invocation's request ids (section 17). The invocation id is minted once
 * (a UUID); each job of the invocation uses `<invocation>:<machine>:<seq>`, so a
 * second machine call of the same command is a different job while a retried
 * start of the same call is the same one.
 */
export class RequestIdMinter {
  private readonly seqByMachine = new Map<string, number>();

  constructor(readonly invocationId: string = randomUUID()) {
    if (!isValidRequestId(invocationId)) {
      throw new Error(`Invalid request id: ${JSON.stringify(invocationId)}`);
    }
  }

  /** The request id of the next job this invocation starts on `machine`. */
  next(machine: string): string {
    const seq = (this.seqByMachine.get(machine) ?? 0) + 1;
    this.seqByMachine.set(machine, seq);
    const safeMachine = machine.replace(/[^A-Za-z0-9._@-]/g, '-').slice(0, 80) || 'machine';
    return `${this.invocationId}:${safeMachine}:${seq}`;
  }
}

let processMinter: RequestIdMinter | undefined;

/** The minter of this process's invocation (one `rdc` run is one invocation). */
export function invocationMinter(): RequestIdMinter {
  processMinter ??= new RequestIdMinter();
  return processMinter;
}

/** Test seam: start a fresh invocation (optionally with a fixed id). */
export function resetInvocationMinter(invocationId?: string): void {
  processMinter = invocationId === undefined ? undefined : new RequestIdMinter(invocationId);
}

// --- origin ------------------------------------------------------------------

/** renet's cap on `--origin` (private/renet/pkg/jobs ParseOrigin). */
export const ORIGIN_MAX_BYTES = 1024;

/** What `job start --origin` carries. renet adds `ssh_user` from SUDO_USER itself. */
export interface JobOrigin {
  client: JobClientKind;
  version?: string;
  config?: { name?: string; id?: string };
  actor?: string;
}

/**
 * The `--origin` JSON for a job start, within renet's 1 KiB cap. A field that
 * would push it past the cap is dropped (actor first, then the config id),
 * because a start must never fail over a label.
 */
export function originJson(origin: JobOrigin): string {
  const candidates: JobOrigin[] = [
    origin,
    { ...origin, actor: undefined },
    {
      ...origin,
      actor: undefined,
      config: origin.config ? { name: origin.config.name } : undefined,
    },
    { client: origin.client },
  ];
  for (const candidate of candidates) {
    const json = JSON.stringify(candidate);
    if (Buffer.byteLength(json, 'utf8') <= ORIGIN_MAX_BYTES) return json;
  }
  return JSON.stringify({ client: origin.client });
}
