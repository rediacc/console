import { describe, expect, it } from 'vitest';
import { feedbackFingerprint, normalizeError, shortFeedbackFingerprint } from '../fingerprint.js';

const base = { commandPath: 'repo up', exitCode: 1 };

describe('feedbackFingerprint', () => {
  it('is 64 lowercase hex chars and a 12 char short form', async () => {
    const fp = await feedbackFingerprint({ ...base, error: 'boom' });
    expect(fp).toMatch(/^[0-9a-f]{64}$/);
    expect(shortFeedbackFingerprint(fp)).toBe(fp.slice(0, 12));
  });

  it('ignores paths, hex ids, uuids, ips and numbers', async () => {
    const a = await feedbackFingerprint({
      ...base,
      error:
        'Cannot open /home/alice/x.json id deadbeef01 pid 123 at 10.0.0.1 req 123e4567-e89b-12d3-a456-426614174000',
    });
    const b = await feedbackFingerprint({
      ...base,
      error:
        'cannot open ~/other/y.json id cafebabe99 pid 98765 at 172.16.4.9 req 00000000-0000-0000-0000-000000000000',
    });
    expect(a).toBe(b);
  });

  it('separates different messages, exit codes and commands', async () => {
    const a = await feedbackFingerprint({ ...base, error: 'timeout' });
    expect(await feedbackFingerprint({ ...base, error: 'refused' })).not.toBe(a);
    expect(await feedbackFingerprint({ ...base, exitCode: 2, error: 'timeout' })).not.toBe(a);
    expect(
      await feedbackFingerprint({ commandPath: 'repo down', exitCode: 1, error: 'timeout' })
    ).not.toBe(a);
  });

  it('normalises clock times the same way with and without seconds', () => {
    expect(normalizeError('failed at 12:30:45')).toBe(normalizeError('failed at 09:05'));
    expect(normalizeError('failed at 12:30:45')).toBe('failed at <time>');
  });

  it('still treats a colon-separated hex address as an ip', () => {
    expect(normalizeError('peer 2001:db8::1 down')).toBe('peer <ip> down');
  });

  it('collapses numbered hostnames but keeps hostnames without digits apart', () => {
    expect(normalizeError('connect to web01 refused')).toBe(
      normalizeError('connect to web02 refused')
    );
    expect(normalizeError('connect to web01 refused')).toBe('connect to web<n> refused');
    expect(normalizeError('connect to alpha refused')).not.toBe(
      normalizeError('connect to beta refused')
    );
  });

  it('normalises paths and digits', () => {
    expect(normalizeError('Failed  at /a/b 42')).toBe('failed at <path> <n>');
  });
});
