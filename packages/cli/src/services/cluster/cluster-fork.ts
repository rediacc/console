/**
 * Whole-cluster fork / rehearse / migrate lifecycle (docs/design/04-cluster-fork-migrate.md).
 * Split out of cluster-kube.ts (max-lines): a PURE move — these sequence the same
 * renet datastore_/kube_/repository_ bridge primitives via the shared install/naming
 * helpers exported from cluster-kube.ts. No behavior change.
 *   - FORK    = quiesced (syncfs) rbd group snapshot → clone → fenced attach (--writes)
 *               → identity-rewrite operation=fork (PKI re-mint + secret scrub) → rejoin.
 *   - REHEARSE= fork into a throwaway, health-gate, discard.
 *   - MIGRATE = in-Ceph fenced remap (identity-rewrite operation=migrate, CA preserved).
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { getCluster } from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { auditService } from '../core/audit.js';
import { outputService } from '../core/output.js';
import { getExecutor } from '../executor/executor-factory.js';
import { parseCapturedJson } from '../executor/local-executor.js';
import {
  allocateAgentNetworkId,
  assertDestNotRunningOwnK3s,
  clusterMount,
  controlDatastore,
  controlDatastoreMount,
  dispatch,
  K8S_SERVER_ROLES,
  type K8sMember,
  k8sPoolsOf,
  NAMED_DS_BASE,
  prepareForkDest,
  prepareMigrateDest,
  resolveControlDsBackend,
  resolveK8sMembers,
  serverUrl,
} from './cluster-kube.js';

export interface ForkClusterOptions {
  tag: string;
  /** Existing destination cluster to fork onto (its members host the fork). */
  cluster?: string;
  /**
   * Write disposition for the fork's datastores (04 §2): `local` = ephemeral
   * dm-COW overlay over a read-only clone (zero Ceph footprint — a throwaway test
   * cluster), `ceph` = durable RW clone. Default `local`.
   */
  writes?: 'local' | 'ceph';
  /** Bring the forked repos up and gate on cluster health after the fork boots. */
  up?: boolean;
  /**
   * Effect-isolation ROLE written into the fork's ROLE ConfigMap (02 §4):
   * `fork` (default) or `rehearsal` (a throwaway that runs secretless and reports
   * REDIACC_ROLE=rehearsal, so apps degrade gracefully). `cluster rehearse` sets it.
   */
  role?: 'fork' | 'rehearsal';
  debug?: boolean;
}

/**
 * What a fork produced — enough to tear it down (cluster rehearse discards it).
 */
export interface ForkResult {
  /** Destination control-plane machine name. */
  destControl: string;
  /** The fork control-plane mount path (fork clone of ds-control-<cluster>). */
  forkMount: string;
  /** The fork control-plane networkID (its k3s unit). */
  networkId: number;
  /** Source cluster datastore names that were cloned (record keys are `<name>:<tag>`). */
  datastores: string[];
  /** The fork tag. */
  tag: string;
}

/** The fork datastore record key `<parent>:<tag>` (datastore attach/detach). */
function forkRecordName(parent: string, tag: string): string {
  return `${parent}:${tag}`;
}
/** The fork clone's mount path `/mnt/rediacc-ds/<parent>-<tag>`. */
function forkDatastoreMount(parent: string, tag: string): string {
  return `${NAMED_DS_BASE}/${parent}-${tag}`;
}

/** One datastore record from `renet datastore list --json`. */
interface DatastoreRecord {
  name: string;
  backend: string;
  cluster?: string;
  fork?: unknown;
  implicit?: boolean;
}

/**
 * List the source cluster's CEPH-backed, non-fork datastores (the control
 * datastore + every data datastore) — the group-snap membership and the set to
 * clone. Read from the machine registry via `datastore_list`; the control
 * datastore `ds-control-<cluster>` is guaranteed present first.
 */
