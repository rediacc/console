import type { ExecResult } from '../types';

/**
 * CSI methods for BridgeTestRunner.
 *
 * TRANSLATED, not dropped. These used to dispatch a `kube_csi_template` BRIDGE verb
 * that renet never actually registered — the class existed so the (one-directional)
 * coverage gate would find the name. That is a coverage anchor, and the bidirectional
 * gate caught it.
 *
 * The SUBJECT is alive: standing CSI up so a PVC can bind is what
 * `renet kube csi-install` (cluster-scoped objects: CRDs, CSIDriver, RBAC,
 * VolumeSnapshotClass) and `renet kube csi-node-up` (per-node driver units + the
 * per-datastore StorageClass) do today. Only the TRANSPORT moved — from a bridge
 * dispatch to the root CLI — so these route through the CLI, the same way OpsManager
 * shells out for `renet datastore init`.
 *
 * The verb is gone; the thing is not.
 */
export interface CsiNodeUpOptions {
  /** This node's k8s node name. */
  nodeName: string;
  /** Datastore whose StorageClass (rediacc-csi-<ds>) is applied. */
  datastore: string;
  /** Datastore mount root — the kubelet root is derived from it. */
  mountPath?: string;
  /** Cluster name (sidecar kubeconfig dir). */
  cluster?: string;
  /** Also install the snapshot-controller singleton (control-plane node). */
  controlPlane?: boolean;
}

export class CsiMethods {
  constructor(private readonly exec: (command: string, timeout?: number) => Promise<ExecResult>) {}

  /** Apply the cluster-scoped CSI objects (CRDs, CSIDriver, RBAC, VolumeSnapshotClass). */
  async kubeCsiInstall(kubeconfig?: string): Promise<ExecResult> {
    const kc = kubeconfig ? ` --kubeconfig ${kubeconfig}` : '';
    return this.exec(`sudo renet kube csi-install${kc}`);
  }

  /** Install + start the per-node CSI units and apply the datastore StorageClass. */
  async kubeCsiNodeUp(opts: CsiNodeUpOptions): Promise<ExecResult> {
    const flags = [
      `--node-name ${opts.nodeName}`,
      `--datastore ${opts.datastore}`,
      opts.mountPath ? `--mount-path ${opts.mountPath}` : '',
      opts.cluster ? `--cluster ${opts.cluster}` : '',
      opts.controlPlane ? '--control-plane' : '',
    ]
      .filter(Boolean)
      .join(' ');
    return this.exec(`sudo renet kube csi-node-up ${flags}`);
  }

  /** Stop + remove the per-node CSI units and GC stale storage capacity. */
  async kubeCsiNodeDown(nodeName: string): Promise<ExecResult> {
    return this.exec(`sudo renet kube csi-node-down --node-name ${nodeName}`);
  }
}
