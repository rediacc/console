/**
 * The proxy wire protocol.
 *
 * ONE request shape and one event stream, spoken by three parties:
 *   - `rdc --proxy` (the thin client in services/executor/proxy-client.ts)
 *   - the web console
 *   - `rdc serve` (the executor, container or customer daemon)
 *
 * A request names a COMMAND ("repo fork") and its options. It does not name a
 * renet function. It cannot: the command-to-function mapping lives inside each
 * Commander action body and exists nowhere else, so only something holding the
 * CLI can perform it. The executor holds the CLI and does it server-side.
 *
 * There WAS a second, function-level request (/v1/exec, plus a hand-kept map of
 * the 25 functions anyone had bothered to name). It is gone. It failed closed on
 * every unmapped command, and worse, `rdc --proxy` could not actually reach it:
 * a command's action body reads and writes local config on its way to the
 * executor seam, so a client with no config died before it got there. One wire,
 * one policy anchor (the command path), no map to drift.
 *
 * DESIGN RULE, and the reason the proxy is enforcing rather than advisory:
 * a request carries COMMAND INTENT ONLY. It carries no SSH key, no machine IP,
 * no storage credential, no master password, and no decrypted config of any
 * kind. The executor holds all of that and resolves it server-side. If a field
 * here ever needs a config value to fill in, that field is in the wrong place.
 *
 * Responses are NDJSON: one JSON object per line, renet's own event format
 * forwarded verbatim, terminated by a single `result` line carrying the
 * execution envelope and whatever the command printed. Plain fetch + a line
 * splitter reads it, so no SSE or WebSocket machinery is needed on either end.
 */

import { z } from 'zod';

/** Header carrying the CLI version, so an executor can reject an incompatible client. */
export const CLI_VERSION_HEADER = 'x-rdc-cli-version';
/** Header carrying the contract version the client generated its request from. */
export const CONTRACT_VERSION_HEADER = 'x-rdc-contract-version';

/**
 * A request: the operator's intent, in the operator's own words.
 *
 * The client sends the command PATH and nothing else of substance. The executor
 * runs its own Commander tree to resolve the command, the renet function and its
 * params exactly as a local `rdc` would, and policy is evaluated on that path.
 *
 * A client that sent both a path AND a function could make them disagree, and
 * then the policy check would be guarding a label while something else ran.
 * Sending only the path removes that possibility by construction: what was
 * authorized is what executes, because the executor derived one from the other.
 *
 * `params` are keyed by the command's LONG FLAG ("parent", "tag", "machine").
 * `positionals` are keyed by the command's POSITIONAL name ("ref", "job-id").
 * The executor rejects any key that is not a declared option or positional of
 * that command, so a caller cannot smuggle argv through either bag.
 */
export const CommandRequestSchema = z.object({
  /** Contract version the client built this request from. Mismatch is a 409. */
  contractVersion: z.string().min(1),
  /** Space-separated contract path, e.g. "repo fork". Must exist in the contract. */
  pathKey: z.string().min(1),
  /** Option values keyed by long flag. Booleans are switches; arrays are variadic. */
  params: z.record(z.string(), z.unknown()).default({}),
  /**
   * Positional values keyed by positional name. A string, or a string[] for a
   * variadic positional. Kept SEPARATE from params: a positional is emitted bare
   * (before the flags), and mixing the two bags would lose that ordering.
   */
  positionals: z.record(z.string(), z.unknown()).default({}),
});

export type CommandRequest = z.infer<typeof CommandRequestSchema>;

/**
 * A streamed renet event, forwarded verbatim from the machine.
 *
 * Structurally identical to the CLI's own RenetEvent, which is the point: the
 * client's existing render path (spinners, step timeline) consumes proxied
 * events without knowing they came over HTTP.
 */
export const WireEventSchema = z.object({
  type: z.enum(['log', 'step_start', 'step_done', 'output', 'result']),
  ts: z.string().optional(),
  name: z.string().optional(),
  msg: z.string().optional(),
  level: z.string().optional(),
  duration_ms: z.number().optional(),
  detail: z.string().optional(),
  data: z.unknown().optional(),
});

export type WireEvent = z.infer<typeof WireEventSchema>;

