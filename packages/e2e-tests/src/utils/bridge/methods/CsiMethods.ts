import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Ceph-CSI methods for BridgeTestRunner.
 *
 * Dispatches the `kube_csi_template` bridge function by literal name so the
 * e2e-coverage gate finds it once the lead regenerates the renet contract. The
 * function renders (and optionally applies) the ceph-csi RBD manifests for a
 * cluster's pool + RADOS namespace. The RADOS-namespace fork integration and
 * the live suite-16 exercise land in wave 6b (after wave 5); this is the
 * coverage anchor + harness handle.
 */
export interface CsiTemplateOptions {
  /** Ceph RBD pool to template ceph-csi for. */
  pool: string;
  /** Cluster name (naming/logging). */
  cluster?: string;
}

export class CsiMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  /** Render/apply ceph-csi RBD manifests for a pool (kube_csi_template). */
  async kubeCsiTemplate(opts: CsiTemplateOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_csi_template',
      pool: opts.pool,
      cluster: opts.cluster,
    });
  }
}