async function listClusterCephDatastores(
  machineName: string,
  clusterName: string,
  debug?: boolean
): Promise<string[]> {
  const res = await dispatch('datastore_list', machineName, {}, { debug, capture: true });
  // datastore_list shells out to `renet datastore list --json`; captured stdout is
  // the `[datastore_list] [...]` bridge relay format — strip the prefix (finding #10).
  const records = parseCapturedJson<DatastoreRecord[]>(res.stdout);
  const members = records
    .filter((r) => !r.implicit && !r.fork && r.backend === 'ceph' && r.cluster === clusterName)
    .map((r) => r.name);
  if (members.length === 0) {
    throw new Error(
      `Cluster "${clusterName}" has no ceph-backed datastores to fork. The whole-cluster ` +
        `fork requires an rbd-backed control datastore (created by "cluster create" on ceph); ` +
        `a local-tier cluster forks per-repo by reflink instead.`
    );
  }
  // Deterministic order: control datastore first, then data datastores sorted.
  const control = controlDatastore(clusterName);
  return [...members.filter((m) => m === control), ...members.filter((m) => m !== control).sort()];
}

/**
 * Fork a whole cluster onto a destination cluster's nodes — the ANCHOR+REJOIN
 * model (04 §2, promoted from the P2-A proven battery). The control-plane image
 * IS the cluster, so we move the ANCHOR (a quiesced group snapshot of the
 * cluster's datastores — the parent NEVER stops) and let agents REJOIN fresh with
 * the new-CA token. This is F1-safe by construction: the control-plane identity
 * rewrite runs `--operation fork`, which re-mints the whole PKI and scrubs
 * secrets, so the fork can NEVER carry the parent cluster's CA key.
 *
 * dstAgents >= srcAgents no longer applies: destination node count is free (1..N).
 * Same-machine forks stay forbidden (two k3s cannot share a host netns).
 */
