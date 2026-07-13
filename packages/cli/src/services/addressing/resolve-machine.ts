/**
 * Derived-machine resolution (spec/03 §2.3, R2-F2) — the normative six-step
 * algorithm. `-m/--machine` disappears from repo verbs; every repo verb derives
 * its execution machine from the ref plus config placement, verifying the derived
 * answer against the machine before it acts.
 *
 * This is a PURE function over a `PlacementView` (the config slices it needs) and
 * an injected `verifyMount` callback (step 5's remote round-trip). Keeping the
 * remote check injected is what lets the whole algorithm be unit-tested with
 * fixtures and no machine — the command layer wires the real config service and a
 * real renet mount check; a read-only verb passes `readOnly: true` to skip step 5
 * (spec §2.3 tail).
 *
 * Steps are ordered; the first failure stops with the exit code the spec names:
 *   1. parse the ref                      → exit 2 on a grammar violation
 *   2. look up the family + tag           → exit 5, candidates listed
 *   3. read placement (the tagged union)  → exit 5 (dangling datastore) / exit 12
 *   4. @place redundant-match vs conflict → exit 12 (§3.2 conflict text)
 *   5. verify before executing            → exit 12 (reconcile teaching error)
 *   6. execute on the verified machine
 */

import type { MachineConfig, RdcConfig, RepoFamily } from '@rediacc/shared/config-schema';
import { notFound, stateMismatch } from '../../utils/cli-exit-error.js';
import { placeConflictError } from './place-rules.js';
import { parseRef } from './ref-parser.js';

type DatastoreConfig = NonNullable<NonNullable<RdcConfig['resources']>['datastores']>[string];
type StateDatastore = NonNullable<NonNullable<RdcConfig['state']>['datastores']>[string];

/** The config slices derived-machine resolution reads. */
export interface PlacementView {
  /** `resources.repositories` — families of structural tags. */
  families: Record<string, RepoFamily>;
  /** `resources.datastores` — the named-datastore registry. */
  datastores: Record<string, DatastoreConfig>;
  /** `state.datastores` — attach status (the routing hint step 5 verifies). */
  stateDatastores: Record<string, StateDatastore>;
  /** `resources.machines` — read only for cluster-membership @place acceptance. */
  machines: Record<string, MachineConfig>;
}

export interface ResolveMachineOptions {
  /**
   * Read-only verbs (status/list/log/diff/cat/logs/secret get/list) skip step
   * 5's remote round-trip: the verb is about to talk to the same machine anyway,
   * so the operation's own failure is the verification (spec §2.3 tail).
   */
  readOnly?: boolean;
  /**
   * Step 5's cheap remote mount check. Resolves true when `machine` actually
   * mounts `datastore` (undefined = the machine's implicit default datastore).
   * Omitted => step 5 is skipped, which is what makes pure resolution testable.
   */
  verifyMount?: (machine: string, datastore: string | undefined) => Promise<boolean>;
}

export interface ResolvedMachine {
  /** The verified execution machine. */
  machine: string;
  /** The named datastore, present only for the `{datastore}` placement arm. */
  datastore?: string;
  /** The datastore's cluster backref, when it is a kubernetes-world datastore. */
  cluster?: string;
  /** The resolved stored tag key (the family's grand tag for a bare/base ref). */
  tag: string;
  /** The `@place` the ref carried, once accepted as a redundant confirmation. */
  place?: string;
}

/** Which stored tag key a parsed tag resolves to (bare/base => the grand tag). */
function resolveStoredTag(name: string, family: RepoFamily, parsedTag: string | undefined): string {
  if (parsedTag === undefined) return family.grand;
  if (!(parsedTag in family.tags)) {
    const known = Object.keys(family.tags).sort();
    throw notFound(`repository "${name}" has no tag "${parsedTag}".`, {
      details:
        known.length > 0
          ? [`known tags for "${name}": ${known.join(', ')}`]
          : [`"${name}" has no tags recorded.`],
    });
  }
  return parsedTag;
}

/**
 * Step 2: resolve the family and its stored tag, WITHOUT touching placement or a
 * machine. Config-local verbs (secret get/list/set/unset, branch) that never
 * dispatch to a machine resolve through here so they keep working on a repo whose
 * datastore is currently detached (or whose placement has not been reconciled yet).
 */
function resolveFamilyTag(
  name: string,
  parsedTag: string | undefined,
  view: PlacementView
): { family: RepoFamily; tag: string } {
  // `in` guards, not `?.` — the PlacementView maps are typed non-undefined at
  // the value (noUncheckedIndexedAccess is off), so a membership test is the
  // codebase's lint-clean way to detect a missing key (as resolveStoredTag does).
  if (!(name in view.families)) {
    const known = Object.keys(view.families).sort();
    throw notFound(`repository "${name}" is not in this config.`, {
      details: known.length > 0 ? [`known repositories: ${known.join(', ')}`] : undefined,
    });
  }
  const family = view.families[name];
  const tag = resolveStoredTag(name, family, parsedTag);
  return { family, tag };
}

