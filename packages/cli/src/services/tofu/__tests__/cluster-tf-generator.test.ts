import { describe, expect, it } from 'vitest';
import type { ProviderMapping } from '../../../types/index.js';
import {
  type ClusterTfOptions,
  clusterMemberName,
  generateClusterTfJson,
} from '../cluster-tf-generator.js';

// Fake resolved mappings — the generator is provider-agnostic, so a fabricated
// mapping fully exercises it without depending on the registry.

const linodeMapping: ProviderMapping = {
  source: 'linode/linode',
  version: '~> 3.0',
  tokenAttr: 'token',
  resource: 'linode_instance',
  labelAttr: 'label',
  regionAttr: 'region',
  sizeAttr: 'type',
  imageAttr: 'image',
  ipv4Output: 'ip_address',
  ipv6Output: 'ipv6',
  sshKey: { attr: 'authorized_keys', format: 'inline_list' },
  defaults: { image: 'linode/ubuntu24.04', region: 'de-fra-2', type: 'g6-standard-4' },
  network: {
    resource: 'linode_instance',
    layer: 'l2',
    attachVia: 'interface',
    nicName: 'eth1',
    mtu: 1500,
  },
  disk: 'local-nvme',
  volume: {
    resource: 'linode_volume',
    sizeAttr: 'size',
    attachAttr: 'linode_id',
    labelAttr: 'label',
    needsRegion: true,
  },
};

const hetznerMapping: ProviderMapping = {
  source: 'hetznercloud/hcloud',
  version: '~> 1.49',
  tokenAttr: 'token',
  resource: 'hcloud_server',
  labelAttr: 'name',
  regionAttr: 'location',
  sizeAttr: 'server_type',
  imageAttr: 'image',
  ipv4Output: 'ipv4_address',
  ipv6Output: 'ipv6_address',
  sshKey: { attr: 'ssh_keys', format: 'resource_id', keyResource: 'hcloud_ssh_key' },
  defaults: { image: 'ubuntu-24.04', location: 'fsn1', server_type: 'cx32' },
  network: {
    resource: 'hcloud_network',
    layer: 'l3',
    subnetResource: 'hcloud_network_subnet',
    attachVia: 'attach_resource',
    attachResource: 'hcloud_server_network',
    nicName: 'enp7s0',
    mtu: 1450,
    maxNodes: 100,
  },
  disk: 'local-nvme',
};

const twoPoolSpec: Pick<ClusterTfOptions, 'clusterName' | 'apiToken' | 'sshPublicKey' | 'pools'> = {
  clusterName: 'prod',
  apiToken: 'TOKEN',
  sshPublicKey: 'ssh-ed25519 AAAA test',
  pools: [
    { name: 'ceph', role: 'ceph', count: 3, size: 'g6-dedicated-8' },
    { name: 'k8s', role: 'k8s-server', count: 2 },
  ],
};

