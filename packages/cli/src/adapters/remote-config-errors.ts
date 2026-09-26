/**
 * The remote config adapter's error taxonomy, and the mapping of a config server failure onto it
 * (split from remote-config-adapter.ts, which re-exports every public name, so importers keep
 * importing from the adapter).
 */

import { t } from '../i18n/index.js';
import { ConfigServerError } from '../services/config/config-server-client.js';
import type { RemoteConfig } from '../types/index.js';

// ─── Error Classes ──────────────────────────────────────────────────────

/**
 * The server refused this device's config token (HTTP 401). `reason` is the
 * server's own code from "Config auth failed: <reason>" (config-token.ts), so
 * each cause keeps its message instead of all 401s reading as "expired".
 */
export class RemoteAuthError extends Error {
  constructor(
    public readonly reason: string,
    message: string
  ) {
    super(message);
    this.name = 'RemoteAuthError';
  }
}

/** The token is past its lifetime, or this device holds none at all. */
export class RemoteTokenExpiredError extends RemoteAuthError {
  constructor() {
    super('token_expired', t('commands.config.remote.tokenExpired'));
    this.name = 'RemoteTokenExpiredError';
  }
}

/**
 * The token is bound to another client address: a token chain binds to the
 * address that first uses it, so a token some other client already spent
 * (the enabling browser, before the device-token fix) fails here.
 */
export class RemoteTokenIpMismatchError extends RemoteAuthError {
  constructor() {
    super('ip_mismatch', t('commands.config.remote.tokenIpMismatch'));
    this.name = 'RemoteTokenIpMismatchError';
  }
}

const AUTH_REASON_RE = /Config auth failed: ([a-z_]+)/;

/** The reason of a 401 that names none (no `Config auth failed: <reason>` in its message). */
const UNSTATED_AUTH_REASON = 'unauthorized';

/** Map a 401 onto the error for the server's stated reason. */
function remoteAuthErrorFor(serverMessage: string): RemoteAuthError {
  const reason = AUTH_REASON_RE.exec(serverMessage)?.[1];
  switch (reason) {
    case 'token_expired':
      return new RemoteTokenExpiredError();
    case 'ip_mismatch':
      return new RemoteTokenIpMismatchError();
    case 'token_exhausted':
      return new RemoteAuthError(reason, t('commands.config.remote.tokenExhausted'));
    case 'invalid_token':
    case 'decryption_failed':
      return new RemoteAuthError(reason, t('commands.config.remote.tokenInvalid'));
    default:
      return new RemoteAuthError(
        reason ?? UNSTATED_AUTH_REASON,
        t('commands.config.remote.tokenRejected', { reason: serverMessage })
      );
  }
}

/**
 * Optimistic-version conflict (HTTP 409). Carries the server's message
 * verbatim, it names the real current version (config.service.ts builds it),
 * so no client-side guess is layered on top.
 */
export class RemoteVersionConflictError extends Error {
  constructor(serverMessage: string) {
    super(serverMessage);
    this.name = 'RemoteVersionConflictError';
  }
}

/**
 * The server refused a push that drops committed paths without a matching tombstone (HTTP 409
 * `precondition_failed`, T9): the push was built from a copy older than the server's, or deletes
 * a value this device never saw. Not a version conflict: replaying the same push cannot succeed,
 * so it is raised as is, naming the paths.
 */
export class RemotePreconditionError extends Error {
  constructor(
    public readonly configName: string,
    public readonly paths: string[]
  ) {
    super(
      t('commands.config.remote.preconditionFailed', {
        config: configName,
        paths: paths.length > 0 ? paths.join(', ') : '-',
      })
    );
    this.name = 'RemotePreconditionError';
  }
}

/**
 * The server answered with a config older than one this device already saw (F1): a version below
 * the device's high-water mark, or the pre-v3 envelope after the device saw v3. Nothing is changed
 * locally; the offline cache is not served in its place.
 */
export class RemoteRollbackError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RemoteRollbackError';
  }
}

/**
 * The config server could not be reached at all (DNS, refused connection,
 * timeout, or a 5xx). Distinct from auth/semantic failures: reads may fall
 * back to the offline cache on this error, writes must fail closed.
 */
export class RemoteUnreachableError extends Error {
  constructor(
    public readonly apiUrl: string,
    cause: unknown
  ) {
    super(t('commands.config.remote.unreachable', { server: apiUrl }), { cause });
    this.name = 'RemoteUnreachableError';
  }
}

/**
 * The server refused this config because this account is not a member of the team the config
 * belongs to (HTTP 403 `team_forbidden`, PLAN-config-team-scoping section 2.4). Membership is
 * checked on every request, so this is also what a device sees after its user left the team; the
 * read path then removes the offline copy (ruling E4). The rotated token in the refusal's body is
 * persisted before this is raised, so the device's token chain survives.
 */
export class RemoteTeamForbiddenError extends Error {
  constructor(public readonly configName: string) {
    super(t('commands.config.remote.teamForbidden', { config: configName }));
    this.name = 'RemoteTeamForbiddenError';
  }
}

/**
 * The team this config's pointer names is not a team of the store's organization (HTTP 404
 * `team_not_found`): a team id from another organization, or a team that no longer exists.
 */
export class RemoteTeamNotFoundError extends Error {
  constructor(
    public readonly configName: string,
    public readonly teamId: string | undefined
  ) {
    super(t('commands.config.remote.teamNotFound', { config: configName, team: teamId ?? '-' }));
    this.name = 'RemoteTeamNotFoundError';
  }
}

