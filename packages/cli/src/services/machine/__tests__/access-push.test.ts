/**
 * The access push (PLAN-ssh-key-source-ranges A1). The SFTP side is a fake over
 * a real temp directory, and the compare-and-swap script the push builds runs
 * in a real `sh` against it, so the hash check is exercised, not asserted on.
 */
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { AccessSchema } from '@rediacc/shared/config-schema';
import ssh2 from 'ssh2';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const CONFIG_ID = '0f3c9a21-7d4e-4b6a-9c11-2e5f8d7a6b30';
const HOSTED = { ipv4: ['104.28.0.0/16'], ipv6: ['2a09:bac0::/29'] };

function keyPair(comment: string): { privateKey: string; publicKey: string } {
  const keys = ssh2.utils.generateKeyPairSync('ed25519', { comment });
  return { privateKey: keys.private, publicKey: keys.public };
}

const SESSION = keyPair('team');
const PROBE = keyPair('rediacc-live-console-probe');

interface Fake {
  root: string;
  home: string;
  sshConnection: string;
  sessionPublicKey?: string;
  /** Runs after an SFTP writeFile, to simulate a concurrent writer. */
  afterWrite?: (path: string) => void;
  writes: string[];
  swaps: string[];
  deletes: string[];
}

let fake: Fake;
let access: Record<string, unknown> | undefined;

function runSh(script: string): number {
  const result = spawnSync('sh', ['-c', script], { encoding: 'utf8' });
  return result.status ?? 255;
}

const fakeSftp = {
  exec: vi.fn((command: string) => {
    if (command.includes('$HOME')) {
      return Promise.resolve(`${fake.home}\n${fake.sshConnection}\n`);
    }
    const code = runSh(command);
    if (code !== 0) return Promise.reject(new Error(`Command exited with code ${code}`));
    return Promise.resolve('');
  }),
  execStreaming: vi.fn((command: string) => {
    fake.swaps.push(command);
    return Promise.resolve(runSh(command));
  }),
  exists: vi.fn((path: string) => Promise.resolve(existsSync(path))),
  readFile: vi.fn((path: string) => Promise.resolve(readFileSync(path))),
  writeFile: vi.fn((path: string, data: Buffer) => {
    writeFileSync(path, data);
    fake.writes.push(path);
    fake.afterWrite?.(path);
    return Promise.resolve();
  }),
  delete: vi.fn((path: string) => {
    fake.deletes.push(path);
    try {
      rmSync(path);
    } catch (error) {
      return Promise.reject(error);
    }
    return Promise.resolve();
  }),
};

const release = vi.fn();

vi.mock('../machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn(async () => ({
      sftp: fakeSftp,
      machine: { ip: '72.61.137.225', user: 'muhammed' },
      sshPrivateKey: SESSION.privateKey,
      ensure: vi.fn(),
      release,
    })),
  },
}));

vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn(async () => ({ id: CONFIG_ID, version: 3, access })),
    getLocalConfig: vi.fn(async () => ({ sshPublicKey: fake.sessionPublicKey })),
  },
}));

const {
  pushAccess,
  buildSwapScript,
  desiredAccessKeys,
  AccessFileChangedError,
  AccessLockoutError,
} = await import('../access-push.js');

function sha256(text: string): string {
  return createHash('sha256').update(text).digest('hex');
}

function authorizedKeysPath(): string {
  return join(fake.home, '.ssh', 'authorized_keys');
}

function probeAccess(publicKey = PROBE.publicKey): Record<string, unknown> {
  return {
    sourceRanges: HOSTED,
    keys: { 'console-probe': { publicKey, machines: { hostinger: true } } },
  };
}

const EXISTING = `${SESSION.publicKey} laptop\n# a comment\n`;

beforeEach(() => {
  const root = mkdtempSync(join(tmpdir(), 'access-push-'));
  const home = join(root, 'home', 'muhammed');
  mkdirSync(join(home, '.ssh'), { recursive: true });
  writeFileSync(join(home, '.ssh', 'authorized_keys'), EXISTING);
  fake = {
    root,
    home,
    sshConnection: '104.28.154.80 51234 72.61.137.225 22',
    writes: [],
    swaps: [],
    deletes: [],
  };
  access = probeAccess();
  vi.clearAllMocks();
});

