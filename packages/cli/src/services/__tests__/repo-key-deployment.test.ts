import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { REMOTE_RENET_PATH } from '../renet/renet-provisioner.js';
import {
  buildKeyDeploymentScript,
  buildKeyRemovalScript,
  COUNT_UNGUIDED_KEY_LINES_SCRIPT,
  deployAllRepoKeys,
  deployRepoKey,
  deployRepoKeyIfNeeded,
  removeRepoKeyIfDeployed,
} from '../repo/repo-key-deployment.js';

const { mockExec, mockRelease, mockAcquire, mockConfigService, mockRecordedMount } = vi.hoisted(
  () => {
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
      mockRecordedMount: vi.fn().mockResolvedValue(undefined),
      mockConfigService: {
        getRepository: vi.fn(),
        getLocalConfig: vi.fn(),
        listRepositories: vi.fn(),
      },
    };
  }
);

vi.mock('../machine/machine-connection.js', () => ({
  machineConnections: { acquire: mockAcquire },
}));

vi.mock('../config/config-resources.js', () => ({
  configService: mockConfigService,
}));

vi.mock('../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: mockRecordedMount,
}));

const DS = WK_DATASTORE_PATH;

const PUB_KEY = `ssh-ed25519 ${'A'.repeat(60)} test@rediacc`;

describe('buildKeyDeploymentScript', () => {
  it('produces the exact deployment script (byte-identical snapshot)', () => {
    const script = buildKeyDeploymentScript('myrepo', PUB_KEY, 'guid-123', DS);

    // The remote authorized_keys surgery is load-bearing for sandbox-gateway isolation, so the script must never drift. --datastore follows --guid: renet's prune scanner reads "<repo> --guid <uuid>" as one unit.
    const expected = [
      'set -e',
      'SSH_DIR="$HOME/.ssh"',
      'AUTH_KEYS="$SSH_DIR/authorized_keys"',
      'mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"',
      `KEY_BLOB="${PUB_KEY.split(' ')[1]}"`,
      `if [ -f "$AUTH_KEYS" ] && awk -v b="$KEY_BLOB" '{ for (i = 1; i <= NF; i++) if ($i == b) f = 1 } END { exit !f }' "$AUTH_KEYS"; then TEMP=$(mktemp) && awk -v b="$KEY_BLOB" '{ for (i = 1; i <= NF; i++) if ($i == b) next } 1' "$AUTH_KEYS" > "$TEMP" && mv "$TEMP" "$AUTH_KEYS" || { rm -f "$TEMP"; echo "authorized_keys rewrite failed; key not appended" >&2; exit 1; }; fi`,
      `echo 'command="${REMOTE_RENET_PATH} sandbox-gateway myrepo --guid guid-123 --datastore ${DS}" ${PUB_KEY}' >> "$AUTH_KEYS"`,
      'chmod 600 "$AUTH_KEYS"',
    ].join('; ');

    expect(script).toBe(expected);
    expect(script).toMatchSnapshot();
  });

  it('replaces only the line holding the same blob, not a key sharing its first 50 characters, in a real shell', () => {
    const head = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI';
    const keyA = `${head}AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`;
    const keyB = `${head}AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB`;
    expect(keyA.slice(0, 50)).toBe(keyB.slice(0, 50));
    const home = mkdtempSync(join(tmpdir(), 'keydeploy-'));
    try {
      mkdirSync(join(home, '.ssh'));
      const keys = join(home, '.ssh', 'authorized_keys');
      const lineB = `command="renet sandbox-gateway other --guid g2 --datastore /mnt/x" ${keyB} other`;
      writeFileSync(keys, `ssh-rsa team\n${lineB}\n`);

      execFileSync('bash', ['-c', buildKeyDeploymentScript('repoa', keyA, 'g1', DS)], {
        env: { ...process.env, HOME: home },
      });
      execFileSync('bash', ['-c', buildKeyDeploymentScript('repoa', keyA, 'g1', DS)], {
        env: { ...process.env, HOME: home },
      });

      const lines = readFileSync(keys, 'utf8').trim().split('\n');
      expect(lines).toContain(lineB);
      expect(lines.filter((l) => l.includes(keyA))).toHaveLength(1);
      expect(lines).toHaveLength(3);
    } finally {
      rmSync(home, { recursive: true, force: true });
    }
  });

  it('fails without appending when rewriting the old line fails, so the key never lands twice', () => {
    const key = `ssh-ed25519 ${'B'.repeat(60)}`;
    const home = mkdtempSync(join(tmpdir(), 'keydeploy-'));
    try {
      mkdirSync(join(home, '.ssh'));
      mkdirSync(join(home, 'bin'));
      const keys = join(home, '.ssh', 'authorized_keys');
      const before = `ssh-rsa team\ncommand="old" ${key}\n`;
      writeFileSync(keys, before);
      // An awk whose rewrite pass (the program with `next`) fails, as on a full disk.
      writeFileSync(
        join(home, 'bin', 'awk'),
        '#!/bin/bash\ncase "$*" in *next*) exit 2;; *) exec /usr/bin/env -i PATH=/usr/bin:/bin awk "$@";; esac\n',
        { mode: 0o755 }
      );
      expect(() =>
        execFileSync('bash', ['-c', buildKeyDeploymentScript('repoa', key, 'g1', DS)], {
          env: { ...process.env, HOME: home, PATH: `${join(home, 'bin')}:${process.env.PATH}` },
          stdio: 'pipe',
        })
      ).toThrow(/authorized_keys rewrite failed/);
      expect(readFileSync(keys, 'utf8')).toBe(before);
    } finally {
      rmSync(home, { recursive: true, force: true });
    }
  });

  it('refuses a public key without a base64 blob', () => {
    expect(() => buildKeyDeploymentScript('r', 'ssh-ed25519', 'g', DS)).toThrow(/no base64 blob/);
    expect(() => buildKeyDeploymentScript('r', 'ssh-ed25519 a"b', 'g', DS)).toThrow(
      /no base64 blob/
    );
  });

  it('refuses to build a key line without a repository GUID', () => {
    expect(() => buildKeyDeploymentScript('myrepo', PUB_KEY, '', DS)).toThrow(/without a GUID/);
  });

  it('binds a custom datastore after the --guid flag', () => {
    const script = buildKeyDeploymentScript('myrepo', PUB_KEY, 'guid-123', '/srv/ds-2');
    expect(script).toContain(
      `sandbox-gateway myrepo --guid guid-123 --datastore /srv/ds-2" ${PUB_KEY}`
    );
  });

  it.each([
    'relative/path',
    '/mnt/with space',
    "/mnt/quote'",
    '/mnt/dq"',
    '/mnt/$(id)',
    '/mnt/a;b',
    '/mnt/../etc',
    '',
  ])('refuses datastore %j, which is not a plain absolute path', (ds) => {
    expect(() => buildKeyDeploymentScript('myrepo', PUB_KEY, 'guid-123', ds)).toThrow(
      /not a plain absolute path/
    );
  });
});

