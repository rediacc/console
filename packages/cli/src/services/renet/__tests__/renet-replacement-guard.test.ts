/**
 * What a provision may do to the renet a machine already runs, and what an executor may do at all.
 *
 * THE DEFECT THIS PINS (2026-11-04 12:58 UTC). A proxied `repo up` on hostinger replaced the machine's
 * branch renet (0.0.0-dev) with the bench image's 2.4.0, which lacked flags the nightly backup passes.
 * The guard compared the CLI's VERSION with the version in the CLI's own slot, so it never read the
 * binary being uploaded and never read `current`, the renet the machine actually runs.
 *
 * Real: the provisioner, renet-execution and a temp-file binary carrying a Go build-info blob. Fake: the
 * remote (a shell answered by command), the transfer, and the persisted state.
 */

import { createHash } from 'node:crypto';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CliExitError } from '../../../utils/cli-exit-error.js';

const { state, stageMock, getFreshMock } = vi.hoisted(() => ({
  state: { version: '0.0.0-dev', sea: false, embedded: Buffer.alloc(0) as Buffer },
  stageMock: vi.fn(() => Promise.resolve()),
  getFreshMock: vi.fn((): Promise<unknown> => Promise.resolve(null)),
}));

vi.mock('../../../version.js', () => ({
  get VERSION() {
    return state.version;
  },
}));
vi.mock('../../core/embedded-assets.js', () => ({
  isSEA: () => state.sea,
  getEmbeddedRenetBinary: () => state.embedded,
  computeSha256: (data: Buffer) => createHash('sha256').update(data).digest('hex'),
}));
vi.mock('../renet-binary-transfer.js', () => ({ stageRenetBinary: stageMock }));
vi.mock('../renet-provision-lock.js', () => ({
  withLocalProvisionLock: (_key: string, fn: () => Promise<unknown>) => fn(),
}));
vi.mock('../provision-state.js', () => ({
  getFreshProvisionEntry: getFreshMock,
  recordProvisionVerified: vi.fn(() => Promise.resolve()),
  dropProvisionEntry: vi.fn(() => Promise.resolve()),
  isSetupVerifiedFresh: vi.fn(() => Promise.resolve(false)),
  recordSetupVerified: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../machine/machine-connection.js', () => ({
  sftpConfigForMachine: () => ({ host: 'hostinger', username: 'root', privateKey: 'k' }),
  withSharedOrPooledSftp: (
    shared: unknown,
    _config: unknown,
    fn: (sftp: unknown) => Promise<unknown>
  ) => fn(shared),
}));

const REVISION = 'c'.repeat(40);
const MODINFO_END = Buffer.from('f932433186182072008242104116d8f2', 'hex');
const MACHINE = { ip: '10.0.0.5', user: 'root', port: 22 };
const CONFIG = { host: 'hostinger', username: 'root', privateKey: 'k' };

/** A binary as Go lays one out: junk, then the build-info text between its end sentinel. */
function renetBytes(version: string | null): Buffer {
  const ldflags = version === null ? '' : `build\t-ldflags="-s -w -X main.Version=${version}"\n`;
  return Buffer.concat([
    Buffer.from('\x7fELF junk'),
    Buffer.from(
      `path\tgithub.com/rediacc/renet/cmd/renet\nmod\tgithub.com/rediacc/renet\t(devel)\t\n${ldflags}build\tvcs.revision=${REVISION}\n`
    ),
    MODINFO_END,
    Buffer.from(`trailing -X main.Version=9.9.9 from an embedded asset`),
  ]);
}

interface RemoteRenet {
  hash: string;
  version: string | null;
}

