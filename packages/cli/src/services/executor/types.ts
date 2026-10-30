/**
 * The executor seam.
 *
 * `Executor` is the narrow waist every machine-plane command funnels through.
 * LocalExecutorService (local-executor.ts) is the implementation: it opens SSH
 * to the machine and runs renet there.
 *
 * WHAT THIS SEAM IS NOT, because it was tried and it was wrong. There used to be
 * a second implementation here, a RemoteExecutor that shipped ExecuteOptions to
 * an `rdc serve` over HTTPS, and `--proxy` selected it. That could not work, and
 * the reason is worth keeping: this seam sits INSIDE each command's action body,
 * and a command does config work on its way here. `repo up` reads the repository
 * from the local config and allocates a network id before it ever calls
 * execute(). A proxy client holds no config at all, so it died long before
 * reaching the seam.
 *
 * So `--proxy` now intercepts one level up, at the COMMAND, and sends a contract
 * path plus params to the executor, which runs the real command itself
 * (services/serve/command-dispatch.ts). The client parses, prompts and renders;
 * the executor holds the config, the SSH keys and the master password. This
 * seam's remaining job is to be the single point every LOCAL execute() flows
 * through, which is what lets the event tap observe them all.
 *
 * The non-serializable field (`onEvent`) is realized on the wire as the NDJSON
 * event stream, so the client's render path is identical in both modes.
 */

import type { JobOverlap, JobState } from '@rediacc/shared/cli-contract/wire';

/**
 * One step of a `job start --steps` plan, as renet keeps it in the spool. The
 * same shape as services/jobs/steps.ts SpoolStep, restated rather than imported:
 * this seam module must not reach the step registry (which reaches the
 * executor), or every config-only command importing the request context would
 * look machine-touching to the plane rule (packages/cli/scripts/lib/plane-rules.ts).
 */
export interface JobStepPlan {
  name: string;
  on: 'success' | 'failure' | `marker:${string}`;
  params?: Record<string, string | number | boolean>;
  needs_output?: boolean;
}

/** Structured event from renet's NDJSON events protocol. */
export interface RenetEvent {
  type: 'log' | 'step_start' | 'step_done' | 'output' | 'result';
  ts?: string;
  name?: string;
  msg?: string;
  level?: string;
  duration_ms?: number;
  detail?: string;
  data?: unknown;
}

/** A machine referenced by an operation besides the primary target (backup peers). */
export interface ExtraMachine {
  ip: string;
  port?: number;
  user: string;
  datastore?: string;
}

/** Options for executing a renet function against a machine or cluster. */
export interface ExecuteOptions {
  /** Function name to execute */
  functionName: string;
  /** Target machine name (must exist in the executor's config) */
  machineName: string;
  /** The CLI command that asked for this call (`repo create`), named in the job ticket and in a refusal. Unset, the executor reads it from the output service, which inside the executor daemon names the daemon's own `executor-daemon run`, so the daemon client sets it before the call crosses the socket. */
  verb?: string;
  /**
   * Target a cluster instead of a machine. When set, execution routes to the
   * cluster's control node and KUBECONFIG is injected into the renet env (the
   * analog of DOCKER_HOST on a machine). Mutually exclusive with a machine
   * target.
   */
  kubeCluster?: string;
  /**
   * The resolved placement's datastore mount path, overriding the machine's
   * default datastore FOR THIS DISPATCH (#74).
   *
   * renet reads the datastore from the MACHINE VAULT (`p.Datastore()` ->
   * `machineDatastore`, set only by `WithMachineVault`), which the CLI builds from
   * the config machine record. A `datastore` PARAM is not a channel to it: the
   * kube_* verbs happen to read `p.Export("datastore")`, but `repository_create`
   * calls `AddDatastore`, which reads the vault. So a repo living on a NAMED
   * datastore had no way to say so, and every dispatch silently used the machine's
   * default docker datastore instead of the datastore the repo was created on.
   *
   * This is that channel. It does not change the default, a machine with no named
   * datastore still falls back exactly as before; it lets a caller that KNOWS the
   * placement stop staying silent about it.
   */
  datastore?: string;
  /** Parameters to pass to the function */
  params?: Record<string, unknown>;
  /**
   * Extra machines for multi-machine operations (e.g. backup push to a peer).
   *
   * Normally OMITTED: the executor derives it from `params` against its own
   * config (resolveExtraMachines). Pass it explicitly only from tests or from
   * code that already holds resolved machines. A proxy client can never supply
   * this, because it holds no config.
   */
  extraMachines?: Record<string, ExtraMachine>;
  /** Timeout in milliseconds; unset, renet cancels at 10 minutes except for the data-moving verbs resolveRenetTimeoutMs names */
  timeout?: number;
  /** Enable debug output */
  debug?: boolean;
  /** Output as JSON */
  json?: boolean;
  /** Skip restarting the rediacc-router service after binary update */
  skipRouterRestart?: boolean;
  /** Capture stdout/stderr instead of streaming them directly */
  captureOutput?: boolean;
  /**
   * Stream the REMOTE process's own stdout to the caller, live.
   *
   * Off by default and opted into per command, because the default handler
   * detects step events and drops every other line: right for `repo up`/`fork`/
   * `push`, where renet's chatter is noise, and wrong for the three verbs whose
   * output IS the answer (`repo exec`, `repo logs`, `run -f`), which printed
   * nothing at all until this existed.
   *
   * Not a synonym for `debug`: this strips renet's `[<function>] ` relay prefix
   * and its logrus lines, so only the inner process's bytes survive. Unlike
   * `captureOutput` it streams, which `repo logs --follow` depends on.
   */
  passthroughOutput?: boolean;
  /** Enable NDJSON events mode: renet emits structured events instead of text */
  eventsMode?: boolean;
  /**
   * Callback for handling NDJSON events in real time. Never crosses the wire.
   *
   * The optional second argument is the event's 1-based spool-line ordinal,
   * present only on a detached job's replayed stream, where it lets a
   * re-attaching client dedupe on resume. A synchronous stream omits it.
   */
  onEvent?: (event: RenetEvent, line?: number) => void;
  /** Suppress CLI step spinners (steps still recorded for the timeline) */
  quietSpinners?: boolean;
  /**
   * How long the call stays attached to the machine job it starts
   * (agent/plans/PLAN-detached-jobs.md section 15). Set by the ENTRY POINT at
   * the executor seam (executor-factory's attach decorator), never by a verb:
   * unset is unlimited (a direct terminal run), JOB_ATTACH_WINDOW_MS for the
   * proxy, the web console and MCP, 0 for `--background`. A job that finishes
   * inside the window returns its result; one that outlives it returns the
   * ticket (`state: 'running'`).
   *
   * Every renet call runs as a job (section 14) except the section 24
   * exemptions (`runsOutsideJob`), so there is no `detached` switch.
   */
  attachWindowMs?: number;
  /**
   * The job's idempotency key (section 17). Normally unset: the executor mints
   * `<invocation>:<machine>:<seq>` once per call, and a start retried after a
   * dropped answer carries the same id, so renet attaches it to the first job.
   */
  requestId?: string;
  /**
   * The client-side step plan (`job start --steps`, section 18), written into
   * the job's spool so every observer finds the same plan. Set by
   * `executorJobCall` for a command that runs through `runJob`.
   */
  jobSteps?: JobStepPlan[];
  /**
   * The caller owns the call's ticket (`runJob` writes `starting`, `started`
   * and `finished` around the start), so the executor writes none of its own.
   */
  externalTicket?: boolean;
  /**
   * @deprecated Ignored. Every renet call is a job (section 14). The serve
   * dispatch (services/serve/command-dispatch.ts) still writes it; J6b removes
   * that writer and this field with it.
   */
  detached?: boolean;
  /**
   * @deprecated Ignored. `attachWindowMs` decides how long a call follows its
   * job. The serve dispatch still writes it; J6b removes both.
   */
  follow?: boolean;
  /**
   * Called once with the job id the instant a detached run starts, before any
   * event is streamed. The serve route uses it to emit its `kind:'job'` line so a
   * client can re-attach even if the connection drops before the first event.
   */
  onJobStarted?: (jobId: string) => void;
  /**
   * Skip the post-success repo-identity license refresh for create/fork.
   * Callers that defer must invoke refreshIdentityFor() themselves once the
   * repository is in its final state (e.g. compound fork --up flows).
   */
  deferIdentityRefresh?: boolean;
}

