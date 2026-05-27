import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/queue-vault';

// Find the initial network ID when the forward counter is missing or stale.
// Avoids `Math.max(...usedIds)` because JS engines cap function arguments
// around 65536 while the network ID space allows ~261000 IDs — a long-lived
// shared config can hit that cap before the MAX_NETWORK_ID ceiling.
export function pickInitialNetworkId(usedIds: Set<number>): number {
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
export function findFreeNetworkIdSlot(usedIds: Set<number>, maxNetworkId: number): number {
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