export async function forkCluster(
  clusterName: string,
  options: ForkClusterOptions
): Promise<ForkResult> {
  const startTime = Date.now();
  const role = options.role ?? DEFAULTS.CLUSTER.FORK_ROLE;
  if (!options.cluster) {
    throw new Error(
      `A whole-cluster fork must land on distinct machines (two k3s cannot share a host netns). ` +
        `Provision or name a destination cluster and pass --cluster <dest>.`
    );
  }
  // Validate against the allowed set on a string-typed value: an unvalidated CLI
  // string (or a test bypassing the type) must still be rejected, but the typed
  // union would make the literal comparison "always false" to the checker.
  const writesRaw: string = options.writes ?? DEFAULTS.CLUSTER.FORK_WRITES;
  if (writesRaw !== 'local' && writesRaw !== 'ceph') {
    throw new Error(`--writes must be "local" or "ceph" (got "${writesRaw}").`);
  }
  const writes = writesRaw;

  const source = await getCluster(clusterName);
  const dest = await getCluster(options.cluster);
  const srcMembers = await resolveK8sMembers(clusterName, k8sPoolsOf(source));
  const dstMembers = await resolveK8sMembers(options.cluster, k8sPoolsOf(dest));
  const srcControl = srcMembers.find((m) => K8S_SERVER_ROLES.has(m.role));
  const dstControl = dstMembers.find((m) => K8S_SERVER_ROLES.has(m.role));
  const dstAgents = dstMembers.filter((m) => m.role === 'k8s-agent');
  if (!srcControl || !dstControl) {
    throw new Error(`Both "${clusterName}" and "${options.cluster}" need a k8s-server member.`);
  }

  // 0. Fail fast (finding #8): refuse a dest whose control node already runs its
  //    own k3s (:6443 collision) BEFORE any snapshot/clone work — dispatch
  //    nothing destructive on a bad target.
  await assertDestNotRunningOwnK3s(options.cluster, dstControl.name, options.debug);

  // 0b. Give the dest members SOURCE-ceph access + the rbd/sqlite3 tooling the
  //     adopt/attach + kine-scrub need (findings #7/#15) — createCluster only
  //     seeds a cluster's own nodes with its own ceph.
  await prepareForkDest(clusterName, source, dstMembers, options.debug);

  const snapshot = `fork-${options.tag}`;
  outputService.info(
    `Fork "${clusterName}" -> "${options.cluster}" [${options.tag}, writes=${writes}]: ` +
      `group snapshot (parent stays live)...`
  );

  // 1. ONE atomic group snapshot across the cluster's ceph datastores — QUIESCED
  //    (fork semantics, #440: a fork carries what you just wrote), so every member
  //    is syncfs-flushed, inner filesystems first, before the instant. syncfs
  //    flushes without pausing: no drain, no stop — the parent never notices
  //    (04 §2 step 1). The bare cluster-snapshot verb stays crash-consistent and
  //    never passes quiesce.
  const clusterDatastores = await listClusterCephDatastores(
    srcControl.name,
    clusterName,
    options.debug
  );
  await dispatch(
    'datastore_snapshot_create',
    srcControl.name,
    { group: clusterName, snapshot, quiesce: true },
    { debug: options.debug }
  );

  // 2. Clone each datastore from the group snap (clone-format-2 per-call). The
  //    fork records are `<ds>:<tag>` DETACHED (04 §2 step 2). datastore_fork
  //    registers the fork record ONLY in the SOURCE machine's registry; the attach
  //    below runs on the DEST, whose registry has no such record — so we ferry the
  //    record (the `datastore fork --json` output) to the dest and `datastore_adopt`
  //    it there before attaching (finding #14: cross-machine fork-record propagation).
  for (const ds of clusterDatastores) {
    const forkRes = await dispatch(
      'datastore_fork',
      srcControl.name,
      { parent: ds, tag: options.tag, snapshot, group: clusterName },
      { debug: options.debug, capture: true }
    );
    const record = parseCapturedJson<unknown>(forkRes.stdout);
    const recordB64 = Buffer.from(JSON.stringify(record)).toString('base64');
    await dispatch(
      'datastore_adopt',
      dstControl.name,
      { name: forkRecordName(ds, options.tag), record_b64: recordB64 },
      { debug: options.debug }
    );
  }

  // 3. Attach every clone on the destination control node with --writes composing
  //    (one beefy machine mounts all — 04 §2 step 3 / §3). `local` = ephemeral
  //    dm-COW overlay, `ceph` = durable RW clone.
  for (const ds of clusterDatastores) {
    await dispatch(
      'datastore_attach',
      dstControl.name,
      { name: forkRecordName(ds, options.tag), writes },
      { debug: options.debug }
    );
  }

  // 4. Control-plane identity rewrite, operation=FORK: the F1-safe 8-step PKI
  //    re-mint + secret scrub + ROLE=fork rewrite + stale-Node delete, with a NEW
  //    networkID (04 §2 step 4). The clone mounts at the stable-name path.
  const controlDs = controlDatastore(clusterName);
  const forkMount = forkDatastoreMount(controlDs, options.tag);
  const forkNet = await configService.allocateNetworkId();
  outputService.info(
    `  control-plane fork identity rewrite (PKI re-mint + scrub) on ${dstControl.name}...`
  );
  await dispatch(
    'kube_identity_rewrite',
    dstControl.name,
    {
      mount_path: forkMount,
      operation: 'fork',
      mode: 'server',
      new_node_ip: dstControl.ip,
      new_network_id: forkNet,
      role,
      writes,
    },
    { debug: options.debug }
  );

  // 5. Fresh agents REJOIN the fork with the NEW-CA token (04 §2 step 5; agents
  //    are disposable, dst count is free). The fork's F8 already deleted the
  //    parent's stale Node objects, so fresh agents register clean.
  const tokenRes = await dispatch(
    'kube_join_token',
    dstControl.name,
    { mount_path: forkMount },
    { debug: options.debug, capture: true }
  );
  const token = /K10[^"\s]+/.exec(tokenRes.stdout ?? '')?.[0];
  if (!token) throw new Error('Could not read the fork control-plane join token.');
  const forkEndpoint = serverUrl(dstControl.ip);
  for (const agent of dstAgents) {
    outputService.info(`  fresh agent join ${agent.name} (${agent.ip})...`);
    const agentNet = await allocateAgentNetworkId();
    await dispatch(
      'kube_join',
      agent.name,
      {
        mount_path: clusterMount(options.cluster),
        network_id: agentNet,
        role: 'agent',
        token,
        endpoint: forkEndpoint,
        bind_ip: agent.ip,
      },
      { debug: options.debug }
    );
  }

  // 6. --up + health gate (04 §4): gate the fork control plane on readiness before
  //    declaring success (the rollback window — the parent is untouched throughout).
  if (options.up) {
    await clusterHealthGate(dstControl.name, forkMount, options.debug);
  }

  auditService.recordOperation({
    functionName: 'cluster_fork',
    machineName: clusterName,
    success: true,
    exitCode: 0,
    durationMs: Date.now() - startTime,
  });
  outputService.success(
    `Cluster "${clusterName}" forked as "${options.tag}" onto "${options.cluster}" ` +
      `(${clusterDatastores.length} datastore(s), ${dstAgents.length} agent(s), writes=${writes}, ` +
      `role=${role}). PKI re-minted, parent untouched.`
  );
  return {
    destControl: dstControl.name,
    forkMount,
    networkId: forkNet,
    datastores: clusterDatastores,
    tag: options.tag,
  };
}

/** Per-attempt gate timeout + total window (04 §4 / gate C5 defaults). */
const HEALTH_GATE_ATTEMPT_MS = 30_000;
const HEALTH_GATE_WINDOW_MS = 300_000;

/**
 * Gate on the cluster control plane becoming healthy (04 §4 layer 1: the distro
 * /readyz healthcheck), retrying until the window expires. Used by fork --up and
 * migrate to confirm the destination serves before releasing the source. Throws
 * on window expiry so the caller keeps the rollback source intact.
 */
async function clusterHealthGate(
  machineName: string,
  mountPath: string,
  debug?: boolean
): Promise<void> {
  const deadline = gateNow() + HEALTH_GATE_WINDOW_MS;
  let lastErr = '';
  while (gateNow() < deadline) {
    const res = await getExecutor().execute({
      functionName: 'kube_health',
      machineName,
      params: { mount_path: mountPath },
      captureOutput: true,
      debug,
    });
    if (res.success) return;
    lastErr = res.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR;
    await delay(HEALTH_GATE_ATTEMPT_MS);
  }
  throw new Error(`Cluster health gate did not pass within ${HEALTH_GATE_WINDOW_MS}ms: ${lastErr}`);
}

/** Injectable delay + clock (overridden in tests to avoid real waits/wall-clock). */
let delay: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms));
let gateNow: () => number = Date.now;
/** Test seam: replace the health-gate delay. */
export function __setHealthGateDelay(fn: (ms: number) => Promise<void>): void {
  delay = fn;
}
/** Test seam: replace the health-gate clock (so a failing gate expires fast). */
export function __setHealthGateClock(fn: () => number): void {
  gateNow = fn;
}

