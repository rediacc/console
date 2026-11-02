/**
 * Which repositories a scheduled backup unit covers, resolved from the config.
 *
 * renet takes repository GUIDs only (`backup snapshot --repo <guid>`, `--exclude-repo <guid>`), so a
 * strategy's include/exclude NAMES are resolved here, against the config, before anything is
 * rendered. An unknown name is an error, never a pass-through: a name on argv is refused by renet at
 * run time, inside a timer nobody watches.
 *
 * Name grammar, as in the rest of the strategy surface:
 *   - `name`      every tag of the family (the grand and its forks), so a fork made later joins the
 *                 schedule on the next render;
 *   - `name:tag`  exactly that tag.
 *
 * Placement decides the datastore. A family placed on `{ machine: m }` lives on m's implicit
 * datastore; one placed on `{ datastore: ref }` lives on that named datastore. A unit is rendered per
 * (strategy, datastore), and only repositories placed on that datastore reach its argv.
 *
 * Everything here is pure over the config, so the unit content stays deterministic (the reconciler
 * diffs by hash).
 */

import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { RdcConfig, RepoFamily } from '@rediacc/shared/config-schema';
import type { BackupStrategyConfig } from '../../types/index.js';

/** One datastore of a machine that can carry a backup unit. */
export interface ScheduleDatastore {
  /** Registry key of a named datastore; undefined for the machine's implicit datastore. */
  key: string | undefined;
  /** Mount path renet is pointed at with --datastore. */
  path: string;
}

/**
 * A strategy as the scheduler reads it. `repoSchedules` is the per-repo cadence override (a repo ref
 * mapped to its own 5-field cron); the strategy's `schedule` applies to every other repository.
 */
export type ScheduledStrategy = BackupStrategyConfig & {
  repoSchedules?: Record<string, string>;
};

/** The repositories one unit covers. */
export interface UnitScope {
  /** `--repo <guid>` values; undefined means every repository on the datastore. */
  include?: string[];
  /** `--exclude-repo <guid>` values; only used when include is undefined. */
  exclude: string[];
}

/** One unit to render: a strategy on a datastore, at a cadence, over a scope. */
export interface ScheduleUnitSpec {
  /** Unit name suffix: `rediacc-backup-<unitName>.service`. */
  unitName: string;
  strategyName: string;
  strategy: BackupStrategyConfig;
  /** 5-field cron this unit's timer runs on. */
  schedule: string;
  datastore: ScheduleDatastore;
  scope: UnitScope;
  /** The ref of a per-repo override unit; absent for the strategy's main unit. */
  repoRef?: string;
}

type DatastoreMap = NonNullable<NonNullable<RdcConfig['resources']>['datastores']>;
type AttachMap = NonNullable<NonNullable<RdcConfig['state']>['datastores']>;

const byText = (a: string, b: string): number => a.localeCompare(b);

/** Where a named datastore is mounted on `machineName`, or undefined when it is not there. */
function namedDatastorePath(
  key: string,
  named: DatastoreMap,
  attached: AttachMap,
  machineName: string
): string | undefined {
  const backend = named[key].backend;
  if (backend.kind === 'local') return backend.machine === machineName ? backend.path : undefined;
  if (!(key in attached)) return undefined;
  const st = attached[key];
  return st.attachedTo === machineName ? st.mountPath : undefined;
}

/**
 * Every datastore of `machineName` a unit can run against: the implicit one, each named local
 * datastore anchored on the machine, and each mobile (rbd) datastore currently attached to it with a
 * known mount path. Sorted by key so rendering order is stable.
 */
export function scheduleDatastoresFor(config: RdcConfig, machineName: string): ScheduleDatastore[] {
  const machine = config.resources?.machines?.[machineName];
  if (!machine) throw new Error(`Machine "${machineName}" not found in config`);
  const result: ScheduleDatastore[] = [
    { key: undefined, path: machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH },
  ];
  const named: DatastoreMap = config.resources?.datastores ?? {};
  const attached: AttachMap = config.state?.datastores ?? {};
  for (const key of Object.keys(named).sort(byText)) {
    const path = namedDatastorePath(key, named, attached, machineName);
    if (path) result.push({ key, path });
  }
  return result;
}

