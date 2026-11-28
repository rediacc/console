/**
 * Switching a server's renet for a preview and back (PLAN-preview-signer.md D9), from the machine's side.
 *
 * Real: the provisioner, the replacement guard, and the pin, prune and switch-back shell fragments run in a
 * real POSIX shell against a temp tree. Fake: the remote (a shell answered by command), the transfer, the
 * persisted provision state, and the overlay's record (`recordPreviewTouch`, whose own semantics
 * `preview/__tests__/state.test.ts` pins).
 */

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { WK_RENET_REPO } from '@rediacc/shared/config/well-known.generated';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildPinCommand, buildSwitchBackBody, parsePinOutput } from '../../preview/slot.js';
import { buildSlotPruneStep } from '../renet-slot-prune.js';

const { state, stageMock, touchMock } = vi.hoisted(() => ({
  state: { version: '0.0.0-dev', sea: false },
  stageMock: vi.fn(() => Promise.resolve()),
  touchMock: vi.fn((..._args: unknown[]) => Promise.resolve(true)),
}));

vi.mock('../../../version.js', () => ({
  get VERSION() {
    return state.version;
  },
}));
vi.mock('../../core/embedded-assets.js', () => ({
  isSEA: () => state.sea,
  getEmbeddedRenetBinary: () => Buffer.alloc(0),
  computeSha256: (data: Buffer) => createHash('sha256').update(data).digest('hex'),
}));
vi.mock('../renet-binary-transfer.js', () => ({ stageRenetBinary: stageMock }));
vi.mock('../renet-provision-lock.js', () => ({
  withLocalProvisionLock: (_key: string, fn: () => Promise<unknown>) => fn(),
}));
vi.mock('../provision-state.js', () => ({
  getFreshProvisionEntry: vi.fn(() => Promise.resolve(null)),
  recordProvisionVerified: vi.fn(() => Promise.resolve()),
  dropProvisionEntry: vi.fn(() => Promise.resolve()),
  isSetupVerifiedFresh: vi.fn(() => Promise.resolve(false)),
  recordSetupVerified: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../machine/machine-connection.js', () => ({
  sftpConfigForMachine: () => ({ host: 'vm1', username: 'root', privateKey: 'k' }),
  withSharedOrPooledSftp: (
    shared: unknown,
    _config: unknown,
    fn: (sftp: unknown) => Promise<unknown>
  ) => fn(shared),
}));
vi.mock('../../preview/state.js', () => ({ recordPreviewTouch: touchMock }));

const MODINFO_END = Buffer.from('f932433186182072008242104116d8f2', 'hex');
const CONFIG = { host: 'vm1', username: 'root', privateKey: 'k' };

function renetBytes(version: string): Buffer {
  return Buffer.concat([
    Buffer.from('\x7fELF junk'),
    Buffer.from(
      `path\tgithub.com/${WK_RENET_REPO}/cmd/renet\nmod\tgithub.com/${WK_RENET_REPO}\t(devel)\t\nbuild\t-ldflags="-s -w -X main.Version=${version}"\nbuild\tvcs.revision=${'c'.repeat(40)}\n`
    ),
    MODINFO_END,
  ]);
}

interface RemoteRenet {
  hash: string;
  version: string | null;
}

/** A remote answering the provisioner's commands, the pin command included. */
function remote(slot: RemoteRenet | null, current: RemoteRenet | null, pinAnswer?: string) {
  const answer = (renet: RemoteRenet | null): string =>
    renet ? `${renet.hash}\nrenet version ${renet.version ?? ''}` : '\n';
  const probe = (tag: string, renet: RemoteRenet | null): string =>
    renet
      ? `${tag}_HASH ${renet.hash}\n${tag}_VERSION renet version ${renet.version ?? ''}\n`
      : `${tag}_ABSENT\n`;
  const answers: [string, string][] = [
    ['uname -m', process.arch === 'arm64' ? 'aarch64\n' : 'x86_64\n'],
    [
      'echo "PREVIEW_PIN',
      pinAnswer ?? `PREVIEW_PIN /usr/lib/rediacc/renet/${current?.version ?? 'old'}\n`,
    ],
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

async function provision(
  cli: string,
  local: Buffer,
  running: RemoteRenet | null,
  previewTouch?: { machine: string }
) {
  state.version = cli;
  const file = path.join(dir, 'renet');
  fs.writeFileSync(file, local);
  const mod = await import('../renet-provisioner.js');
  mod.renetProvisioner.clearCache();
  const sftp = remote(null, running);
  const result = await mod.renetProvisioner.provision(
    CONFIG,
    { localBinaryPath: file, ...(previewTouch ? { previewTouch } : {}) },
    sftp as never
  );
  return { result, sftp };
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'renet-preview-'));
  state.sea = false;
  delete process.env.REDIACC_ALLOW_DOWNGRADE;
});

afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

describe('the first replacement of a server while a preview is active', () => {
  const preview = '2.5.0-preview.abc1234';

  it('pins the running slot and records its slot, version and hash before anything is uploaded', async () => {
    const { result, sftp } = await provision(
      preview,
      renetBytes(preview),
      { hash: 'oldhash', version: '2.4.0' },
      { machine: 'vm1' }
    );

    expect(result).toMatchObject({ success: true });
    expect(touchMock).toHaveBeenCalledTimes(1);
    expect(touchMock).toHaveBeenCalledWith('vm1', {
      slot: '/usr/lib/rediacc/renet/2.4.0',
      version: '2.4.0',
      sha256: 'oldhash',
      touchedAt: expect.any(String),
    });
    const calls = sftp.exec.mock.calls.map(([c]) => c);
    const pinAt = calls.findIndex((c) => c.includes('echo "PREVIEW_PIN'));
    const installAt = calls.findIndex((c) => c.includes('flock -w 120'));
    expect(pinAt).toBeGreaterThanOrEqual(0);
    expect(pinAt).toBeLessThan(installAt);
    expect(stageMock.mock.invocationCallOrder[0]).toBeGreaterThan(
      touchMock.mock.invocationCallOrder[0]
    );
  });

  it('records nothing for a call with no preview active', async () => {
    const { result, sftp } = await provision(preview, renetBytes(preview), {
      hash: 'oldhash',
      version: '2.4.0',
    });
    expect(result).toMatchObject({ success: true });
    expect(touchMock).not.toHaveBeenCalled();
    expect(sftp.exec.mock.calls.some(([c]) => c.includes('echo "PREVIEW_PIN'))).toBe(false);
  });

  it('records nothing when the machine already runs the local bytes or a preview renet', async () => {
    const local = renetBytes(preview);
    const same = await provision(
      preview,
      local,
      { hash: createHash('sha256').update(local).digest('hex'), version: preview },
      { machine: 'vm1' }
    );
    expect(same.result).toMatchObject({ success: true });
    const other = await provision(
      preview,
      renetBytes(preview),
      { hash: 'otherpreview', version: '2.5.0-preview.zzz9999' },
      { machine: 'vm1' }
    );
    expect(other.result).toMatchObject({ success: true });
    expect(touchMock).not.toHaveBeenCalled();
  });

  it('leaves the machine alone when the way back cannot be pinned', async () => {
    state.version = preview;
    const file = path.join(dir, 'renet');
    fs.writeFileSync(file, renetBytes(preview));
    const mod = await import('../renet-provisioner.js');
    mod.renetProvisioner.clearCache();
    const sftp = remote(null, { hash: 'oldhash', version: '2.4.0' }, '');
    const result = await mod.renetProvisioner.provision(
      CONFIG,
      { localBinaryPath: file, previewTouch: { machine: 'vm1' } },
      sftp as never
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain('could not be pinned');
    expect(stageMock).not.toHaveBeenCalled();
    expect(touchMock).not.toHaveBeenCalled();
  });
});

describe('an unnamed machine during a preview', () => {
  const preview = '2.5.0-preview.abc1234';
  async function unnamed(running: RemoteRenet, local: Buffer) {
    const { ValidationError } = await import('../../../utils/errors.js');
    const refusal = new ValidationError('machine cannot be named');
    state.version = preview;
    const file = path.join(dir, 'renet');
    fs.writeFileSync(file, local);
    const mod = await import('../renet-provisioner.js');
    mod.renetProvisioner.clearCache();
    const sftp = remote(null, running);
    const outcome = await mod.renetProvisioner
      .provision(CONFIG, { localBinaryPath: file, previewTouch: { refusal } }, sftp as never)
      .catch((caught: unknown) => caught);
    return { outcome, sftp, refusal };
  }

  it('does not refuse a provision that replaces nothing', async () => {
    const local = renetBytes(preview);
    const hash = createHash('sha256').update(local).digest('hex');
    const { outcome } = await unnamed({ hash, version: preview }, local);
    expect(outcome).toMatchObject({ success: true });
  });

  it('refuses a first replacement before anything is pinned or staged', async () => {
    const { outcome, sftp, refusal } = await unnamed(
      { hash: 'oldhash', version: '2.4.0' },
      renetBytes(preview)
    );
    expect(outcome).toBe(refusal);
    expect(sftp.exec.mock.calls.some(([c]) => c.includes('echo "PREVIEW_PIN'))).toBe(false);
    expect(stageMock).not.toHaveBeenCalled();
    expect(touchMock).not.toHaveBeenCalled();
  });
});

describe('the upload guard against a pending pin', () => {
  const preview = '2.5.0-preview.abc1234';

  async function guarded(guard: () => void) {
    state.version = preview;
    const file = path.join(dir, 'renet');
    fs.writeFileSync(file, renetBytes(preview));
    const mod = await import('../renet-provisioner.js');
    mod.renetProvisioner.clearCache();
    const sftp = remote(null, { hash: 'oldhash', version: '2.4.0' });
    const result = await mod.renetProvisioner.provision(
      CONFIG,
      { localBinaryPath: file, previewTouch: { machine: 'vm1' }, uploadGuard: guard },
      sftp as never
    );
    return { result, sftp };
  }

  it('leaves neither the pin nor its record behind when the guard refuses', async () => {
    const { result, sftp } = await guarded(() => {
      throw new Error('renet source is dirty');
    });
    expect(result.success).toBe(false);
    expect(result.error).toContain('renet source is dirty');
    expect(sftp.exec.mock.calls.some(([c]) => c.includes('echo "PREVIEW_PIN'))).toBe(false);
    expect(touchMock).not.toHaveBeenCalled();
    expect(stageMock).not.toHaveBeenCalled();
  });

  it('pins and records as before when the guard admits', async () => {
    const { result, sftp } = await guarded(() => undefined);
    expect(result).toMatchObject({ success: true });
    expect(sftp.exec.mock.calls.some(([c]) => c.includes('echo "PREVIEW_PIN'))).toBe(true);
    expect(touchMock).toHaveBeenCalledTimes(1);
  });
});

describe('the replacement guard around a preview renet', () => {
  it('admits a release replacing a -preview. renet that sorts above it', async () => {
    const { result } = await provision('2.4.0', renetBytes('2.4.0'), {
      hash: 'prev',
      version: '2.4.1-preview.abc1234',
    });
    expect(result).toMatchObject({ success: true });
    expect(stageMock).toHaveBeenCalledTimes(1);
  });

  it('still refuses a release replacing a newer release', async () => {
    const { result } = await provision('2.4.0', renetBytes('2.4.0'), {
      hash: 'newer',
      version: '2.5.0',
    });
    expect(result).toMatchObject({ success: false, code: 'RENET_DOWNGRADE_REFUSED' });
    expect(stageMock).not.toHaveBeenCalled();
  });

  it("still refuses what is not this CLI's build when replacing a preview renet", async () => {
    const { result } = await provision('2.5.0', renetBytes('2.7.0'), {
      hash: 'prev',
      version: '2.4.1-preview.abc1234',
    });
    expect(result).toMatchObject({ success: false, code: 'RENET_BUILD_UNVERIFIED' });
  });
});

/** A fake machine tree: slots under `root`, `current/renet` linked to one, each renet a script printing its hash. */
function tree() {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'renet-slots-'));
  const root = path.join(base, 'renet');
  fs.mkdirSync(path.join(root, 'current'), { recursive: true });
  const unitDir = path.join(base, 'units');
  fs.mkdirSync(unitDir);
  const slot = (name: string, ageDays: number, hash = `hash-${name}`): string => {
    const d = path.join(root, name);
    fs.mkdirSync(d, { recursive: true });
    fs.writeFileSync(path.join(d, 'renet'), `#!/bin/sh\necho ${hash}\n`, { mode: 0o755 });
    const when = new Date(Date.now() - ageDays * 86_400_000);
    fs.utimesSync(path.join(d, 'renet'), when, when);
    return d;
  };
  const point = (d: string) => {
    fs.rmSync(path.join(root, 'current', 'renet'), { force: true });
    fs.symlinkSync(path.join(d, 'renet'), path.join(root, 'current', 'renet'));
  };
  return { base, root, unitDir, slot, point, currentPath: path.join(root, 'current', 'renet') };
}