export interface RehearseClusterOptions {
  /** Destination cluster whose nodes host the throwaway rehearsal fork. */
  cluster?: string;
  /** Optional tag for the rehearsal fork (default a timestamped one). */
  tag?: string;
  debug?: boolean;
}

/**
 * Rehearse a cluster: boot an EPHEMERAL throwaway fork of the latest state on a
 * destination, health-gate it, report, and DISCARD it (05 §2 rung 1 + 04 §4).
 * This is a thin wrapper over `forkCluster` with `--writes local` (zero Ceph
 * footprint) + `role=rehearsal` (the fork runs SECRETLESS — apps see
 * REDIACC_ROLE=rehearsal and degrade gracefully) + `--up` (health gate). It is
 * the "costs ~nothing, catches most" pre-release rung: a fork rehearsal proves a
 * release/upgrade boots healthy before it touches the live cluster. The parent is
 * never stopped; the rehearsal is always torn down (best-effort discard even on a
 * failed gate, so a rehearsal never leaves state behind).
 */
export async function rehearseCluster(
  clusterName: string,
  options: RehearseClusterOptions
): Promise<void> {
  if (!options.cluster) {
    throw new Error(
      `A rehearsal boots a whole throwaway control plane, so it needs a destination cluster ` +
        `to run on. Pass --on <dest-cluster>.`
    );
  }
  const destCluster = options.cluster;
  const tag = options.tag ?? `rehearse-${Date.now()}`;
  outputService.info(`Rehearse "${clusterName}" [${tag}] on "${destCluster}" (ephemeral fork)...`);

  // ★ BUG #44: resolve the destination CONTROL MACHINE up front. The failure path
  // below needs it, and `options.cluster` is a CLUSTER name, not a machine — the
  // catch used to pass it straight into discardRehearsal's `destControl` (machine)
  // parameter, so every teardown step dispatched at a machine that does not exist.
  // tryDispatch is best-effort, so it swallowed the errors and a FAILED rehearsal
  // silently left its whole fork behind: the exact residue rehearse promises never
  // to leave.
  const destControl = await resolveDestControl(destCluster);

  let result: ForkResult;
  try {
    result = await forkCluster(clusterName, {
      tag,
      cluster: destCluster,
      writes: 'local',
      role: 'rehearsal',
      up: true,
      debug: options.debug,
    });
  } catch (err) {
    // A failed fork/gate still tries to discard whatever partial state exists.
    await discardRehearsal(destControl, clusterName, tag, options.debug);
    throw err;
  }

  outputService.success(
    `Rehearsal "${clusterName}" [${tag}] passed the health gate (secretless, role=rehearsal). Discarding...`
  );
  await discardRehearsal(result.destControl, clusterName, tag, options.debug, result);
  outputService.success(`Rehearsal "${clusterName}" [${tag}] discarded with no residue.`);
}

