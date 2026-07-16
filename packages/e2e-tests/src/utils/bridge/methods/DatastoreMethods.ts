import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Named-datastore lifecycle methods for BridgeTestRunner.
 *
 * These dispatch the `datastore_*` bridge functions by literal name — the
 * datastore-cluster model's storage unit (spec 01 §4 / 02). The legacy
 * `datastore_init/mount/unmount` verbs (single implicit `/mnt/rediacc`
 * datastore) live alongside the named-registry verbs the kube suites 15/16/17
 * drive: create → attach → (snapshot → fork → attach `--writes`) → detach/delete.
 */
export interface DatastoreCreateOptions {
  name: string;
  /** local (BTRFS loop) or ceph (RBD-backed) — the fork axis (local forks are refused). */
  backend: 'local' | 'ceph';
  size: string;
  /** Ceph pool (ceph backend). */
  pool?: string;
  /** RBD image name (ceph backend; defaults to name). */
  image?: string;
  /** Ceph CLI cluster name (ceph backend). */
  cephCluster?: string;
  /** k8s cluster backref: makes repos on this datastore dispatch to KubeRuntime. */
  cluster?: string;
}

export interface DatastoreAttachOptions {
  name: string;
  /** Fork write home: local (ephemeral dm-COW overlay) or ceph (durable RW clone). */
  writes?: 'local' | 'ceph';
  /** Fence a stale ceph holder (migrate remap). */
  force?: boolean;
  /** Skip the on-boot re-attach. */
  noAuto?: boolean;
  /** dm-thin overlay size (--writes local). */
  cowSize?: string;
}

export interface DatastoreForkOptions {
  parent: string;
  tag: string;
  /** Clone from an existing (group) snapshot — the cluster-fork path. */
  snapshot?: string;
  /** RBD group owning --snapshot (whole-cluster group snap). */
  group?: string;
  cowSize?: string;
}

export interface DatastoreSnapshotOptions {
  /** Single-datastore snapshot. */
  name?: string;
  /** Cluster name: a GROUP snapshot atomic across the cluster's ceph datastores. */
  group?: string;
  snapshot: string;
  /**
   * Flush member filesystems before the capture (fork semantics: "every write
   * completed before the fork is in the fork"). Default false — the bare
   * snapshot verb is crash-consistent by documented contract and never flushes.
   */
  quiesce?: boolean;
}

/**
 * Datastore management methods for BridgeTestRunner.
 */
export class DatastoreMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  async datastoreExpand(newSize: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_expand',
      newSize,
      datastorePath,
    });
  }

  async datastoreResize(newSize: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_resize',
      newSize,
      datastorePath,
    });
  }

  async datastoreValidate(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_validate',
      datastorePath,
    });
  }

  // --- Named-datastore registry lifecycle (datastore-cluster model) ---

  /** Create a named datastore, local or ceph-backed (datastore_create). */
  async datastoreCreate(opts: DatastoreCreateOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_create',
      name: opts.name,
      backend: opts.backend,
      size: opts.size,
      pool: opts.pool,
      image: opts.image,
      cephCluster: opts.cephCluster,
      cluster: opts.cluster,
    });
  }

  /** Attach a datastore (or a fork, selecting its write home) (datastore_attach). */
  async datastoreAttach(opts: DatastoreAttachOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_attach',
      name: opts.name,
      writes: opts.writes,
      force: opts.force,
      noAuto: opts.noAuto,
      cowSize: opts.cowSize,
    });
  }

  /** Detach a datastore; --discard removes a fork (datastore_detach). */
  async datastoreDetach(name: string, discard?: boolean): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_detach',
      name,
      discard,
    });
  }

  /** Delete a datastore (datastore_delete). */
  async datastoreDelete(name: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_delete',
      name,
    });
  }

  /** List the datastore registry as JSON (datastore_list). */
  async datastoreList(): Promise<ExecResult> {
    return this.testFunction({ function: 'datastore_list' });
  }

  /**
   * Fork a ceph datastore from a (group) snapshot, clone-format-2
   * (datastore_fork). A local-backed parent is REFUSED (gate C8) — repos inside
   * a local datastore fork individually by reflink instead.
   */
  async datastoreFork(opts: DatastoreForkOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_fork',
      parent: opts.parent,
      tag: opts.tag,
      snapshot: opts.snapshot,
      group: opts.group,
      cowSize: opts.cowSize,
    });
  }

  /**
   * Create a datastore snapshot; --group makes it an atomic GROUP snapshot
   * across a cluster's ceph datastores (datastore_snapshot_create).
   */
  async datastoreSnapshotCreate(opts: DatastoreSnapshotOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_snapshot_create',
      name: opts.name,
      group: opts.group,
      snapshot: opts.snapshot,
      quiesce: opts.quiesce,
    });
  }

  /**
   * Delete a datastore snapshot; --group deletes a cluster's GROUP snapshot
   * (refuses while it still has live fork clones — discard those first)
   * (datastore_snapshot_delete).
   */
  async datastoreSnapshotDelete(opts: DatastoreSnapshotOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_snapshot_delete',
      name: opts.name,
      group: opts.group,
      snapshot: opts.snapshot,
    });
  }
}
