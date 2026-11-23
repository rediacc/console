import { describe, expect, it } from 'vitest';
import {
  consoleFeedbackDeclineRequestSchema,
  consoleFeedbackPreviewRequestSchema,
  consoleFeedbackPreviewResponseSchema,
  consoleFeedbackSendRequestSchema,
  FEEDBACK_LIMITS,
  feedbackReportSchema,
  feedbackSettingsSchema,
} from '../schema.js';

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

describe('console feedback additions', () => {
  const digest = 'a'.repeat(64);

  it('parses an old CLI body (no source) as cli', () => {
    expect(feedbackReportSchema.parse(valid).source).toBe('cli');
  });

  it('keeps an explicit console source and rejects an unknown one', () => {
    expect(feedbackReportSchema.parse({ ...valid, source: 'console' }).source).toBe('console');
    expect(feedbackReportSchema.safeParse({ ...valid, source: 'web' }).success).toBe(false);
  });

  it('settings accept offerBugReports and still accept the old body', () => {
    expect(feedbackSettingsSchema.parse({ shareWithOrgAdmins: true })).toEqual({
      shareWithOrgAdmins: true,
    });
    expect(
      feedbackSettingsSchema.parse({ shareWithOrgAdmins: false, offerBugReports: false })
    ).toEqual({ shareWithOrgAdmins: false, offerBugReports: false });
    expect(
      feedbackSettingsSchema.safeParse({ shareWithOrgAdmins: false, offerBugReports: 'no' }).success
    ).toBe(false);
  });

  it('preview request needs a runId and caps the text fields', () => {
    expect(consoleFeedbackPreviewRequestSchema.safeParse({ runId: 'r1' }).success).toBe(true);
    expect(consoleFeedbackPreviewRequestSchema.safeParse({}).success).toBe(false);
    expect(
      consoleFeedbackPreviewRequestSchema.safeParse({
        runId: 'r1',
        stderrTail: 'x'.repeat(FEEDBACK_LIMITS.stderrTail + 1),
      }).success
    ).toBe(false);
  });

  it('preview response carries the body and a sha-256 digest', () => {
    const body = { ...valid, source: 'console' };
    expect(consoleFeedbackPreviewResponseSchema.safeParse({ body, digest }).success).toBe(true);
    expect(consoleFeedbackPreviewResponseSchema.safeParse({ body, digest: 'abc' }).success).toBe(
      false
    );
  });

  it('send requires the digest, decline needs only the run', () => {
    expect(consoleFeedbackSendRequestSchema.safeParse({ runId: 'r1' }).success).toBe(false);
    expect(consoleFeedbackSendRequestSchema.safeParse({ runId: 'r1', digest }).success).toBe(true);
    expect(consoleFeedbackDeclineRequestSchema.safeParse({ runId: 'r1' }).success).toBe(true);
    expect(consoleFeedbackDeclineRequestSchema.safeParse({}).success).toBe(false);
  });
});
