/**
 * The T8 drivers, keyed by registry driver name, for DRIVER_TABLE in scripts/lib/pins/
 * driver.ts. Each value is built by a factory over the network and process seams of
 * ./shared.ts, so the selftest builds the same drivers over stubs.
 *
 * A driver module may not touch scripts/lib/pins/driver.ts at module evaluation (the table
 * is built while that file is still evaluating when a driver is the entry point); every use
 * of its exports sits inside a function.
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
