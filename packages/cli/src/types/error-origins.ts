// Who an error is for: the person who typed the command, the machine or network it ran on, or Rediacc.

import { ERROR_CODES, type ErrorCode } from './errors.js';

/**
 * `user` is input, auth, permission or plan limits. `environment` is the network, a machine, SSH,
 * Docker or disk. `rediacc` is a defect or outage on Rediacc's side.
 */
export type ErrorOrigin = 'user' | 'environment' | 'rediacc';

/** The 15 envelope codes. `Record<ErrorCode, ...>` makes the type checker refuse a missing code. */
export const ERROR_CODE_ORIGINS: Record<ErrorCode, ErrorOrigin> = {
  GENERAL_ERROR: 'environment',
  INVALID_REQUEST: 'user',
  AUTH_REQUIRED: 'user',
  PERMISSION_DENIED: 'user',
  NOT_FOUND: 'user',
  NETWORK_ERROR: 'environment',
  SERVER_ERROR: 'rediacc',
  VALIDATION_ERROR: 'user',
  PRECONDITION_MISMATCH: 'user',
  AMBIGUOUS: 'user',
  STATE_MISMATCH: 'user',
  HEALTH_GATE_FAILED: 'environment',
  INFRA_FAILED: 'environment',
  BUSY: 'environment',
  DETACHED: 'environment',
};

/**
 * Named codes the source emits as `errorCode`, as a `code` property or literal, or as the first argument of a CliExitError. A named
 * code's origin overrides the origin of the envelope code it rides on. Codes that renet reports
 * and the CLI forwards verbatim (cluster-snapshot, renet-execution) are not listed: they are not
 * known at build time, and the envelope omits `origin` for them.
 */
export const NAMED_ERROR_ORIGINS: Record<string, ErrorOrigin> = {
  UNCAUGHT_EXCEPTION: 'rediacc',
  EGRESS_UNREACHABLE: 'environment',
  SSH_REFUSED: 'environment',
  SSH_HANDSHAKE_TIMEOUT: 'environment',
  SSH_AUTH_FAILED: 'user',
  LICENSE_REQUIRED: 'user',
  FREE_LICENSE_NO_BACKUP: 'user',
  FEEDBACK_DAILY_LIMIT: 'user',
  EXECUTOR_SESSION_UNKNOWN: 'environment',
  LOCAL_EXECUTION_FAILED: 'environment',
  RENET_NOT_ON_MACHINE: 'environment',
  REPO_LICENSE_ISSUANCE_REQUIRED: 'user',
  REPO_LICENSE_REFRESH_REQUIRED: 'user',
  REPO_LICENSE_MACHINE_MISMATCH: 'user',
  REPO_LICENSE_REPOSITORY_MISMATCH: 'user',
  REPO_LICENSE_IDENTITY_MISMATCH: 'user',
  REPO_LICENSE_INTEGRITY_ERROR: 'environment',
  REPO_LICENSE_DELEGATION_CERT_EXPIRED: 'user',
  REPO_LICENSE_DELEGATION_CERT_INVALID: 'environment',
  RENET_BUILD_UNVERIFIED: 'environment',
  RENET_DEV_ON_MACHINE: 'environment',
  RENET_DOWNGRADE_REFUSED: 'user',
  RENET_UPLOAD_REFUSED_IN_EXECUTOR: 'environment',
  ACCESS_LOCKOUT: 'user',
  GRAND_REPO_DENIED: 'user',
  ACCESS_KEY_CONFLICT: 'user',
  ACCESS_KEY_DUPLICATE_BLOB: 'user',
  ACCESS_FILE_CHANGED: 'environment',
  TIMEOUT: 'environment',
  EXECUTION_ERROR: 'environment',
  POLICY_DENIED: 'user',
  // The policy decision a grand-guarded destructive call gets until the caller confirms it (LM4: elicitation or the `confirm` argument).
  CONFIRMATION_REQUIRED: 'user',
  EXECUTOR_FAILED: 'environment',
};

function lookup(code: string | undefined): ErrorOrigin | undefined {
  if (code === undefined) return undefined;
  if (Object.hasOwn(NAMED_ERROR_ORIGINS, code)) return NAMED_ERROR_ORIGINS[code];
  if (Object.hasOwn(ERROR_CODE_ORIGINS, code)) return ERROR_CODE_ORIGINS[code as ErrorCode];
  return undefined;
}

/**
 * The origin of a failure: its named code first, then its envelope code. Undefined for a code the
 * tables do not know, which the JSON envelope then leaves without `origin`.
 */
export function errorOrigin(code: string, namedCode?: string): ErrorOrigin | undefined {
  return lookup(namedCode) ?? lookup(code);
}

/** Every envelope code, for consumers that list them next to their origin. */
export function listErrorCodeOrigins(): { code: string; origin: ErrorOrigin }[] {
  return [...Object.keys(ERROR_CODES), ...Object.keys(NAMED_ERROR_ORIGINS)].map((code) => ({
    code,
    origin: lookup(code) as ErrorOrigin,
  }));
}
