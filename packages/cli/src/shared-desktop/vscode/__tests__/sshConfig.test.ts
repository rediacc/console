import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// getSSHHome is called at module load time via getSSHConfigPath, so we must
// mock the platform module before importing sshConfig.
const mockGetSSHHome = vi.fn<[], string>();

vi.mock('../../utils/platform.js', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../utils/platform.js');
  return { ...actual, getSSHHome: () => mockGetSSHHome() };
});

// Now import the functions under test AFTER mock is registered.
const { addMachineSSHConfigEntry, addSSHConfigEntry, removeMachineSSHConfigEntry } = await import(
  '../sshConfig.js'
);

let tmpHome: string;

beforeEach(() => {
  tmpHome = join(tmpdir(), `sshconfig-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  mkdirSync(tmpHome, { recursive: true });
  mockGetSSHHome.mockReturnValue(tmpHome);
});

afterEach(() => {
  vi.clearAllMocks();
});

function readConfigFile(): string {
  const configPath = join(tmpHome, '.ssh', 'config_rediacc');
  if (!existsSync(configPath)) return '';
  return readFileSync(configPath, 'utf8');
}

describe('addMachineSSHConfigEntry', () => {
  it('writes Host rediacc--<name> block with SetEnv REDIACC_MACHINE', () => {
    addMachineSSHConfigEntry({ machineName: 'm1', host: '1.2.3.4', port: 22, sshUser: 'u1' });
    const content = readConfigFile();
    expect(content).toContain('Host rediacc--m1');
    expect(content).toContain('HostName 1.2.3.4');
    expect(content).toContain('SetEnv REDIACC_MACHINE=m1');
  });

  it('omits IdentityFile and UserKnownHostsFile when not provided', () => {
    addMachineSSHConfigEntry({ machineName: 'm1', host: '1.2.3.4', port: 22, sshUser: 'u1' });
    const content = readConfigFile();
    expect(content).not.toMatch(/IdentityFile\s/);
    expect(content).not.toMatch(/UserKnownHostsFile\s/);
  });

  it('includes REDIACC_TEAM and REDIACC_DATASTORE when provided', () => {
    addMachineSSHConfigEntry({
      machineName: 'm2',
      host: '10.0.0.1',
      port: 2222,
      sshUser: 'deploy',
      teamName: 'myteam',
      datastore: '/mnt/data',
    });
    const content = readConfigFile();
    expect(content).toContain('SetEnv REDIACC_TEAM=myteam');
    expect(content).toContain('SetEnv REDIACC_DATASTORE=/mnt/data');
  });

  it('upserts on second call with different IP', () => {
    addMachineSSHConfigEntry({ machineName: 'm1', host: '1.2.3.4', port: 22, sshUser: 'u1' });
    addMachineSSHConfigEntry({ machineName: 'm1', host: '5.6.7.8', port: 22, sshUser: 'u1' });
    const content = readConfigFile();
    const hostMatches = [...content.matchAll(/^Host rediacc--m1$/gm)];
    expect(hostMatches).toHaveLength(1);
    expect(content).toContain('HostName 5.6.7.8');
    expect(content).not.toContain('HostName 1.2.3.4');
  });

  it('removes the block', () => {
    addMachineSSHConfigEntry({ machineName: 'm1', host: '1.2.3.4', port: 22, sshUser: 'u1' });
    removeMachineSSHConfigEntry('m1');
    const content = readConfigFile();
    expect(content).not.toContain('Host rediacc--m1');
  });

  it('preserves an existing rediacc-team-<machine> vscode block', () => {
    // Pre-write a vscode-style block (with identity files) using addSSHConfigEntry directly
    addSSHConfigEntry({
      host: 'rediacc-myteam-m1',
      hostname: '9.9.9.9',
      user: 'vscode',
      port: 22,
      identityFile: '/home/user/.ssh/id_ed25519',
      userKnownHostsFile: '/home/user/.ssh/known_hosts_m1',
    });
    // Now write machine-only block
    addMachineSSHConfigEntry({ machineName: 'm1', host: '1.2.3.4', port: 22, sshUser: 'u1' });
    const content = readConfigFile();
    expect(content).toContain('Host rediacc-myteam-m1');
    expect(content).toContain('Host rediacc--m1');
  });
});
