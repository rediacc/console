import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_PREVIEW_SAMPLE_ORIGIN,
} from '@rediacc/shared/config/well-known.generated';

vi.mock('../../backup/backup-store-universe.js', () => ({
  expectedAccountServerOrigin: () => WK_PREVIEW_SAMPLE_ORIGIN,
}));

import { reposWithForeignLicenseOrigin } from '../../account/license-batch.js';
import {
  buildDeleteCommand,
  buildLicenceListCommand,
  type LicenceDeps,
  licenceReportLines,
  parseLicenceListing,
  releaseLicencesOnLeave,
} from '../licences.js';

const ROOT = '/var/lib/rediacc/license';
const MASTER_KEY = 'aaaaaaaaaaaaaaaa';
const PREVIEW_KEY = 'bbbbbbbbbbbbbbbb';

function blob(subscriptionId: string, keyId: string): string {
  const payload = Buffer.from(JSON.stringify({ subscriptionId })).toString('base64');
  return JSON.stringify({ payload, signature: 'sig', publicKeyId: keyId });
}

const previewBlob = () => blob('pv-pv-amber-river-stone-0a1b2c3d', PREVIEW_KEY);
const realBlob = () => blob('sub_real_1', MASTER_KEY);

/** A machine's licence store as a path -> blob map, answering the list and delete commands. */
function machine(initial: Record<string, string>) {
  const files = new Map(Object.entries(initial));
  const commands: string[] = [];
  const exec = vi.fn((_machine: string, command: string): Promise<string> => {
    commands.push(command);
    if (command === buildLicenceListCommand()) {
      return Promise.resolve([...files].map(([p, b]) => `${p}\t${b}`).join('\n'));
    }
    if (command.startsWith('sudo rm -f -- ')) {
      for (const match of command.matchAll(/'([^']+)'/g)) files.delete(match[1]);
      return Promise.resolve('');
    }
    return Promise.reject(new Error(`unexpected command: ${command}`));
  });
  return { files, commands, exec };
}

function deps(
  m: ReturnType<typeof machine>,
  refusals: Record<string, string> = {}
): LicenceDeps & { relicense: ReturnType<typeof vi.fn> } {
  const relicense = vi.fn((_machine: string, guid: string) => {
    if (refusals[guid]) return Promise.resolve({ ok: false as const, reason: refusals[guid] });
    m.files.set(`${ROOT}/repos/${guid}/${MASTER_KEY}.json`, realBlob());
    return Promise.resolve({ ok: true as const });
  });
  return {
    exec: m.exec,
    relicense,
    repoName: (guid) => `repo-${guid}`,
  };
}

const path = (guid: string, key: string) => `${ROOT}/repos/${guid}/${key}.json`;

describe('parseLicenceListing', () => {
  it('classifies a file by the subscription id in its payload', () => {
    const files = parseLicenceListing(
      [
        `${path('g1', PREVIEW_KEY)}\t${previewBlob()}`,
        `${path('g1', MASTER_KEY)}\t${realBlob()}`,
        `${ROOT}/datastores/ds1/repos/g2/${PREVIEW_KEY}.json\t${previewBlob()}`,
      ].join('\n')
    );
    expect(files.map((f) => [f.guid, f.keyId, f.preview])).toEqual([
      ['g1', PREVIEW_KEY, true],
      ['g1', MASTER_KEY, false],
      ['g2', PREVIEW_KEY, true],
    ]);
  });

  it('refuses a listing it cannot classify instead of reading it as "not a preview file"', () => {
    expect(() => parseLicenceListing(`${path('g1', PREVIEW_KEY)}\t{not json`)).toThrow(
      /not readable JSON/
    );
    expect(() => parseLicenceListing(`/etc/passwd\t{}`)).toThrow(/unexpected licence path/);
  });

  it('refuses to delete a path outside the licence layout', () => {
    expect(() =>
      buildDeleteCommand([
        { path: '/etc/passwd', dir: '/etc', guid: 'x', keyId: 'y', preview: true },
      ])
    ).toThrow(/refusing to delete/);
  });
});

