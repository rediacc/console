import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Registry (zot pull-through cache) methods for BridgeTestRunner.
 *
 * These dispatch the `kube_registry_*` bridge functions by literal name, so the
 * e2e-coverage gate (which greps bridge-tests for each generated function name)
 * sees them once the lead regenerates the renet contract. The zot registry
 * replaces the old registry:2/registry:3 "reregistry" as the pull-through cache:
 *   - kube_registry_up:   bring the zot cache online on the control node
 *     (extract binary, render config with sync.onDemand upstreams, systemd unit)
 *   - kube_registry_wire: point containerd certs.d + k3s registries.yaml at it
 *
 * The suite that exercises these against a live VM is env-gated skip (wave 5+);
 * this harness wiring makes the coverage present now.
 */
export interface RegistryUpOptions {
  /** Comma-separated upstream hosts (default docker.io,ghcr.io,quay.io). */
  upstreams?: string;
  /** machine | cluster (sizing/placement hint). */
  scope?: 'machine' | 'cluster';
  /** Datastore path; the zot blob store is placed under <datastore>/zot. */
  datastorePath?: string;
}

export interface RegistryWireOptions {
  /** zot cache endpoint (host:port) to route pulls through. */
  endpoint?: string;
}

export class RegistryMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  /** Bring the zot pull-through cache online (kube_registry_up). */
  async kubeRegistryUp(opts: RegistryUpOptions = {}): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_registry_up',
      upstreams: opts.upstreams,
      scope: opts.scope,
      datastorePath: opts.datastorePath,
    });
  }

  /** Wire containerd + k3s to pull through the zot cache (kube_registry_wire). */
  async kubeRegistryWire(opts: RegistryWireOptions = {}): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_registry_wire',
      endpoint: opts.endpoint,
    });
  }
}