/** A remote answering the provisioner's commands; null is a slot with no binary. */
function remote(slot: RemoteRenet | null, current: RemoteRenet | null) {
  const answer = (renet: RemoteRenet | null): string =>
    renet ? `${renet.hash}\nrenet version ${renet.version ?? ''}` : '\n';
  const probe = (tag: string, renet: RemoteRenet | null): string =>
    renet
      ? `${tag}_HASH ${renet.hash}\n${tag}_VERSION renet version ${renet.version ?? ''}\n`
      : `${tag}_ABSENT\n`;
  // First match wins: the install's flock body names both paths, and the probe names both tags.
  const answers: [string, string][] = [
    ['uname -m', process.arch === 'arm64' ? 'aarch64\n' : 'x86_64\n'],
    ['flock -w 120', 'UPDATED CURRENT_UPDATED\n'],
    ['SLOT_HASH', probe('SLOT', slot) + probe('CURRENT', current)],
    ['/current/renet', answer(current)],
    [' version 2>/dev/null', answer(slot)],
  ];
  const exec = vi.fn(
    (command: string): Promise<string> =>
      Promise.resolve(answers.find(([marker]) => command.includes(marker))?.[1] ?? '')
  );
  return { exec, close: vi.fn(), writeFile: vi.fn(), exists: vi.fn() };
}

let dir: string;

function writeBinary(bytes: Buffer): string {
  const file = path.join(dir, 'renet');
  fs.writeFileSync(file, bytes);
  return file;
}

function sha(bytes: Buffer): string {
  return createHash('sha256').update(bytes).digest('hex');
}

async function provisioner() {
  const mod = await import('../renet-provisioner.js');
  mod.renetProvisioner.clearCache();
  return mod.renetProvisioner;
}

/** Run one provision with the CLI at `cli` holding a local binary at `local`. */
async function provisionWith(
  cli: string,
  local: Buffer,
  slot: RemoteRenet | null,
  current: RemoteRenet | null
) {
  state.version = cli;
  const p = await provisioner();
  const sftp = remote(slot, current);
  const result = await p.provision(CONFIG, { localBinaryPath: writeBinary(local) }, sftp as never);
  return { result, sftp };
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  getFreshMock.mockResolvedValue(null);
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'renet-guard-'));
  state.sea = false;
  state.embedded = Buffer.alloc(0);
  delete process.env.REDIACC_ALLOW_DOWNGRADE;
});

afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
  delete process.env.REDIACC_ALLOW_DOWNGRADE;
});

