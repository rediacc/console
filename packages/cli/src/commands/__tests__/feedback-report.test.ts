import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  print: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
  format: { current: 'table' },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: m.print, info: m.info, success: m.success },
}));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => m.format.current,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: 'missing' }),
}));
vi.mock('../../services/config/config-name.js', () => ({
  getEffectiveConfigName: () => 'rediacc',
}));
vi.mock('../../utils/agent-guard.js', () => ({ isAgentEnvironment: () => false }));
vi.mock('../../utils/prompt.js', () => ({ askConfirm: vi.fn() }));

import { findInstalledFreeBlob } from '../../services/feedback/free-blob.js';
import type { RingEntry } from '../../services/feedback/ring.js';
import {
  type FeedbackAuth,
  type FetchFn,
  resolveFeedbackAuth,
} from '../../services/feedback/send.js';
import { type ReportDeps, runReport } from '../feedback.js';

const entry = (over: Partial<RingEntry>): RingEntry => ({
  at: '2026-11-19T10:00:00.000Z',
  commandPath: 'repo up',
  argv: 'repo up shop@<machine>',
  exitCode: 1,
  stderrTail: 'boom',
  cliVersion: '1.2.3',
  ...over,
});

// Oldest first, as the ring file stores them.
const RING = [
  entry({ argv: 'repo up old', exitCode: 1, errorMessage: 'older failure' }),
  entry({ argv: 'repo up newest-failed', exitCode: 2, errorMessage: 'newest failure' }),
  entry({ argv: 'status', commandPath: 'status', exitCode: 0 }),
];
const BLOB = { payload: 'p', signature: 's', publicKeyId: '0123456789abcdef' };

function deps(over: Partial<ReportDeps> = {}) {
  const fetchFn = vi.fn().mockResolvedValue({
    id: 'r1',
    fingerprint: 'a'.repeat(64),
    status: 'new',
    duplicate: false,
  });
  const confirm = vi.fn().mockResolvedValue(true);
  const auth: FeedbackAuth = { kind: 'token' };
  const full: ReportDeps = {
    readRing: () => RING,
    resolveAuth: async () => auth,
    confirm,
    fetchFn: fetchFn as unknown as FetchFn,
    yes: () => false,
    agent: () => false,
    ...over,
  };
  return { full, fetchFn, confirm };
}

beforeEach(() => {
  m.format.current = 'table';
  vi.clearAllMocks();
});