/**
 * Steps 1-2 as a standalone: parse the ref and resolve its family + stored tag,
 * with NO placement/machine derivation. For config-local verbs (spec §2.3 tail:
 * "purely config-local reads never verify"; the same applies to config-local
 * writes like `secret set` and `branch`). Grammar violation => exit 2, unknown
 * family/tag => exit 5.
 */
export function resolveRefLocal(
  ref: string,
  view: PlacementView
): { name: string; tag: string; place?: string } {
  const { name, tag: parsedTag, place } = parseRef(ref);
  const { tag } = resolveFamilyTag(name, parsedTag, view);
  return { name, tag, ...(place !== undefined && { place }) };
}

/** Steps 2-3: resolve the family, tag, and candidate machine from placement. */
function resolvePlacement(
  name: string,
  parsedTag: string | undefined,
  view: PlacementView
): { candidate: string; datastore?: string; cluster?: string; tag: string } {
  const { family, tag } = resolveFamilyTag(name, parsedTag, view);

  const placement = family.placement;
  if (!placement) {
    throw stateMismatch(
      `repository "${name}" has no recorded placement. ` +
        `Run "rdc config reconcile" to derive it from the machines that hold its data.`
    );
  }

  if ('machine' in placement) {
    return { candidate: placement.machine, tag };
  }

  // {datastore} arm: resolve the named datastore, then its live attach machine.
  const datastore = placement.datastore;
  if (!(datastore in view.datastores)) {
    throw notFound(
      `repository "${name}" references datastore "${datastore}", ` +
        `which is not in the datastore registry.`
    );
  }
  const ds = view.datastores[datastore];
  const attachedTo =
    datastore in view.stateDatastores ? view.stateDatastores[datastore].attachedTo : undefined;
  if (!attachedTo) {
    throw stateMismatch(
      `datastore ${datastore} is not attached to any machine. ` +
        `Attach it: "rdc datastore attach ${datastore} --to <machine>" ` +
        `(or "rdc config reconcile" if it is attached but the config does not know).`
    );
  }
  return { candidate: attachedTo, datastore, cluster: ds.cluster, tag };
}

/** The cluster a machine belongs to, preferring its own membership record. */
function clusterOf(
  machine: string,
  view: PlacementView,
  datastoreCluster?: string
): string | undefined {
  if (!(machine in view.machines)) return datastoreCluster;
  return view.machines[machine].cluster?.cluster ?? datastoreCluster;
}

/** Step 4: a redundant @place is accepted; a contradictory one is exit 12 (§3.2). */
function assertPlaceMatches(
  name: string,
  place: string,
  candidate: string,
  cluster: string | undefined,
  view: PlacementView
): void {
  const machineCluster = clusterOf(candidate, view, cluster);
  if (place !== candidate && place !== machineCluster) {
    throw placeConflictError(name, candidate, place);
  }
}

/**
 * Step 5: verify the derived machine actually mounts the datastore before acting
 * (exit 12). A no-op for a read-only verb or when no verifier is injected — the
 * routing hint's own failure is the verification for those (spec §2.3 tail).
 */
async function verifyBeforeExecuting(
  name: string,
  candidate: string,
  datastore: string | undefined,
  options: ResolveMachineOptions
): Promise<void> {
  if (options.readOnly || !options.verifyMount) return;
  const mounted = await options.verifyMount(candidate, datastore);
  if (mounted) return;
  const subject = datastore ?? `${name}'s datastore`;
  throw stateMismatch(
    `config says ${subject} is attached to ${candidate}, ` +
      `but ${candidate} does not mount it. Run "rdc config reconcile", then retry.`
  );
}

/**
 * Resolve a repo ref to its verified execution machine (spec/03 §2.3). Throws a
 * CliExitError with the spec's exit code at the first failing step.
 */
export async function resolveMachine(
  ref: string,
  view: PlacementView,
  options: ResolveMachineOptions = {}
): Promise<ResolvedMachine> {
  // Step 1: parse (exit 2 on a grammar violation).
  const { name, tag: parsedTag, place } = parseRef(ref);

  // Steps 2-3: family, tag, and candidate machine from placement.
  const { candidate, datastore, cluster, tag } = resolvePlacement(name, parsedTag, view);

  // Step 4: @place is either redundant (accept) or contradictory (exit 12).
  if (place !== undefined) {
    assertPlaceMatches(name, place, candidate, cluster, view);
  }

  // Step 5: verify before executing — state is a routing hint, not truth.
  await verifyBeforeExecuting(name, candidate, datastore, options);

  // Step 6: the caller executes on the verified machine.
  return {
    machine: candidate,
    ...(datastore !== undefined && { datastore }),
    ...(cluster !== undefined && { cluster }),
    tag,
    ...(place !== undefined && { place }),
  };
}

/**
 * Build a `PlacementView` from a decrypted config. The command layer calls this
 * with `configService.getCurrent()`; the resolution algorithm above stays pure
 * and fixture-testable by never touching the config service itself.
 */
export function placementViewFromConfig(config: RdcConfig): PlacementView {
  return {
    families: config.resources?.repositories ?? {},
    datastores: config.resources?.datastores ?? {},
    stateDatastores: config.state?.datastores ?? {},
    machines: config.resources?.machines ?? {},
  };
}
