import type { Placement } from '@rediacc/shared/config-schema';
import { DEFAULT_DATASTORE } from '../services/account/license-machine.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { shellQuote } from '../utils/shell-quote.js';

const GUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PRESENT = 'present';
const ABSENT = 'absent';

/**
 * Whether the place machine holds the source repo's image at `repositories/<guid>`: the artifact
 * `repo push --to <machine>` leaves there, under the source's own GUID. `true` and `false` are
 * answers; `undefined` means the machine could not be asked, and the caller falls back to the
 * snapshot index.
 *
 * This decides the restore route when `--at` is absent. The snapshot index is keyed by LINEAGE,
 * which every fork and every machine of a family shares, so a family whose grand is backed up on
 * one machine has snapshots for a fork that was only ever pushed to another. Routing on the index
 * alone sent a pushed fork into the chunk route, whose stream probe ran `backup verify` on a
 * machine that never backed the repo up (live 2026-11-05, observability:lab@obs-lab).
 */
export async function sourceImageOnMachine(source: {
  machine: string;
  guid: string;
  placement?: Placement;
}): Promise<boolean | undefined> {
  if (!GUID_RE.test(source.guid)) return undefined;
  let lease: Awaited<ReturnType<typeof machineConnections.acquire>>;
  try {
    lease = await machineConnections.acquire(source.machine);
  } catch {
    return undefined;
  }
  try {
    const mounts = candidateMounts(source.placement, lease.machine.datastore);
    for (const mount of mounts) {
      const answer = await probeImage(lease.sftp, `${mount}/repositories/${source.guid}`);
      if (answer !== false) return answer;
    }
    return false;
  } catch {
    return undefined;
  } finally {
    lease.release();
  }
}

/** The recorded named datastore first, then the machine's own: where the image can be. */
function candidateMounts(placement: Placement | undefined, machineDatastore?: string): string[] {
  const placed =
    placement && 'datastore' in placement ? namedDatastoreMount(placement.datastore) : undefined;
  return [...new Set([placed, machineDatastore ?? DEFAULT_DATASTORE])].filter(
    (m): m is string => !!m
  );
}

/** One `test -e`: true, false, or undefined for any answer but the two words (sudo refused, no shell). */
async function probeImage(
  sftp: { exec(command: string): Promise<string> },
  path: string
): Promise<boolean | undefined> {
  const answer = (
    await sftp.exec(`sudo sh -c "test -e ${shellQuote(path)} && echo ${PRESENT} || echo ${ABSENT}"`)
  ).trim();
  if (answer === PRESENT) return true;
  return answer === ABSENT ? false : undefined;
}
