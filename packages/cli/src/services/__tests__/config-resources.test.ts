import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock configFileStorage (required by the module graph).
let mockConfig: Record<string, unknown> = {};

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    update: vi.fn(
      (_name: string, fn: (cfg: Record<string, unknown>) => Record<string, unknown>) => {
        mockConfig = fn(mockConfig);
      }
    ),
    // #89: removeMachine now drops the OBSERVATIONS of a machine that is gone
    // (state.machines, plus any state.datastores hint still naming it), which goes
    // through updateState — the no-version-bump writer.
    updateState: vi.fn(
      (_name: string, fn: (cfg: Record<string, unknown>) => Record<string, unknown>) => {
        mockConfig = fn(mockConfig);
      }
    ),
    read: vi.fn(() => mockConfig),
    load: vi.fn(() => Promise.resolve(mockConfig)),
  },
}));

// Mock the remote/ SSH helper — spied per test.
const mockAddMachineSSHConfigEntry = vi.fn();
const mockRemoveMachineSSHConfigEntry = vi.fn();

// A Windows-home path, i.e. what getSSHConfigPath() actually resolves to under
// WSL. The sshConfigWritten message must repeat THIS, never a literal ~/.ssh/…
const SSH_CONFIG_PATH = '/mnt/c/Users/tester/.ssh/config_rediacc';

vi.mock('../../remote/vscode/index.js', () => ({
  // Returns the file it wrote, which is what the message must repeat.
  addMachineSSHConfigEntry: (...args: unknown[]) => {
    mockAddMachineSSHConfigEntry(...args);
    return SSH_CONFIG_PATH;
  },
  removeMachineSSHConfigEntry: (...args: unknown[]) => mockRemoveMachineSSHConfigEntry(...args),
}));

// Mock outputService
const mockOutputInfo = vi.fn();
const mockOutputWarn = vi.fn();

vi.mock('../core/output.js', () => ({
  outputService: {
    info: (...args: unknown[]) => mockOutputInfo(...args),
    warn: (...args: unknown[]) => mockOutputWarn(...args),
  },
}));

// Stub i18n t() to return the key so assertions are key-based. Interpolation
// params are recorded separately so a test can pin them.
const mockT = vi.fn((key: string, _opts?: unknown) => key);

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, opts?: unknown) => mockT(key, opts),
}));

// Mock the base class.
let mockMachines: Record<string, unknown> = {};

vi.mock('../config/config-base.js', () => ({
  ConfigServiceBase: class {
    getEffectiveConfigName() {
      return 'test';
    }
    requireSelfHosted() {
      return Promise.resolve({ version: 1 });
    }
    getCurrent() {
      return Promise.resolve({ version: 1 });
    }
    getResourceState() {
      return Promise.resolve({
        getMachines: () => ({ ...mockMachines }),
        setMachines: (m: Record<string, unknown>) => {
          mockMachines = m;
          return Promise.resolve();
        },
        getStorages: () => ({}),
        setStorages: vi.fn(),
        getRepositories: () => ({}),
        setRepositories: vi.fn(),
        getDeletedRepositories: () => [],
        setDeletedRepositories: vi.fn(),
      });
    }
  },
}));

vi.mock('../../types/index.js', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../types/index.js');
  return {
    ...actual,
  };
});

describe('configService.addMachine — SSH config side effect', { timeout: 30000 }, () => {
  beforeEach(() => {
    mockConfig = {};
    mockMachines = {};
    mockAddMachineSSHConfigEntry.mockReset();
    mockRemoveMachineSSHConfigEntry.mockReset();
    mockOutputInfo.mockReset();
    mockOutputWarn.mockReset();
    mockT.mockClear();
  });

  it('addMachine writes an SSH config entry', async () => {
    const { configService } = await import('../config/config-resources.js');
    await configService.addMachine('m1', { ip: '1.2.3.4', user: 'u1', port: 22 });
    expect(mockAddMachineSSHConfigEntry).toHaveBeenCalledOnce();
    expect(mockAddMachineSSHConfigEntry).toHaveBeenCalledWith(
      expect.objectContaining({
        machineName: 'm1',
        host: '1.2.3.4',
        sshUser: 'u1',
        port: 22,
      })
    );
    expect(mockOutputInfo).toHaveBeenCalledWith('commands.config.machine.add.sshConfigWritten');
  });

  it('reports the SSH config path it actually wrote, not a hardcoded ~/.ssh', async () => {
    const { configService } = await import('../config/config-resources.js');
    await configService.addMachine('m1', { ip: '1.2.3.4', user: 'u1', port: 22 });

    expect(mockT).toHaveBeenCalledWith('commands.config.machine.add.sshConfigWritten', {
      name: 'm1',
      path: SSH_CONFIG_PATH,
    });
  });

  it('addMachine does not throw if SSH config write fails', async () => {
    mockAddMachineSSHConfigEntry.mockImplementationOnce(() => {
      throw new Error('disk full');
    });
    const { configService } = await import('../config/config-resources.js');
    await expect(
      configService.addMachine('m2', { ip: '5.6.7.8', user: 'u2', port: 22 })
    ).resolves.toBeUndefined();
    expect(mockOutputWarn).toHaveBeenCalledWith('commands.config.machine.add.sshConfigFailed');
  });

  it('removeMachine removes the SSH entry', async () => {
    mockMachines = { m3: { ip: '9.9.9.9', user: 'u3', port: 22 } };
    const { configService } = await import('../config/config-resources.js');
    await configService.removeMachine('m3');
    expect(mockRemoveMachineSSHConfigEntry).toHaveBeenCalledOnce();
    expect(mockRemoveMachineSSHConfigEntry).toHaveBeenCalledWith('m3');
    expect(mockOutputInfo).toHaveBeenCalledWith('commands.config.machine.remove.sshConfigCleared');
  });
});
