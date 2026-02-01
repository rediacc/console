import { describe, expect, it, vi } from 'vitest';

// Mock heavy service dependencies to prevent side effects when importing cli.ts
vi.mock('../../services/telemetry.js', () => ({
  telemetryService: {
    initialize: vi.fn(),
    startCommand: vi.fn(),
    endCommand: vi.fn(),
    trackMetric: vi.fn(),
    setUserContext: vi.fn(),
    shutdown: vi.fn(),
  },
}));

vi.mock('../../services/context.js', () => ({
  contextService: {
    getCurrent: vi.fn().mockResolvedValue({ mode: 'cloud' }),
    getLanguage: vi.fn().mockResolvedValue('en'),
    getUserEmail: vi.fn().mockResolvedValue(null),
    getTeam: vi.fn().mockResolvedValue(null),
    setRuntimeContext: vi.fn(),
    applyDefaults: vi.fn((opts: unknown) => opts),
    getCurrentName: vi.fn().mockReturnValue('default'),
    listLocalMachines: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('../../services/output.js', () => ({
  outputService: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    print: vi.fn(),
  },
}));

vi.mock('../../services/auth.js', () => ({
  authService: {
    requireAuth: vi.fn().mockResolvedValue(undefined),
    isAuthenticated: vi.fn().mockResolvedValue(true),
    requireMasterPassword: vi.fn().mockResolvedValue('test'),
  },
}));

vi.mock('../../services/api.js', () => ({
  typedApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({}) }),
}));

vi.mock('../../providers/index.js', () => ({
  getStateProvider: vi.fn().mockResolvedValue({
    mode: 'cloud',
    machines: {
      list: vi.fn().mockResolvedValue([]),
      create: vi.fn(),
      rename: vi.fn(),
      delete: vi.fn(),
      getVault: vi.fn().mockResolvedValue([]),
      updateVault: vi.fn(),
      getWithVaultStatus: vi.fn().mockResolvedValue(null),
    },
    queue: { list: vi.fn().mockResolvedValue([]) },
    storage: { list: vi.fn().mockResolvedValue([]) },
    repositories: { list: vi.fn().mockResolvedValue([]) },
    vaults: { getConnectionVaults: vi.fn().mockResolvedValue({}) },
  }),
}));

vi.mock('../../services/queue.js', () => ({
  queueService: { buildQueueVault: vi.fn() },
}));

// Import cli after all mocks are set up
const { cli } = await import('../../cli.js');

describe('Cloud-only command guards', () => {
  const expectedCloudOnlyCommands = [
    'auth',
    'bridge',
    'team',
    'region',
    'organization',
    'user',
    'permission',
    'audit',
    'ceph',
    'repository',
  ];

  describe('CLOUD_ONLY_COMMANDS set', () => {
    for (const cmdName of expectedCloudOnlyCommands) {
      it(`should include "${cmdName}" as a registered command`, () => {
        const cmd = cli.commands.find((c) => c.name() === cmdName);
        expect(cmd).toBeDefined();
      });
    }
  });

  describe('[cloud only] help annotations', () => {
    for (const cmdName of expectedCloudOnlyCommands) {
      it(`"${cmdName}" description should contain [cloud only]`, () => {
        const cmd = cli.commands.find((c) => c.name() === cmdName);
        expect(cmd).toBeDefined();
        expect(cmd!.description()).toContain('[cloud only]');
      });
    }

    it('non-cloud commands should NOT have [cloud only] in description', () => {
      const nonCloudCommands = ['context', 'doctor', 'sync', 'update'];
      for (const cmdName of nonCloudCommands) {
        const cmd = cli.commands.find((c) => c.name() === cmdName);
        if (cmd) {
          expect(cmd.description()).not.toContain('[cloud only]');
        }
      }
    });
  });

  describe('Machine subcommand guards', () => {
    it('"assign-bridge" subcommand should have [cloud only] annotation', () => {
      const machineCmd = cli.commands.find((c) => c.name() === 'machine');
      expect(machineCmd).toBeDefined();

      const assignBridgeCmd = machineCmd!.commands.find((c) => c.name() === 'assign-bridge');
      expect(assignBridgeCmd).toBeDefined();
      expect(assignBridgeCmd!.description()).toContain('[cloud only]');
    });

    it('"test-connection" subcommand should have [cloud only] annotation', () => {
      const machineCmd = cli.commands.find((c) => c.name() === 'machine');
      expect(machineCmd).toBeDefined();

      const testConnectionCmd = machineCmd!.commands.find((c) => c.name() === 'test-connection');
      expect(testConnectionCmd).toBeDefined();
      expect(testConnectionCmd!.description()).toContain('[cloud only]');
    });

    it('"machine" itself should NOT have [cloud only] (it works in all modes)', () => {
      const machineCmd = cli.commands.find((c) => c.name() === 'machine');
      expect(machineCmd).toBeDefined();
      expect(machineCmd!.description()).not.toContain('[cloud only]');
    });
  });
});