/**
 * The destination cluster's control-plane MACHINE (the host every teardown step
 * dispatches at). Resolved before the fork so the failure path has it too (#44).
 */
async function resolveDestControl(destCluster: string): Promise<string | undefined> {
  const dest = await getCluster(destCluster);
  const members = await resolveK8sMembers(destCluster, k8sPoolsOf(dest));
  return members.find((m) => K8S_SERVER_ROLES.has(m.role))?.name;
}

/**
 * Tear down a rehearsal fork: uninstall the fork's k3s control plane, then
 * `datastore detach --discard` every fork clone (removes the overlay/clone + the
 * record). Best-effort per step so a partial rehearsal still cleans up.
 */
async function discardRehearsal(
  destControl: string | undefined,
  clusterName: string,
  tag: string,
  debug?: boolean,
  result?: ForkResult
): Promise<void> {
  if (!destControl) return;
  const forkMount = result?.forkMount ?? forkDatastoreMount(controlDatastore(clusterName), tag);
  // The datastores to discard: from the fork result, else re-derive from the
  // registry (a partial rehearsal that failed before returning a result).
  let datastores = result?.datastores;
  if (!datastores) {
    try {
      datastores = await listClusterCephDatastores(destControl, clusterName, debug);
    } catch {
      datastores = [controlDatastore(clusterName)];
    }
  }
  await tryDispatch('kube_uninstall', destControl, { mount_path: forkMount }, debug);
  for (const ds of datastores) {
    await tryDispatch(
      'datastore_detach',
      destControl,
      { name: forkRecordName(ds, tag), discard: true },
      debug
    );
  }
}

