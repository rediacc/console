/**
 * Wire validation for the CEK handoff blob.
 *
 * The blob type itself lives in shared config-crypto; this is the zod guard the
 * executor puts in front of it, because the blob arrives over the network from
 * a client and must be shape-checked before it reaches the crypto layer.
 */

import type { CekHandoffBlob } from '@rediacc/shared/config-crypto';
import { z } from 'zod';

const base64 = z
  .string()
  .min(1)
  .regex(/^[A-Za-z0-9+/]+={0,2}$/, 'Must be base64');

export const CekHandoffBlobSchema = z.object({
  v: z.number().int().positive(),
  /** Ephemeral X25519 public key, SPKI, base64. */
  eph: base64,
  salt: base64,
  iv: base64,
  /** The CEK, sealed to `eph`. */
  ct: base64,
}) satisfies z.ZodType<CekHandoffBlob>;
