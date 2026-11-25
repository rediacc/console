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

/** Config names that need no shell quoting. */
const SHELL_SAFE_NAME = /^[A-Za-z0-9._@:+-]+$/;

/**
 * The text of an `rdc` command a hint tells the user to run, aimed at the config the failure is about:
 * `rdc --config <name> <sub>` when a non-default config is active (or named in `configName`), `rdc <sub>`
 * for the default one. A hint that names the bare command sends the user to the default config instead,
 * which enrolled the wrong one on 2026-11-25 and cost a second browser 2FA round.
 */
export function rdcCommand(sub: string, configName: string = getEffectiveConfigName()): string {
  if (configName === DEFAULTS.CONTEXT.CONFIG_NAME) return `rdc ${sub}`;
  const shown = SHELL_SAFE_NAME.test(configName)
    ? configName
    : `'${configName.replace(/'/g, `'\\''`)}'`;
  return `rdc --config ${shown} ${sub}`;
}