describe('deployRepoKey', () => {
  it('executes the deployment script over the provided session', async () => {
    const exec = vi.fn().mockResolvedValue('');
    const sftp = { exec } as unknown as SFTPClient;

    await deployRepoKey(sftp, 'myrepo', PUB_KEY, 'guid-123', DS);

    expect(exec).toHaveBeenCalledExactlyOnceWith(
      buildKeyDeploymentScript('myrepo', PUB_KEY, 'guid-123', DS)
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
      buildKeyDeploymentScript('myrepo', PUB_KEY, 'guid-123', DS)
    );
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });

  it("binds the key to the machine's datastore when the repo records none", async () => {
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: { m1: { ip: '127.0.0.1', user: 'root', datastore: '/srv/custom' } },
    });
    mockConfigService.getRepository.mockResolvedValue({
      sshPublicKey: PUB_KEY,
      repositoryGuid: 'guid-123',
    });

    await deployRepoKeyIfNeeded('myrepo', 'm1');

    expect(mockExec).toHaveBeenCalledExactlyOnceWith(
      buildKeyDeploymentScript('myrepo', PUB_KEY, 'guid-123', '/srv/custom')
    );
  });

  it('binds the key to the datastore the repo is recorded on, over the machine default', async () => {
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: { m1: { ip: '127.0.0.1', user: 'root', datastore: '/srv/custom' } },
    });
    mockConfigService.getRepository.mockResolvedValue({
      sshPublicKey: PUB_KEY,
      repositoryGuid: 'guid-123',
    });
    mockRecordedMount.mockResolvedValueOnce('/mnt/rediacc-ds/fast');

    await deployRepoKeyIfNeeded('myrepo:dev', 'm1');

    expect(mockRecordedMount).toHaveBeenCalledWith('myrepo:dev');
    expect(mockExec).toHaveBeenCalledExactlyOnceWith(
      buildKeyDeploymentScript('myrepo:dev', PUB_KEY, 'guid-123', '/mnt/rediacc-ds/fast')
    );
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
    mockConfigService.getRepository.mockResolvedValue({
      sshPublicKey: PUB_KEY,
      repositoryGuid: 'guid-123',
    });
    mockExec.mockRejectedValueOnce(new Error('boom'));
    const warnSpy = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);

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
      { name: 'b', config: { sshPublicKey: PUB_KEY, repositoryGuid: 'g-x' } },
    ]);

    const deployed = await deployAllRepoKeys('m1');

    expect(deployed).toBe(2);
    expect(mockAcquire).toHaveBeenCalledExactlyOnceWith('m1');
    expect(mockExec).toHaveBeenCalledTimes(3);
    expect(mockExec).toHaveBeenNthCalledWith(3, COUNT_UNGUIDED_KEY_LINES_SCRIPT);
    expect(mockExec).toHaveBeenNthCalledWith(1, buildKeyDeploymentScript('a', PUB_KEY, 'g-a', DS));
    expect(mockExec).toHaveBeenNthCalledWith(2, buildKeyDeploymentScript('b', PUB_KEY, 'g-x', DS));
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
      { name: 'a', config: { sshPublicKey: PUB_KEY, repositoryGuid: 'g-x' } },
      { name: 'b', config: { sshPublicKey: PUB_KEY, repositoryGuid: 'g-x' } },
    ]);
    mockExec.mockRejectedValueOnce(new Error('transient'));

    const deployed = await deployAllRepoKeys('m1');

    expect(deployed).toBe(1);
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });
});