afterEach(() => {
  rmSync(fake.root, { recursive: true, force: true });
});

function sshDirEntries(): string[] {
  return readdirSync(join(fake.home, '.ssh')).sort();
}

describe('pushAccess', () => {
  it('an unchanged plan makes zero writeFile calls', async () => {
    await pushAccess('hostinger');
    const before = readFileSync(authorizedKeysPath(), 'utf8');
    vi.clearAllMocks();
    fake.writes = [];
    fake.swaps = [];

    const report = await pushAccess('hostinger');

    expect(report.written).toBe(false);
    expect(report.changes.map((c) => c.action)).toEqual(['unchanged']);
    expect(fakeSftp.writeFile).not.toHaveBeenCalled();
    expect(fakeSftp.execStreaming).not.toHaveBeenCalled();
    expect(readFileSync(authorizedKeysPath(), 'utf8')).toBe(before);
    expect(release).toHaveBeenCalledOnce();
  });

  it('a changed plan writes the temp file and swaps it in with the recorded sha256', async () => {
    const report = await pushAccess('hostinger');

    expect(report).toMatchObject({
      machine: 'hostinger',
      path: authorizedKeysPath(),
      written: true,
    });
    expect(report.changes.map((c) => [c.key, c.action, c.line])).toEqual([
      ['console-probe', 'append', 3],
    ]);
    expect(fake.writes).toHaveLength(1);
    expect(fake.writes[0]).toMatch(/\/\.ssh\/\.authorized_keys\.rdc-[0-9a-f]{16}$/);
    expect(fake.swaps).toHaveLength(1);
    expect(fake.swaps[0]).toContain(`want='${sha256(EXISTING)}'`);

    const after = readFileSync(authorizedKeysPath(), 'utf8');
    const lines = after.split('\n');
    expect(lines.slice(0, 2).join('\n')).toBe(EXISTING.trimEnd());
    expect(lines[2]).toMatch(
      /^from="104\.28\.0\.0\/16,2a09:bac0::\/29",no-port-forwarding,.* rdc-access:0f3c9a21:console-probe$/
    );
    // The temp file is gone and the result carries the modes sshd requires.
    expect(sshDirEntries()).toEqual(['authorized_keys']);
    expect(spawnSync('stat', ['-c', '%a', authorizedKeysPath()]).stdout.toString().trim()).toBe(
      '600'
    );
    expect(
      spawnSync('stat', ['-c', '%a', join(fake.home, '.ssh')])
        .stdout.toString()
        .trim()
    ).toBe('700');
  });

  it('a file changed between read and swap gives ACCESS_FILE_CHANGED and removes the temp file', async () => {
    const concurrent = `${EXISTING}ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEhHFMWEgJsVTETiAlNItf/5IPfpQLAj7TO/dLNDmeKg other\n`;
    fake.afterWrite = () => writeFileSync(authorizedKeysPath(), concurrent);

    const error = await pushAccess('hostinger').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(AccessFileChangedError);
    expect(error).toMatchObject({ code: 'ACCESS_FILE_CHANGED', retryable: true });
    expect(readFileSync(authorizedKeysPath(), 'utf8')).toBe(concurrent);
    expect(sshDirEntries()).toEqual(['authorized_keys']);
    expect(release).toHaveBeenCalledOnce();
  });

  it('a missing authorized_keys reads as empty and is created', async () => {
    rmSync(join(fake.home, '.ssh'), { recursive: true });

    const report = await pushAccess('hostinger');

    expect(report.written).toBe(true);
    expect(report.changes.map((c) => c.action)).toEqual(['append']);
    expect(fake.swaps[0]).toContain("want='absent'");
    expect(readFileSync(authorizedKeysPath(), 'utf8').split('\n')).toHaveLength(2);
  });

  it('refuses ACCESS_LOCKOUT with zero writes when the session key is desired and the address is outside its ranges', async () => {
    access = probeAccess(SESSION.publicKey);
    fake.sshConnection = '203.0.113.7 51234 72.61.137.225 22';

    const error = await pushAccess('hostinger').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(AccessLockoutError);
    expect(error).toMatchObject({ code: 'ACCESS_LOCKOUT', clientAddress: '203.0.113.7' });
    expect((error as Error).message).toMatch(
      /do not contain this session's source address 203\.0\.113\.7; pushing would lock the CLI out, so nothing was written$/
    );
    expect(fakeSftp.writeFile).not.toHaveBeenCalled();
    expect(fakeSftp.execStreaming).not.toHaveBeenCalled();
    expect(readFileSync(authorizedKeysPath(), 'utf8')).toBe(EXISTING);
  });

  it('refuses ACCESS_LOCKOUT when only the configured public key names the session key', async () => {
    const other = keyPair('configured');
    fake.sessionPublicKey = other.publicKey;
    access = probeAccess(other.publicKey);
    fake.sshConnection = '203.0.113.7 51234 72.61.137.225 22';

    await expect(pushAccess('hostinger')).rejects.toBeInstanceOf(AccessLockoutError);
    expect(fakeSftp.writeFile).not.toHaveBeenCalled();
  });

  it('the session key inside its ranges proceeds', async () => {
    access = probeAccess(SESSION.publicKey);
    fake.sshConnection = '2a09:bac1:5540:28::3e4:28 51234 2a02:4780::1 22';

    const report = await pushAccess('hostinger');
    expect(report.written).toBe(true);
    expect(report.changes.map((c) => c.action)).toEqual(['adopt']);
  });

  it('a different session key proceeds from an out-of-range address', async () => {
    fake.sshConnection = '203.0.113.7 51234 72.61.137.225 22';

    const report = await pushAccess('hostinger');
    expect(report.written).toBe(true);
  });

  it('--dry-run never writes', async () => {
    const report = await pushAccess('hostinger', { dryRun: true });

    expect(report.written).toBe(false);
    expect(report.changes.map((c) => c.action)).toEqual(['append']);
    expect(fakeSftp.writeFile).not.toHaveBeenCalled();
    expect(fakeSftp.execStreaming).not.toHaveBeenCalled();
    expect(readFileSync(authorizedKeysPath(), 'utf8')).toBe(EXISTING);
  });

  it('a machine with no binding removes only this config’s marked lines', async () => {
    await pushAccess('hostinger');
    access = undefined;

    const report = await pushAccess('hostinger');
    expect(report.changes.map((c) => c.action)).toEqual(['remove']);
    expect(readFileSync(authorizedKeysPath(), 'utf8')).toBe(EXISTING);
  });
});

