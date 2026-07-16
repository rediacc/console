/**
 * Repo-command target resolution (design D14): repo verbs are the single surface
 * for repo operations, targeting a machine (`-m`) or a cluster (`--cluster`).
 *
 * This is the thin per-command adapter over the wave-1 funnel
 * (resolveExecutionTarget): it enforces the mutually-exclusive one-of rule and
 * maps a cluster target to its control-node machine plus the `kubeCluster`
 * marker that local-executor threads into KUBECONFIG. Every cluster-capable
 * repo verb resolves through here and passes { machineName, kubeCluster } down
 * to executeRepoFunction / localExecutorService.execute.
 */
import { termConnectCollisionError } from '../services/addressing/place-rules.js';
import { parseRef } from '../services/addressing/ref-parser.js';
import {
  placementViewFromConfig,
  type ResolveMachineOptions,
  resolveMachine,
  resolveRefLocal,
} from '../services/addressing/resolve-machine.js';
import { resolveExecutionTarget } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { probeRepoPresent } from '../services/repo/repo-mount-check.js';
import { ambiguous, notFound } from './cli-exit-error.js';

/**
 * Inject the default step-5 verifier (spec/03 §2.3) unless the caller opted out.
 * A read-only verb (`readOnly: true`) skips step 5; a caller that already passed
 * its own `verifyMount` keeps it. Otherwise every MUTATING repo verb, through
 * this single funnel, gets the GUID-presence probe: the derived machine must
 * know the resolved tag's image or the verb refuses with exit 12 rather than
 * deploying to the wrong host. Probe-infrastructure failure fails OPEN (undefined
 * => true): the verb's own execution against the same machine surfaces the real
 * error moments later (repo-mount-check convention).
 */
function withDefaultVerifier(options: ResolveMachineOptions): ResolveMachineOptions {
  if (options.readOnly || options.verifyMount) return options;
  return {
    ...options,
    verifyMount: async ({ machine, datastore, repoGuid }) => {
      // #92: the presence probe serves the MACHINE arm only. probeRepoPresent
      // rides repository_list, which enumerates DOCKER repos under
      // <datastore>/repositories — a kube repo lives at <ds>/repos/<guid> on a
      // NAMED datastore and is structurally invisible to it, so probing the
      // datastore arm false-refused every mutating verb on a cluster repo with
      // exit 12 (found live by the B1 window, the arm's first-ever execution).
      // The datastore arm's routing is verified at dispatch instead: derivation
      // rides the attach hint, and renet errors loudly on an unmounted
      // datastore — a wrong host cannot silently succeed there. A datastore-
      // aware presence probe (a renet verb that can see <ds>/repos/) is the
      // recorded follow-up, spec/13.
      if (datastore !== undefined) return true;
      const present = await probeRepoPresent(repoGuid, machine);
      return present !== false;
    },
  };
}

export interface RepoTarget {
  /** Effective machine to SSH to — the cluster's control node for a cluster target. */
  machineName: string;
  /** Set when the target is a cluster; threaded into execute() to inject KUBECONFIG. */
  kubeCluster?: string;
}

/**
 * The resolved target of a positional repo `<ref>` (spec/03 §2.2/§2.3): the
 * derived execution machine plus the identifiers downstream code needs.
 *
 * This is the reshape-era funnel that replaces `resolveRepoTarget` as `-m`/
 * `--cluster` come off the repo verbs. Every repo verb registers `.argument('<ref>')`
 * and resolves through here, so the six-step derivation (parse -> placement tagged
 * union -> @place check -> verify -> execute) lives in exactly one place.
 */
export interface ResolvedRepoRef {
  /** The repo family name parsed from the ref (`shop` for `shop:test@m1`). */
  name: string;
  /**
   * The config/renet identifier: the ref minus any `@place` (`shop` for a bare
   * ref, `shop:test` for a tagged one). This is what `configService.getRepository`
   * and renet's `repository:` param expect (both already speak `name[:tag]`).
   */
  repoKey: string;
  /** The verified execution machine (spec §2.3 step 6). */
  machineName: string;
  /** kubeCluster marker (the datastore's cluster backref); set for k8s-world repos. */
  kubeCluster?: string;
  /** The named datastore backing the repo, for the `{datastore}` placement arm. */
  datastore?: string;
  /** The resolved stored tag key (the family's grand tag for a bare/base ref). */
  tag: string;
  /** The `@place` the ref carried, once accepted as a redundant confirmation. */
  place?: string;
}

/**
 * Resolve a positional repo `<ref>` to its verified execution machine and the
 * identifiers downstream code consumes (spec/03 §2.3). Read-only verbs pass
 * `readOnly: true` to skip step 5's remote round-trip; mutating verbs inject a
 * `verifyMount` for the routing-hint verification. Throws a `CliExitError` with
 * the spec's exit code at the first failing step.
 */
