import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '../../shared-desktop/sftp/index.js';
import { REMOTE_RENET_PATH } from '../renet-provisioner.js';
import {
  buildKeyDeploymentScript,
  deployAllRepoKeys,
  deployRepoKey,
  deployRepoKeyIfNeeded,
} from '../repo-key-deployment.js';

const { mockExec, mockRelease, mockAcquire, mockConfigService } = vi.hoisted(() => {
  const mockExec = vi.fn().mockResolvedValue('');
  const sftp = { exec: mockExec };
  const mockRelease = vi.fn();
  const mockAcquire = vi.fn().mockResolvedValue({
    sftp,
    machine: { machineName: 'm1', ip: '127.0.0.1', user: 'root', port: 22 },
    sshPrivateKey: 'dummy-key',
    ensure: vi.fn().mockResolvedValue(sftp),
    release: mockRelease,
  });
  return {
    mockExec,
    mockRelease,
    mockAcquire,
    mockConfigService: {
      getRepository: vi.fn(),
      getLocalConfig: vi.fn(),
      listRepositories: vi.fn(),
    },
  };
});

vi.mock('../machine-connection.js', () => ({
  machineConnections: { acquire: mockAcquire },
}));

vi.mock('../config-resources.js', () => ({
  configService: mockConfigService,
}));

const PUB_KEY = `ssh-ed25519 ${'A'.repeat(60)} test@rediacc`;
const KEY_PREFIX = PUB_KEY.slice(0, 50);

describe('buildKeyDeploymentScript', () => {
  it('produces the exact legacy deployment script (byte-identical snapshot)', () => {
    const script = buildKeyDeploymentScript('myrepo', PUB_KEY, 'guid-123');

    // This literal mirrors the script previously built inline in deployRepoKey
    // (pre-shared-connection). It must never drift: the remote authorized_keys
    // surgery is load-bearing for sandbox-gateway isolation.
    const expected = [
      'set -e',
      'SSH_DIR="$HOME/.ssh"',
      'AUTH_KEYS="$SSH_DIR/authorized_keys"',
      'mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"',
      `KEY_PREFIX="${KEY_PREFIX}"`,
      `if [ -f "$AUTH_KEYS" ] && grep -qF "$KEY_PREFIX" "$AUTH_KEYS"; then TEMP=$(mktemp) && grep -vF "$KEY_PREFIX" "$AUTH_KEYS" > "$TEMP" 2>/dev/null || true && mv "$TEMP" "$AUTH_KEYS"; fi`,
      `echo 'command="${REMOTE_RENET_PATH} sandbox-gateway myrepo --guid guid-123" ${PUB_KEY}' >> "$AUTH_KEYS"`,
      'chmod 600 "$AUTH_KEYS"',
    ].join('; ');

    expect(script).toBe(expected);
    expect(script).toMatchSnapshot();
  });

  it('omits the --guid flag when no repository GUID is given', () => {
    const script = buildKeyDeploymentScript('myrepo', PUB_KEY);
    expect(script).toContain(`sandbox-gateway myrepo" ${PUB_KEY}`);
    expect(script).not.toContain('--guid');
    expect(script).toMatchSnapshot();
  });
});

describe('deployRepoKey', () => {
  it('executes the deployment script over the provided session', async () => {
    const exec = vi.fn().mockResolvedValue('');
    const sftp = { exec } as unknown as SFTPClient;

    await deployRepoKey(sftp, 'myrepo', PUB_KEY, 'guid-123');

    expect(exec).toHaveBeenCalledExactlyOnceWith(
      buildKeyDeploymentScript('myrepo', PUB_KEY, 'guid-123')
    );
  });
});

describe('deployRepoKeyIfNeeded', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: { m1: { ip: '127.0.0.1', user: 'root' } },
    });
  });

  it('acquires a shared lease, deploys the key, and releases', async () => {
    mockConfigService.getRepository.mockResolvedValue({
      sshPublicKey: PUB_KEY,
      repositoryGuid: 'guid-123',
    });

    await deployRepoKeyIfNeeded('myrepo', 'm1');

    expect(mockAcquire).toHaveBeenCalledExactlyOnceWith('m1');
    expect(mockExec).toHaveBeenCalledExactlyOnceWith(
      buildKeyDeploymentScript('myrepo', PUB_KEY, 'guid-123')
    );
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });

  it('does nothing when the repo has no public key', async () => {
    mockConfigService.getRepository.mockResolvedValue({});

    await deployRepoKeyIfNeeded('myrepo', 'm1');

    expect(mockAcquire).not.toHaveBeenCalled();
  });

  it('does nothing when the machine is unknown', async () => {
    mockConfigService.getRepository.mockResolvedValue({ sshPublicKey: PUB_KEY });

    await deployRepoKeyIfNeeded('myrepo', 'nope');

    expect(mockAcquire).not.toHaveBeenCalled();
  });

  it('releases the lease and warns instead of throwing when exec fails', async () => {
    mockConfigService.getRepository.mockResolvedValue({ sshPublicKey: PUB_KEY });
    mockExec.mockRejectedValueOnce(new Error('boom'));
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await expect(deployRepoKeyIfNeeded('myrepo', 'm1')).resolves.toBeUndefined();

    expect(mockRelease).toHaveBeenCalledTimes(1);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('boom'));
    warnSpy.mockRestore();
  });
});

describe('deployAllRepoKeys', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: { m1: { ip: '127.0.0.1', user: 'root' } },
    });
  });

  it('reuses a single lease for the whole loop and counts deployments', async () => {
    mockConfigService.listRepositories.mockResolvedValue([
      { name: 'a', config: { sshPublicKey: PUB_KEY, repositoryGuid: 'g-a' } },
      { name: 'no-key', config: {} },
      { name: 'b', config: { sshPublicKey: PUB_KEY } },
    ]);

    const deployed = await deployAllRepoKeys('m1');

    expect(deployed).toBe(2);
    expect(mockAcquire).toHaveBeenCalledExactlyOnceWith('m1');
    expect(mockExec).toHaveBeenCalledTimes(2);
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });

  it('skips connecting entirely when no repo has a key', async () => {
    mockConfigService.listRepositories.mockResolvedValue([{ name: 'a', config: {} }]);

    const deployed = await deployAllRepoKeys('m1');

    expect(deployed).toBe(0);
    expect(mockAcquire).not.toHaveBeenCalled();
  });

  it('continues past per-repo failures and still releases once', async () => {
    mockConfigService.listRepositories.mockResolvedValue([
      { name: 'a', config: { sshPublicKey: PUB_KEY } },
      { name: 'b', config: { sshPublicKey: PUB_KEY } },
    ]);
    mockExec.mockRejectedValueOnce(new Error('transient'));

    const deployed = await deployAllRepoKeys('m1');

    expect(deployed).toBe(1);
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });
});
