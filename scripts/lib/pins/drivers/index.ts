/**
 * The T8 drivers, keyed by registry driver name; scripts/lib/pins/drivers/table.ts spreads
 * them into the table the CLI registers with registerDrivers. Each value is built by a
 * factory over the network and process seams of ./shared.ts, so the selftest builds the
 * same drivers over stubs.
 */
import type { PinDriver } from '../driver.js';
import type { Driver } from '../registry.js';
import { actionsDriver } from './actions.js';
import { cephImageDriver } from './cephimage.js';
import { dockerDriver } from './docker.js';
import { gomodDriver } from './gomod.js';
import { osCephHostDriver } from './os.js';
import { realProviderDriver } from './realprovider.js';

export const T8_DRIVERS: Partial<Record<Driver, PinDriver>> = {
  actions: actionsDriver(),
  'go-mod': gomodDriver(),
  'os-ceph-host': osCephHostDriver(),
  'ceph-image': cephImageDriver(),
  'real-provider': realProviderDriver(),
  docker: dockerDriver(),
};
