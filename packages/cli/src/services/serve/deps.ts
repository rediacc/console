/**
 * What the executor app needs, injected rather than imported.
 *
 * `createServeApp(deps)` is a pure function of this interface, which is what
 * lets the loopback harness drive the real HTTP surface with a fake executor and
 * throwaway keys, and lets the container and daemon builds wire the same app to
 * different config sources without either one growing a mode flag.
 */

import type { AiConfigs } from '@rediacc/shared/ai';
import type { ContractCommand } from '@rediacc/shared/cli-contract';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { PolicyDecision } from '@rediacc/shared/policy';
import type { AiRecorder } from '../ai/recorder.js';
import type { Executor } from '../executor/types.js';
import type { AgentGrantSessions } from './agent-grant-session.js';
import type { AuthVerifier } from './auth.js';
import type { EgressReportTarget, EgressUnreachableAnswer } from './egress-report.js';
import type { AuthorizeArgs } from './policy.js';
import type { RunIndex } from './run-index.js';
import type { SessionPrincipal, SessionStore } from './sessions.js';

/** The audit event the executor ships for every command it runs. */
export interface ExecutorAuditEvent {
  principal: SessionPrincipal;
  commandPath: string;
  /** The renet function the command called, absent when it reached none. */
  functionName?: string;
  machineName?: string;
  params: Record<string, unknown>;
  /** The params of the renet call `functionName` names, observed like it; never shipped whole (audit.ts reads the repository identity out of them). */
  functionParams?: Record<string, unknown>;
  success: boolean;
  exitCode: number;
  durationMs: number;
  destructive: boolean;
  /** The job the command ran as, when it ran as one. */
  jobId?: string;
  /** `started` for a ticket handed back before the job ended, else the job's terminal state. */
  outcome?: 'started' | 'succeeded' | 'failed' | 'cancelled';
  /** The command request's id, shipped so the account Worker joins this event to the console run that caused it. */
  requestId?: string;
}

export interface ServeCrypto {
  generateEphemeralKeyPair: () => Promise<{ publicKey: CryptoKey; privateKey: CryptoKey }>;
  exportPublicKey: (key: CryptoKey) => Promise<string>;
}

export interface ServeDeps {
  /** Where this executor runs. Reported in server-info; changes no behavior. */
  mode: 'container' | 'daemon';
  /** The org and team this executor is bound to, when it is bound to one. */
  scope?: { orgId: string; teamId: string };

  /** Resolves the identity behind a client token, via the account server. */
  auth: AuthVerifier;
  /** Holds granted config keys in memory, one per session. */
  sessions: SessionStore;
  /** Runs the command. In production this is the LocalExecutorService. */
  executor: Executor;
  /** X25519 helpers for the CEK grant. */
  crypto: ServeCrypto;

  /**
   * The decrypted config this principal's commands run against.
   *
   * `configSessionId` is present when the request named a session (the web
   * console's X-Config-Session header): a session-holding loader (the container
   * tier) must draw the key from THAT session rather than the principal's
   * latest grant. A loader with its own config (the daemon tier) ignores it.
   */
  loadConfig: (principal: SessionPrincipal, configSessionId?: string) => Promise<RdcConfig>;
  /**
   * Record with the account server that the bearer's user granted this session
   * its config key (PLAN-backup-program S7). Called once the CEK grant leg
   * succeeds; a failure undoes the grant. Set by the container tier, whose
   * config token is minted only under a recorded grant; the daemon tier, which
   * reads its own enrolled config, leaves it unset.
   */
  recordGrant?: (sessionId: string, bearerToken: string) => Promise<void>;
  /**
   * Tell the account side that this executor's path to `target` never answered
   * (container tier only); the proxy probes `target` itself before the report
   * counts. Never throws; answers undefined when no answer came back. Absent in
   * container mode, the server uses the default reporter; in daemon mode it is
   * never called.
   */
  reportEgressUnreachable?: (
    target: EgressReportTarget
  ) => Promise<EgressUnreachableAnswer | undefined>;
  /** Throws PolicyDenied when the principal may not run the command. */
  authorize: (args: AuthorizeArgs) => PolicyDecision;
  /**
   * Ships one audit event. Awaited, so a killed process cannot lose it. Throws
   * AuditUnavailableError (audit.ts) when the event could not be delivered: a
   * mutating command whose `started` event fails is refused before dispatch
   * (AUDIT_UNAVAILABLE), and an outcome event that fails is reported in the
   * result instead.
   */
  audit?: (event: ExecutorAuditEvent) => Promise<void>;
  /**
   * Whether a command's machine work runs detached. Defaults to the contract's
   * `detachable` when absent. Injectable so a deployment (or a test) can force
   * synchronous execution, a daemon that never wants detach, or a loopback
   * harness whose fake executor does not implement the job spool.
   */
  detach?: (entry: ContractCommand) => boolean;
  /**
   * Records every dispatched command in the account server's run index
   * (run-index.ts). Never fails or delays a command; absent in a harness that does not
   * want the account round trips.
   */
  runIndex?: RunIndex;
  /**
   * The agent-grant sessions behind `POST /v1/mcp/call` (agent-grant-session.ts). Set by `rdc serve`
   * in both modes (commands/serve.ts configLoading), always pinned to the executor's org; without it
   * the route is not registered.
   */
  agentGrants?: AgentGrantSessions;
  /**
   * Seals and posts each AI chat message to the account server's conversation store
   * (services/ai/recorder.ts). The store's conversation row is what the account's approval route
   * looks up, so a chat this executor does not record cannot have a held call approved from the
   * page. Absent in a harness that does not want the account round trips.
   */
  aiRecorder?: AiRecorder;
  /**
   * The AI profile sources of a chat, team over shared (container-config.ts
   * `teamOverSharedAiConfigs`). Absent: the request's own config is the only source, which is the
   * daemon tier's one enrolled config.
   */
  aiConfigs?: (
    principal: SessionPrincipal,
    config: RdcConfig,
    configSessionId?: string
  ) => Promise<AiConfigs>;
}