describe('the upgrades that must keep working', () => {
  it('a release CLI upgrades a machine on an older release', async () => {
    const local = renetBytes('2.5.0');
    const { result } = await provisionWith('2.5.0', local, null, { hash: 'old', version: '2.4.0' });
    expect(result.success).toBe(true);
    expect(stageMock).toHaveBeenCalledTimes(1);
  });

  it('a SEA upgrades a machine on an older release from its embedded binary', async () => {
    state.version = '2.5.0';
    state.sea = true;
    state.embedded = renetBytes('2.5.0');
    const p = await provisioner();
    const result = await p.provision(
      CONFIG,
      {},
      remote(null, { hash: 'old', version: '2.4.0' }) as never
    );
    expect(result.success).toBe(true);
    expect(stageMock).toHaveBeenCalledTimes(1);
  });

  it('a SEA whose embedded binary carries no readable stamp stands on the version it was built with', async () => {
    state.version = '2.5.0';
    state.sea = true;
    state.embedded = Buffer.from('compressed');
    const p = await provisioner();
    const result = await p.provision(
      CONFIG,
      {},
      remote(null, { hash: 'old', version: '2.4.0' }) as never
    );
    expect(result.success).toBe(true);
  });

  it('a dev CLI replaces a dev build with a fresh dev build (./rdc.sh)', async () => {
    const local = renetBytes('0.0.0-dev');
    const old = { hash: 'old', version: '0.0.0-dev' };
    const { result } = await provisionWith('0.0.0-dev', local, old, old);
    expect(result.success).toBe(true);
    expect(stageMock).toHaveBeenCalledTimes(1);
  });

  it('a dev CLI puts its own dev build on a machine on a release (./rdc.sh on purpose)', async () => {
    const local = renetBytes('0.0.0-dev');
    const { result } = await provisionWith('0.0.0-dev', local, null, {
      hash: 'old',
      version: '2.4.0',
    });
    expect(result.success).toBe(true);
    expect(stageMock).toHaveBeenCalledTimes(1);
  });

  it('a tag-suffixed dev build counts as a dev build', async () => {
    const local = renetBytes('2.4.0-dev');
    const { result } = await provisionWith('0.0.0-dev', local, null, {
      hash: 'old',
      version: '2.5.0-dev',
    });
    expect(result.success).toBe(true);
  });

  it('a plain go build with no version stamp may replace a dev build from a dev CLI (the upgrade drill)', async () => {
    const local = renetBytes(null);
    const { result } = await provisionWith('0.0.0-dev', local, null, {
      hash: 'old',
      version: '0.0.0-dev',
    });
    expect(result.success).toBe(true);
  });

  it('a first install has nothing to compare', async () => {
    const { result } = await provisionWith('0.0.0-dev', renetBytes('2.4.0'), null, null);
    expect(result.success).toBe(true);
    expect(stageMock).toHaveBeenCalledTimes(1);
  });

  it('a machine whose renet reports no version can still be repaired', async () => {
    const local = renetBytes('2.5.0');
    const broken = { hash: 'broken', version: null };
    const { result } = await provisionWith('2.5.0', local, broken, broken);
    expect(result.success).toBe(true);
  });

  it('nothing is decided when the machine already runs the local bytes', async () => {
    const local = renetBytes('2.4.0');
    const same = { hash: sha(local), version: '2.4.0' };
    const { result } = await provisionWith('0.0.0-dev', local, same, same);
    expect(result.success).toBe(true);
    expect(stageMock).not.toHaveBeenCalled();
  });
});