describe('rdc feedback report', () => {
  it('--last fills from the newest failed ring entry, skipping a newer success', async () => {
    const { full, fetchFn } = deps();
    await runReport({ last: true }, full);
    const body = fetchFn.mock.calls[0][1].body;
    expect(body).toMatchObject({ argv: 'repo up newest-failed', exitCode: 2, kind: 'bug' });
  });

  it('--command picks by newest-first index; a bad index is refused (control)', async () => {
    const { full, fetchFn } = deps();
    await runReport({ command: '3' }, full);
    expect(fetchFn.mock.calls[0][1].body).toMatchObject({ argv: 'repo up old' });
    await expect(runReport({ command: '9' }, deps().full)).rejects.toThrow(
      'feedback.noSuchCommand'
    );
  });

  it('the preview is exactly the body that is sent', async () => {
    const { full, fetchFn } = deps({ yes: () => true });
    await runReport({ last: true, message: 'it hangs' }, full);
    const printed = m.print.mock.calls[0][0] as string;
    expect(JSON.parse(printed)).toEqual(fetchFn.mock.calls[0][1].body);
    expect(printed).toContain('it hangs');
  });

  it('a declined confirm sends nothing; an accepted one sends (control)', async () => {
    const declined = deps({ confirm: vi.fn().mockResolvedValue(false) });
    await runReport({ last: true }, declined.full);
    expect(declined.fetchFn).not.toHaveBeenCalled();
    const accepted = deps();
    await runReport({ last: true }, accepted.full);
    expect(accepted.confirm).toHaveBeenCalledOnce();
    expect(accepted.fetchFn).toHaveBeenCalledOnce();
  });

  it('--yes sends without asking', async () => {
    const { full, fetchFn, confirm } = deps({ yes: () => true });
    await runReport({ last: true }, full);
    expect(confirm).not.toHaveBeenCalled();
    expect(fetchFn).toHaveBeenCalledOnce();
  });

  it('an agent without --yes gets the preview and a next, and nothing is sent', async () => {
    const { full, fetchFn, confirm } = deps({ agent: () => true });
    m.format.current = 'json';
    await runReport({ last: true }, full);
    expect(fetchFn).not.toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
    const data = m.print.mock.calls[0][0];
    expect(data.sent).toBe(false);
    expect(data.preview).toMatchObject({ argv: 'repo up newest-failed' });
    expect(data.next.options[0].run).toBe('rdc feedback report --last --yes');
  });

  it('an agent with --yes sends (control)', async () => {
    const { full, fetchFn } = deps({ agent: () => true, yes: () => true });
    await runReport({ last: true }, full);
    expect(fetchFn).toHaveBeenCalledOnce();
  });

  it('no token and no FREE blob is a refusal naming both routes', async () => {
    const error = await resolveFeedbackAuth({
      tokenReady: () => false,
      freeBlob: () => undefined,
      machineId: async () => 'x',
    }).catch((e: unknown) => e as { next: { options: { run: string }[] } });
    expect(error.next.options.map((o) => o.run)).toEqual([
      'rdc subscription login',
      'rdc repo create --help',
    ]);
  });

  it('a stored token wins over an installed FREE blob; a blob is used without one (control)', async () => {
    const blobDeps = { freeBlob: () => BLOB, machineId: async () => 'mid' };
    expect(await resolveFeedbackAuth({ tokenReady: () => true, ...blobDeps })).toEqual({
      kind: 'token',
    });
    expect(await resolveFeedbackAuth({ tokenReady: () => false, ...blobDeps })).toEqual({
      kind: 'free',
      credential: { license: BLOB, machineId: 'mid' },
    });
  });

  it('a FREE blob rides in the body with noAuth; a token sends the report alone', async () => {
    const free = deps({
      yes: () => true,
      resolveAuth: async () => ({
        kind: 'free',
        credential: { license: BLOB, machineId: 'mid' },
      }),
    });
    await runReport({ last: true }, free.full);
    expect(free.fetchFn.mock.calls[0][1]).toMatchObject({
      noAuth: true,
      body: { license: BLOB, machineId: 'mid' },
    });
    const token = deps({ yes: () => true });
    await runReport({ last: true }, token.full);
    expect(token.fetchFn.mock.calls[0][1].noAuth).toBeUndefined();
    expect(token.fetchFn.mock.calls[0][1].body).not.toHaveProperty('license');
  });

  it('a 429 daily limit names the reset time; another failure passes through (control)', async () => {
    const limited = Object.assign(new Error('x'), {
      status: 429,
      code: 'FEEDBACK_DAILY_LIMIT',
      details: { subjectKind: 'user', resetAt: '2026-11-20T00:00:00Z' },
    });
    const a = deps({ yes: () => true });
    a.fetchFn.mockRejectedValue(limited);
    await expect(runReport({ last: true }, a.full)).rejects.toMatchObject({
      code: 'FEEDBACK_DAILY_LIMIT',
      exitCode: 9,
      message: expect.stringContaining('2026-11-20T00:00:00Z'),
    });
    const other = deps({ yes: () => true });
    other.fetchFn.mockRejectedValue(Object.assign(new Error('down'), { status: 500 }));
    await expect(runReport({ last: true }, other.full)).rejects.toThrow('down');
  });

  it('refuses without a failed command or a message, and --last with --command', async () => {
    await expect(runReport({}, deps().full)).rejects.toThrow('feedback.needsMessage');
    await expect(
      runReport({ last: true }, deps({ readRing: () => [RING[2]] }).full)
    ).rejects.toThrow('feedback.noFailedCommand');
    await expect(runReport({ last: true, command: '1' }, deps().full)).rejects.toThrow(
      'feedback.lastAndCommand'
    );
  });

  it('a message alone files a feedback report; a bad kind is refused (control)', async () => {
    const { full, fetchFn } = deps({ yes: () => true });
    await runReport({ message: 'nice tool' }, full);
    expect(fetchFn.mock.calls[0][1].body).toMatchObject({ kind: 'feedback', exitCode: 0 });
    await expect(runReport({ message: 'x', kind: 'nope' }, deps().full)).rejects.toThrow(
      'feedback.badKind'
    );
  });

  it('--list-recent prints newest first and sends nothing', async () => {
    const { full, fetchFn } = deps();
    await runReport({ listRecent: true }, full);
    expect(m.print.mock.calls[0][0]).toMatch(/^1 .*status/);
    expect(fetchFn).not.toHaveBeenCalled();
  });
});

describe('findInstalledFreeBlob', () => {
  let root: string;
  beforeEach(() => {
    root = mkdtempSync(path.join(tmpdir(), 'free-blob-'));
  });
  afterEach(() => rmSync(root, { recursive: true, force: true }));

  const install = (rel: string, subscriptionId: string) => {
    const dir = path.join(root, rel);
    mkdirSync(dir, { recursive: true });
    const payload = Buffer.from(JSON.stringify({ subscriptionId })).toString('base64');
    writeFileSync(
      path.join(dir, '0123456789abcdef.json'),
      JSON.stringify({ payload, signature: 's', publicKeyId: '0123456789abcdef' })
    );
  };

  it('finds a FREE blob in a datastore-scoped population and ignores a paid one', () => {
    install('repos/g1', 'sub_paid');
    expect(findInstalledFreeBlob(root)).toBeUndefined();
    install('datastores/ds1/repos/g2', 'free:abc');
    expect(findInstalledFreeBlob(root)?.publicKeyId).toBe('0123456789abcdef');
  });
});