export async function resolveRepoRef(
  ref: string,
  options: ResolveMachineOptions = {}
): Promise<ResolvedRepoRef> {
  const parsed = parseRef(ref);
  const config = await configService.getCurrent();
  if (!config) {
    throw notFound(`repository "${parsed.name}" is not in this config.`);
  }
  const view = placementViewFromConfig(config);
  const resolved = await resolveMachine(ref, view, withDefaultVerifier(options));
  return {
    name: parsed.name,
    repoKey: parsed.tag ? `${parsed.name}:${parsed.tag}` : parsed.name,
    machineName: resolved.machine,
    ...(resolved.cluster !== undefined && { kubeCluster: resolved.cluster }),
    ...(resolved.datastore !== undefined && { datastore: resolved.datastore }),
    tag: resolved.tag,
    ...(resolved.place !== undefined && { place: resolved.place }),
  };
}

/**
 * The config-local resolution of a positional repo `<ref>`: the family/tag and
 * the derived identifiers, WITHOUT resolving (or requiring) a placement machine.
 * For verbs whose whole effect lands in the local config and that never dispatch
 * to a machine (`repo secret get|list|set|unset`, `repo branch`) — resolving a
 * machine there is both unnecessary and harmful, because it would refuse the verb
 * on a repo whose datastore is currently detached or whose placement has not been
 * reconciled yet.
 */
export interface ResolvedRepoRefLocal {
  /** The repo family name parsed from the ref (`shop` for `shop:test`). */
  name: string;
  /** The config/renet identifier: the ref minus any `@place` (`shop`, `shop:test`). */
  repoKey: string;
  /** The resolved stored tag key (the family's grand tag for a bare/base ref). */
  tag: string;
  /** The `@place` the ref carried (advisory for config-local verbs; not verified). */
  place?: string;
}

/**
 * Resolve a positional repo `<ref>` to its family/tag WITHOUT machine derivation
 * (spec/03 §2.3 tail). Throws a `CliExitError` (exit 2 grammar / exit 5 unknown
 * family or tag) but never exit 12 for a missing placement or detached datastore.
 */
export async function resolveRepoRefLocal(ref: string): Promise<ResolvedRepoRefLocal> {
  const parsed = parseRef(ref);
  const config = await configService.getCurrent();
  if (!config) {
    throw notFound(`repository "${parsed.name}" is not in this config.`);
  }
  const view = placementViewFromConfig(config);
  const { name, tag, place } = resolveRefLocal(ref, view);
  return {
    name,
    repoKey: parsed.tag ? `${parsed.name}:${parsed.tag}` : parsed.name,
    tag,
    ...(place !== undefined && { place }),
  };
}

/**
 * Resolve a repo command's `-m`/`--cluster` options to a concrete target.
 * Exactly one must be provided (resolveExecutionTarget throws otherwise).
 */
export async function resolveRepoTarget(options: {
  machine?: string;
  cluster?: string;
}): Promise<RepoTarget> {
  const target = await resolveExecutionTarget({
    machine: options.machine,
    cluster: options.cluster,
  });
  return { machineName: target.machineName, kubeCluster: target.cluster };
}

/**
 * The resolved target of a `term connect <target>` / `vscode connect <target>`
 * positional (spec/03 §5.8, §5.9). One token addresses two namespaces:
 *
 *   - a PLACE (a machine, or a cluster => its control node) -> a machine shell;
 *   - a repo ref `repo[:tag][@place]` -> a shell inside the repo, with its
 *     Docker environment (or, for a cluster-placed repo, KUBECONFIG plus a
 *     namespace pin) already set up.
 *
 * `kind` is the discriminant the two verbs branch on: the repo arm carries the
 * repo identifiers, the place arm carries none.
 */
export type ConnectTarget =
  | {
      kind: 'place';
      /** The machine to SSH to — a cluster's control node for a cluster place. */
      machineName: string;
      /** Set when the place named a cluster; threaded into KUBECONFIG injection. */
      kubeCluster?: string;
      /** Session-title label: the place as the user typed it. */
      label: string;
    }
  | {
      kind: 'repo';
      /** The repo's derived execution machine (spec §2.3). */
      machineName: string;
      /** Set when the repo is placed in a kubernetes cluster's datastore. */
      kubeCluster?: string;
      /** Session-title label: the cluster for a k8s repo, else the machine. */
      label: string;
      /** The config/renet identifier: `name` or `name:tag`. */
      repoKey: string;
      /** The repo family name (`shop` for `shop:test@m1`). */
      repoName: string;
      /** The resolved stored tag key. */
      tag: string;
    };

