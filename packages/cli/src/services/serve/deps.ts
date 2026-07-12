/**
 * What the executor app needs, injected rather than imported.
 *
 * `createServeApp(deps)` is a pure function of this interface, which is what
 * lets the loopback harness drive the real HTTP surface with a fake executor and
 * throwaway keys, and lets the container and daemon builds wire the same app to
 * different config sources without either one growing a mode flag.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { PolicyDecision } from '@rediacc/shared/policy';
import type { Executor } from '../executor/types.js';
import type { AuthVerifier } from './auth.js';
import type { AuthorizeArgs } from './policy.js';
import type { SessionPrincipal, SessionStore } from './sessions.js';

/** The audit event the executor ships for every command it runs. */
export interface ExecutorAuditEvent {
  principal: SessionPrincipal;
  commandPath: string;
  functionName: string;
  machineName?: string;
  params: Record<string, unknown>;
  success: boolean;
  durationMs: number;
  destructive: boolean;
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

  /** The decrypted config this principal's commands run against. */
  loadConfig: (principal: SessionPrincipal) => Promise<RdcConfig>;
  /** Throws PolicyDenied when the principal may not run the command. */
  authorize: (args: AuthorizeArgs) => PolicyDecision;
  /** Ships one audit event per command. Awaited, so a killed process cannot lose it. */
  audit?: (event: ExecutorAuditEvent) => Promise<void>;
}
