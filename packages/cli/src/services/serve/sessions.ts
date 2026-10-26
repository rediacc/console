/**
 * Per-session CEK grants.
 *
 * The account server is zero-knowledge: it cannot hand the executor the key that
 * decrypts a config, because it does not have it. So a client who DOES have it
 * grants it, for one session, using the same CekHandoffBlob primitive that
 * member invites already use:
 *
 *   1. The client opens a session. The executor mints an ephemeral X25519
 *      keypair and returns the public half.
 *   2. The client unwraps the CEK locally (passkey PRF in the browser, or the
 *      enrolled headless key in the CLI), seals it to that public key, and posts
 *      the blob back.
 *   3. The executor opens the blob and holds the CEK in memory for the life of
 *      the session. Nothing is written to disk.
 *
 * TRUST BOUNDARY, stated plainly: a CEK that is in the executor's RAM cannot be
 * revoked by the server. Rotating tokens and SDK epochs gate re-DERIVING a key,
 * not one already held. The executor's memory is the boundary, in both the
 * container tier and the customer-hosted tier. Sessions therefore expire, and
 * they are the only thing that holds a key.
 */

import { randomUUID } from 'node:crypto';
import {
  type CekHandoffBlob,
  cekHandoffDecrypt,
  importAesKey,
} from '@rediacc/shared/config-crypto';

/** How long a granted CEK may live in memory with no activity. */
const DEFAULT_TTL_MS = 30 * 60 * 1000;

/** The identity an executor acts for, resolved from the account server. */
export interface SessionPrincipal {
  orgId: string;
  teamId: string | null;
  userId: string;
  userEmail: string;
  orgRole: 'owner' | 'admin' | 'member';
  /** The token id the command was submitted under, for audit attribution. */
  tokenId?: string;
}

interface SessionEntry {
  id: string;
  principal: SessionPrincipal;
  /** The org that opened the session. A grant or an exec from another org never reaches it. */
  orgId: string;
  /** Ephemeral X25519 private key, discarded once the CEK arrives. */
  ephemeralPrivateKey?: CryptoKey;
  /** The granted config-encryption key. RAM only, never persisted. */
  cek?: CryptoKey;
  createdAt: number;
  lastUsedAt: number;
}

export interface SessionStoreOptions {
  ttlMs?: number;
  /** Injectable clock for tests. */
  now?: () => number;
}

/**
 * In-memory session store. One per executor process.
 *
 * Keyed by session id, but a session is always scoped to one (org, team), which
 * is what lets the container tier key its Durable Object by org:team and keep a
 * warm SSH pool and decrypted-config cache per tenant.
 */
export class SessionStore {
  private readonly sessions = new Map<string, SessionEntry>();
  /** (orgId, userId) -> the session they granted a key through. See sessionFor(). */
  private readonly grantsByUser = new Map<string, string>();
  private readonly ttlMs: number;
  private readonly now: () => number;

  constructor(options: SessionStoreOptions = {}) {
    this.ttlMs = options.ttlMs ?? DEFAULT_TTL_MS;
    this.now = options.now ?? Date.now;
  }

  /**
   * Open a session and mint the ephemeral keypair the client will seal the CEK
   * to. Returns the session id and the public key (base64 SPKI).
   */
  async open(
    principal: SessionPrincipal,
    generateKeyPair: () => Promise<{ publicKey: CryptoKey; privateKey: CryptoKey }>,
    exportPublicKey: (key: CryptoKey) => Promise<string>
  ): Promise<{ sessionId: string; publicKey: string }> {
    this.evictExpired();

    const keyPair = await generateKeyPair();
    const id = randomUUID();
    const at = this.now();

    this.sessions.set(id, {
      id,
      principal,
      orgId: principal.orgId,
      ephemeralPrivateKey: keyPair.privateKey,
      createdAt: at,
      lastUsedAt: at,
    });

    return { sessionId: id, publicKey: await exportPublicKey(keyPair.publicKey) };
  }

  /**
   * Accept the sealed CEK for a session.
   *
   * OWNERSHIP: the key may be granted only by the principal who OPENED the
   * session. The session records its opener; a grant from anyone else is
   * refused, even with a valid token for the same org. Without this, a second
   * user could complete a grant on someone else's session and, because the grant
   * index is keyed by the session's opener, cause that opener's later commands to
   * run against a key the second user chose. The ephemeral key exchange already
   * makes this hard to exploit blind, but a security boundary must not rest on an
   * attacker not knowing a public key.
   *
   * The ephemeral private key is dropped immediately afterwards: it exists only
   * to open this one blob, and keeping it would widen the window in which a
   * memory disclosure yields anything reusable.
   */
  async grantCek(
    sessionId: string,
    blob: CekHandoffBlob,
    grantingPrincipal: SessionPrincipal
  ): Promise<void> {
    const session = this.require(sessionId);
    if (!ownedBy(session, grantingPrincipal)) {
      // Deliberately the same message require() gives for an unknown session, so a caller cannot probe which session ids exist by whether the error changes from "unknown" to "not yours".
      throw new SessionError('Unknown or expired session. Open a new one.', SESSION_UNKNOWN_CODE);
    }
    if (!session.ephemeralPrivateKey) {
      throw new SessionError('This session has already received its key.');
    }

    const raw = await cekHandoffDecrypt(blob, session.ephemeralPrivateKey);
    session.cek = await importAesKey(raw);
    session.ephemeralPrivateKey = undefined;
    session.lastUsedAt = this.now();

    // Index the grant so sessionFor() can find it. See that method for why this is keyed by user and never by org.
    this.grantsByUser.set(grantKey(session.orgId, session.principal.userId), sessionId);
  }

