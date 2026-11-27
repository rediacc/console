/**
 * Per-field encryption-at-rest transform for the config file (v3).
 *
 * Encryption is a STORAGE-LAYER transform, not a caller behavior: every writer
 * goes through ConfigFileStorage, which decrypts on read and re-encrypts on
 * write, so no caller ever produces or sees a blob. This is the single
 * chokepoint that makes the R2-F3 data-loss class impossible, there is no
 * second "plaintext resources" path that a persist can clobber.
 *
 * Granularity is driven ENTIRELY by schema/sensitivity.ts: any leaf whose
 * registry meta has `encryptAtRest` (default true for secret/credential) is
 * moved out of the plaintext tree into `encryption.encryptedFields[pointer]`.
 * The one deliberate exception is `/credentials/masterPasswordVerifier`
 * (encryptAtRest:false), encrypting it under the password it verifies would
 * be a bootstrapping deadlock.
 *
 * Every sealed mode (anything but `plaintext`, PLAN-config-sealed-local.md D1)
 * runs the transform. A new blob is v2: AES-256-GCM under the field key of
 * adapters/config-seal-key.ts, with `pointer|keyringId` as AAD. A blob with no
 * `v` is legacy (per-blob PBKDF2 at the legacy count under the password); it is
 * read, never written, and the next encrypt re-seals it as v2.
 *
 * Because an encrypted leaf is ABSENT from the plaintext tree at rest, a strict
 * schema parse of the on-disk form would reject required fields (e.g. a cloud
 * provider's apiToken). `injectEncryptedStubs` hydrates each encrypted leaf with
 * a type-valid placeholder before parse so public reads succeed WITHOUT
 * prompting for the master password (spec 04 §2.4); `decryptConfigFields`
 * replaces the stubs with real values when a sensitive field is actually read.
 */

import type { EncryptedBlob, RdcConfig } from '@rediacc/shared/config-schema';
import {
  getByPointer,
  isSealed,
  setByPointer,
  usesKeyring,
  usesMasterPassword,
  walkSensitive,
} from '@rediacc/shared/config-schema';
import {
  deriveFieldKey,
  newSealKdf,
  openString,
  type SealKdf,
  SealKeyLostError,
  sealString,
} from './config-seal-key.js';
import { nodeCryptoProvider } from './crypto.js';

const STUB_PREFIX = '<encrypted:';

/** Type-valid placeholder for an encrypted leaf we have not decrypted. */
function stubFor(pointer: string): string {
  return `${STUB_PREFIX}${pointer}>`;
}

function isStub(value: unknown): boolean {
  return typeof value === 'string' && value.startsWith(STUB_PREFIX);
}

function parentPointer(pointer: string): string {
  const idx = pointer.lastIndexOf('/');
  return idx <= 0 ? '' : pointer.slice(0, idx);
}

/** The AAD of a v2 blob: binds it to its field and to the keyring key it was sealed under. */
function blobAad(pointer: string, keyringId: string | undefined): string {
  return `${pointer}|${keyringId ?? ''}`;
}

/**
 * Fill every encrypted leaf with a type-valid stub so a strict parse of the
 * at-rest config succeeds. `encryptedFields` is left intact so a later
 * decryptConfigFields can restore the real values. No-op unless sealed. Never
 * touches a key: a public read through stubs needs no secure storage and no
 * password.
 */
export function injectEncryptedStubs(config: RdcConfig): RdcConfig {
  if (!isSealed(config)) return config;
  const fields = config.encryption?.encryptedFields;
  if (!fields) return config;

  let result: RdcConfig = config;
  for (const pointer of Object.keys(fields)) {
    if (getByPointer(result, pointer) === undefined) {
      result = setByPointer(result, pointer, stubFor(pointer)) as RdcConfig;
    }
  }
  return result;
}

type Blobs = Record<string, EncryptedBlob>;

/** What one encrypt pass seals with: the derived key, the keyring id for the AAD, and the password for legacy blobs. */
interface SealContext {
  key: CryptoKey;
  keyringId: string | undefined;
  password: string | undefined;
}

async function sealValue(
  ctx: SealContext,
  pointer: string,
  value: unknown
): Promise<EncryptedBlob> {
  return {
    v: 2,
    data: await sealString(ctx.key, JSON.stringify(value), blobAad(pointer, ctx.keyringId)),
  };
}

/**
 * Carry a blob whose leaf this pass never decrypted. A v2 blob is carried only after it opens under
 * the current key, so a re-seal that forgot to decrypt first fails here instead of writing a field no
 * key opens. A legacy blob is re-sealed as v2, which needs the password it was made with.
 */
async function carryBlob(
  ctx: SealContext,
  pointer: string,
  blob: EncryptedBlob
): Promise<EncryptedBlob> {
  if (blob.v === 2) {
    try {
      await openString(ctx.key, blob.data, blobAad(pointer, ctx.keyringId));
    } catch {
      throw new Error(
        `sealed field ${pointer} was not sealed under the current key; decrypt the config before re-sealing it`
      );
    }
    return blob;
  }
  if (ctx.password === undefined) {
    throw new Error(`legacy sealed field ${pointer} needs the master password to be re-sealed`);
  }
  return sealValue(
    ctx,
    pointer,
    JSON.parse(await nodeCryptoProvider.decrypt(blob.data, ctx.password))
  );
}

/**
 * Preserve blobs whose leaf is absent but whose parent container still exists
 * (a writer spread the at-rest config without decrypting that leaf).
 */