describe('releaseLicencesOnLeave', () => {
  let m: ReturnType<typeof machine>;

  beforeEach(() => {
    m = machine({});
  });

  it('leaves a repo that holds both a master and a preview file with only the master one', async () => {
    m = machine({
      [path('g1', PREVIEW_KEY)]: previewBlob(),
      [path('g1', MASTER_KEY)]: realBlob(),
    });
    const d = deps(m);
    const report = await releaseLicencesOnLeave('vm1', d);

    expect([...m.files.keys()]).toEqual([path('g1', MASTER_KEY)]);
    expect(report.cleaned).toEqual(['repo-g1']);
    expect(d.relicense).not.toHaveBeenCalled();
  });

  it('re-licenses a preview-only repo from the real account and deletes its preview file only once a real one stands', async () => {
    m = machine({ [path('g2', PREVIEW_KEY)]: previewBlob() });
    const d = deps(m);
    const report = await releaseLicencesOnLeave('vm1', d);

    expect(d.relicense).toHaveBeenCalledWith('vm1', 'g2');
    expect([...m.files.keys()]).toEqual([path('g2', MASTER_KEY)]);
    expect(report.relicensed).toEqual(['repo-g2']);
    expect(report.refused).toEqual([]);
    // The preview file was removed after the second listing showed the real one, not before the request.
    const rmAt = m.commands.findIndex((c) => c.startsWith('sudo rm'));
    expect(rmAt).toBeGreaterThan(1);
  });

  it('reports a full plan per repo with the reason, and deletes nothing', async () => {
    m = machine({
      [path('g3', PREVIEW_KEY)]: previewBlob(),
      [path('g4', PREVIEW_KEY)]: previewBlob(),
    });
    const d = deps(m, { g3: 'Plan limit reached: 5 of 5 repositories' });
    const report = await releaseLicencesOnLeave('vm1', d);

    expect(report.refused).toEqual([
      { repo: 'repo-g3', guid: 'g3', reason: 'Plan limit reached: 5 of 5 repositories' },
    ]);
    expect(report.relicensed).toEqual(['repo-g4']);
    // g3 keeps its (preview) licence so it still runs; no repo or file of g3 was deleted.
    expect(m.files.has(path('g3', PREVIEW_KEY))).toBe(true);
    expect(m.files.has(path('g4', PREVIEW_KEY))).toBe(false);
    const lines = licenceReportLines(report, WK_ACCOUNT_DEFAULT_ORIGIN).join('\n');
    expect(lines).toContain('repo-g3');
    expect(lines).toContain('Plan limit reached: 5 of 5 repositories');
    expect(lines).toContain('repo-g4');
  });

  it('counts a repo as refused when the account answered ok but no real file appeared', async () => {
    m = machine({ [path('g5', PREVIEW_KEY)]: previewBlob() });
    const d = deps(m);
    d.relicense.mockResolvedValue({ ok: true });
    const report = await releaseLicencesOnLeave('vm1', d);
    expect(report.relicensed).toEqual([]);
    expect(report.refused).toHaveLength(1);
    expect(m.files.has(path('g5', PREVIEW_KEY))).toBe(true);
  });

  it('touches nothing on a server with no preview licence', async () => {
    m = machine({ [path('g6', MASTER_KEY)]: realBlob() });
    const d = deps(m);
    const report = await releaseLicencesOnLeave('vm1', d);
    expect(report).toEqual({ machine: 'vm1', relicensed: [], cleaned: [], refused: [] });
    expect(m.commands.filter((c) => c.startsWith('sudo rm'))).toEqual([]);
  });
});

describe('a licence is requested in preview only for a repo with no master-key licence', () => {
  it('skips a repo whose installed licence names the real server, and keeps the others in the batch', () => {
    const foreign = reposWithForeignLicenseOrigin(
      [
        {
          repositoryGuid: 'master-held',
          requestedSizeGb: 1,
          currentRenewalUrl: `${WK_ACCOUNT_DEFAULT_ORIGIN}/account/api/v1/renew`,
        },
        {
          repositoryGuid: 'preview-held',
          requestedSizeGb: 1,
          currentRenewalUrl: `${WK_PREVIEW_SAMPLE_ORIGIN}/account/api/v1/renew`,
        },
        { repositoryGuid: 'unlicensed', requestedSizeGb: 1 },
      ],
      'vm1'
    );
    expect([...foreign]).toEqual(['master-held']);
  });
});
