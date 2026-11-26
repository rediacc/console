/**
 * `rdc config import-machine <machine> --from <config>`: copy one machine and everything placed on
 * it from another config into the active one (PLAN-hostinger-to-bench Design 5).
 *
 * Copied: the machine entry when the active config lacks it, every repository family placed on the
 * machine with every tag (GUID, credential, keys and secrets), the named local datastore a family is
 * placed on, and each backup strategy bound to the machine together with its binding. Nothing that
 * already exists is overwritten: an equal entry is a no-op, and a differing one is refused (a
 * same-name repository with another GUID, a machine at another address, a datastore with another
 * backend, a network ID another repository already holds). A differing strategy is refused unless `--strategy-from-source` replaces it. Any refusal
 * writes nothing, so a run either lands whole or not at all.
 *
 * The write goes through `updateSyncedConfig`, and the plan is computed again inside the edit from
 * the document the edit is given, so a remote config's version-conflict replay re-checks against
 * the fresh server copy. The report carries names and verdicts only, never a credential, key or
 * GUID value.
 *
 * Each imported repository also carries its `state.repos.<family>.<tag>.networkId`, the id of its
 * Docker daemon on the machine, and the target's `state.networkIds.next` counter moves past it so
 * a later allocation cannot hand it out again. A repository whose source has no networkId stays
 * without one. An id the target holds for another repository, or for the same tag under another
 * value, is refused: the id is a real daemon on the machine, so it is never reused or renumbered.
 */

import { isDeepStrictEqual } from 'node:util';
import { DEFAULTS } from '@rediacc/shared/config';
import { NETWORK_ID_INCREMENT } from '@rediacc/shared/renet-contract';
import type { Command } from 'commander';
import { configFileStorage } from '../adapters/config-file-storage.js';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { updateSyncedConfig } from '../services/config/synced-write.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat, RdcConfig } from '../types/index.js';
import { stateMismatch } from '../utils/cli-exit-error.js';
import { handleError, ValidationError } from '../utils/errors.js';

type Resources = NonNullable<RdcConfig['resources']>;
type MachineEntry = NonNullable<Resources['machines']>[string];
type RepoFamily = NonNullable<Resources['repositories']>[string];
type DatastoreEntry = NonNullable<Resources['datastores']>[string];
type StateRepos = NonNullable<NonNullable<RdcConfig['state']>['repos']>;

type ImportKind =
  | 'machine'
  | 'datastore'
  | 'strategy'
  | 'binding'
  | 'repository'
  | 'tag'
  | 'networkId';
type ImportStatus = 'equal' | 'added' | 'replaced' | 'refused';
type RefusalReason =
  | 'machine-differs'
  | 'datastore-differs'
  | 'strategy-differs'
  | 'strategy-missing'
  | 'placement-differs'
  | 'grand-differs'
  | 'guid-differs'
  | 'tag-differs'
  | 'network-id-differs'
  | 'network-id-collision';

/** One verdict of the import report. `name` is a resource name (`family:tag` for a tag), never a value. */
interface ImportRow {
  kind: ImportKind;
  name: string;
  status: ImportStatus;
  reason?: RefusalReason;
}

interface ImportPlan {
  rows: ImportRow[];
  /** The target config with every non-refused change applied; equal to the input when nothing changes. */
  config: RdcConfig;
  changes: number;
  refusals: number;
  /** Detail lines of the network ID collisions, each naming both repositories. */
  collisions: string[];
}

interface ImportOptions {
  strategyFromSource?: boolean;
}

/** The connection identity of a machine: the same name at another address or user is another machine. */
function machineIdentity(m: MachineEntry): unknown {
  return {
    ip: m.ip,
    user: m.user,
    port: m.port ?? DEFAULTS.SSH.PORT,
    datastore: m.datastore ?? null,
  };
}

/** True when `family` is placed on `machine`, directly or through a local datastore anchored there. */
function placedOn(
  family: RepoFamily,
  machine: string,
  datastores: Resources['datastores']
): boolean {
  const placement = family.placement;
  if (!placement) return false;
  if ('machine' in placement) return placement.machine === machine;
  const backend = datastores?.[placement.datastore]?.backend;
  return backend?.kind === 'local' && backend.machine === machine;
}

class Planner {
  readonly rows: ImportRow[] = [];
  readonly res: Resources;
  /** The target's state.repos with the imported networkIds applied. */
  readonly stateRepos: StateRepos;
  private readonly state: RdcConfig['state'];
  private importedMax = 0;