/** The execution envelope, mirroring the CLI's ExecuteResult. */
export const WireResultSchema = z.object({
  success: z.boolean(),
  exitCode: z.number(),
  error: z.string().optional(),
  errorCode: z.string().optional(),
  errorGuidance: z.string().optional(),
  licenseFailureReason: z.string().optional(),
  durationMs: z.number(),
  operationDurationMs: z.number().optional(),
  stdout: z.string().optional(),
  stderr: z.string().optional(),
  outputEchoed: z.boolean().optional(),
  steps: z
    .array(z.object({ name: z.string(), duration_ms: z.number(), detail: z.string().optional() }))
    .optional(),
  cliSteps: z
    .array(
      z.object({
        name: z.string(),
        duration_ms: z.number(),
        startedAtMs: z.number().optional(),
      })
    )
    .optional(),
  allSteps: z
    .array(z.object({ name: z.string(), duration_ms: z.number(), detail: z.string().optional() }))
    .optional(),
});

export type WireResult = z.infer<typeof WireResultSchema>;

/**
 * One line of the response stream.
 *
 * Exactly one `result` line is emitted, last. A stream that ends without it
 * means the executor died mid-operation, and the client must surface that as a
 * failure rather than as success with no output.
 */
export const StreamLineSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('event'),
    event: WireEventSchema,
    /**
     * The event's 1-based spool-line ordinal, present only on a detached job's
     * replayed stream. A re-attaching client dedupes on it, so a resume that
     * re-sends a boundary line renders it exactly once. Absent on a synchronous
     * stream, where there is no spool to resume from.
     */
    line: z.number().int().positive().optional(),
  }),
  z.object({
    kind: z.literal('result'),
    result: WireResultSchema,
    /**
     * What the COMMAND printed, which is not the same thing as `result.stdout`.
     *
     * `result.stdout` is renet's output, captured from the machine. This is what
     * the command itself rendered: its JSON envelope, its table, its warnings.
     * On a laptop it would have gone straight to the terminal. A proxy client
     * prints it verbatim, so `rdc --proxy repo status` shows exactly what
     * `rdc repo status` shows; without it the client would have nothing to say.
     */
    stdout: z.string().optional(),
    stderr: z.string().optional(),
  }),
  z.object({
    kind: z.literal('job'),
    jobId: z.string(),
    /** Line offset to resume from when re-attaching to a detached job. */
    sinceLine: z.number().int().nonnegative().default(0),
  }),
]);

export type StreamLine = z.infer<typeof StreamLineSchema>;

/** Body of a 409 version-mismatch response. */
export const VersionMismatchSchema = z.object({
  error: z.literal('contract_version_mismatch'),
  clientContractVersion: z.string(),
  executorContractVersion: z.string(),
  executorCliVersion: z.string(),
});

export type VersionMismatch = z.infer<typeof VersionMismatchSchema>;

/** What `GET /v1/server-info` returns. Lets a client check compatibility up front. */
export const ServerInfoSchema = z.object({
  cliVersion: z.string(),
  contractVersion: z.string(),
  mode: z.enum(['container', 'daemon']),
  /** Present when the executor is bound to one org and team. */
  scope: z.object({ orgId: z.string(), teamId: z.string() }).optional(),
});

export type ServerInfo = z.infer<typeof ServerInfoSchema>;

/** Route paths, shared so client and server cannot drift. */
export const PROXY_ROUTES = {
  /** Run a command. The only execution route: both clients speak it. */
  command: '/v1/command',
  health: '/v1/health',
  serverInfo: '/v1/server-info',
  session: '/v1/session',
  sessionCek: (sessionId: string) => `/v1/session/${sessionId}/cek`,
  /** The same route as a server-side pattern, so the two cannot drift apart. */
  sessionCekPattern: '/v1/session/:id/cek',
  /** Re-attach to a detached job's event stream: `?machine=<m>&sinceLine=<n>`. */
  jobEvents: (jobId: string) => `/v1/jobs/${jobId}/events`,
  /** The same route as a server-side pattern, so client and server cannot drift. */
  jobEventsPattern: '/v1/jobs/:id/events',
} as const;
