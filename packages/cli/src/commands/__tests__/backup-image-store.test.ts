/** `rdc backup download --store`: the session reaches renet on stdin only, and every refusal names its cure. */

import { describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

import {
  LUKS_MAGIC,
  type RenetRun,
  runStoreFetch,
  type StoreFetchDeps,
} from '../../services/backup-image/store-fetch.js';

const LINEAGE = 'f6545d49-c46e-4c14-8006-0ad5b37f3e08';
const SNAP = '20260814T120000Z-0011223344556677';
const TOKEN = 'rdt_secret_token_value';
const FETCHED = JSON.stringify({ status: 'fetched', snapshotId: SNAP, bytesFetched: 42 });

function deps(over: Partial<StoreFetchDeps> = {}) {
  const runRenet = vi.fn(
    async (_r: string, _a: string[], _s: string): Promise<RenetRun> => ({
      code: 0,
      stdout: `${FETCHED}\n`,
      stderr: '',
    })
  );
  const base: StoreFetchDeps = {
    resolveLineage: vi.fn(async () => LINEAGE),
    resolveSnapshot: vi.fn(async () => SNAP),
    mintSession: vi.fn(async () => ({
      token: TOKEN,
      lineageGuid: LINEAGE,
      expiresAt: '2999-01-01T00:00:00Z',
    })),
    apiBase: () => 'https://account.example/account/api/v1/backups',
    renetPath: async () => '/usr/bin/renet',
    runRenet,
    readHead: vi.fn(async () => Buffer.concat([LUKS_MAGIC, Buffer.alloc(8)])),
    now: () => new Date('2026-08-14T12:00:00Z'),
    ...over,
  };
  return { base, runRenet };
}

describe('runStoreFetch', () => {
  it('passes the session with apiBase on stdin and checks the header', async () => {
    const { base, runRenet } = deps();
    const result = await runStoreFetch({ ref: 'mail', dest: '/d/mail.latest.img' }, base);
    expect(result.snapshotId).toBe(SNAP);
    const [renet, args, stdin] = runRenet.mock.calls[0];
    expect(renet).toBe('/usr/bin/renet');
    expect(args).toEqual([
      'backup',
      'fetch-image',
      '--dest',
      '/d/mail.latest.img',
      '--snapshot',
      SNAP,
    ]);
    const session = JSON.parse(stdin);
    expect(session).toMatchObject({
      token: TOKEN,
      lineageGuid: LINEAGE,
      apiBase: 'https://account.example/account/api/v1/backups',
    });
  });

  it('never puts the token in argv', async () => {
    const { base, runRenet } = deps();
    await runStoreFetch({ ref: 'mail', dest: '/d/x.img', at: SNAP }, base);
    const [renet, args] = runRenet.mock.calls[0];
    expect([renet, ...args].join(' ')).not.toContain(TOKEN);
  });

  it('resolves --at through the shared resolver, and the newest snapshot without it', async () => {
    const a = deps();
    await runStoreFetch({ ref: 'mail', dest: '/d/x.img', at: '2026-08-01T00:00:00Z' }, a.base);
    expect(a.base.resolveSnapshot).toHaveBeenCalledWith(LINEAGE, '2026-08-01T00:00:00Z');
    const b = deps();
    await runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, b.base);
    expect(b.base.resolveSnapshot).toHaveBeenCalledWith(LINEAGE, '2026-08-14T12:00:00.000Z');
  });

  it('turns a 403 without a recognised code into the backup:restore message', async () => {
    const { base, runRenet } = deps({
      mintSession: vi.fn(() =>
        Promise.reject(Object.assign(new Error('forbidden'), { status: 403 }))
      ),
    });
    await expect(runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, base)).rejects.toThrow(
      'errors.backupImage.storeNoScope'
    );
    expect(runRenet).not.toHaveBeenCalled();
  });

  it('a 403 from the backup:read lineage or manifest lookup names the scopes, before any mint', async () => {
    const mintSession = vi.fn();
    const { base, runRenet } = deps({
      resolveSnapshot: vi.fn(() =>
        Promise.reject(
          Object.assign(new Error('Missing required scope: backup:read'), { status: 403 })
        )
      ),
      mintSession,
    });
    await expect(runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, base)).rejects.toThrow(
      'errors.backupImage.storeNoScope'
    );
    expect(mintSession).not.toHaveBeenCalled();
    expect(runRenet).not.toHaveBeenCalled();
    // Control: a non-403 lookup failure passes through unchanged.
    const other = deps({
      resolveLineage: vi.fn(() => Promise.reject(new Error('repo not found: mail'))),
    });
    await expect(runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, other.base)).rejects.toThrow(
      'repo not found: mail'
    );
  });

  it.each([
    [404, undefined, 'storeLineageNotFound'],
    [429, undefined, 'storeRateLimited'],
    [403, 'BACKUP_RETENTION_EXPIRED', 'storeRetentionExpired'],
    [403, 'TEAM_SCOPE_REQUIRED', 'storeTeamScope'],
    [403, 'INSUFFICIENT_ORG_ROLE', 'storeRole'],
  ])('maps %s %s to %s', async (status, code, key) => {
    const { base } = deps({
      mintSession: vi.fn(() => Promise.reject(Object.assign(new Error('x'), { status, code }))),
    });
    await expect(runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, base)).rejects.toThrow(
      `errors.backupImage.${key}`
    );
  });

  it('refuses a file without the LUKS header', async () => {
    const { base } = deps({ readHead: vi.fn(async () => Buffer.from('not a luks volume')) });
    await expect(runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, base)).rejects.toThrow(
      'errors.backupImage.storeNoLuksHeader'
    );
  });

  it('reports renet failure with its reason and the resume file', async () => {
    const { base } = deps({
      runRenet: vi.fn(async () => ({
        code: 1,
        stdout: `${JSON.stringify({ status: 'failed', reason: 'chunk hash mismatch', partial: '/d/x.img.partial' })}\n`,
        stderr: '',
      })),
    });
    await expect(runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, base)).rejects.toThrow(
      /chunk hash mismatch[\s\S]*x\.img\.partial/
    );
  });
});

describe('backup download --store option refusals', () => {
  it('refuses -m, --checkpoint and --include-forks', async () => {
    vi.resetModules();
    vi.doMock('../../utils/errors.js', async (orig) => ({
      ...(await orig<typeof import('../../utils/errors.js')>()),
      getOutputFormat: () => 'json',
      handleError: (e: unknown) => {
        throw e;
      },
    }));
    const { Command } = await import('commander');
    const { registerBackupImageCommands } = await import('../backup-image.js');
    for (const flag of [['-m', 'box'], ['--checkpoint'], ['--include-forks']]) {
      const backup = new Command().exitOverride();
      registerBackupImageCommands(backup);
      await expect(
        backup.parseAsync(['download', 'mail', '--to', '/tmp', '--store', ...flag], {
          from: 'user',
        })
      ).rejects.toThrow(/errors\.backupImage\.storeRefuses/);
    }
    const backup = new Command().exitOverride();
    registerBackupImageCommands(backup);
    await expect(
      backup.parseAsync(['download', 'mail', '--to', '/tmp', '--at', 'now'], { from: 'user' })
    ).rejects.toThrow('errors.backupImage.atNeedsStore');
  });
});
