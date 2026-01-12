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
    accessKey: 'rustfsadmin',
    secretKey: 'rustfsadmin',
    bucket: 'rediacc-test',
  },
  testRepositoryPrefix: 'test-repo',
  testRepositoryName: 'test-repo',
  testContainerPrefix: 'test-container',
  testPassword: 'test-password-123',
  testUser: 'muhammed',
  testTeam: 'Test Team',
  renetBinaryPath: '/usr/bin/renet',
} as const;

export type TestEnv = typeof TEST_ENV;