describe('the replacements a provision refuses', () => {
  it('the incident: a dev CLI holding a release binary against a dev build on the machine', async () => {
    const dev = { hash: 'branch', version: '0.0.0-dev' };
    const { result } = await provisionWith('0.0.0-dev', renetBytes('2.4.0'), dev, dev);
    expect(result.success).toBe(false);
    expect(result.action).toBe('version_rejected');
    expect(result).toMatchObject({ code: 'RENET_DEV_ON_MACHINE' });
    expect(result.error).toContain('2.4.0');
    expect(result.error).toContain('0.0.0-dev');
    expect(stageMock).not.toHaveBeenCalled();
  });

  it('a release binary never beats a dev build, whatever the CLI is', async () => {
    const local = renetBytes('2.5.0');
    const { result } = await provisionWith('2.5.0', local, null, {
      hash: 'branch',
      version: '0.0.0-dev',
    });
    expect(result).toMatchObject({ success: false, code: 'RENET_DEV_ON_MACHINE' });
    expect(stageMock).not.toHaveBeenCalled();
  });

  it('an older release refuses against a newer one, naming both', async () => {
    const local = renetBytes('2.4.0');
    const { result } = await provisionWith('2.4.0', local, null, {
      hash: 'newer',
      version: '2.5.0',
    });
    expect(result).toMatchObject({ success: false, code: 'RENET_DOWNGRADE_REFUSED' });
    expect(result.error).toContain('2.4.0');
    expect(result.error).toContain('2.5.0');
    expect(stageMock).not.toHaveBeenCalled();
  });

  it('reads `current`, not the slot named after this CLI, for what the machine runs', async () => {
    // The old guard read only the slot, so an older CLI with no slot on the machine replaced a newer current.
    const local = renetBytes('2.4.0');
    const { result } = await provisionWith('2.4.0', local, null, {
      hash: 'newer',
      version: '2.5.0',
    });
    expect(result.action).toBe('version_rejected');
  });

  it('a slot already holding the local bytes does not repoint a newer `current` at them', async () => {
    const local = renetBytes('2.4.0');
    const { result, sftp } = await provisionWith(
      '2.4.0',
      local,
      { hash: sha(local), version: '2.4.0' },
      { hash: 'newer', version: '2.5.0' }
    );
    expect(result).toMatchObject({ success: false, code: 'RENET_DOWNGRADE_REFUSED' });
    expect(sftp.exec.mock.calls.some(([c]) => c.includes('flock -w 120'))).toBe(false);
  });

  it('reads the binary being uploaded, not the CLI version: a stale binary under a current CLI', async () => {
    const { result } = await provisionWith('2.6.0', renetBytes('2.4.0'), null, {
      hash: 'newer',
      version: '2.5.0',
    });
    expect(result).toMatchObject({ success: false, code: 'RENET_DOWNGRADE_REFUSED' });
    expect(result.error).toContain('2.4.0');
  });

  it('a newer binary this CLI was not built with cannot be shown to be its build', async () => {
    const { result } = await provisionWith('2.5.0', renetBytes('2.7.0'), null, {
      hash: 'old',
      version: '2.4.0',
    });
    expect(result).toMatchObject({ success: false, code: 'RENET_BUILD_UNVERIFIED' });
  });

  it('a dev CLI holding a release binary against an older release cannot show it either', async () => {
    const { result } = await provisionWith('0.0.0-dev', renetBytes('2.4.0'), null, {
      hash: 'old',
      version: '2.3.0',
    });
    expect(result).toMatchObject({ success: false, code: 'RENET_BUILD_UNVERIFIED' });
  });

  it('a release CLI holding a dev binary cannot show it either', async () => {
    const { result } = await provisionWith('2.5.0', renetBytes('0.0.0-dev'), null, {
      hash: 'old',
      version: '2.4.0',
    });
    expect(result).toMatchObject({ success: false, code: 'RENET_BUILD_UNVERIFIED' });
  });

  it('a binary with no readable version does not replace a release', async () => {
    const { result } = await provisionWith('0.0.0-dev', Buffer.from('not go'), null, {
      hash: 'old',
      version: '2.4.0',
    });
    expect(result).toMatchObject({ success: false, code: 'RENET_BUILD_UNVERIFIED' });
  });

  it('REDIACC_ALLOW_DOWNGRADE is the operator override for every one of these', async () => {
    process.env.REDIACC_ALLOW_DOWNGRADE = '1';
    const { result } = await provisionWith('2.5.0', renetBytes('2.5.0'), null, {
      hash: 'branch',
      version: '0.0.0-dev',
    });
    expect(result.success).toBe(true);
  });

  it('a probe of the slot that cannot run stops the upload instead of reading as an empty slot', async () => {
    state.version = '2.5.0';
    const p = await provisioner();
    const sftp = remote(null, null);
    const original = sftp.exec.getMockImplementation();
    sftp.exec.mockImplementation((command: string) => {
      if (
        command.includes(' version 2>/dev/null') &&
        !command.includes('/current/renet') &&
        !command.includes('flock')
      ) {
        return Promise.reject(new Error('connection reset'));
      }
      return original?.(command) ?? Promise.resolve('');
    });
    const result = await p.provision(
      CONFIG,
      { localBinaryPath: writeBinary(renetBytes('2.5.0')) },
      sftp as never
    );
    expect(result.success).toBe(false);
    expect(stageMock).not.toHaveBeenCalled();
  });

  it('a probe of `current` that cannot run stops the upload instead of reading as no renet', async () => {
    state.version = '2.5.0';
    const p = await provisioner();
    const sftp = remote(null, { hash: 'x', version: '2.6.0' });
    const original = sftp.exec.getMockImplementation();
    sftp.exec.mockImplementation((command: string) => {
      if (command.includes('/current/renet') && !command.includes('flock')) {
        return Promise.reject(new Error('connection reset'));
      }
      return original?.(command) ?? Promise.resolve('');
    });
    const result = await p.provision(
      CONFIG,
      { localBinaryPath: writeBinary(renetBytes('2.5.0')) },
      sftp as never
    );
    expect(result.success).toBe(false);
    expect(stageMock).not.toHaveBeenCalled();
  });
});