function sh(script: string): string {
  return execFileSync('sh', ['-c', script], { encoding: 'utf8' });
}

describe('the pin, the prune and the switch-back in a real shell', () => {
  it('a pinned slot survives three installs that prune everything else, and a control without the pin does not', () => {
    const t = tree();
    try {
      const old = t.slot('2.4.0', 90);
      const unpinned = t.slot('2.3.0', 95);
      t.point(old);
      const pin = sh(buildPinCommand(t.currentPath, ''));
      expect(parsePinOutput(pin)).toBe(old);
      expect(fs.existsSync(path.join(old, '.preview-pin'))).toBe(true);

      for (const [i, version] of [
        '2.5.0-preview.a',
        '2.5.0-preview.b',
        '2.5.0-preview.c',
      ].entries()) {
        const fresh = t.slot(version, 3 - i);
        t.point(fresh);
        sh(
          `set -eu; ${buildSlotPruneStep({
            root: t.root,
            currentPath: t.currentPath,
            installPath: path.join(fresh, 'renet'),
            unitDir: t.unitDir,
            keep: 3,
            sudo: '',
          })}`
        );
      }
      expect(fs.existsSync(path.join(old, 'renet'))).toBe(true);
      // Control: the slot nobody pinned went in the same prunes.
      expect(fs.existsSync(path.join(unpinned, 'renet'))).toBe(false);
      // The pin does not use up the keep budget: current plus the two newest others stay.
      expect(fs.existsSync(path.join(t.root, '2.5.0-preview.a'))).toBe(true);
    } finally {
      fs.rmSync(t.base, { recursive: true, force: true });
    }
  });

  const switchBack = (t: ReturnType<typeof tree>, slotDir: string, hash: string): string =>
    sh(
      buildSwitchBackBody({
        slotDir,
        expectedHash: hash,
        currentDir: path.join(t.root, 'current'),
        currentPath: t.currentPath,
        binLink: path.join(t.base, 'usr-bin-renet'),
        sudo: '',
      })
    ).trim();

  it('repoints current to the pinned slot when its hash matches, and drops the pin', () => {
    const t = tree();
    try {
      const old = t.slot('2.4.0', 90, 'hash-old');
      const fresh = t.slot('2.5.0-preview.a', 1);
      t.point(old);
      sh(buildPinCommand(t.currentPath, ''));
      t.point(fresh);

      expect(switchBack(t, old, 'hash-old')).toBe('SWITCHED');
      expect(fs.readlinkSync(t.currentPath)).toBe(path.join(old, 'renet'));
      expect(fs.existsSync(path.join(old, '.preview-pin'))).toBe(false);
      expect(fs.readlinkSync(path.join(t.base, 'usr-bin-renet'))).toBe(t.currentPath);
    } finally {
      fs.rmSync(t.base, { recursive: true, force: true });
    }
  });

  it('changes nothing when the pinned slot hash differs or the slot is gone, so the caller re-provisions', () => {
    const t = tree();
    try {
      const old = t.slot('2.4.0', 90, 'hash-changed');
      const fresh = t.slot('2.5.0-preview.a', 1);
      t.point(fresh);

      expect(switchBack(t, old, 'hash-recorded')).toBe('HASH_MISMATCH');
      expect(fs.readlinkSync(t.currentPath)).toBe(path.join(fresh, 'renet'));
      expect(switchBack(t, path.join(t.root, 'gone'), 'x')).toBe('SLOT_MISSING');
      expect(fs.readlinkSync(t.currentPath)).toBe(path.join(fresh, 'renet'));
    } finally {
      fs.rmSync(t.base, { recursive: true, force: true });
    }
  });
});

