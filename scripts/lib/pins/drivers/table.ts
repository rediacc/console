/**
 * Every real pin driver, keyed by registry driver name: T7's embed, devcontainer and
 * toolchain drivers over the network upstream, and T8's family drivers. The CLI registers
 * this table with registerDrivers at startup; driver.ts never imports it (see the comment
 * on its DRIVER_TABLE).
 */

import type { PinDriver } from '../driver.js';
import type { Driver } from '../registry.js';
import { createDevcontainerDriver } from './devcontainer.js';
import { createEmbedDriver } from './embed.js';
import { T8_DRIVERS } from './index.js';
import { npmDriver } from './npm.js';
import { createToolchainDriver } from './toolchain.js';
import { networkUpstream } from './toolchain-upstream.js';

export function realDrivers(): Partial<Record<Driver, PinDriver>> {
  const upstream = networkUpstream();
  return {
    ...T8_DRIVERS,
    npm: npmDriver,
    embed: createEmbedDriver(upstream),
    devcontainer: createDevcontainerDriver(upstream),
    toolchain: createToolchainDriver(upstream),
  };
}
