import { DEFAULTS } from '@rediacc/shared/config';

/**
 * Config-name resolution as a leaf module (imports nothing but shared defaults)
 * so low-level services (subscription-auth, updater, telemetry, account-pointer)
 * can resolve the effective config name without importing `configService` and
 * risking an import cycle.
 *
 * `configService` (config-base.ts) delegates its own override setter and
 * name resolution to this module, so both agree on a single source of truth.
 */
let runtimeOverride: string | null = null;

/** Set a runtime config-name override (used by the `--config` flag). */
export function setConfigNameOverride(name: string | null): void {
  runtimeOverride = name;
}

/**
 * Get the effective config name.
 * Priority: --config flag > REDIACC_CONFIG env var > "rediacc".
 */
export function getEffectiveConfigName(): string {
  return runtimeOverride ?? process.env.REDIACC_CONFIG ?? DEFAULTS.CONTEXT.CONFIG_NAME;
}