/** Result of an execution. Serializable: this is the proxy's response envelope. */
export interface ExecuteResult {
  /** Whether execution succeeded */
  success: boolean;
  /** Exit code from renet */
  exitCode: number;
  /** Error message if failed */
  error?: string;
  /** Stable machine-readable error code, when available */
  errorCode?: string;
  /** Actionable guidance for operators or automation */
  errorGuidance?: string;
  /**
   * The machine address an `EGRESS_UNREACHABLE` connect never got an answer from. Set only for that code; `rdc serve` sends it in the egress-unreachable report and removes it before the result line is written.
   */
  connectTarget?: { host: string; port: number };
  /** Structured repo-license reason from renet, when available */
  licenseFailureReason?: string;
  /** Total execution duration in milliseconds (includes SSH, provisioning, etc.) */
  durationMs: number;
  /** Renet operation duration in milliseconds (just the remote function execution) */
  operationDurationMs?: number;
  /** Captured stdout, when requested */
  stdout?: string;
  /** Captured stderr, when requested */
  stderr?: string;
  /**
   * True when the full renet output was already echoed to the terminal
   * (non-capture failure path), so failure renderers must not repeat it.
   */
  outputEchoed?: boolean;
  /** The machine job the call ran as. */
  jobId?: string;
  /** The job's request id (section 17), so a caller can find the ticket. */
  requestId?: string;
  /**
   * The job's state when the call returned. `running` means the job outlived
   * the attach window and this result is the ticket, not the answer; the work
   * goes on, and `rdc job wait <id>` follows it.
   */
  state?: JobState;
  /** True when the job finished inside the attach window. */
  attached?: boolean;
  /** The live jobs and scheduled units the start met (section 19). J21 renders them. */
  overlaps?: JobOverlap[];
  /** Step timing from renet (parsed from JSON output) */
  steps?: { name: string; duration_ms: number; detail?: string }[];
  /** CLI-side step timing (config, SSH connect, provision, verify, license) */
  cliSteps?: { name: string; duration_ms: number; startedAtMs?: number }[];
  /** All steps combined (CLI overhead + renet execution) */
  allSteps?: { name: string; duration_ms: number; detail?: string }[];
}

/**
 * The seam. LocalExecutorService implements it.
 *
 * Resolve one with `getExecutor()` (executor-factory.ts) rather than importing
 * the implementation directly, so a dispatch can pin its own and the event tap
 * can observe every call.
 */
export interface Executor {
  execute(options: ExecuteOptions): Promise<ExecuteResult>;
}