  /** The CEK for a session, or an error naming the fix if it has none yet. */
  requireCek(sessionId: string): CryptoKey {
    const session = this.require(sessionId);
    if (!session.cek) {
      throw new SessionError(
        'This session has no config key yet. Complete the key grant before running commands.'
      );
    }
    session.lastUsedAt = this.now();
    return session.cek;
  }

  /** The identity a session acts for. */
  principal(sessionId: string): SessionPrincipal {
    return this.require(sessionId).principal;
  }

  /**
   * The live session through which this principal granted a key, if any.
   *
   * The container tier needs this because the exec wire carries no session id: a
   * command arrives as a bearer token, which resolves to a principal, and
   * nothing else. The key, meanwhile, is held per session. A store that cannot
   * answer "which session holds this user's key" is an incomplete store, so the
   * lookup lives here rather than being bolted on from outside.
   *
   * KEYED BY (ORG, USER), NEVER BY ORG ALONE, and that is a security property,
   * not a detail. Config-store membership is per user: someone who cannot
   * decrypt the config on their own must not have it decrypted for them just
   * because a colleague in the same org happens to have a live session. Matching
   * on org alone would hand one member's key to another. The user id stays part
   * of the key, and the org id keeps one user's sessions in two orgs apart.
   *
   * Sessions expire, so a hit is re-validated against the live map and a stale
   * index entry is dropped rather than returned.
   */
  sessionFor(principal: SessionPrincipal): string | undefined {
    const key = grantKey(principal.orgId, principal.userId);
    const sessionId = this.grantsByUser.get(key);
    if (!sessionId) return undefined;

    const session = this.sessions.get(sessionId);
    if (!session?.cek) {
      this.grantsByUser.delete(key);
      return undefined;
    }
    if (!ownedBy(session, principal)) return undefined;

    // Expiry is enforced by require(), which also evicts.
    try {
      this.require(sessionId);
    } catch {
      this.grantsByUser.delete(key);
      return undefined;
    }
    return sessionId;
  }

  /**
   * The session a command should draw its config key from.
   *
   * When the request NAMES a session (the web console's X-Config-Session
   * header), the named session must exist and belong to the request principal ,
   * the same ownership rule grantCek enforces, refused with the same
   * deliberately indistinguishable message, so a caller cannot probe which
   * session ids exist. The named session wins over the grant index: a user with
   * two live sessions (say, a browser grant and a CLI grant) gets the one they
   * asked for, not whichever granted last.
   *
   * Without a named session this is exactly sessionFor(): the CLI proxy path,
   * unchanged.
   */
  sessionForExec(principal: SessionPrincipal, requestedId?: string): string | undefined {
    if (!requestedId) return this.sessionFor(principal);

    const session = this.require(requestedId);
    if (!ownedBy(session, principal)) {
      throw new SessionError('Unknown or expired session. Open a new one.', SESSION_UNKNOWN_CODE);
    }
    session.lastUsedAt = this.now();
    return requestedId;
  }

  /** Drop a session and the key it holds. */
  close(sessionId: string): void {
    this.forget(sessionId);
  }

  /** Number of live sessions. Diagnostics and tests. */
  size(): number {
    this.evictExpired();
    return this.sessions.size;
  }

  private require(sessionId: string): SessionEntry {
    this.evictExpired();
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new SessionError('Unknown or expired session. Open a new one.', SESSION_UNKNOWN_CODE);
    }
    return session;
  }

  /**
   * Drop idle sessions, which is the only mechanism that removes a CEK from
   * memory short of the process exiting.
   */
  private evictExpired(): void {
    const cutoff = this.now() - this.ttlMs;
    for (const [id, session] of this.sessions) {
      if (session.lastUsedAt < cutoff) this.forget(id);
    }
  }

  /**
   * Remove a session and every trace of it, index included. One place, so a
   * future eviction path cannot drop the session and leave the grant index
   * pointing at a key that is gone.
   */
  private forget(sessionId: string): void {
    const session = this.sessions.get(sessionId);
    const key = session ? grantKey(session.orgId, session.principal.userId) : undefined;
    if (key && this.grantsByUser.get(key) === sessionId) {
      this.grantsByUser.delete(key);
    }
    this.sessions.delete(sessionId);
  }
}

/** Grant-index key: one slot per (org, user), so a user's live sessions in two orgs stay independently reachable. Still never shared between users. */
function grantKey(orgId: string, userId: string): string {
  return `${orgId}\0${userId}`;
}

/** A session belongs to the user AND the org that opened it; both must match, so another org's principal is refused as an unknown session. */
function ownedBy(session: SessionEntry, principal: SessionPrincipal): boolean {
  return session.principal.userId === principal.userId && session.orgId === principal.orgId;
}

/** Wire code on the 404 for a session id the store does not hold (never opened, expired, wiped by a redeploy, or not the caller's). */
export const SESSION_UNKNOWN_CODE = 'EXECUTOR_SESSION_UNKNOWN';

export class SessionError extends Error {
  constructor(
    message: string,
    readonly code?: typeof SESSION_UNKNOWN_CODE
  ) {
    super(message);
    this.name = 'SessionError';
  }
}
