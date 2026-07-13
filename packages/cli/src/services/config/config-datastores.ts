/**
 * The named-datastore registry, config side (spec 02 §1 / 03 §5.3).
 *
 * Two halves, deliberately separate:
 *   - `resources.datastores` = the SPEC (backend, size, cluster backref, parent).
 *     What the operator declared. Written by create/fork/delete.
 *   - `state.datastores`     = the ROUTING HINT (attachedTo, writes, mountPath).
 *     Where it currently lives. Written by attach/detach, and it is exactly what
 *     derived-machine resolution reads to answer "which machine hosts this repo"
 *     (services/addressing/resolve-machine.ts).
 *
 * The machine-side registry (renet's `datastore list`) stays authoritative for
 * what is really mounted; the config records the operator's intent plus the hint.
 * `config reconcile` is what re-syncs the hint after the world moves underneath it,
 * which is why every read here tolerates a stale hint instead of trusting it blindly.
 *
 * The implicit `default` datastore never appears in this registry (R2-F1): it is a
 * property of a machine, not a named, movable pool.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { notFound } from '../../utils/cli-exit-error.js';
import { ValidationError } from '../../utils/errors.js';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { configService } from './config-resources.js';

type DatastoreConfig = NonNullable<NonNullable<RdcConfig['resources']>['datastores']>[string];
export type DatastoreState = NonNullable<NonNullable<RdcConfig['state']>['datastores']>[string];

/** Names reserved for the cluster control plane (spec §5.5: `cluster create` owns them). */
const CONTROL_DS_PREFIX = 'ds-control-';

/** A datastore ref is `name` or `name:tag` (the fork grammar, spec §5.3). */
export function parseDatastoreRef(ref: string): { name: string; tag?: string } {
  const [name, ...rest] = ref.split(':');
  if (!name || rest.length > 1) {
    throw new ValidationError(
      `"${ref}" is not a datastore ref. Use <name> or <name>:<tag> (for example ds-data:exp).`
    );
  }
  return rest.length === 1 && rest[0] ? { name, tag: rest[0] } : { name };
}

/**
 * Refuse the names the model does not own. `default` is implicit (R2-F1) and
 * `ds-control-*` belongs to `cluster create`, which sizes and attaches it as the
 * cluster's anchor; letting an operator mint one by hand would produce a control
 * datastore no cluster knows about.
 */
export function assertCreatableName(name: string): void {
  if (name === 'default') {
    throw new ValidationError(
      'the default datastore is implicit; these verbs manage additional named datastores.'
    );
  }
  if (name.startsWith(CONTROL_DS_PREFIX)) {
    throw new ValidationError(
      `"${CONTROL_DS_PREFIX}*" names are reserved for cluster control planes. ` +
        `"rdc cluster create" provisions them.`
    );
  }
}

export async function listDatastores(): Promise<Record<string, DatastoreConfig>> {
  const cfg = await configService.getCurrent();
  return cfg?.resources?.datastores ?? {};
}

export async function listDatastoreState(): Promise<Record<string, DatastoreState>> {
  const cfg = await configService.getCurrent();
  return cfg?.state?.datastores ?? {};
}

/**
 * `map[key]` lies: the repo does not enable `noUncheckedIndexedAccess`, so a missing
 * key is typed as present while yielding undefined at runtime. Every absence check in
 * this file guards a real runtime case, and going through this helper is what keeps
 * them type-legal — annotating the variable is not enough, because TypeScript narrows
 * a const back to the initializer's (lying) type.
 */
export function at<T>(map: Record<string, T>, key: string): T | undefined {
  return map[key];
}

/** One datastore's record, or exit 5 naming what IS registered. */
export async function getDatastore(ref: string): Promise<DatastoreConfig> {
  const all = await listDatastores();
  const record = at(all, ref);
  if (!record) {
    const known = Object.keys(all).sort();
    throw notFound(`datastore "${ref}" is not in this config.`, {
      details:
        known.length > 0
          ? [`registered datastores: ${known.join(', ')}`]
          : ['no named datastores are registered. Create one with "rdc datastore create <name>".'],
    });
  }
  return record;
}

/** The machine a datastore is currently attached to, per the routing hint. */
async function datastoreHost(ref: string): Promise<string | undefined> {
  return at(await listDatastoreState(), ref)?.attachedTo;
}

/**
 * The machine to DISPATCH a datastore operation at. An attached datastore is
 * reached through its holder; a detached one has no host, so the caller must say
 * where (`--to`, or `--machine` for create). Exit 12 rather than a guess: dispatching
 * a datastore op at the wrong machine is how you fence a live holder by accident.
 */
export async function requireDatastoreHost(ref: string): Promise<string> {
  const host = await datastoreHost(ref);
  if (!host) {
    throw new ValidationError(
      `datastore "${ref}" is not attached to any machine, so there is nowhere to run this. ` +
        `Attach it first: rdc datastore attach ${ref} --to <machine>.`
    );
  }
  return host;
}

export async function recordDatastore(name: string, record: DatastoreConfig): Promise<void> {
  await configFileStorage.update(configService.getEffectiveConfigName(), (cfg) => ({
    ...cfg,
    resources: {
      ...(cfg.resources ?? {}),
      datastores: { ...(cfg.resources?.datastores ?? {}), [name]: record },
    },
  }));
}

export async function forgetDatastore(name: string): Promise<void> {
  await configFileStorage.update(configService.getEffectiveConfigName(), (cfg) => {
    const datastores = { ...(cfg.resources?.datastores ?? {}) };
    delete datastores[name];
    return { ...cfg, resources: { ...(cfg.resources ?? {}), datastores } };
  });
}

/** Update the routing hint (attach/detach). Passing undefined clears the entry. */
export async function setDatastoreState(
  name: string,
  state: DatastoreState | undefined
): Promise<void> {
  const current = { ...(await listDatastoreState()) };
  if (state === undefined) {
    delete current[name];
  } else {
    current[name] = state;
  }
  await configService.setStateBucket('datastores', current);
}

/** Repos whose placement points at this datastore (delete refuses on these). */
export async function reposInDatastore(ref: string): Promise<string[]> {
  const cfg = await configService.getCurrent();
  const families = cfg?.resources?.repositories ?? {};
  const found: string[] = [];
  for (const [name, family] of Object.entries(families)) {
    // Placement is a property of the FAMILY (every tag of a repo lives in the same
    // datastore; a fork that moved is a different family). Report each tag so the
    // operator sees exactly what a --force delete would take with it.
    const placement = family.placement;
    if (!placement || !('datastore' in placement) || placement.datastore !== ref) continue;
    for (const tag of Object.keys(family.tags)) {
      found.push(tag === family.grand ? name : `${name}:${tag}`);
    }
  }
  return found.sort();
}
