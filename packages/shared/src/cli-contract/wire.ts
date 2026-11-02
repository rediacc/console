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
  /**
   * The invocation's idempotency key (agent/plans/PLAN-detached-jobs.md section
   * 17). A client retrying a request whose answer it lost sends the same id, and
   * the executor and renet attach the retry to the job the first request
   * started instead of starting a second one. The executor mints one when absent.
   */
  requestId: z
    .string()
    .regex(/^[A-Za-z0-9][A-Za-z0-9._:@-]{0,199}$/)
    .optional(),
});

type CommandRequest = z.infer<typeof CommandRequestSchema>;

export type { CommandRequest };

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

type WireEvent = z.infer<typeof WireEventSchema>;

export type { WireEvent };

/** A job's lifecycle state, as renet's status file records it. */
export const JobStateSchema = z.enum(['running', 'succeeded', 'failed', 'cancelled']);

type JobState = z.infer<typeof JobStateSchema>;

export type { JobState };

/**
 * Another live job (or an active scheduled backup unit) a job start met
 * (agent/plans/PLAN-detached-jobs.md section 19). `action` says whether the
 * start went ahead past it (`warn`) or was refused (`refuse`), and `attach` is
 * the exact command that shows the other job.
 *
 * An entry names its job (`jobId`); a scheduled unit, which has no job id,
 * names its `unit` instead. An entry naming neither is refused, because a
 * warning that cannot say what it overlaps cannot be acted on.
 */
export const JobOverlapSchema = z
  .object({
    jobId: z.string().min(1).optional(),
    function: z.string().optional(),
    command: z.string().optional(),
    verb: z.string().optional(),
    repoGuid: z.string().optional(),
    repo: z.string().optional(),
    machine: z.string().optional(),
    lockClass: z.string().optional(),
    state: z.string().optional(),
    startedAt: z.string().optional(),
    origin: z
      .object({
        client: z.string().optional(),
        version: z.string().optional(),
        sshUser: z.string().optional(),
        config: z.object({ name: z.string().optional(), id: z.string().optional() }).optional(),
        actor: z.string().optional(),
      })
      .optional(),
    unit: z.string().min(1).optional(),
    action: z.enum(['warn', 'refuse']),
    attach: z.string(),
  })
  .refine((o) => o.jobId !== undefined || o.unit !== undefined, {
    message: 'an overlap names its jobId (or, for a scheduled unit, its unit)',
    path: ['jobId'],
  });

type JobOverlap = z.infer<typeof JobOverlapSchema>;

export type { JobOverlap };

/**
 * What `--background -o json` prints and what an MCP tool returns when a job
 * outlives its attach window: the ticket, never the plain hint text
 * (agent/plans/PLAN-detached-jobs.md Design 2, section 26). One schema, shared
 * by the CLI and MCP, so a script or a model parses one shape.
 */
export const BackgroundEnvelopeSchema = z.object({
  jobId: z.string().min(1),
  machine: z.string().min(1),
  verb: z.string(),
  repo: z.string().optional(),
  state: JobStateSchema,
  /** The command that resumes following: `rdc job wait <id>`. */
  follow: z.string(),
  overlaps: z.array(JobOverlapSchema).default([]),
});

type BackgroundEnvelope = z.infer<typeof BackgroundEnvelopeSchema>;

export type { BackgroundEnvelope };

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
  /** The machine job the command ran as, when it ran as one. */
  jobId: z.string().optional(),
  /**
   * The job's state when the result was written. `running` means the job
   * outlived the attach window: the request ended with the ticket, and the
   * client follows with polls. A terminal state means the job finished inside
   * the window and this result is its answer.
   */
  state: JobStateSchema.optional(),
  /** True when the job finished inside the attach window (one round trip). */
  attached: z.boolean().optional(),
  /** The overlapping jobs the start met (section 19). */
  overlaps: z.array(JobOverlapSchema).optional(),
});

