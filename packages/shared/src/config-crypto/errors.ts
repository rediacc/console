/**
 * Typed failures of opening a pulled config, so a caller tells "not the ciphertext sealed for this
 * config and version" apart from "the session layer would not open" without matching message text.
 */

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
