import type { Placement } from '@rediacc/shared/config-schema';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { DEFAULT_DATASTORE } from '../services/account/license-machine.js';
import {
  type AttemptFailure,
  type ResolveInStore,
  runWithFallbackAt,
  type StorePick,
} from '../services/backup/backup-store-pick.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { outputService } from '../services/core/output.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { shellQuote } from '../utils/shell-quote.js';
import type { ChunkRestoreResult } from './backup-restore-chunk.js';
import type { BackupManifestsResponse } from './backup-storage.js';

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
  // The inner script is quoted as one word, so a `$` or backtick in the path is not expanded by the login shell before sh runs.
  const script = `test -e ${shellQuote(path)} && echo ${PRESENT} || echo ${ABSENT}`;
  const answer = (await sftp.exec(`sudo sh -c ${shellQuote(script)}`)).trim();
  if (answer === PRESENT) return true;
  return answer === ABSENT ? false : undefined;
}

/**
 * Whether the account index holds any snapshot of the lineage. An unreachable
 * index or an unreadable answer is "no": the caller then takes the pull route,
 * which is what restore did before the chunk store existed. That fallback is
 * said out loud, since on a chunk-store repo the pull has nothing to fetch.
 */
export async function lineageHasSnapshots(lineage: string, name: string): Promise<boolean> {
  try {
    const result = await accountServerFetch<BackupManifestsResponse>(
      // Whether any row exists: one is enough, and the listing is capped per page.
      `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}&limit=1`
    );
    return result.manifests.length > 0; // a malformed answer throws into the catch
  } catch (error) {
    outputService.warn(
      t('commands.backup.restore.snapshotIndexUnreadable', {
        name,
        reason: error instanceof Error ? error.message : String(error),
      })
    );
    return false;
  }
}

/**
 * Place a whole-image chunk restore from the lineage's stores: `--from`'s store alone, or the account's ranking with
 * a fallback to the next store when one fails for its own reasons (5xx, refused grant, unreachable). The requested
 * point is resolved inside each store before that store's attempt, so a fallback restores the snapshot the next store
 * holds rather than one only the failed store had; a store holding none at or before the point is passed over. An
 * attempt hands its failure back unrendered only when that failure moves the run on to another store; every other
 * failure, the last store's included, is rendered by the attempt itself. Says which store served.
 */
export async function restoreFromStores(args: {
  /** Chosen before the target is registered, so a refused ranking leaves nothing to roll back. */
  pick: StorePick;
  /** The snapshot the requested point names inside `store`; its refusal is thrown before anything is registered. */
  resolve: ResolveInStore;
  /** One attempt against `store`: register the target, restore `snapshotId`, and defer a failure `deferIf` accepts. */
  attempt: (
    store: string,
    snapshotId: string,
    deferIf: ((failure: AttemptFailure) => Promise<boolean>) | undefined
  ) => Promise<ChunkRestoreResult>;
}): Promise<void> {
  const { pick } = args;
  const result = await runWithFallbackAt(
    pick,
    args.resolve,
    async (store, snapshotId, movesOn) => {
      const outcome = await args.attempt(store, snapshotId, pick.explicit ? undefined : movesOn);
      return outcome.ok ? { ok: true, value: undefined } : { ok: false, failure: outcome.failure };
    },
    (failed, next) => {
      outputService.warn(t('commands.backup.restore.storeFallback', { failed, next }));
    }
  );
  if (result.ok)
    outputService.info(t('commands.backup.restore.storeServed', { store: result.store }));
}