  constructor(
    private readonly src: Resources,
    target: Resources,
    private readonly srcState: StateRepos,
    targetState: NonNullable<RdcConfig['state']> | undefined,
    private readonly opts: ImportOptions
  ) {
    this.state = targetState;
    this.stateRepos = Object.fromEntries(
      Object.entries(targetState?.repos ?? {}).map(([f, tags]) => [f, { ...tags }])
    );
    // Shallow copies of every record the plan may write; entries themselves are replaced, never mutated.
    this.res = {
      ...target,
      machines: { ...target.machines },
      datastores: { ...target.datastores },
      repositories: { ...target.repositories },
      backupStrategies: { ...target.backupStrategies },
    };
  }

  /** Record one verdict; returns false for a refusal so a caller can chain on it. */
  row(kind: ImportKind, name: string, status: ImportStatus, reason?: RefusalReason): boolean {
    this.rows.push(reason ? { kind, name, status, reason } : { kind, name, status });
    return status !== 'refused';
  }

  /** The `family:tag` that holds network ID `id` in the working state, other than `self`. */
  private holder(id: number, self: string): string | undefined {
    for (const [family, tags] of Object.entries(this.stateRepos)) {
      for (const [tag, runtime] of Object.entries(tags)) {
        const ref = `${family}:${tag}`;
        if (runtime.networkId === id && ref !== self) return ref;
      }
    }
    return undefined;
  }

  /**
   * Carry the source tag's networkId. Absent in the source: nothing to do. Equal in the target: a
   * no-op. Missing in the target: copied. Another value, or an id held by another repository:
   * refused, never reused or renumbered.
   */
  networkId(family: string, tag: string): void {
    const id = this.srcState[family]?.[tag]?.networkId;
    if (id === undefined) return;
    const ref = `${family}:${tag}`;
    const have = this.stateRepos[family]?.[tag]?.networkId;
    if (have === id) {
      this.row('networkId', ref, 'equal');
      return;
    }
    if (have !== undefined) {
      this.row('networkId', ref, 'refused', 'network-id-differs');
      return;
    }
    const other = this.holder(id, ref);
    if (other) {
      this.collisions.push(
        `networkId ${ref}: network-id-collision (${ref} and ${other} both hold ${id})`
      );
      this.row('networkId', ref, 'refused', 'network-id-collision');
      return;
    }
    this.stateRepos[family] = {
      ...this.stateRepos[family],
      [tag]: { ...this.stateRepos[family]?.[tag], networkId: id },
    };
    this.importedMax = Math.max(this.importedMax, id);
    this.row('networkId', ref, 'added');
  }

  /** The target's state with the imported networkIds and the counter moved past them. */
  stateOut(): RdcConfig['state'] {
    const next = this.state?.networkIds?.next;
    const needed = this.importedMax + NETWORK_ID_INCREMENT;
    // An absent counter is derived from the used ids at allocation time, which now include these.
    const networkIds =
      next !== undefined && this.importedMax > 0 && next < needed
        ? { ...this.state?.networkIds, next: needed }
        : this.state?.networkIds;
    return {
      ...this.state,
      repos: this.stateRepos,
      ...(networkIds ? { networkIds } : {}),
    };
  }

  /** Detail lines naming both repositories of every network ID collision. */
  readonly collisions: string[] = [];

  /** Copy a strategy when absent; equal is a no-op; differing is refused unless the source replaces it. */
  strategy(name: string): boolean {
    const source = this.src.backupStrategies?.[name];
    if (!source) return this.row('strategy', name, 'refused', 'strategy-missing');
    const existing = this.res.backupStrategies![name];
    if (!existing) {
      this.res.backupStrategies![name] = structuredClone(source);
      return this.row('strategy', name, 'added');
    }
    if (isDeepStrictEqual(existing, source)) return this.row('strategy', name, 'equal');
    if (this.opts.strategyFromSource) {
      this.res.backupStrategies![name] = structuredClone(source);
      return this.row('strategy', name, 'replaced');
    }
    return this.row('strategy', name, 'refused', 'strategy-differs');
  }