describe('the lockout guard on removal (review c29ac396.1)', () => {
  it('refuses ACCESS_LOCKOUT when dropping the binding would remove the session key’s last line', async () => {
    access = probeAccess(SESSION.publicKey);
    fake.sshConnection = '2a09:bac1:5540:28::3e4:28 51234 2a02:4780::1 22';
    const adopted = await pushAccess('hostinger');
    expect(adopted.changes.map((c) => c.action)).toEqual(['adopt']);
    const before = readFileSync(authorizedKeysPath(), 'utf8');
    vi.clearAllMocks();
    access = undefined;

    const error = await pushAccess('hostinger').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(AccessLockoutError);
    expect(error).toMatchObject({
      code: 'ACCESS_LOCKOUT',
      keyName: 'console-probe',
      removal: true,
    });
    expect(fakeSftp.writeFile).not.toHaveBeenCalled();
    expect(fakeSftp.execStreaming).not.toHaveBeenCalled();
    expect(readFileSync(authorizedKeysPath(), 'utf8')).toBe(before);
  });

  it('removes the session key’s marked line when another line still carries the key', async () => {
    access = probeAccess(SESSION.publicKey);
    fake.sshConnection = '2a09:bac1:5540:28::3e4:28 51234 2a02:4780::1 22';
    await pushAccess('hostinger');
    // A line added by hand after the adopt keeps the session key authorized.
    writeFileSync(
      authorizedKeysPath(),
      `${readFileSync(authorizedKeysPath(), 'utf8')}${SESSION.publicKey} re-added\n`
    );
    access = undefined;

    const report = await pushAccess('hostinger');
    expect(report.changes.map((c) => c.action)).toEqual(['remove']);
    expect(report.written).toBe(true);
  });
});

