/**
 * Access-key accessors (PLAN-ssh-key-source-ranges): the active config's
 * `access` bucket, read and edited through the synced write path, plus the
 * binding prune `removeMachine` runs. ConfigService (config-resources.ts)
 * extends ConfigAccessService.
 */

import { type AccessConfig, bindingSourceRanges } from '@rediacc/shared/config-schema';
import type { RdcConfig } from '../../types/index.js';
import { omitKey } from '../../utils/omit-key.js';
import { ConfigServiceBase } from './config-base.js';
import { updateSyncedConfig } from './synced-write.js';

function isEmptyAccess(access: AccessConfig): boolean {
  return access.sourceRanges === undefined && Object.keys(access.keys ?? {}).length === 0;
}

/**
 * `access` without any binding to `machineName`. A key whose only range was that binding's would
 * resolve to no range once the binding is gone, which the schema refuses; such a key takes the
 * dropped binding's ranges as its own, so it stays valid and installed nowhere.
 */
export function dropAccessBindings(access: AccessConfig, machineName: string): AccessConfig {
  const keys = { ...(access.keys ?? {}) };
  for (const [keyName, key] of Object.entries(keys)) {
    const binding = key.machines?.[machineName];
    if (binding === undefined) continue;
    const machines = omitKey(key.machines ?? {}, machineName);
    const orphaned =
      Object.keys(machines).length === 0 &&
      key.sourceRanges === undefined &&
      access.sourceRanges === undefined;
    const ownRanges = bindingSourceRanges(binding);
    keys[keyName] = {
      ...key,
      machines,
      ...(orphaned && ownRanges ? { sourceRanges: ownRanges } : {}),
    };
  }
  return { ...access, keys };
}

export abstract class ConfigAccessService extends ConfigServiceBase {
  /** Load the current (or named) config, failing when none is active. */
  protected abstract requireSelfHosted(configName?: string): Promise<RdcConfig>;

  /** The active config's `access` bucket, or undefined when it declares none. */
  async getAccess(): Promise<AccessConfig | undefined> {
    const config = await this.requireSelfHosted();
    return config.access;
  }

  /**
   * Edit the active config's `access` bucket through the synced write path. `edit` receives the
   * bucket of the document being written (an empty one when absent) and must derive its result
   * from it, because a push replays the edit on the fresh server copy after a version conflict.
   * A result with neither ranges nor keys removes the bucket.
   */
  async updateAccess(edit: (access: AccessConfig) => AccessConfig | undefined): Promise<void> {
    const name = this.getEffectiveConfigName();
    await this.requireSelfHosted(name);
    await updateSyncedConfig(name, (cfg) => {
      const next = edit(structuredClone(cfg.access ?? {}));
      const rest = { ...cfg };
      delete rest.access;
      if (next === undefined || isEmptyAccess(next)) return rest;
      return { ...rest, access: next };
    });
  }
}