describe('a coded failure inside the provision', () => {
  it('keeps BUSY on the remote install lock instead of flattening it to a failed result', async () => {
    state.version = '2.5.0';
    const p = await provisioner();
    const sftp = remote(null, null);
    const original = sftp.exec.getMockImplementation();
    sftp.exec.mockImplementation((command: string) =>
      command.includes('flock -w 120')
        ? Promise.reject(new Error('Command exited with code 75: FLOCK_TIMEOUT'))
        : (original?.(command) ?? Promise.resolve(''))
    );
    const error = await p
      .provision(CONFIG, { localBinaryPath: writeBinary(renetBytes('2.5.0')) }, sftp as never)
      .catch((caught: unknown) => caught);
    expect((error as CliExitError).code).toBe('BUSY');
  });
});

describe('an uncoded failure inside the provision', () => {
  it('stays a failed result, and a coded one other than BUSY keeps its code', async () => {
    state.version = '2.5.0';
    const p = await provisioner();
    const uncoded = await p.provision(
      CONFIG,
      {
        localBinaryPath: writeBinary(renetBytes('2.5.1')),
        uploadGuard: () => {
          throw new Error('guard said no');
        },
      },
      remote(null, null) as never
    );
    expect(uncoded.success).toBe(false);
    expect(uncoded.error).toContain('guard said no');
    const { CliExitError: Coded } = await import('../../../utils/cli-exit-error.js');
    const coded = await p
      .provision(
        CONFIG,
        {
          localBinaryPath: writeBinary(renetBytes('2.5.1')),
          uploadGuard: () => {
            throw new Coded('INFRA_FAILED', 'guard refused');
          },
        },
        remote(null, null) as never
      )
      .catch((caught: unknown) => caught);
    expect((coded as CliExitError).code).toBe('INFRA_FAILED');
  });
});

describe('readRenetBuild', () => {
  it('reads the stamp of the renet module and ignores the same text in an embedded asset', async () => {
    const { readRenetBuild } = await import('../renet-replacement.js');
    expect(readRenetBuild(renetBytes('2.4.0'))).toEqual({ version: '2.4.0', revision: REVISION });
  });

  it('answers null for bytes that are not a renet build', async () => {
    const { readRenetBuild } = await import('../renet-replacement.js');
    expect(readRenetBuild(Buffer.from('-X main.Version=9.9.9'))).toEqual({
      version: null,
      revision: null,
    });
  });
});

describe('acquireRemoteRenet in a provisioning run', () => {
  it('throws the refusal with its code and the conflict exit status', async () => {
    state.version = '2.5.0';
    const { acquireRemoteRenet } = await import('../renet-execution.js');
    const { renetProvisioner } = await import('../renet-provisioner.js');
    renetProvisioner.clearCache();
    const sftp = remote(null, { hash: 'newer', version: '2.6.0' });
    const error = await acquireRemoteRenet(
      'provision',
      { renetPath: writeBinary(renetBytes('2.5.0')) },
      MACHINE,
      'key',
      { machineName: 'hostinger' },
      sftp as never
    ).catch((caught: unknown) => caught);
    expect((error as CliExitError).code).toBe('RENET_DOWNGRADE_REFUSED');
    expect((error as CliExitError).exitCode).toBe(12);
  });
});

