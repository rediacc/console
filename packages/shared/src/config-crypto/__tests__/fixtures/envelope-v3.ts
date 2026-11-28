/**
 * Envelope v3, as a pre-v4 client sealed it: the blob under the CEK with the v3 AAD, commitments
 * keyed by CEK-blinded pointers. No client writes v3 any more (ENVELOPE_VERSION is 4); readers still
 * open a stored one, and its next push upgrades it. Tests that pin that read path and that upgrade
 * build their v3 store through this fixture, the way a pre-v4 client left it.
 */

import {
  computeCommitments,
  deriveFieldCommitmentKey,
  derivePointerBlindingKey,
  generateFckSalt,
} from '../../commitments.js';
import { BOUND_ENVELOPE_VERSION, ENVELOPE_FIELDS } from '../../constants.js';
import { configEncrypt } from '../../layers.js';
import { envelopeAad } from '../../selective.js';
import type { ConfigEnvelope, EncryptedConfigPayload, FullConfig } from '../../types.js';

const ENVELOPE_KEYS: ReadonlySet<string> = new Set<string>([
  ...ENVELOPE_FIELDS,
  'envelopeVersion',
  'commitments',
  'wrappedConfigKey',
  'configKeyVersion',
  'cekGeneration',
]);

/** Seal `config` as an envelope v3 payload under `cek`, bound to `storeId` and the config's own id and team. */
export async function sealEnvelopeV3(
  config: FullConfig,
  sdkDerived: CryptoKey,
  cek: CryptoKey,
  options: {
    storeId: string;
    sdkEpoch: number;
    commitEntries: { pointer: string; value: unknown }[];
    fckSalt?: string;
  }
): Promise<EncryptedConfigPayload> {
  const fckSalt = options.fckSalt ?? generateFckSalt();
  const fck = await deriveFieldCommitmentKey(cek, fckSalt);
  const blinding = await derivePointerBlindingKey(cek, config.id);
  const commitments = await computeCommitments(fck, fckSalt, options.commitEntries, blinding);
  const envelope: ConfigEnvelope = {
    envelopeVersion: BOUND_ENVELOPE_VERSION,
    id: config.id,
    version: config.version,
    sdkEpoch: options.sdkEpoch,
    commitments,
  };
  if (config.teamId) envelope.teamId = config.teamId;
  if (config.orgId) envelope.orgId = config.orgId;
  if (config.lastModified) envelope.lastModified = config.lastModified;
  const sensitive: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(config)) {
    if (!ENVELOPE_KEYS.has(key) && value !== undefined) sensitive[key] = value;
  }
  const aad = await envelopeAad(
    { storeId: options.storeId, configId: config.id, teamId: config.teamId ?? null },
    envelope
  );
  const encryptedBlob = await configEncrypt(JSON.stringify(sensitive), sdkDerived, cek, aad);
  return { envelope, encryptedBlob };
}
