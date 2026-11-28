/**
 * Types of the remote config adapter (remote-config-adapter.ts): the pull,
 * push and listing results it returns, its push options, and the server
 * response shapes it opens.
 */

import type { FieldCommitments, importAesKey, PolicyRecord } from '@rediacc/shared/config-crypto';
import type { EffectivePolicy, PolicyOrgRole } from '@rediacc/shared/policy';
import type { RdcConfig } from '../types/index.js';

export interface PullResult {
  /** Decrypted config merged from envelope + sensitive data */
  config: RdcConfig;
  /** Server-side version number */
  version: number;
  /** SDK epoch used for encryption */
  sdkEpoch: number;
  /**
   * The config's own policy record as the pull carried it (null: none saved), still sealed; absent
   * when the server answered without the field. services/config/policy-record.ts opens it.
   */
  policy?: PolicyRecord | null;
}

export interface PushResult {
  /** New version number after push */
  version: number;
}

/** One entry of the store's config list. */
export interface RemoteConfigEntry {
  configId: string;
  version: number;
  lastModified: string;
  teamId?: string | null;
}

/** One archived version of a config, as `GET /configs/:id/versions` lists it. */
export interface RemoteVersionInfo {
  version: number;
  /** When a newer push replaced it and the server archived it (ISO 8601). */
  archivedAt: string;
  /** The SDK epoch the version was sealed under. */
  sdkEpoch: number;
}

export interface PushOptions {
  /**
   * The document this edit was made from, as pulled at `currentVersion` (a remote config's cache
   * file). A committed path it holds that the pushed document drops is deleted with a tombstone
   * proving this device saw its value (T9); without a base, a push can only add and change.
   */
  base?: RdcConfig;
  /** A restore (T16): the version whose content this push re-publishes, for the audit trail. */
  restoredFromVersion?: number;
}

/** A pull (or version read) response: the blob with the org layer removed, and its envelope. */
export interface PulledEnvelope {
  configData: string;
  envelope: {
    envelopeVersion: 2 | 3 | 4;
    configId: string;
    version: number;
    teamId: string | null;
    lastModified: string;
    commitments: FieldCommitments;
    /** The epoch the blob was pushed in; the server's envelope always carries it. */
    sdkEpoch: number;
    /** Envelope v4 only: the content key wrapped under the CEK. */
    wrappedConfigKey?: string;
    /** Envelope v4 only: the content key's version. */
    configKeyVersion?: number;
    /** Envelope v4 only: the CEK generation the content key is wrapped under. */
    cekGeneration?: number;
  };
  hmac: string | null;
  server_secret: string;
  sdk_derived: string;
  /** The store's current CEK generation (T10); recorded once the blob opens. */
  cekGeneration?: number;
  /** The config's policy record beside the blob (PLAN-rmcp-policy-record.md Design 3). */
  policy?: unknown;
}

/** Session crypto material from the server */
export interface SessionMaterial {
  serverSecret: Uint8Array;
  sdkDerived: Awaited<ReturnType<typeof importAesKey>>;
  sdkEpoch: number;
  /** The store's current CEK generation (T10). */
  cekGeneration: number | undefined;
  /**
   * The config token's member as a policy principal, from the session's `orgRole` and `userEmail`
   * (agent/plans/PLAN-rmcp-decide.md D2). Absent when the server answered without a valid role,
   * which a policy decision refuses rather than guess.
   */
  principal: SessionPrincipal | undefined;
}

/** The caller a remote config's session names: its org role and email. */
export interface SessionPrincipal {
  orgRole: PolicyOrgRole;
  userEmail: string;
}

/** What a local run of a remote config is judged with: the session's principal and the effective policy. */
export interface RemotePolicyContext {
  principal: SessionPrincipal;
  policy: EffectivePolicy;
}
