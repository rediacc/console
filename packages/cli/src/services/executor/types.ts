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
  /** Callback for handling NDJSON events in real time. Never crosses the wire. */
  onEvent?: (event: RenetEvent) => void;
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
   * the synchronous path. The proxy executor turns it on.
   */
  detached?: boolean;
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
