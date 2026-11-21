/**
 * Cluster section of the v3 config schema: a named set of node pools, split from schemas.ts to keep it under the line budget.
 */

import { z } from 'zod';
import { resourceName } from './primitives.js';

// =============================================================================
// Cluster (a named set of node pools; members materialize into resources.machines)
// =============================================================================

const ClusterPoolDiskSchema = z.object({
  purpose: z.string().min(1),
  size: z.string().min(1),
  count: z.number().int().min(1).optional(),
});

export const ClusterPoolSchema = z.object({
  name: resourceName,
  role: z.enum(['ceph', 'k8s-server', 'k8s-agent', 'hyperconverged']),
  count: z.number().int().min(1),
  size: z.string().optional(),
  disks: z.array(ClusterPoolDiskSchema).optional(),
  labels: z.record(z.string(), z.string()).optional(),
});

const ClusterNetworkSchema = z.object({
  primitive: z.string().min(1),
  cidr: z.string().optional(),
  mtu: z.number().int().optional(),
});

const ClusterKubernetesSchema = z.object({
  distro: z.enum(['k3s', 'external']).optional(),
  version: z.string().optional(),
});

const ClusterRegistrySchema = z.object({
  enabled: z.boolean().optional(),
  upstreams: z.array(z.string()).optional(),
});

const ClusterCephRefSchema = z.object({
  pool: z.string().optional(),
});

// Local KVM topology. `renet ops` addresses VMs by numeric id; `memberIds` (the booted-VM allocation ledger) has moved to `state.clusters[*].memberIds` (R2-F2) so per-boot allocation churn no longer bumps the version counter.
export const ClusterKvmSchema = z.object({
  netName: z.string().min(1),
  netBase: z.string().min(1),
  netOffset: z.number().int().min(0).optional(),
  controlId: z.number().int().min(1),
  dockerRegistry: z.string().optional(),
});

export const ClusterConfigSchema = z.object({
  provider: z.string().min(1),
  network: ClusterNetworkSchema.optional(),
  pools: z.array(ClusterPoolSchema).min(1, 'A cluster needs at least one pool'),
  kubernetes: ClusterKubernetesSchema.optional(),
  registry: ClusterRegistrySchema.optional(),
  ceph: ClusterCephRefSchema.optional(),
  controlNode: resourceName.optional(),
  kvm: ClusterKvmSchema.optional(),
});
