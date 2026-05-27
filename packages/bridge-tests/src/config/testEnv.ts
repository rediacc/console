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
    bridgeIp: '192.168.111.1',
    worker1Ip: '192.168.111.11',
    worker2Ip: '192.168.111.12',
  },
  rustfs: {
    endpoint: 'http://192.168.111.1:9000',
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
