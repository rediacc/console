/**
 * Parser + flattener for `renet repository prune --output json` output.
 *
 * renet emits a single JSON object — `DatastorePrunableResources` (dry-run) or
 * `DatastorePruneResult` (real run). The captured stdout may carry incidental
 * noise (log prefixes / step events) around it, so we extract the last balanced
 * top-level object that parses. Field names match the Go `json:` tags.
 */

export interface IptablesChain {
  name: string;
  table: string;
  network_id: number;
}
export interface AuthKey {
  path: string;
  home_user: string;
  repo_name: string;
  line_num: number;
}
export interface StaleUnit {
  path: string;
  network_id: number;
}

/** Mirror of renet `DatastorePrunableResources` (nil slices marshal as null). */
export interface DatastorePrunableResources {
  empty_mounts?: string[] | null;
  orphan_immovables?: string[] | null;
  orphan_state_mirrors?: string[] | null;
  orphan_legacy_interim?: string[] | null;
  stale_locks?: string[] | null;
  stale_snapshots?: string[] | null;
  stale_backup_snapshots?: string[] | null;
  orphan_sandboxes?: string[] | null;
  iptables_chains?: IptablesChain[] | null;
  auth_keys?: AuthKey[] | null;
  stale_units?: StaleUnit[] | null;
}

export interface PrunePreviewRow {
  type: string;
  resource: string;
}

/**
 * Extract the prune JSON object from captured stdout. The renet bridge relays
 * the sub-command's stdout with a `[repository_prune] ` prefix on every line
 * (same prefix shape repo-list-parser strips), so we drop that first, then parse
 * the cleaned JSON — falling back to the outermost `{`…`}` span to tolerate any
 * stray log lines around the object.
 */
export function parseDatastorePruneOutput(stdout: string): Record<string, unknown> {
  const cleaned = stdout
    .split('\n')
    .map((line) => line.replace(/^\s*\[[^\]]+\]\s?/, ''))
    .join('\n')
    .trim();

  const direct = tryParseObject(cleaned);
  if (direct) return direct;

  const first = cleaned.indexOf('{');
  const last = cleaned.lastIndexOf('}');
  if (first >= 0 && last > first) {
    const obj = tryParseObject(cleaned.slice(first, last + 1));
    if (obj) return obj;
  }
  throw new Error(`Failed to parse datastore prune JSON from output: ${cleaned.slice(0, 200)}`);
}

/** Flatten a dry-run resources object into uniform `{ type, resource }` rows. */
export function buildPrunePreviewRows(resources: DatastorePrunableResources): PrunePreviewRow[] {
  const rows: PrunePreviewRow[] = [];
  const add = (type: string, items: string[] | null | undefined) => {
    for (const r of items ?? []) rows.push({ type, resource: r });
  };
  add('backup-snapshot', resources.stale_backup_snapshots);
  add('stale-snapshot', resources.stale_snapshots);
  add('empty-mount', resources.empty_mounts);
  add('orphan-immovable', resources.orphan_immovables);
  add('orphan-state-mirror', resources.orphan_state_mirrors);
  add('orphan-legacy-interim', resources.orphan_legacy_interim);
  add('stale-lock', resources.stale_locks);
  add('orphan-sandbox', resources.orphan_sandboxes);
  for (const c of resources.iptables_chains ?? []) {
    rows.push({ type: 'iptables-chain', resource: `${c.name} (network ${c.network_id})` });
  }
  for (const k of resources.auth_keys ?? []) {
    rows.push({ type: 'authorized-key', resource: `${k.path}:${k.line_num} (${k.repo_name})` });
  }
  for (const u of resources.stale_units ?? []) {
    rows.push({ type: 'systemd-unit', resource: `${u.path} (network ${u.network_id})` });
  }
  return rows;
}

/** Total resources actually removed, summed from a `DatastorePruneResult`'s
 * `*_pruned` fields (ints) and `*_pruned` arrays (iptables/auth-keys). */
export function countPrunedResources(result: Record<string, unknown>): number {
  let total = 0;
  for (const [key, value] of Object.entries(result)) {
    if (!key.endsWith('_pruned')) continue;
    if (typeof value === 'number') total += value;
    else if (Array.isArray(value)) total += value.length;
  }
  return total;
}

function tryParseObject(s: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(s);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}
