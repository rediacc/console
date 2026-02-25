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

vi.mock('../../services/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ apiUrl: 'https://api.example.com', token: 'tok' }),
    getLanguage: vi.fn().mockResolvedValue('en'),
    getUserEmail: vi.fn().mockResolvedValue(null),
    getTeam: vi.fn().mockResolvedValue(null),
    setRuntimeConfig: vi.fn(),
    applyDefaults: vi.fn((opts: unknown) => opts),
    getCurrentName: vi.fn().mockReturnValue('default'),
    listMachines: vi.fn().mockResolvedValue([]),
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
    isCloud: true,
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

// Enable experimental mode so cloud-only commands are visible in help
process.env.REDIACC_EXPERIMENTAL = '1';

// Import cli after all mocks are set up
const { cli } = await import('../../cli.js');

// Get formatted help output for testing tag column rendering
const rootHelp = cli.helpInformation();

describe('Command mode guards and tags', () => {
  const cloudOnlyCommands = [
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
    'queue',
  ];

  const localOnlyCommands = ['repo', 'snapshot'];

  const allModeCommands = [
    'machine',
    'storage',
    'config',
    'doctor',
    'sync',
    'run',
    'term',
    'update',
  ];

  describe('[cloud] tag column in help', () => {
    for (const cmdName of cloudOnlyCommands) {
      it(`"${cmdName}" should show [cloud] tag in help output`, () => {
        // Match the line containing this command and verify [cloud] appears
        const pattern = new RegExp(`^\\s+${cmdName}\\b.*\\[cloud\\]`, 'm');
        expect(rootHelp).toMatch(pattern);
      });
    }
  });

  describe('[local] tag column in help', () => {
    for (const cmdName of localOnlyCommands) {
      it(`"${cmdName}" should show [local] tag in help output`, () => {
        const pattern = new RegExp(`^\\s+${cmdName}\\b.*\\[local\\]`, 'm');
        expect(rootHelp).toMatch(pattern);
      });
    }
  });

  describe('all-mode commands have no mode tag in help', () => {
    for (const cmdName of allModeCommands) {
      it(`"${cmdName}" should not show a mode tag in help output`, () => {
        // All-mode commands should NOT have [cloud] or [local] tags
        const cloudTag = new RegExp(`^\\s+${cmdName}\\b.*\\[cloud\\]`, 'm');
        const localTag = new RegExp(`^\\s+${cmdName}\\b.*\\[local\\]`, 'm');
        expect(rootHelp).not.toMatch(cloudTag);
        expect(rootHelp).not.toMatch(localTag);
      });
    }
  });

  describe('descriptions are unmodified', () => {
    it('cloud-only commands have clean descriptions (no tags in description)', () => {
      for (const cmdName of cloudOnlyCommands) {
        const cmd = cli.commands.find((c) => c.name() === cmdName);
        if (cmd) {
          expect(cmd.description()).not.toMatch(/\[cloud\]|\[local/);
        }
      }
    });
  });

  describe('Machine subcommand tags', () => {
    it('"assign-bridge" should show [cloud] in machine help', () => {
      const machineCmd = cli.commands.find((c) => c.name() === 'machine')!;
      const machineHelp = machineCmd.helpInformation();
      expect(machineHelp).toMatch(/assign-bridge.*\[cloud\]/);
    });

    it('"test-connection" should show [cloud] in machine help', () => {
      const machineCmd = cli.commands.find((c) => c.name() === 'machine')!;
      const machineHelp = machineCmd.helpInformation();
      expect(machineHelp).toMatch(/test-connection.*\[cloud\]/);
    });
  });

  describe('Storage subcommand tags', () => {
    it('"browse" should show [local] in storage help', () => {
      const storageCmd = cli.commands.find((c) => c.name() === 'storage')!;
      const storageHelp = storageCmd.helpInformation();
      expect(storageHelp).toMatch(/browse.*\[local\]/);
    });
  });

  describe('Domain grouping', () => {
    it('cloud-only commands have domain help group set', () => {
      const authCmd = cli.commands.find((c) => c.name() === 'auth');
      expect(authCmd).toBeDefined();
      expect(authCmd!.helpGroup()).toBe('Organization');
    });

    it('infrastructure commands have correct group', () => {
      const machineCmd = cli.commands.find((c) => c.name() === 'machine');
      expect(machineCmd).toBeDefined();
      expect(machineCmd!.helpGroup()).toBe('Infrastructure');
    });

    it('tool commands have correct group', () => {
      const configCmd = cli.commands.find((c) => c.name() === 'config');
      expect(configCmd).toBeDefined();
      expect(configCmd!.helpGroup()).toBe('Tools');
    });

    it('help output contains domain headings', () => {
      expect(rootHelp).toContain('Organization');
      expect(rootHelp).toContain('Infrastructure');
      expect(rootHelp).toContain('Repositories');
      expect(rootHelp).toContain('Execution');
      expect(rootHelp).toContain('Tools');
    });
  });
});
