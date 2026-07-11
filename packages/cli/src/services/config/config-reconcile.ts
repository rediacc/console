/**
 * `config reconcile` service layer (spec 04 §4).
 *
 * Rebuilds the STATE half of the config from what the fleet actually reports
 * (`renet list all --json` per machine), and — for configs migrated from v2 —
 * fills MISSING repository placement by matching each repository GUID against
 * the machines' inventories. It NEVER overwrites a declared placement: spec is
 * declaration, state is observation. A GUID seen on a machine that conflicts
 * with a declared placement is reported, not auto-fixed (spec §4.3).
 *
 * The reconcile logic is dependency-injected (fetch status, load config, write
 * state) so it is unit-testable without SSH. The default `reconcile()` wires the
 * real machine-status fetch and the no-version-bump `updateState` writer.
 *
 * The runtime twin of this verb is `verifyRoutingHint` (§1.3 property 3): every
 * derived-machine op that resolves through `state.datastores[*].attachedTo`
 * must verify the hint against reality before acting, failing closed with a
 * message that names both sides and the fix.
 */

import type { ListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import type { Placement, RdcConfig, RdcState, RepoFamily } from '../../schema/schemas.js';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { configService } from './config-resources.js';

/** One repository as observed on a machine, keyed by its on-disk GUID. */
interface ObservedRepo {
  guid: string;
  machine: string;
  repoName?: string;
  mounted: boolean;
  mountPath?: string;
}

/**
 * @public BLOCKER: element type of ReconcileReport.conflicts — the P4 `config
 * reconcile` command renders these per-repo conflicts; exported so that command
 * can type its conflict formatter without indexing ReconcileReport internals.
 */
export interface ReconcileConflict {
  kind: 'placement' | 'duplicate';
  repository: string;
  message: string;
}

export interface ReconcileReport {
  reconciledAt: string;
  machinesSeen: string[];
  machinesUnreachable: { machine: string; error: string }[];
  placementsFilled: { repository: string; placement: Placement }[];
  conflicts: ReconcileConflict[];
}

export interface ReconcileDeps {
  loadConfig: () => Promise<RdcConfig | null>;
  fetchStatus: (machineName: string) => Promise<ListResult>;
  writeState: (updater: (config: RdcConfig) => RdcConfig) => Promise<void>;
}

/** Placement fill or conflict for one repository family, from what was observed. */
function classifyFamilyPlacement(
  name: string,
  family: RepoFamily,
  observed: Map<string, ObservedRepo[]>
): { fill?: { repository: string; placement: Placement }; conflict?: ReconcileConflict } {
  const grandGuid = family.tags[family.grand].repositoryGuid;
  const machines = [...new Set((observed.get(grandGuid) ?? []).map((s) => s.machine))];

  if (family.placement) {
    // A declared machine placement that disagrees with observation is a
    // conflict, never an auto-edit (spec §4.3).
    if (
      'machine' in family.placement &&
      machines.length > 0 &&
      !machines.includes(family.placement.machine)
    ) {
      return {
        conflict: {
          kind: 'placement',
          repository: name,
          message: `repository "${name}" is placed on "${family.placement.machine}" but its image was observed on ${machines.join(', ')}. Use 'rdc repo migrate' to move it, or reconcile with --accept-observed.`,
        },
      };
    }
    return {};
  }

  if (machines.length === 1) {
    return { fill: { repository: name, placement: { machine: machines[0] } } };
  }
  if (machines.length > 1) {
    return {
      conflict: {
        kind: 'duplicate',
        repository: name,
        message: `repository "${name}" (guid ${grandGuid.slice(0, 8)}) observed on multiple machines: ${machines.join(', ')}. Resolve before reconcile can fill placement.`,
      },
    };
  }
  return {};
}

/** Collect the repositories each machine reports, keyed by GUID. */
async function collectObserved(
  config: RdcConfig,
  deps: ReconcileDeps
): Promise<{
  observed: Map<string, ObservedRepo[]>;
  seen: string[];
  unreachable: { machine: string; error: string }[];
}> {
  const observed = new Map<string, ObservedRepo[]>();
  const seen: string[] = [];
  const unreachable: { machine: string; error: string }[] = [];

  for (const machine of Object.keys(config.resources?.machines ?? {})) {
    let result: ListResult;
    try {
      result = await deps.fetchStatus(machine);
    } catch (err) {
      unreachable.push({ machine, error: err instanceof Error ? err.message : String(err) });
      continue;
    }
    seen.push(machine);
    for (const repo of result.repositories) {
      const entry: ObservedRepo = {
        guid: repo.name,
        machine,
        repoName: repo.repo_name,
        mounted: repo.mounted,
        mountPath: repo.mount_path,
      };
      const list = observed.get(repo.name) ?? [];
      list.push(entry);
      observed.set(repo.name, list);
    }
  }
  return { observed, seen, unreachable };
}

/**
 * Reconcile the state half. Returns a report; writes the rebuilt state via the
 * injected `writeState` (which must not bump the version counter).
 */
export async function reconcileState(deps: ReconcileDeps): Promise<ReconcileReport> {
  const config = await deps.loadConfig();
  if (!config) throw new Error('No active config to reconcile');

  const { observed, seen, unreachable } = await collectObserved(config, deps);
  const reconciledAt = new Date().toISOString();

  const placementsFilled: { repository: string; placement: Placement }[] = [];
  const conflicts: ReconcileConflict[] = [];
  const pendingPlacement = new Map<string, Placement>();
  for (const [name, family] of Object.entries(config.resources?.repositories ?? {})) {
    const { fill, conflict } = classifyFamilyPlacement(name, family, observed);
    if (fill) {
      pendingPlacement.set(fill.repository, fill.placement);
      placementsFilled.push(fill);
    }
    if (conflict) conflicts.push(conflict);
  }

  // Rebuild state.machines observations. state.repos.networkId reconciliation
  // requires the renet `network_id` field on RepositoryInfo (spec §1.3, §6.7,
  // a P1 renet addition); until it lands, networkId is left as-is.
  await deps.writeState((cfg) => {
    const state: RdcState = { ...(cfg.state ?? {}) };
    const machines: NonNullable<RdcState['machines']> = { ...(state.machines ?? {}) };
    for (const machine of seen) {
      machines[machine] = { ...(machines[machine] ?? {}), lastSeenAt: reconciledAt };
    }
    state.machines = machines;
    state.reconciledAt = reconciledAt;

    const repositories = { ...(cfg.resources?.repositories ?? {}) };
    for (const [name, placement] of pendingPlacement) {
      // pendingPlacement keys are family names observed this run, so the family
      // is present; only fill when it still declares no placement.
      const family = repositories[name];
      if (!family.placement) repositories[name] = { ...family, placement };
    }

    return {
      ...cfg,
      resources: { ...(cfg.resources ?? {}), repositories },
      state,
    };
  });

  return {
    reconciledAt,
    machinesSeen: seen,
    machinesUnreachable: unreachable,
    placementsFilled,
    conflicts,
  };
}

/**
 * Default wiring: reconcile the active (or named) config against the live fleet.
 * State is written via `updateState`, so reconcile never bumps the version
 * counter or dirties the remote-push document.
 *
 * @public BLOCKER: the `rdc config reconcile` command that calls this default
 * wiring ships in the P4 CLI reshape (config-reconcile.test.ts already asserts
 * the error copy pointing users at it); reconcileState is the DI core, this is
 * the production entry point that command binds to.
 */
export async function reconcile(configName?: string): Promise<ReconcileReport> {
  const { fetchMachineStatus } = await import('../machine/machine-status.js');
  const name = configName ?? configService.getEffectiveConfigName();
  return reconcileState({
    loadConfig: () =>
      configName ? configFileStorage.load(configName) : configService.getCurrent(),
    fetchStatus: (machine) => fetchMachineStatus(machine),
    writeState: async (updater) => {
      await configFileStorage.updateState(name, updater);
    },
  });
}

export interface RoutingVerification {
  ok: boolean;
  error?: string;
}

/**
 * Runtime twin of reconcile (spec §1.3 property 3). A derived-machine op that
 * resolved a datastore through `state.datastores[*].attachedTo` must call this
 * with the machine renet actually reports the datastore mounted on. A mismatch
 * is a hard error naming both sides plus the fix — never a retry elsewhere.
 */
export function verifyRoutingHint(params: {
  datastore: string;
  hintedMachine: string;
  observedMountedOn: string | null;
}): RoutingVerification {
  if (params.observedMountedOn === params.hintedMachine) return { ok: true };
  return {
    ok: false,
    error:
      `state says ${params.datastore} is attached to ${params.hintedMachine}, but ` +
      `${params.hintedMachine} does not have it mounted${
        params.observedMountedOn ? ` (it is on ${params.observedMountedOn})` : ''
      }. Run 'rdc config reconcile' to refresh, or 'rdc datastore attach ${params.datastore} --to <m>'.`,
  };
}