describe('COUNT_UNGUIDED_KEY_LINES_SCRIPT', () => {
  it('counts only sandbox-gateway lines without --guid, in a real shell', () => {
    const home = mkdtempSync(join(tmpdir(), 'keycount-'));
    try {
      mkdirSync(join(home, '.ssh'));
      writeFileSync(
        join(home, '.ssh', 'authorized_keys'),
        [
          'command="renet sandbox-gateway a --guid g1 --datastore /d" ssh-ed25519 A',
          'command="renet sandbox-gateway b --datastore /d" ssh-ed25519 B',
          'command="renet sandbox-gateway c" ssh-ed25519 C',
          'ssh-rsa team',
          '',
        ].join('\n')
      );
      const out = execFileSync('bash', ['-c', COUNT_UNGUIDED_KEY_LINES_SCRIPT], {
        env: { ...process.env, HOME: home },
      });
      expect(out.toString().trim()).toBe('2');
    } finally {
      rmSync(home, { recursive: true, force: true });
    }
  });
});

describe('buildKeyRemovalScript', () => {
  const GUID = '11111111-1111-1111-1111-111111111111';

  it('removes only the exact repo and guid line, in a real shell', () => {
    const home = mkdtempSync(join(tmpdir(), 'keyrm-'));
    try {
      mkdirSync(join(home, '.ssh'));
      const keys = join(home, '.ssh', 'authorized_keys');
      const line = (repo: string, guid: string) =>
        `command="renet sandbox-gateway ${repo} --guid ${guid} --datastore /mnt/x" ssh-ed25519 AAAA-${repo}`;
      const other = line('app:stage2', '22222222-2222-2222-2222-222222222222');
      const sibling = line('app:stage', '33333333-3333-3333-3333-333333333333');
      writeFileSync(keys, `${line('app:stage', GUID)}\n${other}\n${sibling}\nssh-rsa team\n`);

      execFileSync('bash', ['-c', buildKeyRemovalScript('app:stage', GUID)], {
        env: { ...process.env, HOME: home },
      });

      expect(readFileSync(keys, 'utf8')).toBe(`${other}\n${sibling}\nssh-rsa team\n`);
    } finally {
      rmSync(home, { recursive: true, force: true });
    }
  });

  it('leaves authorized_keys unchanged when the rewrite cannot read it (review ef6dbb53.1)', () => {
    const home = mkdtempSync(join(tmpdir(), 'keyrm-'));
    try {
      mkdirSync(join(home, '.ssh'));
      mkdirSync(join(home, 'bin'));
      const keys = join(home, '.ssh', 'authorized_keys');
      const before = `command="renet sandbox-gateway app:stage --guid ${GUID} --datastore /mnt/x" ssh-ed25519 A\nssh-rsa team\n`;
      writeFileSync(keys, before);
      // A grep that finds the line but fails the -v rewrite with a read error (exit 2) after printing part of the file.
      writeFileSync(
        join(home, 'bin', 'grep'),
        '#!/bin/bash\ncase "$1" in -vF) echo partial; exit 2;; *) exec /usr/bin/env -i PATH=/usr/bin:/bin grep "$@";; esac\n',
        { mode: 0o755 }
      );
      expect(() =>
        execFileSync('bash', ['-c', buildKeyRemovalScript('app:stage', GUID)], {
          env: { ...process.env, HOME: home, PATH: `${join(home, 'bin')}:${process.env.PATH}` },
          stdio: 'pipe',
        })
      ).toThrow();
      expect(readFileSync(keys, 'utf8')).toBe(before);
    } finally {
      rmSync(home, { recursive: true, force: true });
    }
  });

  it('refuses unsafe names', () => {
    expect(() => buildKeyRemovalScript("a'; rm -rf ~; '", GUID)).toThrow(/unsafe/);
  });
});

describe('removeRepoKeyIfDeployed', () => {
  beforeEach(() => {
    mockExec.mockClear();
    mockRelease.mockClear();
  });

  it('runs the removal script over the machine lease and releases it', async () => {
    await removeRepoKeyIfDeployed('app:stage', 'm1', 'guid-1');
    expect(mockExec).toHaveBeenCalledWith(buildKeyRemovalScript('app:stage', 'guid-1'));
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });

  it('reports a failed removal on stderr without throwing', async () => {
    mockExec.mockRejectedValueOnce(new Error('ssh down'));
    const spy = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
    try {
      await expect(removeRepoKeyIfDeployed('app:stage', 'm1', 'guid-1')).resolves.toBeUndefined();
      expect(spy.mock.calls.map((c) => String(c[0])).join('')).toContain('ssh down');
    } finally {
      spy.mockRestore();
    }
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });
});
