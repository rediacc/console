import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Ceph-backed datastore methods for BridgeTestRunner.
 *
 * These dispatch the `datastore_ceph_*` bridge functions by literal name, so
 * the e2e-coverage gate (which greps bridge-tests for each generated function
 * name) sees them, and suites 13/14 exercise the real product paths:
 *   - datastore_ceph_init:   create an RBD-backed BTRFS datastore
 *   - datastore_ceph_fork:   snapshot + clone + COW-overlay mount (instant fork)
 *   - datastore_ceph_unfork: tear the fork down in the correct order
 */
export interface CephInitOptions {
  size: string;
  image: string;
  datastorePath: string;
  pool?: string;
  cluster?: string;
  force?: boolean;
}

export interface CephForkOptions {
  source: string;
  dest: string;
  mountPoint: string;
  pool?: string;
  cowSize?: string;
  cluster?: string;
}

export interface CephUnforkOptions {
  source: string;
  dest: string;
  snapshot: string;
  mountPoint?: string;
  pool?: string;
  cluster?: string;
  force?: boolean;
}

export class DatastoreCephMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  /** Initialize a Ceph RBD-backed datastore (datastore_ceph_init). */
  async datastoreCephInit(opts: CephInitOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_ceph_init',
      size: opts.size,
      image: opts.image,
      datastorePath: opts.datastorePath,
      pool: opts.pool,
      cluster: opts.cluster,
      force: opts.force,
    });
  }

  /** Fork a Ceph datastore via RBD snapshot + clone + COW overlay (datastore_ceph_fork). */
  async datastoreCephFork(opts: CephForkOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_ceph_fork',
      source: opts.source,
      dest: opts.dest,
      mountPoint: opts.mountPoint,
      pool: opts.pool,
      cowSize: opts.cowSize,
      cluster: opts.cluster,
    });
  }

  /** Tear down a forked Ceph datastore (datastore_ceph_unfork). */
  async datastoreCephUnfork(opts: CephUnforkOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_ceph_unfork',
      source: opts.source,
      dest: opts.dest,
      snapshot: opts.snapshot,
      mountPoint: opts.mountPoint,
      pool: opts.pool,
      cluster: opts.cluster,
      force: opts.force,
    });
  }
}
