/**
 * The pure parts of the remote config adapter: the failures it classifies, and the sync record and
 * optional-field helpers that hold no adapter state (split out of remote-config-adapter.ts to keep
 * it within the file size budget).
 */

import {
  ConfigEnvelopeTooNewError,
  cekUnwrap,
  deriveWrappingKey,
  ENVELOPE_VERSION,
  fromBase64,
  LEGACY_ENVELOPE_VERSION,
} from '@rediacc/shared/config-crypto';
import { envelopeConfigKeyWrap } from '@rediacc/shared/config-schema';
import { t } from '../i18n/index.js';
import { RemoteTokenRefreshError } from '../services/config/device-token-refresh.js';
import {
  isNetworkError,
  type RemoteAuthError,
  RemoteConfigUndecryptableError,
  RemotePasskeySecretMissingError,
  RemoteRollbackError,
  RemoteStaleSlotError,
  RemoteTeamForbiddenError,
  RemoteTeamNotFoundError,
  RemoteTokenExpiredError,
} from './remote-config-errors.js';
import type { PulledEnvelope } from './remote-config-types.js';
import type { SyncRecord } from './remote-token-storage.js';

/** `fields` without its undefined entries, for spreading into a request body or record. */
export function optionalFields<T extends Record<string, number | undefined>>(
  fields: T
): Partial<T> {
  return Object.fromEntries(
    Object.entries(fields).filter(([, value]) => value !== undefined)
  ) as Partial<T>;
}

/**
 * Refuse a pull older than what this device saw: the version and the envelope version are both
 * authentic (each version's AAD names them), so a lower one than recorded is an old copy served back.
 */
export function refuseRollback(
  configId: string,
  seen: SyncRecord | undefined,
  envelope: PulledEnvelope['envelope']
): void {
  if (!seen) return;
  if (envelope.version < seen.highWater) {
    throw new RemoteRollbackError(
      t('commands.config.remote.rollback', {
        configId,
        version: String(envelope.version),
        highWater: String(seen.highWater),
      })
    );
  }
  if (envelope.envelopeVersion < seen.envelopeVersion) {
    throw new RemoteRollbackError(t('commands.config.remote.envelopeDowngrade', { configId }));
  }
}

/** The sync record of a pulled or pushed envelope: its version, salt, (v4) content-key wrap, and the generation. */
export function buildSyncRecord(
  bindingKey: string,
  envelope: Pick<PulledEnvelope['envelope'], 'envelopeVersion' | 'commitments'> & {
    wrappedConfigKey?: string;
    configKeyVersion?: number;
    cekGeneration?: number;
  },
  highWater: number,
  cekGeneration: number | undefined,
  previous: SyncRecord | undefined
): SyncRecord {
  const configKey = envelopeConfigKeyWrap(envelope);
  return {
    binding: bindingKey,
    highWater,
    envelopeVersion: envelope.envelopeVersion,
    fckSalt: envelope.commitments.fckSalt,
    ...(configKey ? { configKey } : {}),
    ...(cekGeneration === undefined ? {} : { cekGeneration }),
    ...(previous?.policyHighWater ? { policyHighWater: previous.policyHighWater } : {}),
  };
}

/**
 * Turn a selectiveDecrypt failure into something the user can act on.
 *
 * The two failure modes carry different meanings and different recoveries, and
 * the protocol does distinguish them: the CEK layer (the v4 content-key wrap
 * and the blob tag under the v4 AAD, the v3 AAD, or the v2 blob HMAC) fails
 * when the blob is not the one sealed for this config, version and team, or was
 * sealed under a different CEK than the slot handed this device, while a
 * failure PAST it means the CEK layer opened and the server-derived session
 * layer did not.
 */
export function classifyDecryptFailure(storeId: string, error: unknown, configId: string): Error {
  const detail = error instanceof Error ? error.message : String(error);

  // The envelope-version guard already names its own problem.
  if (detail.includes('envelope version')) return error as Error;

  // An envelope newer than this rdc reads is a version gap, not a wrong slot key.
  if (error instanceof ConfigEnvelopeTooNewError) {
    return new RemoteConfigUndecryptableError(
      t('commands.config.remote.envelopeTooNew', {
        configId,
        envelope: error.envelopeVersion,
        legacy: LEGACY_ENVELOPE_VERSION,
        current: ENVELOPE_VERSION,
      })
    );
  }

  if (error instanceof Error && error.name === 'ConfigIntegrityError') {
    return new RemoteConfigUndecryptableError(
      t('commands.config.remote.integrityFailed', { configId, storeId })
    );
  }

  return new RemoteConfigUndecryptableError(
    t('commands.config.remote.undecryptableSession', { configId, detail })
  );
}

/** The error a failed renewal raises; see refreshDeviceToken for what it passes through. */
export function renewalFailure(
  configName: string,
  teamId: string | undefined,
  error: unknown,
  refusal: RemoteAuthError
): unknown {
  // A rotation revoked this device's token and left it no slot at the new generation (T10, F11).
  if (error instanceof RemoteTokenRefreshError && error.code === 'stale_cek_generation') {
    return new RemoteStaleSlotError({ cause: error });
  }
  if (error instanceof RemoteTokenRefreshError) return error;
  const e = error as { status?: unknown; code?: unknown } | null;
  if (e?.status === 403 && e.code === 'team_forbidden') {
    return new RemoteTeamForbiddenError(configName);
  }
  if (e?.status === 404 && e.code === 'team_not_found') {
    return new RemoteTeamNotFoundError(configName, teamId);
  }
  // The server answered the config request a moment ago, so a renewal that could not reach it is reported as the refusal it was meant to cure (never as unreachable: that would let a read serve the offline cache after a 401).
  if (isNetworkError(error)) return Object.assign(refusal, { cause: error });
  return error;
}

/**
 * Unwrap the config key (CEK) from the device's wrapped copy: the key the passkey secret and the
 * server secret derive opens it. A wrong slot secret (or a rotated CEK this device never re-wrapped
 * for) surfaces as an AES-GCM auth failure, translated here into the actionable re-enroll error.
 */
export async function unwrapDeviceCek(
  passkeySecretStr: string | null | undefined,
  serverSecret: Uint8Array,
  wrappedCek: string | undefined
) {
  if (!passkeySecretStr) {
    throw new RemotePasskeySecretMissingError();
  }

  const wrappingKey = await deriveWrappingKey(fromBase64(passkeySecretStr), serverSecret);

  if (!wrappedCek) {
    throw new RemoteTokenExpiredError();
  }

  try {
    return await cekUnwrap(wrappedCek, wrappingKey);
  } catch {
    throw new RemoteStaleSlotError();
  }
}
