/**
 * Rediacc config schema, sensitivity registry, walker, and migrations.
 *
 * This package is the single definition of the config document, shared by three
 * runtimes: the CLI (Node), the executor (`rdc serve`, Node in a container),
 * and the web console (browser). Everything here is dependency-free apart from
 * zod, and uses no Node built-ins, so it bundles for the browser unchanged.
 *
 * Two deliberate exclusions:
 *   - The AES-GCM at-rest field encryption stays in the CLI
 *     (`adapters/config-field-crypto.ts`), because it is a storage-layer
 *     transform bound to a host crypto provider.
 *   - The synchronous SHA-256 fingerprint helpers stay in the CLI
 *     (`schema/fingerprint.ts`), because Web Crypto has no sync digest.
 */

export * from './migrations/index.js';
export * from './payload.js';
export * from './schemas.js';
export * from './sensitivity.js';
export * from './state-schema.js';
export * from './walker.js';