describe('generateClusterTfJson', () => {
  it('materializes one instance per member as <cluster>-<pool>-<n>', () => {
    const tf = generateClusterTfJson({ ...twoPoolSpec, mapping: linodeMapping });
    const instances = (tf.resource as Record<string, Record<string, unknown>>).linode_instance;
    expect(Object.keys(instances).sort()).toEqual([
      'prod-ceph-1',
      'prod-ceph-2',
      'prod-ceph-3',
      'prod-k8s-1',
      'prod-k8s-2',
    ]);
    expect(clusterMemberName('prod', 'ceph', 1)).toBe('prod-ceph-1');
  });

  it('applies per-pool size override and shared inline ssh key (linode)', () => {
    const tf = generateClusterTfJson({ ...twoPoolSpec, mapping: linodeMapping });
    const instances = (tf.resource as Record<string, Record<string, Record<string, unknown>>>)
      .linode_instance;
    expect(instances['prod-ceph-1'].type).toBe('g6-dedicated-8');
    // k8s pool has no size override -> falls back to the mapping default.
    expect(instances['prod-k8s-1'].type).toBe('g6-standard-4');
    expect(instances['prod-ceph-1'].authorized_keys).toEqual(['ssh-ed25519 AAAA test']);
  });

  it('leads with a public interface then the L2 VLAN, MTU only in outputs (linode)', () => {
    // Verified against linode provider v3: config-profile interfaces are
    // positional (public must be eth0 for SSH), and neither `device` nor `mtu`
    // is a valid config-interface argument — MTU is surfaced via the output.
    const tf = generateClusterTfJson({ ...twoPoolSpec, mapping: linodeMapping });
    const instances = (tf.resource as Record<string, Record<string, Record<string, unknown>>>)
      .linode_instance;
    const ifaces = instances['prod-ceph-1'].interface as Record<string, unknown>[];
    expect(ifaces[0]).toEqual({ purpose: 'public' });
    const vlan = ifaces[1];
    expect(vlan.purpose).toBe('vlan');
    expect(vlan.mtu).toBeUndefined();
    expect(vlan.device).toBeUndefined();
    expect(String(vlan.ipam_address)).toMatch(/\/24$/);
    expect((tf.output as Record<string, { value: unknown }>).network_mtu.value).toBe(1500);
  });

  it('emits a block-storage volume per ceph-member disk attached to the instance (linode)', () => {
    const tf = generateClusterTfJson({
      ...twoPoolSpec,
      mapping: linodeMapping,
      pools: [
        {
          name: 'ceph',
          role: 'ceph',
          count: 3,
          size: 'g6-dedicated-2',
          disks: [{ purpose: '/dev/sdc', size: '40' }],
        },
        { name: 'k8s', role: 'k8s-server', count: 2 },
      ],
    });
    const resources = tf.resource as Record<string, Record<string, Record<string, unknown>>>;
    const volumes = resources.linode_volume;
    // One volume per ceph member; k8s members (no disks) get none.
    expect(Object.keys(volumes).sort()).toEqual([
      'prod-ceph-1-osd1',
      'prod-ceph-2-osd1',
      'prod-ceph-3-osd1',
    ]);
    const v = volumes['prod-ceph-1-osd1'];
    expect(v.label).toBe('prod-ceph-1-osd1');
    expect(v.size).toBe(40);
    expect(v.region).toBe('de-fra-2');
    expect(v.linode_id).toBe('${linode_instance.prod-ceph-1.id}');
    // filesystem_path surfaced as an output for in-guest device verification.
    const outputs = tf.output as Record<string, { value: unknown }>;
    expect(outputs.osd_device_ceph_1_1.value).toBe(
      '${linode_volume.prod-ceph-1-osd1.filesystem_path}'
    );
  });

  it('throws when a pool declares disks but the provider has no volume block', () => {
    const noVol = { ...linodeMapping };
    delete (noVol as { volume?: unknown }).volume;
    expect(() =>
      generateClusterTfJson({
        ...twoPoolSpec,
        mapping: noVol,
        pools: [
          { name: 'ceph', role: 'ceph', count: 1, disks: [{ purpose: '/dev/sdc', size: '40' }] },
        ],
      })
    ).toThrow(/no volume block/);
  });

  it('emits network + subnet + per-member attach and a shared key resource (hetzner L3)', () => {
    const tf = generateClusterTfJson({ ...twoPoolSpec, mapping: hetznerMapping });
    const resources = tf.resource as Record<string, Record<string, unknown>>;
    expect(resources.hcloud_network).toBeDefined();
    expect(resources.hcloud_network_subnet).toBeDefined();
    expect(Object.keys(resources.hcloud_server_network).sort()).toEqual([
      'prod-ceph-1',
      'prod-ceph-2',
      'prod-ceph-3',
      'prod-k8s-1',
      'prod-k8s-2',
    ]);
    // resource_id ssh: exactly one shared key resource for the cluster.
    expect(resources.hcloud_ssh_key).toBeDefined();
    expect(Object.keys(resources.hcloud_ssh_key)).toEqual(['cluster']);
  });

  it('surfaces per-member ipv4/ipv6 outputs plus network metadata', () => {
    const tf = generateClusterTfJson({ ...twoPoolSpec, mapping: hetznerMapping });
    const outputs = tf.output as Record<string, { value: unknown }>;
    for (const key of [
      'ipv4_ceph_1',
      'ipv4_ceph_2',
      'ipv4_ceph_3',
      'ipv4_k8s_1',
      'ipv4_k8s_2',
      'ipv6_ceph_1',
      'network_cidr',
      'network_mtu',
    ]) {
      expect(outputs[key]).toBeDefined();
    }
    expect(outputs.network_mtu.value).toBe(1450);
    expect(outputs.network_cidr.value).toBe('10.0.0.0/24');
  });

  it('honors a custom cidr/mtu override from the cluster network config', () => {
    const tf = generateClusterTfJson({
      ...twoPoolSpec,
      mapping: hetznerMapping,
      network: { primitive: 'network', cidr: '10.42.0.0/24', mtu: 1400 },
    });
    const outputs = tf.output as Record<string, { value: unknown }>;
    expect(outputs.network_mtu.value).toBe(1400);
    expect(outputs.network_cidr.value).toBe('10.42.0.0/24');
    const subnet = (tf.resource as Record<string, Record<string, Record<string, unknown>>>)
      .hcloud_network_subnet.cluster;
    expect(subnet.ip_range).toBe('10.42.0.0/24');
  });

  it('rejects a member count above the provider maxNodes', () => {
    expect(() =>
      generateClusterTfJson({
        ...twoPoolSpec,
        mapping: hetznerMapping,
        pools: [{ name: 'big', role: 'k8s-agent', count: 101 }],
      })
    ).toThrow(/at most 100 nodes/);
  });

  it('renders a stable golden object (linode two-pool)', () => {
    const tf = generateClusterTfJson({ ...twoPoolSpec, mapping: linodeMapping });
    expect(tf).toMatchSnapshot();
  });
});
