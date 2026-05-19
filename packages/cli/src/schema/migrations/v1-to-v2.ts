/**
 * Config schema v1 → v2 migration.
 *
 * The v2 schema differs from v1 only by the addition of the explicit
 * `schemaVersion` field. v1 configs were implicitly version 1: they
 * predate the version-pinned schema and lacked the discriminator. v2
 * is the current shape produced by `createEmptyRdcConfig()`.
 *
 * The migration is intentionally minimal: it stamps `schemaVersion: 2`
 * and leaves the rest of the document untouched, relying on the Zod
 * parser run by the caller (`ConfigFileStorage.load()`) to surface any
 * field-level drift as a `ValidationError`. v1 documents that were
 * valid against the implicit v1 shape parse cleanly against v2.
 *
 * Idempotent: running it twice on the same input is a no-op.
 */

export function migrateV1ToV2(raw: Record<string, unknown>): Record<string, unknown> {
  return {
    ...raw,
    schemaVersion: 2,
  };
}
