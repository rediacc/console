/**
 * Persistent per-machine renet provision/verify cache.
 *
 * The provisioner's in-memory cache dies with the process, so every fresh
 * `rdc` invocation used to re-pay the cold path against an already-current
 * machine: SHA-256 over the ~220MB dev binary plus 2-3 provision SSH execs,
 * and 2 more for machine-setup verification (~500ms+ per command). This module
 * remembers a successful provision across processes so consecutive commands
 * skip all of it.
 *
 * Trust envelope — a persisted entry is honored only when ALL hold:
 *  - recorded CLI version equals the running VERSION,
 *  - the entry is younger than the TTL (same 1h as the in-memory cache),
 *  - dev mode only: the source binary's (mtimeMs, size) still match. Dev
 *    VERSION is a constant (`0.0.0-dev`), so a rebuilt `bin/renet` is only
 *    detectable by its stat fingerprint — this preserves the "next rdc.sh run
 *    deploys your renet change" promise at the cost of one ~1ms stat.
 *
 * Any provision failure drops the entry (fail open into the full path).
 *
 * State lives in the CONFIG (`state.renetProvision`), not a sidecar file —
 * same reasoning as `license-refresh-state.ts`: sidecars are machine-local
 * litter that leaks into tests; config state is mocked, versioned, and
 * inspectable. Written through `updateState`, so churn never bumps the
 * config's version counter (R2-F2).
 */

import * as fs from 'node:fs';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { VERSION } from '../../version.js';
import { configService } from '../config/config-resources.js';

export interface RenetProvisionEntry {
  version: string;
  hash: string;
  arch: string;
  verifiedAt: number;
  setupVerifiedAt?: number;
  srcMtimeMs?: number;
  srcSize?: number;
}

/** Mirrors the provisioner's in-memory CACHE_TTL_MS (1 hour). */
export const RENET_PROVISION_STATE_TTL_MS = 60 * 60 * 1000;

/** Stat a dev-mode source binary; null when it cannot be statted. */
function statFingerprint(sourcePath: string): { srcMtimeMs: number; srcSize: number } | null {
  try {
    const st = fs.statSync(sourcePath);
    return { srcMtimeMs: Math.floor(st.mtimeMs), srcSize: st.size };
  } catch {
    return null;
  }
}

function freshEntry(
  entry: RenetProvisionEntry | undefined,
  at: number | undefined,
  now: number
): boolean {
  if (entry?.version !== VERSION) return false;
  if (typeof at !== 'number' || Number.isNaN(at)) return false;
  // A future timestamp means a clock change, not a recent verification.
  if (at > now) return false;
  return now - at < RENET_PROVISION_STATE_TTL_MS;
}

async function readEntry(hostPort: string): Promise<RenetProvisionEntry | undefined> {
  const config = await configService.getCurrent();
  return config?.state?.renetProvision?.[hostPort];
}

/**
 * A provision entry this process may trust, or null. `sourcePath` is the
 * dev-mode local binary (null for SEA-embedded binaries, which are immutable
 * per released version).
 */
export async function getFreshProvisionEntry(
  hostPort: string,
  sourcePath: string | null,
  now = Date.now()
): Promise<RenetProvisionEntry | null> {
  const entry = await readEntry(hostPort);
  if (!entry || !freshEntry(entry, entry.verifiedAt, now)) return null;
  if (sourcePath !== null) {
    const fp = statFingerprint(sourcePath);
    if (!fp || fp.srcMtimeMs !== entry.srcMtimeMs || fp.srcSize !== entry.srcSize) return null;
  }
  return entry;
}

/** Whether machine setup was persistently verified recently for this host. */
export async function isSetupVerifiedFresh(hostPort: string, now = Date.now()): Promise<boolean> {
  const entry = await readEntry(hostPort);
  return freshEntry(entry, entry?.setupVerifiedAt, now);
}

async function writeEntry(
  hostPort: string,
  mutate: (previous: RenetProvisionEntry | undefined) => RenetProvisionEntry | undefined
): Promise<void> {
  const configName = configService.getEffectiveConfigName();
  await configFileStorage.updateState(configName, (config) => {
    const bucket: Record<string, RenetProvisionEntry> = {
      ...(config.state?.renetProvision ?? {}),
    };
    const next = mutate(bucket[hostPort]);
    if (next === undefined) delete bucket[hostPort];
    else bucket[hostPort] = next;
    return {
      ...config,
      state: { ...(config.state ?? {}), renetProvision: bucket },
    };
  });
}

/** Record a successful provision verification. Best-effort at call sites. */
export async function recordProvisionVerified(
  hostPort: string,
  details: { hash: string; arch: string; sourcePath: string | null },
  now = Date.now()
): Promise<void> {
  const fp = details.sourcePath === null ? null : statFingerprint(details.sourcePath);
  await writeEntry(hostPort, (previous) => ({
    version: VERSION,
    hash: details.hash,
    arch: details.arch,
    verifiedAt: now,
    // Preserve a still-relevant setup verification across provision refreshes.
    ...(previous?.setupVerifiedAt !== undefined && { setupVerifiedAt: previous.setupVerifiedAt }),
    ...(fp ?? {}),
  }));
}

/**
 * Record a successful machine-setup verification. Only annotates an existing
 * provision entry — setup verification always runs after provisioning, and a
 * bare setup timestamp without its provision context is not independently
 * trustworthy.
 */
export async function recordSetupVerified(hostPort: string, now = Date.now()): Promise<void> {
  await writeEntry(hostPort, (previous) =>
    previous ? { ...previous, setupVerifiedAt: now } : undefined
  );
}

/** Drop one machine's entry — called on provision failure (fail open). */
export async function dropProvisionEntry(hostPort: string): Promise<void> {
  await writeEntry(hostPort, () => undefined);
}