  machine(name: string, source: MachineEntry, boundOk: string[]): void {
    const existing = this.res.machines![name];
    if (!existing) {
      this.addMachine(name, source, boundOk);
      return;
    }
    if (!isDeepStrictEqual(machineIdentity(existing), machineIdentity(source))) {
      this.row('machine', name, 'refused', 'machine-differs');
      return;
    }
    // Every other field of an existing machine (maintenance window, infra) belongs to the target.
    this.row('machine', name, 'equal');
    const bound = existing.backupStrategies ?? [];
    const missing = boundOk.filter((s) => !bound.includes(s));
    for (const s of boundOk) {
      this.row('binding', `${name}/${s}`, bound.includes(s) ? 'equal' : 'added');
    }
    if (missing.length > 0) {
      this.res.machines![name] = { ...existing, backupStrategies: [...bound, ...missing] };
    }
  }

  private addMachine(name: string, source: MachineEntry, boundOk: string[]): void {
    const copy = structuredClone(source);
    // Only the strategies that are themselves importable are bound.
    if (boundOk.length > 0) copy.backupStrategies = boundOk;
    else delete copy.backupStrategies;
    this.res.machines![name] = copy;
    this.row('machine', name, 'added');
    for (const s of boundOk) this.row('binding', `${name}/${s}`, 'added');
  }

  datastore(ref: string): boolean {
    const source = this.src.datastores?.[ref] as DatastoreEntry;
    const existing = this.res.datastores![ref];
    if (!existing) {
      this.res.datastores![ref] = structuredClone(source);
      return this.row('datastore', ref, 'added');
    }
    if (isDeepStrictEqual(existing, source)) return this.row('datastore', ref, 'equal');
    return this.row('datastore', ref, 'refused', 'datastore-differs');
  }

  family(name: string, source: RepoFamily): void {
    const placement = source.placement;
    if (placement && 'datastore' in placement && !this.datastore(placement.datastore)) {
      this.row('repository', name, 'refused', 'placement-differs');
      return;
    }
    const existing = this.res.repositories![name];
    if (!existing) {
      this.res.repositories![name] = structuredClone(source);
      this.row('repository', name, 'added');
      for (const tag of Object.keys(source.tags)) {
        this.row('tag', `${name}:${tag}`, 'added');
        this.networkId(name, tag);
      }
      return;
    }
    if (!isDeepStrictEqual(existing.placement, source.placement)) {
      this.row('repository', name, 'refused', 'placement-differs');
      return;
    }
    if (existing.grand !== source.grand) {
      this.row('repository', name, 'refused', 'grand-differs');
      return;
    }
    // The family row covers placement and grand only; each tag carries its own row.
    this.row('repository', name, 'equal');
    this.mergeTags(name, existing, source);
  }

  /** Add the absent tags of an existing family; a present tag must match the source exactly. */
  private mergeTags(name: string, existing: RepoFamily, source: RepoFamily): void {
    const tags = { ...existing.tags };
    let added = false;
    for (const [tag, record] of Object.entries(source.tags)) {
      const ref = `${name}:${tag}`;
      const have = existing.tags[tag];
      if (!have) {
        tags[tag] = structuredClone(record);
        added = true;
        this.row('tag', ref, 'added');
        this.networkId(name, tag);
      } else if (have.repositoryGuid !== record.repositoryGuid) {
        this.row('tag', ref, 'refused', 'guid-differs');
      } else if (isDeepStrictEqual(have, record)) {
        this.row('tag', ref, 'equal');
        this.networkId(name, tag);
      } else {
        this.row('tag', ref, 'refused', 'tag-differs');
      }
    }
    // A refusal anywhere discards the whole plan, so the added tags apply only to a clean run.
    if (added) this.res.repositories![name] = { ...existing, tags };
  }
}

/**
 * Plan the import of `machine` from `source` into `target`. Pure: `target` is not mutated. Throws a
 * ValidationError when the source config has no such machine.
 */
