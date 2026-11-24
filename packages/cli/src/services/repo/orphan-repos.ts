/**
 * Repository images on a machine that no config entry names (worklist #48d790e1).
 *
 * `repo delete` takes only a config-resolved ref, so an image whose GUID left every config could not be removed by
 * name. This module classifies a machine's images with the same analysis `machine prune --orphaned-repos` uses
 * (analyzePrune: in the current config, in another config, or archived inside the grace window means protected), adds
 * the one reference that analysis does not read (a configured fork whose grand lineage is the image's GUID), and
 * owns the single delete call both `machine prune` and `repo admin orphan delete` make: renet `repository_delete`
 * with the GUID, never a raw filesystem removal.
 */

import { readFile } from 'node:fs/promises';
import { composeRef } from '@rediacc/shared/ref';
import {
  getRepositories,
  type RepositoryInfo,
} from '@rediacc/shared/renet-contract/data/list-types.generated';
import { t } from '../../i18n/index.js';
import { configService } from '../config/config-resources.js';
import { getExecutor } from '../executor/executor-factory.js';
import type { ExecuteResult } from '../executor/types.js';
import { fetchMachineStatus } from '../machine/machine-status.js';
import { analyzePrune } from './prune.js';

/** One image on the machine, judged against every readable config. */
export interface MachineRepoVerdict {
  guid: string;
  /** The ref the current config's archive record gives the GUID (`name` or `name:tag`), else null: no config entry names an orphan. */
  name: string | null;
  verdict: 'orphaned' | 'protected';
  reason: string;
  mounted: boolean;
  running: boolean;
  containers: number;
  isFork: boolean;
  size: string;
  modified: string;
}

/** The repository's Docker daemon answers, or it has containers: deleting it would stop live work. */
function isRepoRunning(repo: RepositoryInfo): boolean {
  return (
    Boolean(repo.docker_running) || Boolean(repo.containers_running) || repo.container_count > 0
  );
}

/** Grand GUIDs the current config's forks descend from: such an image is a lineage the config still names. */
async function configuredGrandGuids(): Promise<Set<string>> {
  const grands = new Set<string>();
  for (const repo of await configService.listRepositories()) {
    const { grandGuid, repositoryGuid } = repo.config;
    if (grandGuid && grandGuid !== repositoryGuid) grands.add(grandGuid.toLowerCase());
  }
  return grands;
}

/** GUID (lowercase) -> the ref of the current config's archive record for it: the one name an orphaned image can still carry. */
export async function archivedNames(): Promise<Map<string, string>> {
  const names = new Map<string, string>();
  for (const record of await configService.listArchivedRepositories()) {
    if (record.repositoryGuid) {
      names.set(record.repositoryGuid.toLowerCase(), composeRef(record.name, record.tag));
    }
  }
  return names;
}

/** Why analyzePrune listed a GUID in neither bucket: it refused the whole scan (an unreadable config, warned). */
const SCAN_REFUSED = 'config scan refused: a config could not be read (see the warning above)';
const GRAND_OF_FORK = 'grand lineage of a configured fork';

/**
 * Read the machine's repository images and judge each one. Read-only: one `list all` probe, then config reads.
 */
export async function classifyMachineRepos(
  machineName: string,
  options: { debug?: boolean } = {}
): Promise<MachineRepoVerdict[]> {
  const status = await fetchMachineStatus(machineName, {
    sections: ['repositories'],
    debug: options.debug,
  });
  const repos = getRepositories(status);
  if (repos.length === 0) return [];
  const analysis = await analyzePrune(
    repos.map((r) => r.name),
    { forceAvailable: false }
  );
  const orphaned = new Map(analysis.orphaned.map((c) => [c.guid, c.reason]));
  const protectedReasons = new Map(analysis.protected.map((c) => [c.guid, c.reason]));
  const grands = await configuredGrandGuids();
  const names = await archivedNames();

  return repos.map((repo) => {
    const guid = repo.name;
    const base = {
      guid,
      name: names.get(guid.toLowerCase()) ?? null,
      mounted: Boolean(repo.mounted),
      running: isRepoRunning(repo),
      containers: repo.container_count,
      isFork: Boolean(repo.is_fork),
      size: repo.size_human,
      modified: repo.modified_human,
    };
    const protectedReason =
      protectedReasons.get(guid) ??
      (grands.has(guid.toLowerCase()) ? GRAND_OF_FORK : undefined) ??
      (orphaned.has(guid) ? undefined : SCAN_REFUSED);
    if (protectedReason !== undefined) {
      return { ...base, verdict: 'protected' as const, reason: protectedReason };
    }
    return { ...base, verdict: 'orphaned' as const, reason: orphaned.get(guid) ?? '' };
  });
}