/**
 * A write to a remote config was refused because its server is unreachable: the edit, a state
 * record included, is NOT saved anywhere (operator ruling 2026-09-25: offline writes to a remote
 * config fail closed; a local config never contacts a server). Names the config and the server so
 * a caller that treats the write as best-effort can still say why it was lost.
 */
export class RemoteWriteFailedClosedError extends Error {
  constructor(
    public readonly configName: string,
    public readonly apiUrl: string,
    cause: unknown
  ) {
    super(t('commands.config.remote.writeFailedClosed', { config: configName, server: apiUrl }), {
      cause,
    });
    this.name = 'RemoteWriteFailedClosedError';
  }
}

/** The RemoteUnreachableError anywhere in `error`'s cause chain, or undefined. */
export function findUnreachable(error: unknown): RemoteUnreachableError | undefined {
  let current: unknown = error;
  const seen = new Set<unknown>();
  while (current && typeof current === 'object' && !seen.has(current)) {
    seen.add(current);
    if (current instanceof RemoteUnreachableError) return current;
    current = (current as { cause?: unknown }).cause;
  }
  return undefined;
}

/** Error codes (Node net/undici) that mean the server was never reached. */
const NETWORK_ERROR_CODES = new Set([
  'ECONNREFUSED',
  'ECONNRESET',
  'ENOTFOUND',
  'ETIMEDOUT',
  'EAI_AGAIN',
  'EPIPE',
]);

/**
 * Classify an error as network-class (server unreachable / not answering).
 * Walks the `.cause` chain, fetch wraps the socket error in a TypeError, and
 * undici nests its own codes one level deeper.
 */
export function isNetworkError(err: unknown): boolean {
  let current: unknown = err;
  const seen = new Set<unknown>();
  while (current && typeof current === 'object' && !seen.has(current)) {
    seen.add(current);
    if (current instanceof ConfigServerError) return current.status >= 500;
    if (isNetworkErrorNode(current)) return true;
    current = (current as { cause?: unknown }).cause;
  }
  return false;
}

/** One link of the cause chain: a socket/undici code, or fetch's TypeError. */
function isNetworkErrorNode(node: object): boolean {
  const code = (node as { code?: unknown }).code;
  if (typeof code === 'string' && (NETWORK_ERROR_CODES.has(code) || code.startsWith('UND_ERR'))) {
    return true;
  }
  return node instanceof TypeError && /fetch failed/i.test(node.message);
}

export class RemotePasskeySecretMissingError extends Error {
  constructor() {
    super(t('commands.config.remote.passkeySecretMissing'));
    this.name = 'RemotePasskeySecretMissingError';
  }
}

/**
 * The stored slot secret no longer unwraps the CEK. The most common cause is a
 * CEK rotation that bumped the store's generation while this device kept its old
 * wrapping, the AES-GCM auth tag then fails. Surfaced instead of the raw
 * OperationError so the user gets an action (re-enroll) rather than a crypto
 * stack trace. Applies to every enrollment method (passkey and password).
 */
export class RemoteStaleSlotError extends Error {
  constructor() {
    super(t('commands.config.remote.staleSlot'));
    this.name = 'RemoteStaleSlotError';
  }
}

/**
 * The pulled blob will not open, even though the CEK unwrap succeeded.
 *
 * Distinct from RemoteStaleSlotError, which is an unwrap failure: here the slot
 * secret was correct and the store still handed back something this device
 * cannot read. The realistic cause is a store that already holds a config sealed
 * under a DIFFERENT CEK than the slot this device just enrolled against, i.e. a
 * second config for the same organization created from another enrollment.
 *
 * Before this existed the failure escaped as a raw WebCrypto
 * "OperationError: The operation failed for an operation-specific reason".
 */
export class RemoteConfigUndecryptableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RemoteConfigUndecryptableError';
  }
}

/**
 * Map a transport/server failure onto the adapter's typed taxonomy: 401 → the
 * RemoteAuthError for the server's stated reason, 403 `team_forbidden` → not a member of the
 * config's team, 404 `team_not_found` → the pointer names no team of the organization, 409
 * `precondition_failed` → a deletion without a matching tombstone, any other 409 → version
 * conflict (server message verbatim), and network-class failures (fetch TypeError, ECONN*,
 * 5xx, including the getServerKeyMaterial fetch inside configServerFetch) → unreachable, so read
 * paths can cache-serve and write paths fail closed. Everything else passes through unchanged.
 */
export function classifyFetchError(
  error: unknown,
  remote: RemoteConfig,
  configName: string
): unknown {
  if (error instanceof ConfigServerError) {
    const answered = classifyServerAnswer(error, remote, configName);
    if (answered) return answered;
  }
  if (isNetworkError(error)) return new RemoteUnreachableError(remote.apiUrl, error);
  return error;
}

/** The typed error for a refusal the server answered with, or undefined to fall through. */
function classifyServerAnswer(
  error: ConfigServerError,
  remote: RemoteConfig,
  configName: string
): Error | undefined {
  if (error.status === 401) return remoteAuthErrorFor(error.message);
  if (error.status === 403 && error.code === 'team_forbidden') {
    return new RemoteTeamForbiddenError(configName);
  }
  if (error.status === 404 && error.code === 'team_not_found') {
    return new RemoteTeamNotFoundError(configName, remote.teamId);
  }
  if (error.status === 409 && error.code === 'precondition_failed') {
    return new RemotePreconditionError(configName, error.mismatchedPaths ?? []);
  }
  if (error.status === 409) return new RemoteVersionConflictError(error.message);
  return undefined;
}
