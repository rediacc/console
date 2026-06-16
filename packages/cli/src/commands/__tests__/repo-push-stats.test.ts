import { beforeEach, describe, expect, it, vi } from 'vitest';

// i18n stub — return key + interpolated params for assertable strings
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockSuccess = vi.hoisted(() => vi.fn());
vi.mock('../../services/output.js', () => ({
  outputService: { success: mockSuccess, info: vi.fn(), print: vi.fn() },
}));

import { extractPushResult, renderPushStats } from '../repo-push-stats.js';

const fullResult = {
  repository: 'my-app',
  destination: '3f2c1a9b-aaaa-bbbb-cccc-1234567890ab',
  destinationType: 'machine',
  size: 1073741824,
  transferredAt: '2026-06-11T10:30:00Z',
  method: 'rsync',
  duration: '41s',
  transferMode: 'full' as const,
  transferredBytes: 1073873033,
  transferMs: 41000,
};

describe('extractPushResult', () => {
  it('parses a bare push_result line', () => {
    const stdout = `${JSON.stringify({ push_result: fullResult })}\n`;
    expect(extractPushResult(stdout)).toEqual(fullResult);
  });

  it('parses a bridge-prefixed push_result line interleaved with logs', () => {
    const stdout = [
      '[backup_push] Pushing repository to machine',
      'time="2026-06-11T10:30:00Z" level=info msg="Transferring data..."',
      '[backup_push] sent 1,073,873,033 bytes  received 35 bytes  82,605,618.69 bytes/sec',
      `[backup_push] {"steps":[{"name":"transfer","duration_ms":41000}]}`,
      `[backup_push] ${JSON.stringify({ push_result: fullResult })}`,
      '[backup_push] done',
    ].join('\n');
    expect(extractPushResult(stdout)).toEqual(fullResult);
  });

  it('returns undefined when no push_result line is present', () => {
    const stdout = [
      '[backup_push] Transferring data...',
      '{"steps":[{"name":"transfer","duration_ms":41000}]}',
      'not json at all',
    ].join('\n');
    expect(extractPushResult(stdout)).toBeUndefined();
  });

  it('returns undefined for empty/missing stdout', () => {
    expect(extractPushResult(undefined)).toBeUndefined();
    expect(extractPushResult('')).toBeUndefined();
  });

  it('ignores malformed push_result objects (missing required fields)', () => {
    const stdout = `{"push_result":{"repository":"x"}}`;
    expect(extractPushResult(stdout)).toBeUndefined();
  });
});

describe('renderPushStats', () => {
  beforeEach(() => {
    mockSuccess.mockClear();
  });

  it('renders the delta line with shortened base and image size', () => {
    renderPushStats('my-app', 'machine-12', {
      ...fullResult,
      transferMode: 'delta',
      transferredBytes: 52166656,
      deltaBase: '3f2c1a9b-aaaa-bbbb-cccc-1234567890ab',
      transferMs: 6200,
    });
    expect(mockSuccess).toHaveBeenCalledOnce();
    const msg = mockSuccess.mock.calls[0][0] as string;
    expect(msg).toContain('commands.repo.push.statsDelta');
    expect(msg).toContain('"transferred":"49.8 MB"');
    expect(msg).toContain('"duration":"6.2s"');
    expect(msg).toContain('"base":"3f2c1a9b…"');
    expect(msg).toContain('"image":"1.0 GB"');
  });

  it('renders the full line with transferred bytes', () => {
    renderPushStats('my-app', 'machine-12', fullResult);
    const msg = mockSuccess.mock.calls[0][0] as string;
    expect(msg).toContain('commands.repo.push.statsFull');
    expect(msg).toContain('"transferred":"1.0 GB"');
    expect(msg).toContain('"duration":"41.0s"');
  });

  it('omits the byte figure when transferredBytes is -1', () => {
    renderPushStats('my-app', 'machine-12', { ...fullResult, transferredBytes: -1 });
    const msg = mockSuccess.mock.calls[0][0] as string;
    expect(msg).toContain('commands.repo.push.statsNoBytes');
    expect(msg).not.toContain('transferred"');
  });
});
