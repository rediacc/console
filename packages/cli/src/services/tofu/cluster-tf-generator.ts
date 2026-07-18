/**
 * OpenTofu .tf.json generator for multi-machine clusters.
 *
 * Sibling of tf-generator.ts (single machine). Emits N instances across pools
 * plus a private network so Ceph/k8s pools can talk on a private LAN. The
 * generated config is provider-agnostic: all provider differences come from the
 * resolved ProviderMapping (including its `network` block).
 *
 * Scope note: this renders the network TOPOLOGY (instances, network, subnet,
 * NIC attach, per-member outputs) at the abstraction level the campaign needs
 * for golden tests and KVM-first development. Exact provider attribute names
 * for the private NIC are refined against a live provider in the Linode
 * validation wave; MTU is surfaced as an output so the in-guest renet bootstrap
 * can stamp it on the private NIC (the value that silently wrecks Ceph
 * replication when wrong).
 */

import type { ProviderMapping } from '../../types/index.js';

interface ClusterTfPool {
  name: string;
  role: string;
  count: number;
  size?: string;
  disks?: { purpose: string; size: string; count?: number }[];
}

export interface ClusterTfOptions {
  clusterName: string;
  /** Resolved cloud mapping; must include a `network` block for private LAN. */
  mapping: ProviderMapping;
  apiToken: string;
  sshPublicKey: string;
  /** Cluster network config; overrides mapping.network defaults when set. */
  network?: { primitive: string; cidr?: string; mtu?: number };
  pools: ClusterTfPool[];
}

/** Materialized machine name for a pool member (1-indexed): `<cluster>-<pool>-<n>`. */
export function clusterMemberName(clusterName: string, poolName: string, n: number): string {
  return `${clusterName}-${poolName}-${n}`;
}

const DEFAULT_CIDR = '10.0.0.0/24';

interface Member {
  name: string;
  pool: ClusterTfPool;
  index: number; // 1-based within pool
  hostIndex: number; // 1-based across the whole cluster (for private IP assignment)
}

function enumerateMembers(options: ClusterTfOptions): Member[] {
  const members: Member[] = [];
  let hostIndex = 0;
  for (const pool of options.pools) {
    for (let i = 1; i <= pool.count; i++) {
      hostIndex++;
      members.push({
        name: clusterMemberName(options.clusterName, pool.name, i),
        pool,
        index: i,
        hostIndex,
      });
    }
  }
  return members;
}

/** Derive a private IP for a member from the cidr's network prefix + host index. */
function privateIpFor(cidr: string, hostIndex: number): string {
  const [network] = cidr.split('/');
  const octets = network.split('.');
  // Assign .N in the last octet starting at .10 to stay clear of gateways.
  octets[3] = String(10 + hostIndex);
  return octets.join('.');
}

// SSH key injection — inline on each instance for inline_list providers, or one
// shared key resource for the whole cluster for resource_id providers.
function injectSshKey(
  attrs: Record<string, unknown>,
  member: Member,
  mapping: ProviderMapping,
  sshPublicKey: string,
  resources: Record<string, Record<string, unknown>>
): void {
  if (mapping.sshKey.format === 'inline_list') {
    attrs[mapping.sshKey.attr] = [sshPublicKey];
    return;
  }
  if (mapping.sshKey.keyResource) {
    resources[mapping.sshKey.keyResource] ??= {};
    resources[mapping.sshKey.keyResource].cluster = {
      name: `${member.name.split('-').slice(0, -2).join('-')}-key`,
      public_key: sshPublicKey,
    };
    attrs[mapping.sshKey.attr] = [`\${${mapping.sshKey.keyResource}.cluster.id}`];
  }
}

function buildInstanceAttrs(
  member: Member,
  mapping: ProviderMapping,
  sshPublicKey: string,
  cidr: string,
  resources: Record<string, Record<string, unknown>>
): Record<string, unknown> {
  const attrs: Record<string, unknown> = {};
  attrs[mapping.labelAttr] = member.name;

  if (mapping.defaults) {
    Object.assign(attrs, mapping.defaults);
  }
  if (member.pool.size) attrs[mapping.sizeAttr] = member.pool.size;

  injectSshKey(attrs, member, mapping, sshPublicKey, resources);

  // L2 inline interface (e.g. Linode VLAN): the private LAN is defined by the
  // interface label; no separate network resource exists. Linode config-profile
  // interfaces are POSITIONAL — the first entry is eth0 — so a public interface
  // must lead to keep the node reachable over SSH for bootstrap, and the VLAN
  // follows as eth1. Neither `device` nor `mtu` is a valid config-interface
  // argument (verified against linode provider v3): NIC ordering is positional,
  // and MTU is stamped in-guest by the renet bootstrap from the network_mtu
  // output (Linode VLANs cap at MTU 1500, the provider default).
  const net = mapping.network;
  if (net?.attachVia === 'interface') {
    attrs.interface = [
      { purpose: 'public' },
      {
        purpose: 'vlan',
        label: `${member.name.split('-')[0]}-lan`,
        ipam_address: `${privateIpFor(cidr, member.hostIndex)}/${cidr.split('/')[1]}`,
      },
    ];
  }

  return attrs;
}

