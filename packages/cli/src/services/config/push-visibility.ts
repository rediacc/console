/**
 * Push visibility (PLAN-backup-program R2): a config push never happens silently.
 *
 * `RemoteResourceState.pushOnce` and `updateSyncedConfig` skip a push whose synced projection did
 * not change (`isNoopPush`), and print one stderr line for every push that does go out
 * (`announcePush`): the versions, the command that caused it and the JSON pointers that changed.
 */

import { isDeepStrictEqual } from 'node:util';
import { buildPointer, metaForPointer, syncedDocument } from '@rediacc/shared/config-schema';
import type {
  RemoteConfigAdapter,
  RemoteVersionInfo,
} from '../../adapters/remote-config-adapter.js';
import { RemoteAuthError, RemoteUnreachableError } from '../../adapters/remote-config-errors.js';
import { t } from '../../i18n/index.js';
import type { RdcConfig } from '../../types/index.js';
import { getOutputFormat } from '../../utils/errors.js';
import { outputService } from '../core/output.js';

/** The most pointers one line names; the rest is a count. */
const MAX_POINTERS = 8;

let commandPath = '';

/** Record the command path of this invocation (the preAction hook in cli.ts). */
export function setInvocationCommand(path: string): void {
  commandPath = path;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isEmptyObject(value: unknown): boolean {
  return isPlainObject(value) && Object.keys(value).length === 0;
}

function isWholeStored(path: string[]): boolean {
  return path.length > 0 && metaForPointer(buildPointer(path)) !== undefined;
}

/**
 * The synced document as the push compares it. The wire carries the document as JSON
 * (`buildConfigPushPayload` round-trips it through `JSON.stringify`), so an undefined value never
 * travels and is dropped here too.
 *
 * A value at a pointer the sensitivity registry names is stored WHOLE: the walker treats it as one
 * leaf, and a committed one gets one HMAC over all of it (`/policy`, `/access`,
 * `/resources/storages`). An empty object inside it is content, so the value is kept exactly as
 * JSON carries it: adding `{}` there changes the commitment and the push must go out.
 *
 * Elsewhere an empty object is dropped. It does travel on the wire, but it backs no committed leaf,
 * and a pull rebuilds some as `{}` regardless (`fromFullConfig` writes empty `machines` and
 * `repositories`), so keeping them would turn every pulled copy into a spurious push.
 */
function normalize(value: unknown, path: string[] = []): unknown {
  // A whole-stored value is kept as JSON carries it, an empty `{}` at its root included.
  if (value !== undefined && isWholeStored(path)) return JSON.parse(JSON.stringify(value));
  if (Array.isArray(value)) return value.map((item, i) => normalize(item, [...path, String(i)]));
  if (!isPlainObject(value)) return value;
  const out: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value)) {
    const childPath = [...path, key];
    const next = normalize(child, childPath);
    if (next === undefined || (isEmptyObject(next) && !isWholeStored(childPath))) continue;
    out[key] = next;
  }
  return out;
}

function projection(config: RdcConfig): unknown {
  return normalize(syncedDocument(config));
}

function escapeSegment(segment: string): string {
  return segment.replaceAll('~', '~0').replaceAll('/', '~1');
}

function collect(before: unknown, after: unknown, pointer: string, out: string[]): void {
  if (isDeepStrictEqual(before, after)) return;
  if (isPlainObject(before) && isPlainObject(after)) {
    const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
    for (const key of [...keys].sort((a, b) => a.localeCompare(b))) {
      collect(before[key], after[key], `${pointer}/${escapeSegment(key)}`, out);
    }
    return;
  }
  out.push(pointer || '/');
}

/** The JSON pointers at which the synced projections of `before` and `after` differ. */
export function changedPointers(before: unknown, after: unknown): string[] {
  const out: string[] = [];
  collect(before, after, '', out);
  return out;
}

/** True when `merged` and `base` carry the same synced document: pushing would only bump the version. */
export function isNoopPush(merged: RdcConfig, base: RdcConfig): boolean {
  return isDeepStrictEqual(projection(merged), projection(base));
}

/** The pointers a push of `merged` over `base` changes, capped for one line. */
function describeChange(merged: RdcConfig, base: RdcConfig): string {
  const pointers = changedPointers(projection(base), projection(merged));
  const shown = pointers.slice(0, MAX_POINTERS).join(', ');
  return pointers.length > MAX_POINTERS ? `${shown}, +${pointers.length - MAX_POINTERS}` : shown;
}

/** Print the one-line record of a push to stderr. */
export function announcePush(
  configName: string,
  from: number,
  to: number,
  merged: RdcConfig,
  base: RdcConfig
): void {
  const line = t('commands.config.remote.pushVisibility', {
    config: configName,
    from: String(from),
    to: String(to),
    command: commandPath || '-',
    changes: describeChange(merged, base) || '-',
  });
  // outputService.info honours --quiet; a machine-readable run (-o json) keeps stderr to errors.
  if (getOutputFormat() === 'json') return;
  outputService.info(line);
}

export interface ExplainedVersion {
  version: number;
  archivedAt: string;
  /** The pointers this version changed against the next older kept version; null for the oldest. */
  changes: string | null;
  /** Why the version could not be read (pull or decrypt failed); `changes` is null then. */
  unreadable?: string;
}

/**
 * Explain the kept versions entry by entry: each version is pulled (client-side decrypt) and
 * diffed against the next older one. Newest first, like the listing.
 */
export async function explainVersions(
  adapter: Pick<RemoteConfigAdapter, 'pullVersion'>,
  versions: RemoteVersionInfo[]
): Promise<ExplainedVersion[]> {
  const ascending = [...versions].sort((a, b) => a.version - b.version);
  const rows: ExplainedVersion[] = [];
  let previous: RdcConfig | null = null;
  for (const info of ascending) {
    const read = await readVersion(adapter, info.version);
    if ('unreadable' in read) {
      // The next readable version is diffed against the last one that could be read.
      rows.push({
        version: info.version,
        archivedAt: info.archivedAt,
        changes: null,
        unreadable: read.unreadable,
      });
      continue;
    }
    rows.push({
      version: info.version,
      archivedAt: info.archivedAt,
      changes: previous === null ? null : describeChange(read.config, previous) || '-',
    });
    previous = read.config;
  }
  return rows.reverse();
}

/**
 * One version's document, or why it could not be read. One unreadable version (a rotated key, a
 * pruned archive) must not hide the rest, but an unreachable server or a refused token is not a
 * property of the version: it ends the run.
 */
async function readVersion(
  adapter: Pick<RemoteConfigAdapter, 'pullVersion'>,
  version: number
): Promise<{ config: RdcConfig } | { unreadable: string }> {
  try {
    return { config: (await adapter.pullVersion(version)).config };
  } catch (error) {
    if (error instanceof RemoteUnreachableError || error instanceof RemoteAuthError) throw error;
    return { unreadable: error instanceof Error ? error.message : String(error) };
  }
}
