/**
 * How each {@link ResourceKind} is discovered — the single table a console reads
 * to fill a resource picker.
 *
 * Two kinds of source:
 *   - `config`  — the values live in a family of the operator's decrypted config
 *     (e.g. `machine` → `resources.machines`). No round trip; the picker reads
 *     the already-loaded config object.
 *   - `command` — the values come from running a discovery command and pulling a
 *     field out of its `-o json` output (e.g. `container` → run `machine status`,
 *     read `containers[].name`). `needs` lists the config-sourced kinds that must
 *     be supplied as context before the command can run (a container list needs a
 *     machine); `extract` is the JSON path of the values to offer.
 *
 * The picker is only ever a HINT (see {@link ResourceKind}): free text is always
 * accepted, so an empty or failed discovery degrades to a plain text box, never a
 * block.
 */

import type { ResourceKind } from './types.js';

/** Config families (of `resources`) that back a config-sourced discovery. */
export type DiscoveryFamily =
  | 'machines'
  | 'datastores'
  | 'storages'
  | 'repositories'
  | 'clusters'
  | 'cloudProviders'
  | 'backupStrategies';

/** Where the values for a {@link ResourceKind} come from. */
export type DiscoverySource =
  | {
      /** The values are a family of the decrypted config. */
      readonly source: 'config';
      /** The `resources` family to read. */
      readonly family: DiscoveryFamily;
    }
  | {
      /** The values come from a discovery command's `-o json` output. */
      readonly source: 'command';
      /** pathKey of the command to run; resolves via `getCommand()`. */
      readonly pathKey: string;
      /** Config-sourced kinds that must be supplied as context first. */
      readonly needs: readonly ResourceKind[];
      /** JSON path of the values to offer, e.g. "containers[].name". */
      readonly extract: string;
    };

/** Every resource kind, in declaration order — for exhaustiveness checks. */
export const RESOURCE_KINDS = [
  'machine',
  'repo',
  'datastore',
  'storage',
  'cluster',
  'provider',
  'container',
  'template',
  'snapshot',
  'job',
  'strategy',
  'artifact',
] as const satisfies readonly ResourceKind[];

/** Every config family a config-sourced discovery may name. */
export const DISCOVERY_FAMILIES = [
  'machines',
  'datastores',
  'storages',
  'repositories',
  'clusters',
  'cloudProviders',
  'backupStrategies',
] as const satisfies readonly DiscoveryFamily[];

export const RESOURCE_DISCOVERY: Record<ResourceKind, DiscoverySource> = {
  // ── Config-sourced (read straight from the decrypted config) ────────────
  machine: { source: 'config', family: 'machines' },
  repo: { source: 'config', family: 'repositories' },
  datastore: { source: 'config', family: 'datastores' },
  storage: { source: 'config', family: 'storages' },
  cluster: { source: 'config', family: 'clusters' },
  provider: { source: 'config', family: 'cloudProviders' },
  // The 6 strategy positionals bind here; `backupStrategies` is a real
  // ResourcesSchema family (config-schema/schemas.ts).
  strategy: { source: 'config', family: 'backupStrategies' },

  // ── Command-sourced (run a discovery command, extract a field) ──────────
  // VERIFIED: machine status `-o json` (buildEnrichedJson, commands/machine/
  // status.ts) emits a top-level `containers` array whose elements carry `.name`.
  container: {
    source: 'command',
    pathKey: 'machine status',
    needs: ['machine'],
    extract: 'containers[].name',
  },
  // `repo admin template list` iterates the embedded TEMPLATES and prints
  // `tmpl.name` (commands/repo-extended.ts). Templates are static/embedded, so
  // a console may source them without a machine; needs is therefore empty.
  template: {
    source: 'command',
    pathKey: 'repo admin template list',
    needs: [],
    extract: 'name',
  },
  // `datastore snapshot list <datastore>` prints the renet
  // `datastore_snapshot_list` payload verbatim (commands/datastore.ts). The
  // renet-side element shape is not verifiable from console source; `[].name`
  // is the most likely field and the console degrades to free text otherwise.
  snapshot: {
    source: 'command',
    pathKey: 'datastore snapshot list',
    needs: ['datastore'],
    extract: '[].name',
  },
  // VERIFIED: `job list -o json` prints `jobs.map(toListRow)` where each row is
  // `{ id: status.job_id, ... }` (commands/job.ts), so the identifier is `id`.
  job: {
    source: 'command',
    pathKey: 'job list',
    needs: ['machine'],
    extract: '[].id',
  },
  // `backup list` honors `-o json`, emitting the standard success envelope whose
  // `data` is the rendered rows array `{ mode, name, guid, size, modified }`
  // (renderBackupList, commands/repo-backup-list.ts). `name` is the resolved
  // display name that `backup restore <artifact-ref>` resolves against a
  // repository, so `[].name` offers each artifact. A console may pass --storage
  // from context. Artifact refs use the shared ref grammar.
  artifact: {
    source: 'command',
    pathKey: 'backup list',
    needs: ['machine'],
    extract: '[].name',
  },
};