/**
 * Resolve a `term`/`vscode` connect `<target>` against the two namespaces it can
 * name, applying the §3.3 collision rule EXACTLY ONCE for both verbs:
 *
 *   1. An explicit repo ref (it carries `:tag` or `@place`) is a repo, full stop.
 *   2. A bare name that matches exactly one of {place, repo} takes that meaning.
 *   3. A bare name that matches BOTH is refused, exit 11, with the canonical
 *      teaching error (`termConnectCollisionError`).
 *   4. A bare name that matches NEITHER is exit 5, listing the candidates.
 *
 * Places are machines and clusters (one namespace, §2.1); `config` already
 * refuses a cluster whose name collides with a machine (§2.4), so a name is at
 * most one of the two. Repo refs resolve through `resolveRepoRef`, so the repo
 * arm inherits the whole §2.3 derivation (placement, `@place` verification, and
 * — for a mutating caller that injects one — the step-5 mount check).
 */
export async function resolveConnectTarget(
  target: string,
  options: ResolveMachineOptions = {}
): Promise<ConnectTarget> {
  const parsed = parseRef(target);

  // Step 1: `:tag` or `@place` makes the intent unambiguous — it is a repo ref,
  // even when the name also happens to be a place. `resolveRepoRef` raises the
  // exit-5 "no such repository" (or the exit-12 @place conflict) if it is not one.
  const isExplicitRepoRef = parsed.tag !== undefined || parsed.place !== undefined;
  if (!isExplicitRepoRef) {
    const config = await configService.getCurrent();
    const place = await resolveBarePlace(parsed.name, {
      machines: config?.resources?.machines ?? {},
      clusters: config?.resources?.clusters ?? {},
      families: config?.resources?.repositories ?? {},
    });
    // A defined result means the bare name is a place; `undefined` means it is a
    // repo (a collision or an unknown name has already thrown).
    if (place) return place;
  }

  // Step 2 (repo): the full §2.3 derivation, including the `@place` check.
  const resolved = await resolveRepoRef(target, options);
  return {
    kind: 'repo',
    machineName: resolved.machineName,
    ...(resolved.kubeCluster !== undefined && { kubeCluster: resolved.kubeCluster }),
    label: resolved.kubeCluster ?? resolved.machineName,
    repoKey: resolved.repoKey,
    repoName: resolved.name,
    tag: resolved.tag,
  };
}

/** The three config namespaces a bare connect target is matched against. */
interface ConnectNamespaces {
  machines: Record<string, unknown>;
  clusters: Record<string, unknown>;
  families: Record<string, unknown>;
}

/**
 * Steps 2-4 of the §3.3 rule for a BARE name: the place target when it names a
 * machine or a cluster, `undefined` when it names a repo, and a throw when it
 * names both (exit 11) or neither (exit 5).
 */
async function resolveBarePlace(
  name: string,
  ns: ConnectNamespaces
): Promise<ConnectTarget | undefined> {
  const isMachine = name in ns.machines;
  const isCluster = name in ns.clusters;
  const isRepo = name in ns.families;

  if (!isMachine && !isCluster) {
    if (isRepo) return undefined;
    // Step 4: neither namespace knows the name.
    throw notFound(`"${name}" is neither a repository nor a machine in this config.`, {
      details: candidateLines(ns),
    });
  }

  // Step 3: both namespaces claim the bare name — refuse, never guess.
  if (isRepo) {
    throw isMachine ? termConnectCollisionError(name) : clusterCollisionError(name);
  }

  // Step 2 (place): a machine is itself; a cluster is its control node.
  if (isCluster) {
    const resolved = await resolveExecutionTarget({ cluster: name });
    return {
      kind: 'place',
      machineName: resolved.machineName,
      ...(resolved.cluster !== undefined && { kubeCluster: resolved.cluster }),
      label: name,
    };
  }
  return { kind: 'place', machineName: name, label: name };
}

/**
 * The §3.3 collision error for the CLUSTER half of the place namespace (exit 11).
 * The spec spells out only the machine case, whose canonical text lives in
 * `termConnectCollisionError`; clusters share the place namespace (§2.1), so the
 * same refusal applies with the noun changed.
 */
function clusterCollisionError(name: string) {
  return ambiguous(
    `${name} is both a repository and a cluster. ` +
      `Use "term connect ${name}@<machine>" for the repository shell, ` +
      `or "term connect <cluster-name>" for the cluster control-node shell.`
  );
}

/** The exit-5 candidate listing for an unknown connect target (§3.3 step 3). */
function candidateLines(ns: ConnectNamespaces): string[] {
  const lines: string[] = [];
  const repos = Object.keys(ns.families).sort();
  const places = [...Object.keys(ns.machines), ...Object.keys(ns.clusters)].sort();
  if (repos.length > 0) lines.push(`known repositories: ${repos.join(', ')}`);
  if (places.length > 0) lines.push(`known machines and clusters: ${places.join(', ')}`);
  return lines;
}