function familyDatastoreKey(name: string, family: RepoFamily, machineName: string): string | null {
  const placement = family.placement;
  if (!placement) {
    throw new Error(
      `Repository "${name}" has no placement in the config, so the datastore its backup runs on is unknown. Record it with: rdc config reconcile`
    );
  }
  if ('datastore' in placement) return `ds:${placement.datastore}`;
  return placement.machine === machineName ? 'implicit' : null;
}

function datastoreToken(ds: ScheduleDatastore): string {
  return ds.key === undefined ? 'implicit' : `ds:${ds.key}`;
}

/** A resolved repo: its ref (`name:tag`) and GUID. */
interface ResolvedRepo {
  ref: string;
  guid: string;
}

/**
 * Resolve one strategy ref to the repos it names on the given datastore. Throws on an unknown family
 * or tag; returns [] when the family lives elsewhere (another machine or datastore).
 */
function resolveRef(
  ref: string,
  families: Record<string, RepoFamily>,
  machineName: string,
  ds: ScheduleDatastore
): ResolvedRepo[] {
  const colon = ref.indexOf(':');
  const name = colon === -1 ? ref : ref.slice(0, colon);
  const tag = colon === -1 ? undefined : ref.slice(colon + 1);
  if (!(name in families)) {
    throw new Error(
      `Backup strategy names repository "${ref}", which is not in the config. Refusing to render a unit: renet takes GUIDs only, and a name it cannot resolve would fail the backup at run time.`
    );
  }
  const family = families[name];
  if (tag !== undefined && !(tag in family.tags)) {
    throw new Error(
      `Backup strategy names "${ref}", but repository "${name}" has no tag "${tag}".`
    );
  }
  if (familyDatastoreKey(name, family, machineName) !== datastoreToken(ds)) return [];
  const tags = tag === undefined ? Object.keys(family.tags).sort(byText) : [tag];
  return tags.map((t) => ({ ref: `${name}:${t}`, guid: family.tags[t].repositoryGuid }));
}

function resolveRefs(
  refs: string[] | undefined,
  families: Record<string, RepoFamily>,
  machineName: string,
  ds: ScheduleDatastore
): ResolvedRepo[] {
  const seen = new Set<string>();
  const out: ResolvedRepo[] = [];
  for (const ref of refs ?? []) {
    for (const repo of resolveRef(ref, families, machineName, ds)) {
      if (seen.has(repo.guid)) continue;
      seen.add(repo.guid);
      out.push(repo);
    }
  }
  return out;
}

/** systemd unit names allow [A-Za-z0-9:_.\\-]; '.' separates the parts, ':' becomes '.'. */
function unitPart(value: string): string {
  return value.replaceAll(':', '.');
}

interface RepoOverride {
  repo: ResolvedRepo;
  schedule: string;
}

/**
 * The per-repo cadence overrides that apply on this datastore: a repo the strategy excludes, or does
 * not include, gets no unit of its own; the first override naming a repo wins.
 */
function resolveOverrides(
  strategy: ScheduledStrategy,
  families: Record<string, RepoFamily>,
  machineName: string,
  ds: ScheduleDatastore,
  included: ResolvedRepo[] | undefined,
  excludedGuids: Set<string>
): RepoOverride[] {
  const schedules = strategy.repoSchedules ?? {};
  const inScope = (guid: string): boolean =>
    !excludedGuids.has(guid) && (!included || included.some((r) => r.guid === guid));
  const overrides: RepoOverride[] = [];
  for (const ref of Object.keys(schedules).sort(byText)) {
    for (const repo of resolveRef(ref, families, machineName, ds)) {
      if (!inScope(repo.guid) || overrides.some((o) => o.repo.guid === repo.guid)) continue;
      overrides.push({ repo, schedule: schedules[ref] });
    }
  }
  return overrides;
}