function planMachineImport(
  source: RdcConfig,
  target: RdcConfig,
  machine: string,
  opts: ImportOptions = {}
): ImportPlan {
  const src = source.resources ?? {};
  const sourceMachine = src.machines?.[machine];
  if (!sourceMachine) {
    throw new ValidationError(t('commands.config.importMachine.machineMissing', { machine }));
  }
  const planner = new Planner(
    src,
    target.resources ?? {},
    source.state?.repos ?? {},
    target.state,
    opts
  );

  const boundOk = (sourceMachine.backupStrategies ?? []).filter((s) => planner.strategy(s));
  planner.machine(machine, sourceMachine, boundOk);

  const families = Object.entries(src.repositories ?? {}).filter(([, f]) =>
    placedOn(f, machine, src.datastores)
  );
  for (const [name, family] of families) planner.family(name, family);

  const changes = planner.rows.filter(
    (r) => r.status === 'added' || r.status === 'replaced'
  ).length;
  const refusals = planner.rows.filter((r) => r.status === 'refused').length;
  const config =
    changes > 0 && refusals === 0
      ? { ...target, resources: planner.res, state: planner.stateOut() }
      : target;
  return { rows: planner.rows, config, changes, refusals, collisions: planner.collisions };
}

interface ImportMachineCliOptions {
  from: string;
  dryRun?: boolean;
  strategyFromSource?: boolean;
}

function refusalError(plan: ImportPlan): Error {
  return stateMismatch(t('commands.config.importMachine.refused', { count: plan.refusals }), {
    details: plan.rows
      .filter((r) => r.status === 'refused')
      .map(
        (r) =>
          plan.collisions.find((c) => c.startsWith(`${r.kind} ${r.name}: ${r.reason}`)) ??
          `${r.kind} ${r.name}: ${r.reason}`
      ),
  });
}

function render(
  plan: ImportPlan,
  meta: { machine: string; from: string; to: string; dryRun: boolean; written: boolean },
  format: OutputFormat
): void {
  if (format !== 'table') {
    outputService.print(
      {
        ...meta,
        changes: plan.changes,
        refusals: plan.refusals,
        rows: plan.rows,
      },
      format
    );
    return;
  }
  outputService.print(
    plan.rows.map((r) => ({
      kind: r.kind,
      name: r.name,
      status: r.status,
      reason: r.reason ?? '',
    })),
    format
  );
  const params = { machine: meta.machine, from: meta.from, count: plan.changes };
  outputService.info(
    meta.dryRun
      ? t('commands.config.importMachine.summaryDryRun', params)
      : t('commands.config.importMachine.summary', params)
  );
}

async function runImportMachine(
  machine: string,
  options: ImportMachineCliOptions,
  format: OutputFormat
): Promise<void> {
  const to = configService.getEffectiveConfigName();
  const from = options.from;
  if (from === to) {
    throw new ValidationError(t('commands.config.importMachine.sameConfig', { name: from }));
  }
  if (!(await configFileStorage.exists(from))) {
    throw new ValidationError(t('commands.config.importMachine.sourceMissing', { name: from }));
  }
  const source = await configFileStorage.loadDecrypted(from);
  const target = await configService.getDecryptedConfig();
  if (!target) {
    throw new ValidationError(t('commands.config.importMachine.targetMissing', { name: to }));
  }
  const opts: ImportOptions = { strategyFromSource: options.strategyFromSource };
  let plan = planMachineImport(source, target, machine, opts);
  const meta = { machine, from, to, dryRun: Boolean(options.dryRun), written: false };

  if (options.dryRun || plan.refusals > 0 || plan.changes === 0) {
    render(plan, meta, format);
    // A dry run exits like the real run would, so a script can gate on the preview.
    if (plan.refusals > 0) throw refusalError(plan);
    return;
  }

  // Planned again inside the edit: a remote push replays it on the fresh server copy.
  await updateSyncedConfig(to, (cfg) => {
    plan = planMachineImport(source, cfg, machine, opts);
    if (plan.refusals > 0) throw refusalError(plan);
    return plan.config;
  });
  render(plan, { ...meta, written: plan.changes > 0 }, format);
}

/** Register `config import-machine` under the `config` command. */
export function registerImportMachineCommand(config: Command, program: Command): void {
  config
    .command('import-machine')
    .argument('<machine>', t('commands.config.importMachine.argMachine'))
    .summary(t('commands.config.importMachine.descriptionShort'))
    .description(t('commands.config.importMachine.description'))
    .requiredOption('--from <config>', t('commands.config.importMachine.optionFrom'))
    .option('--dry-run', t('commands.config.importMachine.optionDryRun'))
    .option('--strategy-from-source', t('commands.config.importMachine.optionStrategyFromSource'))
    .action(async (machine: string, options: ImportMachineCliOptions) => {
      try {
        await runImportMachine(machine, options, program.opts().output as OutputFormat);
      } catch (error) {
        handleError(error);
      }
    });
}