type WireResult = z.infer<typeof WireResultSchema>;

export type { WireResult };

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
    /**
     * The command's stdout as base64, sent in place of `stdout` when the command
     * wrote raw bytes (`repo cat` of a binary file). A client writes the decoded
     * bytes verbatim; carrying them as a JSON string would corrupt anything that
     * is not valid UTF-8.
     */
    stdoutBase64: z.string().optional(),
    stderr: z.string().optional(),
  }),
  z.object({
    kind: z.literal('job'),
    jobId: z.string(),
    /**
     * The machine the job runs on, so a client polls it without re-deriving
     * the target. Optional only until the serve route emits it (J6b).
     */
    machine: z.string().min(1).optional(),
    /** Line offset to resume from when re-attaching to a detached job. */
    sinceLine: z.number().int().nonnegative().default(0),
    /** The overlapping jobs the start met (section 19). */
    overlaps: z.array(JobOverlapSchema).optional(),
  }),
  /**
   * Written every 10 s of a quiet attach window, so a mobile NAT mapping and
   * the client's idle timers stay alive while a job runs without output.
   */
  z.object({
    kind: z.literal('heartbeat'),
    ts: z.string().optional(),
  }),
]);

type StreamLine = z.infer<typeof StreamLineSchema>;

export type { StreamLine };

/**
 * What `GET /v1/jobs/:id/poll` returns: the new spool lines past `sinceLine`
 * and the job's status, in one answer (agent/plans/PLAN-detached-jobs.md
 * Design 4). `more: true` tells the client to poll again at once.
 */
export const JobPollResponseSchema = z.object({
  events: z.array(z.object({ line: z.number().int().positive(), event: WireEventSchema })),
  nextLine: z.number().int().nonnegative(),
  more: z.boolean(),
  status: z.object({
    state: JobStateSchema,
    exitCode: z.number().int().optional(),
    finishedAt: z.string().optional(),
    function: z.string(),
  }),
});

type JobPollResponse = z.infer<typeof JobPollResponseSchema>;

export type { JobPollResponse };

/** Body of a 409 version-mismatch response. */
export const VersionMismatchSchema = z.object({
  error: z.literal('contract_version_mismatch'),
  clientContractVersion: z.string(),
  executorContractVersion: z.string(),
  executorCliVersion: z.string(),
});

type VersionMismatch = z.infer<typeof VersionMismatchSchema>;

export type { VersionMismatch };

/** What `GET /v1/server-info` returns. Lets a client check compatibility up front. */
export const ServerInfoSchema = z.object({
  cliVersion: z.string(),
  contractVersion: z.string(),
  mode: z.enum(['container', 'daemon']),
  /** Present when the executor is bound to one org and team. */
  scope: z.object({ orgId: z.string(), teamId: z.string() }).optional(),
});

type ServerInfo = z.infer<typeof ServerInfoSchema>;

export type { ServerInfo };

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
  /**
   * Re-attach to a detached job's held event stream: `?machine=<m>&sinceLine=<n>`.
   * Replaced by `jobPoll`; J6b deletes it together with the serve route and the
   * client's re-attach loop.
   */
  jobEvents: (jobId: string) => `/v1/jobs/${jobId}/events`,
  /** The same route as a server-side pattern, so client and server cannot drift. */
  jobEventsPattern: '/v1/jobs/:id/events',
  /** One short poll: `?machine=<m>&sinceLine=<n>&maxLines=<k>`, answered by JobPollResponseSchema. */
  jobPoll: (jobId: string) => `/v1/jobs/${jobId}/poll`,
  jobPollPattern: '/v1/jobs/:id/poll',
  /** Cancel a job: `POST ?machine=<m>`, authorized as `job cancel`. */
  jobCancel: (jobId: string) => `/v1/jobs/${jobId}/cancel`,
  jobCancelPattern: '/v1/jobs/:id/cancel',
} as const;
