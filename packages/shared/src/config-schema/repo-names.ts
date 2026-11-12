/**
 * Join a repository GUID to the name an operator knows it by.
 *
 * Licence notices and the licence tables carry GUIDs only; the config holds the
 * names. `repoNamesByGuid` is the one join, shared by the portal and the CLI.
 */

import { composeRef } from '../ref/index.js';
import type { RdcConfig } from './schemas.js';

type Resources = NonNullable<RdcConfig['resources']>;
type Placement = NonNullable<Resources['repositories']>[string]['placement'];
type Datastores = NonNullable<Resources['datastores']>;

export interface RepoNameEntry {
  /** `name` for the grand tag, `name:tag` for a fork. */
  ref: string;
  family: string;
  tag: string;
  isGrand: boolean;
  machine: string | null;
  datastore: string | null;
  deleted: boolean;
}

/**
 * The machine a repository family resolves to, through its placement.
 *
 * A `machine` placement names the machine directly; a `datastore` placement
 * resolves through the named datastore: a local datastore is anchored to a
 * machine, an RBD datastore is mobile and names none (so the repo's machine is
 * `null`).
 */
export function machineOfPlacement(
  placement: Placement,
  datastores: Datastores
): { machine: string | null; datastore: string | null } {
  if (!placement) return { machine: null, datastore: null };
  if ('machine' in placement) return { machine: placement.machine, datastore: null };
  const store = datastores[placement.datastore];
  if (store && store.backend.kind === 'local') {
    return { machine: store.backend.machine, datastore: placement.datastore };
  }
  return { machine: null, datastore: placement.datastore };
}

export function shortGuid(guid: string): string {
  return guid.slice(0, 8);
}

/** Map every repository GUID in the config, live or deleted, to its name. */
export function repoNamesByGuid(config: RdcConfig): Map<string, RepoNameEntry> {
  const out = new Map<string, RepoNameEntry>();
  const resources = config.resources ?? {};
  const datastores = resources.datastores ?? {};
  for (const [family, record] of Object.entries(resources.repositories ?? {})) {
    const { machine, datastore } = machineOfPlacement(record.placement, datastores);
    for (const [tag, tagRecord] of Object.entries(record.tags)) {
      const isGrand = tag === record.grand;
      out.set(tagRecord.repositoryGuid, {
        ref: composeRef(family, isGrand ? undefined : tag),
        family,
        tag,
        isGrand,
        machine,
        datastore,
        deleted: false,
      });
    }
  }
  for (const archived of resources.deletedRepositories ?? []) {
    if (out.has(archived.repositoryGuid)) continue;
    out.set(archived.repositoryGuid, {
      ref: composeRef(archived.name, archived.tag),
      family: archived.name,
      tag: archived.tag,
      isGrand: false,
      machine: null,
      datastore: null,
      deleted: true,
    });
  }
  return out;
}
