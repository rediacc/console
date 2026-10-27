/**
 * Typed failures of opening a pulled config, so a caller tells "not the ciphertext sealed for this
 * config and version" apart from "the session layer would not open" without matching message text.
 */

import { ENVELOPE_VERSION, LEGACY_ENVELOPE_VERSION } from './constants.js';

/**
 * The CEK layer refused the blob: its GCM tag does not verify under this CEK and the envelope's
 * binding (envelope v3 AAD), or the v2 blob HMAC does not match. Either the server answered with a
 * blob sealed for another config, version or team, or the blob was sealed under a different CEK.
 */
export class ConfigIntegrityError extends Error {
  constructor(
    message = 'Config integrity check failed. The encrypted data may have been corrupted or tampered with.'
  ) {
    super(message);
    this.name = 'ConfigIntegrityError';
  }
}

/**
 * The payload's envelope is newer than this reader knows. The blob is not corrupt and the slot key
 * is not wrong: another device wrote it with a newer rdc. The fix is upgrading this one.
 */
export class ConfigEnvelopeTooNewError extends Error {
  constructor(public readonly envelopeVersion: number) {
    super(
      `Written by a newer rdc (envelope v${envelopeVersion}); this rdc reads v${LEGACY_ENVELOPE_VERSION} and v${ENVELOPE_VERSION}. Upgrade rdc.`
    );
    this.name = 'ConfigEnvelopeTooNewError';
  }
}
