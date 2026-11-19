import { describe, expect, it } from 'vitest';
import { FEEDBACK_LIMITS, feedbackReportSchema } from '../schema.js';

const valid = {
  kind: 'bug',
  commandPath: 'repo up',
  argv: 'repo up <machine>',
  exitCode: 1,
  cliVersion: '1.0.0',
  os: 'linux',
  arch: 'x64',
  configFingerprint: 'abcdef012345',
  agent: false,
  ci: false,
};

describe('feedbackReportSchema', () => {
  it('accepts a valid report', () => {
    expect(feedbackReportSchema.safeParse(valid).success).toBe(true);
  });

  it('rejects an unknown kind and a bad config fingerprint', () => {
    expect(feedbackReportSchema.safeParse({ ...valid, kind: 'other' }).success).toBe(false);
    expect(feedbackReportSchema.safeParse({ ...valid, configFingerprint: 'xyz' }).success).toBe(
      false
    );
  });

  const capped = [
    'commandPath',
    'argv',
    'errorCode',
    'errorMessage',
    'stderrTail',
    'message',
    'cliVersion',
    'os',
    'arch',
  ] as const;
  for (const field of capped) {
    it(`enforces the ${field} cap`, () => {
      const max = FEEDBACK_LIMITS[field];
      const atCap = { ...valid, [field]: 'a'.repeat(max) };
      const over = { ...valid, [field]: 'a'.repeat(max + 1) };
      expect(feedbackReportSchema.safeParse(atCap).success).toBe(true);
      expect(feedbackReportSchema.safeParse(over).success).toBe(false);
    });
  }
});
