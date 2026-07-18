/**
 * Config schema migration runner (issue #382).
 *
 * Reads `schemaVersion` from a raw parsed JSON object and applies registered
 * migrations sequentially until reaching CURRENT_SCHEMA_VERSION. The caller
 * (ConfigFileStorage.load()) then runs `parseConfig` on the upgraded object and
 * persists the result if any migration ran.
 *
 * The runner is ASYNC and carries a MigrationContext: unpacking the v2 compound
 * `/resources` encryption blob (v2→v3 transform 5) needs the master password at
 * migration time. Plaintext migrations ignore the context.
 *
 * Adding a new migration:
 *   1. Bump RdcConfigSchema.schemaVersion's z.literal in ../schemas.ts.
 *   2. Bump CURRENT_SCHEMA_VERSION below.
 *   3. Add packages/shared/src/config-schema/migrations/v<N>-to-v<N+1>.ts.
 *   4. Register it in the MIGRATIONS array below.
 *   5. Drop a fixture at packages/cli/src/__tests__/fixtures/config/v<N>-sample.json.
 *   6. CI gate `check:ci-config-migrations` will round-trip the fixture.
 */

import { migrateV1ToV2 } from './v1-to-v2.js';
import { migrateV2ToV3 } from './v2-to-v3.js';

export const CURRENT_SCHEMA_VERSION = 3;

/** Runtime services a migration may need (lazy — most migrations ignore it). */
export interface MigrationContext {
  /** Resolve the master password (prompts / env), for decrypting v2 blobs. */
  getMasterPassword: () => Promise<string>;
  /**
   * Decrypt a legacy v2 compound `/resources` blob.
   *
   * Injected rather than imported: the AES-GCM provider is a host adapter
   * (node:crypto in the CLI, Web Crypto in a browser), and this package must
   * stay runtime-portable. The CLI passes `nodeCryptoProvider.decrypt`.
   */
  decryptLegacyBlob: (data: string, password: string) => Promise<string>;
}

interface Migration {
  readonly fromVersion: number;
  readonly toVersion: number;
  readonly migrate: (
    raw: Record<string, unknown>,
    ctx: MigrationContext
  ) => Promise<Record<string, unknown>> | Record<string, unknown>;
}

const MIGRATIONS: readonly Migration[] = [
  { fromVersion: 1, toVersion: 2, migrate: migrateV1ToV2 },
  { fromVersion: 2, toVersion: 3, migrate: migrateV2ToV3 },
];

export interface MigrationResult {
  config: Record<string, unknown>;
  migrated: boolean;
  fromVersion: number;
  toVersion: number;
}

/**
 * Apply all pending migrations to a raw config object.
 *
 * - Missing `schemaVersion` is treated as 1 (the original implicit version).
 * - Returns `migrated: false` when the input is already current.
 * - Throws if the input is newer than this CLI knows about — refusing to
 *   downgrade is safer than silently dropping fields.
 */
export async function runMigrations(raw: unknown, ctx: MigrationContext): Promise<MigrationResult> {
  if (!isObject(raw)) {
    throw new TypeError('Config root must be an object');
  }

  const fromVersion = readSchemaVersion(raw);
  if (fromVersion > CURRENT_SCHEMA_VERSION) {
    throw new Error(
      `Config schemaVersion ${fromVersion} is newer than this CLI supports (max ${CURRENT_SCHEMA_VERSION}). Upgrade rdc to read this config.`
    );
  }
  if (fromVersion === CURRENT_SCHEMA_VERSION) {
    return { config: raw, migrated: false, fromVersion, toVersion: fromVersion };
  }

  let current = raw;
  let cursor = fromVersion;
  while (cursor < CURRENT_SCHEMA_VERSION) {
    const next = MIGRATIONS.find((m) => m.fromVersion === cursor);
    if (!next) {
      throw new Error(
        `No migration registered from schemaVersion ${cursor} to ${cursor + 1}. ` +
          `This is a CLI bug — every version gap must have a corresponding migration file.`
      );
    }
    current = await next.migrate(current, ctx);
    cursor = next.toVersion;
  }

  return { config: current, migrated: true, fromVersion, toVersion: cursor };
}

function readSchemaVersion(raw: Record<string, unknown>): number {
  const v = raw.schemaVersion;
  if (v === undefined) return 1;
  if (typeof v !== 'number' || !Number.isInteger(v) || v < 1) {
    throw new TypeError(
      `Invalid schemaVersion ${JSON.stringify(v)} — expected positive integer or absent (defaults to 1).`
    );
  }
  return v;
}

function isObject(x: unknown): x is Record<string, unknown> {
  return typeof x === 'object' && x !== null && !Array.isArray(x);
}

export { migrateV1ToV2, migrateV2ToV3 };
