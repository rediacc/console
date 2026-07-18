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
   * This is that channel. It does not change the default — a machine with no named
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
  /** Timeout in milliseconds (default: 10 minutes) */
  timeout?: number;
  /** Enable debug output */
  debug?: boolean;
  /** Output as JSON */
  json?: boolean;
  /** Skip restarting the rediacc-router service after binary update */
  skipRouterRestart?: boolean;
  /** Capture stdout/stderr instead of streaming them directly */
  captureOutput?: boolean;
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
   * Run the operation as a DETACHED renet job rather than a synchronous one.
   *
   * The machine starts the work under a transient systemd unit and records its
   * progress to a job spool, so the operation survives a dropped connection and
   * a client can re-attach to the event stream where it left off. This is what
   * makes a long backup or migration safe to run through a proxy, where the
   * connection cannot be assumed to outlive the work.
   *
   * Off by default: an operator watching a command in their own terminal wants
   * the synchronous path. Nothing sets it yet; the serve dispatch turns it on
   * for proxied commands, where the connection cannot outlive the work.
   */
  detached?: boolean;
  /**
   * Whether a detached run FOLLOWS the job to completion (the default) or returns
   * the moment the job starts. `--background` turns this off: the CLI prints the
   * job id and a resume hint and exits, leaving the work running on the machine.
   * Only meaningful together with `detached`.
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
  /** The detached job id, set when a run started one but did not follow it (--background). */
  jobId?: string;
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
