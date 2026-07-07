// The bridge/worker IPs and the RustFS endpoint are derived from the VM group's
// network env (VM_NET_BASE / VM_NET_OFFSET / VM_BRIDGE / VM_WORKERS) so a second
// concurrent KVM group (e.g. VM_NET_BASE=192.168.112) resolves its own topology
// instead of the hardcoded 192.168.111.x. Fallbacks equal the historical
// single-group constants, so a normal run (whose .env already sets these to the
// group-A values) is unaffected. Read once at import; playwright loads the group
// .env before test modules import, so process.env is already populated.
const NET_BASE = process.env.VM_NET_BASE ?? '192.168.111';
const NET_OFFSET = Number.parseInt(process.env.VM_NET_OFFSET ?? '0', 10) || 0;
// VM_CONTROL is the canonical control-node env var; VM_BRIDGE stays as a kept
// alias (renet reads both, VM_CONTROL winning).
const BRIDGE_ID = Number.parseInt(process.env.VM_CONTROL ?? process.env.VM_BRIDGE ?? '1', 10) || 1;
const WORKER_IDS = (process.env.VM_WORKERS ?? '11 12')
  .split(/\s+/)
  .map((id) => Number.parseInt(id, 10))
  .filter((id) => !Number.isNaN(id));

const vmIp = (id: number): string => `${NET_BASE}.${NET_OFFSET + id}`;
const BRIDGE_IP = vmIp(BRIDGE_ID);
const WORKER_1_IP = vmIp(WORKER_IDS[0] ?? 11);
const WORKER_2_IP = vmIp(WORKER_IDS[1] ?? 12);

export const TEST_ENV = {
  datastorePath: '/mnt/rediacc',
  uid: '7111',
  network: {
    defaultId: '9152',
    forkA: '9216',
    forkB: '9280',
    defaultCephPgNum: '32',
  },
  vm: {
    bridgeIp: BRIDGE_IP,
    worker1Ip: WORKER_1_IP,
    worker2Ip: WORKER_2_IP,
  },
  rustfs: {
    endpoint: `http://${BRIDGE_IP}:9000`,
    // Must match renet's RustFS defaults (pkg/infra/config/config.go): non-default
    // creds are required since rustfs (CVE-2025-68926) rejects "rustfsadmin" on
    // the bridge's non-loopback 0.0.0.0:9000 listener.
    accessKey: 'rediacc-rustfs',
    secretKey: 'rediacc-rustfs-secret-key',
    bucket: 'rediacc-test',
  },
  testRepositoryPrefix: 'test-repo',
  testRepositoryName: 'test-repo',
  testContainerPrefix: 'test-container',
  testPassword: 'test-password-123',
  testUser: 'muhammed',
  testTeam: 'Test Team',
  /** Installation path for renet on VMs (NOT the local build path) */
  vmRenetInstallPath: '/usr/bin/renet',
} as const;
