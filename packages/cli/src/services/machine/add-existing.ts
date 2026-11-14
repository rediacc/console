/**
 * Register a machine that already exists and answers SSH: the config record plus a host-key scan.
 *
 * Shared by `rdc machine add` and the machine step of `rdc server install`, which registers a
 * brought server or LAN device from `--ip --user [--port] [--name]` before it touches it.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { t } from '../../i18n/index.js';
import type { MachineConfig } from '../../types/index.js';
import { assertResourceName, MachineConfigSchema, parseConfig } from '../../utils/config-schema.js';
import { scanHostKeys } from '../../utils/host-keys.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';

export interface ExistingMachineInput {
  ip: string;
  user: string;
  port?: number | string;
}

/** Write the machine record, then pin its host keys; a failed scan is not fatal, as in `machine add`. */
export async function addExistingMachine(
  name: string,
  input: ExistingMachineInput
): Promise<MachineConfig> {
  assertResourceName(name);
  const port =
    typeof input.port === 'number'
      ? input.port
      : Number.parseInt(input.port ?? String(DEFAULTS.SSH.PORT), 10);
  const machineConfig = parseConfig(
    MachineConfigSchema,
    { ip: input.ip.trim(), user: input.user.trim(), port },
    'machine config'
  ) as MachineConfig;

  await configService.addMachine(name, machineConfig);
  outputService.success(
    t('commands.machine.add.success', { name, user: machineConfig.user, ip: machineConfig.ip })
  );

  try {
    const keyscan = scanHostKeys(machineConfig.ip, machineConfig.port ?? DEFAULTS.SSH.PORT);
    if (keyscan) {
      await configService.updateMachine(name, { knownHosts: keyscan });
      outputService.info(t('commands.machine.scanKeys.keysScanned', { name }));
    }
  } catch {
    /* non-fatal */
  }
  return machineConfig;
}