/**
 * Delete one repository image by GUID through renet `repository_delete` (it stops the repository's Docker daemon,
 * unmounts, closes LUKS and removes the image, its grants, licence blobs and backup state). The one delete call of
 * every GUID-addressed path, so `machine prune` and `repo admin orphan delete` cannot drift apart.
 */
export function deleteRepoImageByGuid(
  machineName: string,
  guid: string,
  options: { debug?: boolean; quietSpinners?: boolean } = {}
): Promise<ExecuteResult> {
  return getExecutor().execute({
    functionName: 'repository_delete',
    machineName,
    params: { repository: guid },
    debug: options.debug,
    ...(options.quietSpinners ? { quietSpinners: true } : {}),
  });
}

/** One line of `executor_orphans list --json` (.ci/rediacc_ci/ops/executor_orphans.py): an executor-created repo, fork or machine. */
export interface ExecutorEvent {
  machine: string | null;
  repo: string | null;
  guid: string | null;
  at: string | null;
}

function textOrNull(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null;
}

/** Parse the tool's JSON lines (blank lines skipped). A line that is not a JSON object is a hard error naming its number. */
export function parseExecutorEvents(text: string): ExecutorEvent[] {
  const events: ExecutorEvent[] = [];
  for (const [index, line] of text.split('\n').entries()) {
    if (line.trim() === '') continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      parsed = null;
    }
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      throw new Error(
        t('commands.repo.admin.orphan.list.executorEventsBadLine', { line: index + 1 })
      );
    }
    const row = parsed as Record<string, unknown>;
    events.push({
      machine: textOrNull(row.machine),
      repo: textOrNull(row.repo),
      guid: textOrNull(row.guid),
      at: textOrNull(row.at),
    });
  }
  return events;
}

export async function readExecutorEvents(file: string): Promise<ExecutorEvent[]> {
  let text: string;
  try {
    text = await readFile(file, 'utf8');
  } catch (error) {
    throw new Error(
      t('commands.repo.admin.orphan.list.executorEventsUnreadable', {
        file,
        error: error instanceof Error ? error.message : String(error),
      })
    );
  }
  return parseExecutorEvents(text);
}

/** A GUID-less event names the repo as the executor saw it: the whole archived ref (`name` or `name:tag`) or its name part. */
function namesEvent(ref: string | null, repo: string): boolean {
  return ref !== null && (ref === repo || ref.split(':')[0] === repo);
}

/**
 * Join the executor's events onto the verdicts. Only an event whose machine is `machine` counts: an event naming no
 * machine cannot place the image on this one. An event carrying a GUID matches the image with that GUID; an event
 * carrying none (one recorded before the executor shipped the GUID) matches the orphan whose archived name is the
 * event's repo name. A matched orphan gets the executor reason with the event time. A protected image keeps its verdict
 * and reason, and an unmatched orphan keeps its own reason: another cause produced it.
 */
export function applyExecutorEvents(
  rows: MachineRepoVerdict[],
  events: ExecutorEvent[],
  machine: string
): MachineRepoVerdict[] {
  const onMachine = events.filter((e) => e.machine === machine);
  return rows.map((row) => {
    if (row.verdict !== 'orphaned') return row;
    const guid = row.guid.toLowerCase();
    const hit = onMachine.find((e) =>
      e.guid === null ? namesEvent(row.name, e.repo) : e.guid.toLowerCase() === guid
    );
    if (!hit) return row;
    return {
      ...row,
      reason: t('commands.repo.admin.orphan.list.executorReason', { at: hit.at ?? '-' }),
    };
  });
}
