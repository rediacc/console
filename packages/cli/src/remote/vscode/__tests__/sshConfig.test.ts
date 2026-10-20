import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// getSSHHome is called at module load time via getSSHConfigPath, so we must mock the platform module before importing sshConfig.
const mockGetSSHHome = vi.fn<() => string>();
const mockIsWSL = vi.fn<() => boolean>(() => false);
const mockWslToWindows = vi.fn<(p: string) => string>((p) => p);

vi.mock('../../utils/platform.js', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../utils/platform.js');
  return {
    ...actual,
    getSSHHome: () => mockGetSSHHome(),
    isWSL: () => mockIsWSL(),
    wslPathToWindows: (p: string) => mockWslToWindows(p),
  };
});

// Now import the functions under test AFTER mock is registered.
const {
  addMachineSSHConfigEntry,
  addSSHConfigEntry,
  removeMachineSSHConfigEntry,
  removeSSHConfigEntry,
} = await import('../sshConfig.js');

let tmpHome: string;

beforeEach(() => {
  tmpHome = join(tmpdir(), `sshconfig-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  mkdirSync(tmpHome, { recursive: true });
  mockGetSSHHome.mockReturnValue(tmpHome);
});

afterEach(() => {
  vi.clearAllMocks();
  mockIsWSL.mockReturnValue(false);
  mockWslToWindows.mockImplementation((p) => p);
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

  it('includes REDIACC_TEAM and REDIACC_DATASTORE_PATH when provided', () => {
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
    expect(content).toContain('SetEnv REDIACC_DATASTORE_PATH=/mnt/data');
    expect(content).not.toMatch(/SetEnv REDIACC_DATASTORE=/);
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

  it('returns the file it wrote, resolved through getSSHHome', () => {
    // Under WSL getSSHHome() is the WINDOWS home, not $HOME, so callers must report this return value rather than assuming ~/.ssh/config_rediacc.
    const winHome = join(tmpdir(), `sshconfig-winhome-${Math.random().toString(36).slice(2)}`);
    mkdirSync(winHome, { recursive: true });
    mockGetSSHHome.mockReturnValue(winHome);

    const written = addMachineSSHConfigEntry({
      machineName: 'm1',
      host: '1.2.3.4',
      port: 22,
      sshUser: 'u1',
    });

    expect(written).toBe(join(winHome, '.ssh', 'config_rediacc'));
    expect(existsSync(written)).toBe(true);
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

describe('removeSSHConfigEntry key cleanup', () => {
  const keysDir = () => join(tmpHome, '.ssh', 'rediacc_keys');
  function writeKey(name: string, content = 'KEY'): string {
    mkdirSync(keysDir(), { recursive: true });
    const p = join(keysDir(), name);
    writeFileSync(p, content);
    return p;
  }
  function addHost(host: string, identityFile: string, known?: string): void {
    addSSHConfigEntry({
      host,
      hostname: '1.2.3.4',
      user: 'u',
      port: 22,
      identityFile,
      userKnownHostsFile: known ?? '',
    });
  }

  it('removes the per-repo key the removed block names', () => {
    const key = writeKey('_ops-worker_vmcheck-base_vc0a');
    addHost('rediacc--ops-worker-vc0a', key);
    removeSSHConfigEntry('rediacc--ops-worker-vc0a');
    expect(existsSync(key)).toBe(false);
    expect(readConfigFile()).not.toContain('rediacc--ops-worker-vc0a');
  });

  it('keeps a key another remaining block still uses', () => {
    const key = writeKey('shared_key');
    addHost('rediacc-a', key);
    addHost('rediacc-b', key);
    removeSSHConfigEntry('rediacc-a');
    expect(existsSync(key)).toBe(true);
    removeSSHConfigEntry('rediacc-b');
    expect(existsSync(key)).toBe(false);
  });

  it('never removes the shared known_hosts file', () => {
    const key = writeKey('t_m_r');
    const hosts = writeKey('t_m_known_hosts');
    addHost('rediacc-t-m-r', key, hosts);
    removeSSHConfigEntry('rediacc-t-m-r');
    expect(existsSync(key)).toBe(false);
    expect(existsSync(hosts)).toBe(true);
  });

  it('never removes a file outside rediacc_keys', () => {
    const outside = join(tmpHome, 'id_ed25519');
    writeFileSync(outside, 'USERKEY');
    addHost('rediacc-x', outside);
    removeSSHConfigEntry('rediacc-x');
    expect(existsSync(outside)).toBe(true);
  });

  it('never removes a same-named file from a lookalike directory', () => {
    const other = join(tmpHome, 'elsewhere', 'rediacc_keys');
    mkdirSync(other, { recursive: true });
    const file = join(other, 'k');
    writeFileSync(file, 'X');
    addHost('rediacc-y', file);
    removeSSHConfigEntry('rediacc-y');
    expect(existsSync(file)).toBe(true);
  });

  it('never removes the rediacc_keys directory or its parent via a dot basename', () => {
    const key = writeKey('k');
    for (const dot of ['.', '..']) {
      addHost(`rediacc-dot${dot.length}`, `${keysDir()}/${dot}`);
      removeSSHConfigEntry(`rediacc-dot${dot.length}`);
    }
    expect(existsSync(key)).toBe(true);
    expect(existsSync(keysDir())).toBe(true);
  });

  it('removes the key when the config names it in the WSL Windows-path form', () => {
    const key = writeKey('t_m_r');
    mockIsWSL.mockReturnValue(true);
    mockWslToWindows.mockImplementation((p) => p.replace(tmpHome, 'C:\\Users\\dev'));
    addHost('rediacc-wsl', 'C:/Users/dev/.ssh/rediacc_keys/t_m_r');
    removeSSHConfigEntry('rediacc-wsl');
    expect(existsSync(key)).toBe(false);
  });

  it('keeps a key whose Windows-path form lives in another directory under WSL', () => {
    const key = writeKey('t_m_r');
    mockIsWSL.mockReturnValue(true);
    mockWslToWindows.mockImplementation((p) => p.replace(tmpHome, 'C:\\Users\\dev'));
    addHost('rediacc-wsl2', 'C:/Users/other/.ssh/rediacc_keys/t_m_r');
    removeSSHConfigEntry('rediacc-wsl2');
    expect(existsSync(key)).toBe(true);
  });
});
