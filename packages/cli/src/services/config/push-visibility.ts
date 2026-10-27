/**
 * Push visibility (PLAN-backup-program R2): a config push never happens silently.
 *
 * `RemoteResourceState.pushOnce` and `updateSyncedConfig` skip a push whose synced projection did
 * not change (`isNoopPush`), and print one stderr line for every push that does go out
 * (`announcePush`): the versions, the command that caused it and the JSON pointers that changed.
 */

import { isDeepStrictEqual } from 'node:util';
import { syncedDocument } from '@rediacc/shared/config-schema';
import type {
  RemoteConfigAdapter,
  RemoteVersionInfo,
} from '../../adapters/remote-config-adapter.js';
import { t } from '../../i18n/index.js';
import type { RdcConfig } from '../../types/index.js';

/** The most pointers one line names; the rest is a count. */
const MAX_POINTERS = 8;

let commandPath = '';

/** Record the command path of this invocation (the preAction hook in cli.ts). */
export function setInvocationCommand(path: string): void {
  commandPath = path;
}

/** The command path of this invocation, or '' before the hook ran. */
export function getInvocationCommand(): string {
  return commandPath;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** Drop undefined values and empty objects, which the wire encoding never carries as content. */
function normalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalize);
  if (!isPlainObject(value)) return value;
  const out: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value)) {
    const next = normalize(child);
    if (next === undefined || (isPlainObject(next) && Object.keys(next).length === 0)) continue;
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
export function describeChange(merged: RdcConfig, base: RdcConfig): string {
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
  process.stderr.write(`${line}\n`);
}

export interface ExplainedVersion {
  version: number;
  archivedAt: string;
  /** The pointers this version changed against the next older kept version; null for the oldest. */
  changes: string | null;
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
    const { config } = await adapter.pullVersion(info.version);
    rows.push({
      version: info.version,
      archivedAt: info.archivedAt,
      changes: previous === null ? null : describeChange(config, previous) || '-',
    });
    previous = config;
  }
  return rows.reverse();
}