describe('buildSwapScript (review c29ac396.2)', () => {
  it('runs every preparatory step before the hash, so only the check separates the hash from the mv', () => {
    const lines = buildSwapScript(
      '/h/.ssh',
      '/h/.ssh/authorized_keys',
      '/h/.ssh/.t',
      'absent'
    ).split('\n');
    const check = lines.findIndex((line) => line.includes('"$have" != "$want"'));
    const hash = lines.findIndex((line) => line.includes('have=$(sum'));
    const modes = lines.findIndex((line) => line.includes('chmod 600 "$t"'));
    expect(check).toBeGreaterThan(hash);
    expect(hash).toBe(check - 1);
    expect(modes).toBeLessThan(hash);
    expect(lines.slice(check + 1)).toEqual(['mv -f "$t" "$f"']);
  });
});

describe('desiredAccessKeys', () => {
  it('a plain binding takes the key ranges and an object binding its own; unbound keys are skipped', () => {
    const own = { ipv4: ['198.51.100.0/24'] };
    const desired = desiredAccessKeys(
      AccessSchema.parse({
        sourceRanges: HOSTED,
        keys: {
          plain: { publicKey: PROBE.publicKey, machines: { hostinger: true } },
          ranged: { publicKey: SESSION.publicKey, machines: { hostinger: { sourceRanges: own } } },
          other: { publicKey: keyPair('other').publicKey, machines: { edge: true } },
        },
      }),
      'hostinger'
    );
    expect(desired.map((d) => [d.name, d.ranges])).toEqual([
      ['plain', HOSTED],
      ['ranged', own],
    ]);
  });
});

describe('dropAccessBindings (machine remove)', () => {
  const load = async () =>
    (
      await vi.importActual<typeof import('../../config/config-resources.js')>(
        '../../config/config-resources.js'
      )
    ).dropAccessBindings;

  it('drops the machine from every key and leaves other bindings alone', async () => {
    const dropAccessBindings = await load();
    const result = dropAccessBindings(
      {
        sourceRanges: HOSTED,
        keys: {
          a: { publicKey: PROBE.publicKey, machines: { hostinger: true, edge: true } },
          b: { publicKey: SESSION.publicKey, machines: { edge: true } },
        },
      },
      'hostinger'
    );
    expect(result.keys?.a.machines).toEqual({ edge: true });
    expect(result.keys?.b.machines).toEqual({ edge: true });
  });

  it('a key whose only range was the dropped binding keeps that range on the key', async () => {
    const dropAccessBindings = await load();
    const ranges = { ipv6: ['2a09:bac0::/29'] };
    const result = dropAccessBindings(
      {
        keys: {
          a: { publicKey: PROBE.publicKey, machines: { hostinger: { sourceRanges: ranges } } },
        },
      },
      'hostinger'
    );
    expect(result.keys?.a).toEqual({
      publicKey: PROBE.publicKey,
      machines: {},
      sourceRanges: ranges,
    });
    expect(AccessSchema.safeParse(result).success).toBe(true);
  });

  it('a plain binding hands the key no range when the config supplies one', async () => {
    const dropAccessBindings = await load();
    const result = dropAccessBindings(
      {
        sourceRanges: HOSTED,
        keys: { a: { publicKey: PROBE.publicKey, machines: { hostinger: true } } },
      },
      'hostinger'
    );
    expect(result.keys?.a).toEqual({ publicKey: PROBE.publicKey, machines: {} });
    expect(AccessSchema.safeParse(result).success).toBe(true);
  });
});