async function preserveAbsentBlobs(
  ctx: SealContext,
  config: RdcConfig,
  existing: Blobs,
  fields: Blobs
): Promise<void> {
  for (const [pointer, blob] of Object.entries(existing)) {
    if (Object.hasOwn(fields, pointer)) continue;
    if (getByPointer(config, pointer) !== undefined) continue;
    if (getByPointer(config, parentPointer(pointer)) !== undefined) {
      fields[pointer] = await carryBlob(ctx, pointer, blob);
    }
  }
}

/** The key one encrypt pass seals with, and the kdf record it writes (created when a password mode has none yet). */
async function sealContext(
  config: RdcConfig,
  encryption: NonNullable<RdcConfig['encryption']>,
  password: string | undefined
): Promise<{ ctx: SealContext; kdf: SealKdf | undefined }> {
  const kdf = usesMasterPassword(encryption.mode)
    ? (encryption.kdf ?? newSealKdf())
    : encryption.kdf;
  const target: RdcConfig = { ...config, encryption: { ...encryption, kdf } };
  const ctx: SealContext = {
    key: await deriveFieldKey(target, password),
    keyringId: usesKeyring(encryption.mode) ? encryption.keyringId : undefined,
    password,
  };
  return { ctx, kdf };
}

/**
 * Move every encrypt-at-rest leaf into `encryption.encryptedFields` as a fresh
 * v2 blob and remove it from the plaintext tree. A leaf that is still a stub
 * (never decrypted this cycle) carries its existing blob (see carryBlob), so a
 * save that never decrypted cannot corrupt or drop encrypted data. No-op when
 * not sealed.
 *
 * The seal parameters come from `config.encryption`: its mode, its `keyringId`
 * (minted by the caller with `mintKey` before the first keyring seal) and its
 * `kdf`, which is created here when a password mode has none yet (the legacy
 * master-password file). `password` is required when the mode includes the
 * master password, and to re-seal a legacy blob. Every other `encryption`
 * field (`sealOptOut` included) is kept.
 */
export async function encryptConfigFields(
  config: RdcConfig,
  password?: string
): Promise<RdcConfig> {
  const encryption = config.encryption;
  if (!encryption || !isSealed(config)) return config;
  const existing: Blobs = encryption.encryptedFields ?? {};
  const { ctx, kdf } = await sealContext(config, encryption, password);

  const leaves = [...walkSensitive(config)].filter(
    (e) => e.meta.encryptAtRest && e.value !== undefined
  );

  let result: RdcConfig = config;
  const encryptedFields: Blobs = {};
  for (const { pointer, value } of leaves) {
    if (!isStub(value)) {
      encryptedFields[pointer] = await sealValue(ctx, pointer, value);
    } else if (Object.hasOwn(existing, pointer)) {
      encryptedFields[pointer] = await carryBlob(ctx, pointer, existing[pointer]);
    }
    result = setByPointer(result, pointer, undefined) as RdcConfig;
  }

  await preserveAbsentBlobs(ctx, result, existing, encryptedFields);
  return { ...result, encryption: { ...encryption, kdf, encryptedFields } };
}

/** Open one blob: v2 under the field key, legacy under the password. */
async function openBlob(
  config: RdcConfig,
  pointer: string,
  blob: EncryptedBlob,
  fieldKey: () => Promise<CryptoKey>,
  password: string | undefined
): Promise<string> {
  const encryption = config.encryption;
  if (blob.v !== 2) {
    if (password === undefined)
      throw new Error(`legacy sealed field ${pointer} needs the master password`);
    return nodeCryptoProvider.decrypt(blob.data, password);
  }
  const keyringId = usesKeyring(encryption?.mode) ? encryption?.keyringId : undefined;
  const key = await fieldKey();
  try {
    return await openString(key, blob.data, blobAad(pointer, keyringId));
  } catch {
    // Under a key that includes the keyring key, a failure the password cannot explain is key loss
    // (the caller checks the password against its verifier before unsealing).
    if (keyringId !== undefined) throw new SealKeyLostError(config.id, keyringId, 'auth');
    throw new Error(
      `sealed field ${pointer} did not open: wrong master password or a damaged file`
    );
  }
}

/**
 * Restore every encrypted leaf back into the plaintext tree (overwriting stubs).
 * Returns the config with `encryptedFields` cleared in memory (the mode and the
 * seal parameters stay, so a subsequent save re-seals). No-op when not sealed or
 * when there is nothing to decrypt. The field key is derived only when a v2 blob
 * is present, and at most once per call.
 *
 * Throws SealKeyLostError when the keyring key is missing, or a v2 blob fails
 * under a key that includes it.
 */
export async function decryptConfigFields(
  config: RdcConfig,
  password?: string
): Promise<RdcConfig> {
  const encryption = config.encryption;
  if (!encryption || !isSealed(config)) return config;
  const encryptedFields = encryption.encryptedFields;
  if (!encryptedFields || Object.keys(encryptedFields).length === 0) return config;

  let derived: Promise<CryptoKey> | undefined;
  const fieldKey = () => (derived ??= deriveFieldKey(config, password));

  let result: RdcConfig = config;
  for (const [pointer, blob] of Object.entries(encryptedFields)) {
    const json = await openBlob(config, pointer, blob, fieldKey, password);
    result = setByPointer(result, pointer, JSON.parse(json)) as RdcConfig;
  }

  return { ...result, encryption: { ...encryption, encryptedFields: {} } };
}