/** Emit the L3 private network, subnet, and per-member NIC attach resources. */
function buildL3Network(
  net: NonNullable<ProviderMapping['network']>,
  mapping: ProviderMapping,
  members: Member[],
  clusterName: string,
  cidr: string,
  resources: Record<string, Record<string, unknown>>
): void {
  resources[net.resource] = { cluster: { name: `${clusterName}-net`, ip_range: cidr } };
  if (net.subnetResource) {
    resources[net.subnetResource] = {
      cluster: {
        network_id: `\${${net.resource}.cluster.id}`,
        type: 'cloud',
        network_zone: 'eu-central',
        ip_range: cidr,
      },
    };
  }
  if (net.attachResource) {
    const attachMap: Record<string, unknown> = {};
    for (const member of members) {
      attachMap[member.name] = {
        server_id: `\${${mapping.resource}.${member.name}.id}`,
        network_id: `\${${net.resource}.cluster.id}`,
        ip: privateIpFor(cidr, member.hostIndex),
      };
    }
    resources[net.attachResource] = attachMap;
  }
}

/** Per-member public-IP outputs plus network metadata the in-guest bootstrap reads. */
function buildOutputs(
  members: Member[],
  mapping: ProviderMapping,
  cidr: string,
  mtu: number | undefined
): Record<string, { value: unknown }> {
  const outputs: Record<string, { value: unknown }> = {};
  for (const member of members) {
    outputs[`ipv4_${member.pool.name}_${member.index}`] = {
      value: `\${${mapping.resource}.${member.name}.${mapping.ipv4Output}}`,
    };
    if (mapping.ipv6Output) {
      outputs[`ipv6_${member.pool.name}_${member.index}`] = {
        value: `\${${mapping.resource}.${member.name}.${mapping.ipv6Output}}`,
      };
    }
  }
  outputs.network_cidr = { value: cidr };
  if (mtu !== undefined) outputs.network_mtu = { value: mtu };
  return outputs;
}

/** GB integer from a size string like "40", "40G", "40GB". */
function parseVolumeSizeGb(size: string): number {
  const n = Number.parseInt(String(size).replaceAll(/[^0-9]/g, ''), 10);
  if (!Number.isFinite(n) || n <= 0) {
    throw new Error(`Invalid disk size "${size}" (expected e.g. "40" or "40G")`);
  }
  return n;
}

/**
 * Emit one block-storage volume per member per pool disk (e.g. Linode Block
 * Storage for Ceph OSDs, since a vanilla instance has only its boot disk) and
 * attach it to the member instance. The in-guest device path is NOT chosen
 * here — it is the pool's disks[].purpose (uniform across the pool, consumed by
 * the Ceph install). Each volume's filesystem_path (the by-id device symlink)
 * is surfaced as an output so provisioning can verify the device before OSD
 * creation.
 */
function buildVolumes(
  members: Member[],
  mapping: ProviderMapping,
  resources: Record<string, Record<string, unknown>>,
  outputs: Record<string, { value: unknown }>
): void {
  const vol = mapping.volume;
  const withDisks = members.filter((m) => (m.pool.disks?.length ?? 0) > 0);
  if (withDisks.length === 0) return;
  if (!vol) {
    throw new Error(
      `Pool '${withDisks[0].pool.name}' declares disks but provider '${mapping.source}' has no volume block to create them.`
    );
  }
  const region = mapping.defaults?.[mapping.regionAttr];
  const volumeMap: Record<string, unknown> = {};
  for (const member of withDisks) {
    (member.pool.disks ?? []).forEach((disk, i) => {
      const name = `${member.name}-osd${i + 1}`;
      const attrs: Record<string, unknown> = {
        [vol.labelAttr]: name,
        [vol.sizeAttr]: parseVolumeSizeGb(disk.size),
        [vol.attachAttr]: `\${${mapping.resource}.${member.name}.id}`,
      };
      if (vol.needsRegion && region) attrs[mapping.regionAttr] = region;
      volumeMap[name] = attrs;
      outputs[`osd_device_${member.pool.name}_${member.index}_${i + 1}`] = {
        value: `\${${vol.resource}.${name}.filesystem_path}`,
      };
    });
  }
  resources[vol.resource] = volumeMap;
}

/**
 * Generate a complete cluster .tf.json object.
 */
export function generateClusterTfJson(options: ClusterTfOptions): Record<string, unknown> {
  const { clusterName, mapping, apiToken, sshPublicKey } = options;
  const members = enumerateMembers(options);

  const net = mapping.network;
  if (net?.maxNodes && members.length > net.maxNodes) {
    throw new Error(
      `Cluster '${clusterName}' has ${members.length} members but provider '${mapping.source}' allows at most ${net.maxNodes} nodes per network segment.`
    );
  }

  const cidr = options.network?.cidr ?? DEFAULT_CIDR;
  const mtu = options.network?.mtu ?? net?.mtu;

  const providerName = mapping.source.split('/').pop()!;
  const providerNs = mapping.source.includes('/') ? mapping.source.split('/')[0] : providerName;

  const resources: Record<string, Record<string, unknown>> = {};

  // Instances (one per member), all under the single resource type.
  const instanceMap: Record<string, unknown> = {};
  for (const member of members) {
    instanceMap[member.name] = buildInstanceAttrs(member, mapping, sshPublicKey, cidr, resources);
  }
  resources[mapping.resource] = instanceMap;

  // L3 private network + subnet + per-member NIC attachment (e.g. Hetzner).
  if (net?.attachVia === 'attach_resource') {
    buildL3Network(net, mapping, members, clusterName, cidr, resources);
  }

  const outputs = buildOutputs(members, mapping, cidr, mtu);
  buildVolumes(members, mapping, resources, outputs);

  return {
    terraform: {
      required_providers: {
        [providerName]: {
          source: `${providerNs}/${providerName}`,
          ...(mapping.version ? { version: mapping.version } : {}),
        },
      },
    },
    provider: { [providerName]: { [mapping.tokenAttr]: apiToken } },
    resource: resources,
    output: outputs,
  };
}
