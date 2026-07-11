import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/renet-contract';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import type { RdcConfig } from '../../types/index.js';

// Network ID space: 2816 to ~16,777,152, step 64 → ~261,944 possible IDs.
const MAX_NETWORK_ID = 16_711_680;

/** Collect network IDs already assigned to repositories (v3: state.repos). */
function scanUsedNetworkIds(config: RdcConfig): Set<number> {
  const usedIds = new Set<number>();
  for (const tags of Object.values(config.state?.repos ?? {})) {
    for (const runtime of Object.values(tags)) {
      if (runtime.networkId !== undefined && runtime.networkId > 0) usedIds.add(runtime.networkId);
    }
  }
  return usedIds;
}

/**
 * Allocate the next network ID in a named config, advancing the forward
 * counter. The counter lives in `state.networkIds.next` (status half) and is
 * written via `updateState` so allocation churn never bumps the version
 * counter (R2-F2).
 */
export async function allocateNetworkIdInStore(configName: string): Promise<number> {
  let allocated = 0;
  await configFileStorage.updateState(configName, (config) => {
    const usedIds = scanUsedNetworkIds(config);
    let nextId = config.state?.networkIds?.next;
    if (nextId === undefined || nextId < MIN_NETWORK_ID) nextId = pickInitialNetworkId(usedIds);
    // If the forward counter is approaching the limit, scan for freed gaps
    // (handles long-lived systems where many repos have been created + deleted).
    if (nextId > MAX_NETWORK_ID) nextId = findFreeNetworkIdSlot(usedIds, MAX_NETWORK_ID);
    allocated = nextId;
    return {
      ...config,
      state: {
        ...(config.state ?? {}),
        networkIds: { next: nextId + NETWORK_ID_INCREMENT },
      },
    };
  });
  return allocated;
}

// Find the initial network ID when the forward counter is missing or stale.
// Avoids `Math.max(...usedIds)` because JS engines cap function arguments
// around 65536 while the network ID space allows ~261000 IDs — a long-lived
// shared config can hit that cap before the MAX_NETWORK_ID ceiling.
function pickInitialNetworkId(usedIds: Set<number>): number {
  if (usedIds.size === 0) return MIN_NETWORK_ID;
  let maxId = -1;
  for (const id of usedIds) {
    if (id > maxId) maxId = id;
  }
  return maxId + NETWORK_ID_INCREMENT;
}

// Linear scan for the first free slot when the forward counter has walked
// past the allowed ceiling. Thrown error is caught by the outer allocation
// path and surfaced to the user.
function findFreeNetworkIdSlot(usedIds: Set<number>, maxNetworkId: number): number {
  let candidate = MIN_NETWORK_ID;
  while (usedIds.has(candidate) && candidate <= maxNetworkId) {
    candidate += NETWORK_ID_INCREMENT;
  }
  if (candidate > maxNetworkId) {
    const totalSlots = Math.floor((maxNetworkId - MIN_NETWORK_ID) / NETWORK_ID_INCREMENT + 1);
    throw new Error(
      `Network ID space exhausted: all ${totalSlots} slots are in use. Delete unused repositories to free slots.`
    );
  }
  return candidate;
}