/** Dispatch a teardown step, swallowing failures (discard is best-effort). */
async function tryDispatch(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<void> {
  try {
    await getExecutor().execute({ functionName, machineName, params, debug });
  } catch (err) {
    outputService.warn(`  discard: ${functionName} on ${machineName} failed (continuing): ${err}`);
  }
}

export interface MigrateClusterOptions {
  to: string;
  debug?: boolean;
}

/**
 * Migrate a cluster's control plane to another machine — the anchor-model
 * IN-CEPH FENCED REMAP (04 §3): a pure datastore failover with ZERO data copy.
 * The control-plane data-dir lives in the rbd-backed control datastore, so
 * relocating it is: down() the source CP → detach the datastore (release its
 * exclusive lock) → attach on the destination (FENCING any stale holder) →
 * identity rewrite `--operation migrate` (CA PRESERVED — same principal —
 * networkID KEPT, IP-only) → health-gate the destination before declaring done.
 * Node-to-node moves inside one Ceph reach stop being "migrate" and become this
 * failover; today's backup_push block transfer disappears for this case.
 *
 * Cross-site migrate (different Ceph reach: rbd-mirror / iterated export-diff
 * between separate ceph clusters, or ceph→local) needs a datastore-level transfer
 * transport that is NOT a landed primitive (the old backup_push was repo-image
 * level, from the pre-anchor model) — it is a documented P3 follow-up; this path
 * refuses cleanly rather than do a half-correct transfer.
 */
export async function migrateCluster(
  clusterName: string,
  options: MigrateClusterOptions
): Promise<void> {
  const startTime = Date.now();
  const source = await getCluster(clusterName);
  const members = await resolveK8sMembers(clusterName, k8sPoolsOf(source));
  const control = members.find((m) => K8S_SERVER_ROLES.has(m.role));
  if (!control) throw new Error(`Cluster "${clusterName}" has no k8s-server member to migrate.`);

  // The anchor control datastore must be ceph-backed for the in-Ceph remap.
  if (resolveControlDsBackend(source, {}) !== 'ceph') {
    throw new Error(
      `cluster migrate "${clusterName}" currently supports the in-Ceph fenced remap only ` +
        `(ceph-backed control datastore). Cross-site / local-tier cluster migrate (datastore ` +
        `transfer via rbd-mirror or export-diff) is a P3 follow-up.`
    );
  }

  const destMachine = await configService.getLocalMachine(options.to);
  const controlDs = controlDatastore(clusterName);
  const controlDsMount = controlDatastoreMount(clusterName);

  outputService.info(
    `Migrate "${clusterName}" -> "${options.to}" (in-Ceph fenced remap, zero copy)...`
  );

  // 0a. Seed the dest with SOURCE-ceph client access + the rbd/sqlite3 tooling the
  //     fenced attach needs (finding #19) — a fresh bare dest has neither, and
  //     createCluster only seeds a cluster's own nodes. Non-destructive to the
  //     source (a config/package push), so it precedes everything.
  await prepareMigrateDest(clusterName, source, options.to, options.debug);

  // 0b. Ferry the control-datastore RECORD to the dest and ADOPT it (registry-only,
  //    no disk work), then VERIFY — BEFORE anything destructive (finding #18). The
  //    per-machine registry holds the control-datastore record ONLY on the source,
  //    so a naive dest attach fails "not registered on this machine" AFTER the
  //    source is already downed+detached, stranding the cluster. Adopting the plain
  //    (non-fork) record and verifying it here makes that failure mode impossible by
  //    construction: a registry miss is caught with the source still serving.
  const recordB64 = await captureDatastoreRecord(control.name, controlDs, options.debug);
  await dispatch(
    'datastore_adopt',
    options.to,
    { name: controlDs, record_b64: recordB64, plain: true },
    { debug: options.debug }
  );
  await verifyDatastoreRegistered(options.to, controlDs, options.debug);

  // The cutover clock starts at the source down() — everything above is registry
  // paperwork the live source never notices (zero downtime contribution).
  const downStart = Date.now();

  // 1. down() the source control plane so the datastore is consistent before the
  //    lock is released (04 §4 step 0 — a clean shutdown, not a crash).
  await dispatch(
    'kube_prep_fork',
    control.name,
    { mount_path: controlDsMount, node: '' },
    { debug: options.debug }
  );

  // 2. Detach the control datastore from the source (release its exclusive lock).
  await dispatch('datastore_detach', control.name, { name: controlDs }, { debug: options.debug });

  // 3. Attach on the destination, FENCING any stale holder (rbd lock break + osd
  //    blocklist). Same mount path (mount-path stability, 04 §6) — PV objects in
  //    kine reference it and need zero rewriting. On an attach-layer failure, roll
  //    back to the source (re-attach + restart its CP) so a mid-cutover error never
  //    leaves BOTH sides down; the found registry failure mode is already excluded
  //    by step 0, so a failure here can only be attach-layer (fencing / rbd map).
  try {
    await dispatch(
      'datastore_attach',
      options.to,
      { name: controlDs, force: true },
      { debug: options.debug }
    );
  } catch (attachErr) {
    await rollbackMigrateToSource(control, controlDs, controlDsMount, options.debug);
    throw new Error(
      `cluster migrate "${clusterName}" failed at the destination attach and was ROLLED BACK to ` +
        `"${control.name}" (control datastore re-attached + control plane restarted). The dest's ` +
        `adopted record is harmless (registry-only) and is reused on retry. If the source did not ` +
        `recover, on ${control.name} run: renet datastore attach --name ${controlDs} --force, then ` +
        `renet kube identity-rewrite --mount-path ${controlDsMount} --operation migrate --new-node-ip ` +
        `${control.ip}. Original error: ${attachErr instanceof Error ? attachErr.message : String(attachErr)}`
    );
  }

  // 4. Identity rewrite operation=migrate: CA PRESERVED, networkID KEPT (no
  //    new_network_id), serving leaf regenerated for the new IP, secrets stay.
  await dispatch(
    'kube_identity_rewrite',
    options.to,
    {
      mount_path: controlDsMount,
      operation: 'migrate',
      mode: 'server',
      new_node_ip: destMachine.ip,
    },
    { debug: options.debug }
  );

  // 5. Health-gate the destination control plane before declaring done — the
  //    rollback window (04 §4 step 4): the source is only released once the gate
  //    passes (here the datastore already moved, so a gate failure is surfaced
  //    loudly for operator recovery rather than silently succeeding).
  await clusterHealthGate(options.to, controlDsMount, options.debug);

  const downtimeMs = Date.now() - downStart;

  // 6. Single-mounter invariant: drop the SOURCE's now-stale control-datastore
  //    record so it can never become a second attach candidate for the SAME shared
  //    rbd image now serving on the dest. Registry-only (Forget), NEVER delete — the
  //    image is the moved data, so `datastore delete` (rbd rm) would destroy it.
  //    Best-effort: the cutover already succeeded and is healthy, so a forget hiccup
  //    warns (with the manual command) rather than failing an otherwise-good migrate.
  try {
    await dispatch('datastore_forget', control.name, { name: controlDs }, { debug: options.debug });
  } catch (forgetErr) {
    outputService.warn(
      `  migrate succeeded but could not drop the stale source record on ${control.name}: ` +
        `${forgetErr instanceof Error ? forgetErr.message : String(forgetErr)}. Run manually to ` +
        `restore the single-mounter invariant: renet datastore forget --name ${controlDs}.`
    );
  }

  auditService.recordOperation({
    functionName: 'cluster_migrate',
    machineName: clusterName,
    success: true,
    exitCode: 0,
    durationMs: Date.now() - startTime,
  });
  outputService.success(
    `Cluster "${clusterName}" migrated to "${options.to}" (zero-copy in-Ceph remap). ` +
      `Cutover downtime: ${(downtimeMs / 1000).toFixed(1)}s.`
  );
}

/**
 * Capture a datastore's full registry record (base64 of its JSON) from
 * `datastore_list` on a machine — the migrate record-ferry (finding #18), mirroring
 * how the fork path ferries `datastore fork --json`. The list emits each row as the
 * flattened Record plus its `name`, so the captured object carries the ceph
 * pool/image + cluster backref the dest needs to reconstruct the row.
 */
async function captureDatastoreRecord(
  machineName: string,
  name: string,
  debug?: boolean
): Promise<string> {
  const res = await dispatch('datastore_list', machineName, {}, { debug, capture: true });
  const records = parseCapturedJson<Record<string, unknown>[]>(res.stdout);
  const rec = records.find((r) => r.name === name);
  if (!rec) {
    throw new Error(
      `Datastore "${name}" is not registered on ${machineName}; cannot migrate its cluster.`
    );
  }
  return Buffer.from(JSON.stringify(rec)).toString('base64');
}

/**
 * Post-adopt gate: confirm a datastore name is now in a machine's registry. Runs
 * BEFORE the source is downed, so a registry miss aborts cleanly with the source
 * still serving (finding #18: the failure can never strand a downed source).
 */
async function verifyDatastoreRegistered(
  machineName: string,
  name: string,
  debug?: boolean
): Promise<void> {
  const res = await dispatch('datastore_list', machineName, {}, { debug, capture: true });
  const records = parseCapturedJson<{ name: string }[]>(res.stdout);
  if (!records.some((r) => r.name === name)) {
    throw new Error(
      `Migrate pre-flight failed: after adopt, "${name}" is still not registered on ${machineName}. ` +
        `Refusing to down the source. Nothing destructive has happened.`
    );
  }
}

/**
 * Best-effort rollback after a failed destination attach: re-attach the control
 * datastore on the SOURCE (force-fencing any partial dest holder) and restart its
 * control plane via an identity rewrite to its OWN IP (operation=migrate preserves
 * the CA and starts the k3s unit prep_fork stopped). Every step is best-effort so a
 * secondary failure still surfaces the original error + manual recovery path.
 */
async function rollbackMigrateToSource(
  control: K8sMember,
  controlDs: string,
  controlDsMount: string,
  debug?: boolean
): Promise<void> {
  await tryDispatch('datastore_attach', control.name, { name: controlDs, force: true }, debug);
  await tryDispatch(
    'kube_identity_rewrite',
    control.name,
    { mount_path: controlDsMount, operation: 'migrate', mode: 'server', new_node_ip: control.ip },
    debug
  );
}