describe('switchBackToPinnedSlot', () => {
  const pinned = { slotDir: '/usr/lib/rediacc/renet/2.4.0', sha256: 'oldhash' };

  async function switchBack(output: string) {
    const mod = await import('../renet-provisioner.js');
    const exec = vi.fn((_command: string) => Promise.resolve(output));
    const refresh = vi.spyOn(mod.renetProvisioner, 'refreshRouter').mockResolvedValue(true);
    const outcome = await mod.renetProvisioner.switchBackToPinnedSlot({ exec } as never, pinned);
    return { outcome, exec, refresh };
  }

  it('runs the switch under the host install lock with its timeout exit, then moves the router onto the pinned binary', async () => {
    const { outcome, exec, refresh } = await switchBack('SWITCHED\n');
    expect(outcome).toBe('switched');
    const command = exec.mock.calls[0][0];
    expect(command).toContain("flock -w 120 -E 75 '/tmp/.rdc-renet-provision.lock' sh -c");
    expect(command).toContain('/usr/lib/rediacc/renet/2.4.0/renet');
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(refresh.mock.calls[0][1]).toBe('/usr/lib/rediacc/renet/2.4.0/renet');
  });

  it.each(['SLOT_MISSING', 'HASH_MISMATCH'])(
    'leaves the router alone when the body says %s',
    async (token) => {
      const { outcome, refresh } = await switchBack(`${token}\n`);
      expect(outcome).toBe(token === 'SLOT_MISSING' ? 'slot_missing' : 'hash_mismatch');
      expect(refresh).not.toHaveBeenCalled();
    }
  );
});