/** The main unit's scope, or null when an include list leaves nothing to back up here. */
function mainScope(
  included: ResolvedRepo[] | undefined,
  excludedGuids: Set<string>,
  overrideGuids: Set<string>
): UnitScope | null {
  if (!included) return { exclude: [...excludedGuids, ...overrideGuids].sort(byText) };
  const guids = included
    .map((r) => r.guid)
    .filter((g) => !excludedGuids.has(g) && !overrideGuids.has(g));
  return guids.length > 0 ? { include: guids, exclude: [] } : null;
}

/**
 * The units one strategy needs on one datastore: the main unit (unless its scope resolved to
 * nothing) and one unit per repository with a per-repo cadence override.
 *
 * An include list that resolves to no repository on this datastore yields NO main unit. Emitting a
 * unit with no --repo would back up every repository on the datastore, the opposite of what an
 * include list says.
 */
export function strategyUnitSpecs(
  strategyName: string,
  strategy: ScheduledStrategy,
  config: RdcConfig,
  machineName: string,
  ds: ScheduleDatastore
): ScheduleUnitSpec[] {
  const families = config.resources?.repositories ?? {};
  const baseName = ds.key === undefined ? strategyName : `${strategyName}.ds.${unitPart(ds.key)}`;
  const included = strategy.include?.length
    ? resolveRefs(strategy.include, families, machineName, ds)
    : undefined;
  const excludedGuids = new Set(
    resolveRefs(strategy.exclude, families, machineName, ds).map((r) => r.guid)
  );
  const overrides = resolveOverrides(strategy, families, machineName, ds, included, excludedGuids);
  const scope = mainScope(included, excludedGuids, new Set(overrides.map((o) => o.repo.guid)));

  const common = { strategyName, strategy, datastore: ds };
  const specs: ScheduleUnitSpec[] = [];
  if (scope) specs.push({ ...common, unitName: baseName, schedule: strategy.schedule, scope });
  for (const { repo, schedule } of overrides) {
    specs.push({
      ...common,
      unitName: `${baseName}.repo.${unitPart(repo.ref)}`,
      schedule,
      scope: { include: [repo.guid], exclude: [] },
      repoRef: repo.ref,
    });
  }
  return specs;
}

/**
 * Every unit the bound strategies need on a machine, across all of its datastores. A strategy whose
 * include list names only repositories on other datastores contributes nothing there.
 */
export function machineUnitSpecs(
  strategies: { name: string; config: ScheduledStrategy }[],
  config: RdcConfig,
  machineName: string
): ScheduleUnitSpec[] {
  const specs: ScheduleUnitSpec[] = [];
  for (const ds of scheduleDatastoresFor(config, machineName)) {
    for (const { name, config: strategy } of strategies) {
      specs.push(...strategyUnitSpecs(name, strategy, config, machineName, ds));
    }
  }
  return specs;
}

/** GUIDs of every placed repository on one datastore of the machine. */
function guidsOnDatastore(
  families: Record<string, RepoFamily>,
  machineName: string,
  ds: ScheduleDatastore
): string[] {
  const token = datastoreToken(ds);
  return Object.entries(families)
    .filter(
      ([name, family]) =>
        family.placement && familyDatastoreKey(name, family, machineName) === token
    )
    .flatMap(([, family]) => Object.values(family.tags).map((t) => t.repositoryGuid));
}

/**
 * GUIDs of every repository a unit set covers on a machine, mapped to the crons of the units
 * covering it. A unit with no include list covers every repository placed on its datastore, minus
 * its exclude list.
 */
export function coverageByGuid(
  specs: ScheduleUnitSpec[],
  config: RdcConfig,
  machineName: string
): Map<string, string[]> {
  const families = config.resources?.repositories ?? {};
  const result = new Map<string, string[]>();
  for (const spec of specs) {
    const excluded = new Set(spec.scope.exclude);
    const guids =
      spec.scope.include ??
      guidsOnDatastore(families, machineName, spec.datastore).filter((g) => !excluded.has(g));
    for (const guid of guids) result.set(guid, [...(result.get(guid) ?? []), spec.schedule]);
  }
  return result;
}