describe('an executor (a served request)', () => {
  async function asExecutor<T>(fn: () => Promise<T>): Promise<T> {
    const { createOutputState, runInRequestContext } = await import(
      '../../core/request-context.js'
    );
    return runInRequestContext({ output: createOutputState(), stdout: [], stderr: [] }, fn);
  }

  async function acquire(access: 'provision' | 'read-only', sftp: ReturnType<typeof remote>) {
    state.version = '0.0.0-dev';
    const { acquireRemoteRenet } = await import('../renet-execution.js');
    const { renetProvisioner } = await import('../renet-provisioner.js');
    renetProvisioner.clearCache();
    return asExecutor(() =>
      acquireRemoteRenet(
        access,
        { renetPath: writeBinary(renetBytes('2.4.0')) },
        MACHINE,
        'key',
        { machineName: 'hostinger' },
        sftp as never
      )
    );
  }

  it('the incident: runs the renet the machine has and uploads nothing', async () => {
    const dev = { hash: 'branch', version: '0.0.0-dev' };
    const sftp = remote(dev, dev);
    const result = await acquire('provision', sftp);
    expect(result.uploaded).toBe(false);
    expect(result.routerRefreshDue).toBeFalsy();
    expect(result.remotePath).toBe('/usr/lib/rediacc/renet/0.0.0-dev/renet');
    expect(stageMock).not.toHaveBeenCalled();
    expect(sftp.exec.mock.calls.some(([c]) => c.includes('flock -w 120'))).toBe(false);
  });

  it('runs an older release too rather than upgrading it', async () => {
    const sftp = remote(null, { hash: 'older', version: '2.3.0' });
    const result = await acquire('provision', sftp);
    expect(result.remotePath).toBe('/usr/lib/rediacc/renet/current/renet');
    expect(stageMock).not.toHaveBeenCalled();
  });

  it('says the machine differs and what updates it, once per host', async () => {
    const { outputService } = await import('../../core/output.js');
    const warn = vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);
    await acquire('provision', remote(null, { hash: 'older', version: '2.3.0' }));
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0]?.[0]).toContain('without --proxy');
    expect(warn.mock.calls[0]?.[0]).not.toContain('any mutating command');
    warn.mockRestore();
  });

  it('refuses with a code when the machine has no renet, naming what provisions it', async () => {
    const error = await acquire('provision', remote(null, null)).catch((caught: unknown) => caught);
    expect((error as CliExitError).code).toBe('RENET_NOT_ON_MACHINE');
    expect((error as Error).message).toContain('rdc machine setup hostinger');
    expect((error as Error).message).toContain('without --proxy');
    expect(stageMock).not.toHaveBeenCalled();
  });

  it('read-only access answers the same way', async () => {
    const error = await acquire('read-only', remote(null, null)).catch((caught: unknown) => caught);
    expect((error as CliExitError).code).toBe('RENET_NOT_ON_MACHINE');
  });

  it('does not trust a persisted entry: it looks at the machine every time', async () => {
    getFreshMock.mockResolvedValue({
      version: '0.0.0-dev',
      hash: 'stale',
      arch: 'amd64',
      verifiedAt: Date.now(),
    });
    const sftp = remote(null, { hash: 'other', version: '2.3.0' });
    const result = await acquire('provision', sftp);
    expect(result.remotePath).toBe('/usr/lib/rediacc/renet/current/renet');
    expect(sftp.exec.mock.calls.some(([c]) => c.includes('SLOT_HASH'))).toBe(true);
  });

  it('REDIACC_ALLOW_DOWNGRADE does not open the executor', async () => {
    process.env.REDIACC_ALLOW_DOWNGRADE = '1';
    const dev = { hash: 'branch', version: '0.0.0-dev' };
    await acquire('provision', remote(dev, dev));
    expect(stageMock).not.toHaveBeenCalled();
  });

  it('the provisioner itself refuses a provision in a request, as the last line', async () => {
    state.version = '0.0.0-dev';
    const p = await provisioner();
    const result = await asExecutor(() =>
      p.provision(
        CONFIG,
        { localBinaryPath: writeBinary(renetBytes('0.0.0-dev')) },
        remote(null, null) as never
      )
    );
    expect(result).toMatchObject({ success: false, code: 'RENET_UPLOAD_REFUSED_IN_EXECUTOR' });
    expect(stageMock).not.toHaveBeenCalled();
  });
});
