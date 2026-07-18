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

import type { Placement, RdcConfig, RdcState, RepoFamily } from '@rediacc/shared/config-schema';
import type { ListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
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

/** One declared placement that `--accept-observed` would rewrite to match reality. */
interface AcceptedPlacement {
  repository: string;
  from: string;
  to: string;
}

export interface ReconcileReport {
  reconciledAt: string;
  machinesSeen: string[];
  machinesUnreachable: { machine: string; error: string }[];
  placementsFilled: { repository: string; placement: Placement }[];
  /**
   * Declared placements rewritten to match observation under `--accept-observed`
   * (or, under `--dry-run`, the ones that WOULD be). Only the unambiguous
   * machine-arm drift class (spec/04 §4.3); duplicates never appear here.
   */
  placementsAccepted: AcceptedPlacement[];
  conflicts: ReconcileConflict[];
}

export interface ReconcileOptions {
  /**
   * Overwrite a declared placement with the observed one — but ONLY for the
   * unambiguous machine-arm drift class (grand GUID on exactly one machine that
   * differs from the declaration). Duplicates stay conflicts even with the flag
   * (spec/04 §4.3: ambiguity errors, never guesses).
   */
  acceptObserved?: boolean;
}

export interface ReconcileDeps {
  loadConfig: () => Promise<RdcConfig | null>;
  fetchStatus: (machineName: string) => Promise<ListResult>;
  /** State-half writer (no version bump, excluded from remote push). */
  writeState: (updater: (config: RdcConfig) => RdcConfig) => Promise<void>;
  /**
   * Spec-half writer (version-bumping, remote-push-dirty). Distinct from
   * `writeState` on purpose: `--accept-observed` rewrites a DECLARATION, which
   * is a version-bumping change, so the two write paths stay two visible calls.
   */
  writeResources: (updater: (config: RdcConfig) => RdcConfig) => Promise<void>;
}

type Classified = {
  fill?: { repository: string; placement: Placement };
  conflict?: ReconcileConflict;
  accept?: AcceptedPlacement;
};

/**
 * Classify a DECLARED machine placement against observation (spec §4.3). Never
 * an auto-edit: drift is a conflict, and the unambiguous single-machine drift
 * additionally carries the `accept` --accept-observed would apply (it always
 * rides alongside the conflict, so a run without the flag still reports it).
 */
function classifyDeclaredMachine(
  name: string,
  declared: string,
  machines: string[],
  grandGuid: string
): Classified {
  if (!machines.includes(declared)) {
    const conflict: ReconcileConflict = {
      kind: 'placement',
      repository: name,
      message: `repository "${name}" is placed on "${declared}" but its image was observed on ${machines.join(', ')}. Use 'rdc repo migrate' to move it, or accept the observed placement: 'rdc config reconcile --accept-observed'.`,
    };
    // Unambiguous drift: exactly one observed machine, different from the
    // declaration. This is the only class --accept-observed rewrites.
    if (machines.length === 1) {
      return { conflict, accept: { repository: name, from: declared, to: machines[0] } };
    }
    return { conflict };
  }
  // R4: the declared machine holds a copy, but the grand GUID also lives on
  // OTHER machines — stray copies (interrupted migrate, `--keep-source`, or a
  // pushed backup left mounted). spec/04 §4.3 lists "same GUID on two machines"
  // as a conflict class; this is its declared-plus-strays case.
  if (machines.length > 1) {
    const strays = machines.filter((m) => m !== declared);
    return {
      conflict: {
        kind: 'duplicate',
        repository: name,
        message: `repository "${name}" (guid ${grandGuid.slice(0, 8)}) is placed on "${declared}" but its image is ALSO on ${strays.join(', ')}. If that is a leftover from an interrupted migrate or 'rdc repo migrate --keep-source', remove it there ('rdc machine prune <machine>'); a pushed backup is fine unbooted but should be a storage artifact, not a mounted repo.`,
      },
    };
  }
  return {};
}

/**
 * Placement fill / conflict / would-accept for one family, from what was
 * observed.
 */
function classifyFamilyPlacement(
  name: string,
  family: RepoFamily,
  observed: Map<string, ObservedRepo[]>
): Classified {
  const grandGuid = family.tags[family.grand].repositoryGuid;
  const machines = [...new Set((observed.get(grandGuid) ?? []).map((s) => s.machine))];

  if (family.placement) {
    if ('machine' in family.placement && machines.length > 0) {
      return classifyDeclaredMachine(name, family.placement.machine, machines, grandGuid);
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
export async function reconcileState(
  deps: ReconcileDeps,
  options: ReconcileOptions = {}
): Promise<ReconcileReport> {
  const config = await deps.loadConfig();
  if (!config) throw new Error('No active config to reconcile');

  const { observed, seen, unreachable } = await collectObserved(config, deps);
  const reconciledAt = new Date().toISOString();

  const placementsFilled: { repository: string; placement: Placement }[] = [];
  const placementsAccepted: AcceptedPlacement[] = [];
  const conflicts: ReconcileConflict[] = [];
  const pendingPlacement = new Map<string, Placement>();
  // Declared-placement rewrites accepted under --accept-observed (spec-half).
  const pendingAccept = new Map<string, Placement>();
  for (const [name, family] of Object.entries(config.resources?.repositories ?? {})) {
    const { fill, conflict, accept } = classifyFamilyPlacement(name, family, observed);
    if (fill) {
      pendingPlacement.set(fill.repository, fill.placement);
      placementsFilled.push(fill);
    }
    // The unambiguous drift carries both `accept` and `conflict`. With the flag,
    // resolve it (record the acceptance, suppress the conflict); without, report
    // the conflict as usual. Duplicates have no `accept`, so they stay conflicts
    // even under the flag.
    if (accept && options.acceptObserved) {
      pendingAccept.set(accept.repository, { machine: accept.to });
      placementsAccepted.push(accept);
    } else if (conflict) {
      conflicts.push(conflict);
    }
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

  // Spec-half rewrite (--accept-observed) — a SEPARATE, version-bumping write,
  // kept visibly distinct from the state write above (spec/04 §4.3). Under
  // --dry-run the command wires this to a no-op, so placementsAccepted still
  // reports what WOULD change while nothing is written.
  if (pendingAccept.size > 0) {
    await deps.writeResources((cfg) => {
      const repositories = { ...(cfg.resources?.repositories ?? {}) };
      for (const [name, placement] of pendingAccept) {
        // pendingAccept keys are family names classified this run, so present.
        repositories[name] = { ...repositories[name], placement };
      }
      return { ...cfg, resources: { ...(cfg.resources ?? {}), repositories } };
    });
  }

  return {
    reconciledAt,
    machinesSeen: seen,
    machinesUnreachable: unreachable,
    placementsFilled,
    placementsAccepted,
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
    // Version-bumping write for the --accept-observed declaration rewrite.
    writeResources: async (updater) => {
      await configFileStorage.update(name, updater);
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
