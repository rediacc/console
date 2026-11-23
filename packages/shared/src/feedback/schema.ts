/** Wire schemas for feedback reports, shared by the CLI and the account routes. */
import { z } from 'zod';

export const FEEDBACK_KINDS = ['bug', 'feedback', 'docs'] as const;
export const FEEDBACK_STATUSES = [
  'new',
  'screening',
  'quarantined',
  'confirmed',
  'planned',
  'fixed',
  'rejected',
] as const;

export const FEEDBACK_LIMITS = {
  commandPath: 128,
  argv: 1024,
  errorCode: 64,
  errorMessage: 1024,
  stderrTail: 4096,
  message: 2048,
  cliVersion: 32,
  os: 32,
  arch: 32,
} as const;

export const FEEDBACK_SOURCES = ['cli', 'console'] as const;

export const feedbackKindSchema = z.enum(FEEDBACK_KINDS);
export const feedbackStatusSchema = z.enum(FEEDBACK_STATUSES);
export const feedbackSourceSchema = z.enum(FEEDBACK_SOURCES);

export const feedbackReportSchema = z.object({
  kind: feedbackKindSchema,
  commandPath: z.string().max(FEEDBACK_LIMITS.commandPath),
  argv: z.string().max(FEEDBACK_LIMITS.argv),
  exitCode: z.number().int(),
  errorCode: z.string().max(FEEDBACK_LIMITS.errorCode).optional(),
  errorMessage: z.string().max(FEEDBACK_LIMITS.errorMessage).optional(),
  stderrTail: z.string().max(FEEDBACK_LIMITS.stderrTail).optional(),
  message: z.string().max(FEEDBACK_LIMITS.message).optional(),
  cliVersion: z.string().max(FEEDBACK_LIMITS.cliVersion),
  os: z.string().max(FEEDBACK_LIMITS.os),
  arch: z.string().max(FEEDBACK_LIMITS.arch),
  configFingerprint: z.string().regex(/^[0-9a-f]{12}$/),
  agent: z.boolean(),
  ci: z.boolean(),
  /** Where the report came from. A body without it is an old CLI's and parses as `cli`. */
  source: feedbackSourceSchema.default('cli'),
});
type FeedbackReport = z.infer<typeof feedbackReportSchema>;
export type { FeedbackReport };

export const feedbackSubmitResponseSchema = z.object({
  id: z.string(),
  fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  status: feedbackStatusSchema,
  duplicate: z.boolean(),
});
type FeedbackSubmitResponse = z.infer<typeof feedbackSubmitResponseSchema>;
export type { FeedbackSubmitResponse };

export const feedbackListItemSchema = z.object({
  id: z.string(),
  /** Short display form (shortFeedbackFingerprint); the submit response carries the full 64. */
  fingerprint: z.string().regex(/^[0-9a-f]{12}$/),
  kind: feedbackKindSchema,
  status: feedbackStatusSchema,
  fixedIn: z.string().nullable(),
  commandPath: z.string(),
  occurrenceCount: z.number().int().min(1),
  firstSeenAt: z.string(),
  lastSeenAt: z.string(),
});
type FeedbackListItem = z.infer<typeof feedbackListItemSchema>;
export type { FeedbackListItem };

export const feedbackListResponseSchema = z.object({ reports: z.array(feedbackListItemSchema) });
type FeedbackListResponse = z.infer<typeof feedbackListResponseSchema>;
export type { FeedbackListResponse };

export const feedbackSettingsSchema = z.object({
  shareWithOrgAdmins: z.boolean(),
  /**
   * Whether the console may offer a bug report after a Rediacc-origin failure. Absent means the
   * default, on; the account routes (AF3) store and return it once the column exists (AF2).
   */
  offerBugReports: z.boolean().optional(),
});
type FeedbackSettings = z.infer<typeof feedbackSettingsSchema>;
export type { FeedbackSettings };

export const feedbackLimitErrorSchema = z.object({
  code: z.literal('FEEDBACK_DAILY_LIMIT'),
  subjectKind: z.enum(['user', 'org', 'machine']),
  resetAt: z.string(),
});
type FeedbackLimitError = z.infer<typeof feedbackLimitErrorSchema>;
export type { FeedbackLimitError };

/**
 * Console bug-report offers (agent/plans/PLAN-console-ai-feedback.md D3). The preview request names
 * the run and the user-editable text; the worker takes the command path, exit code and error code
 * from the run row and returns the exact body with a digest of its canonical JSON.
 */
export const consoleFeedbackPreviewRequestSchema = z.object({
  runId: z.string().min(1),
  message: z.string().max(FEEDBACK_LIMITS.message).optional(),
  stderrTail: z.string().max(FEEDBACK_LIMITS.stderrTail).optional(),
  env: z
    .object({
      cliVersion: z.string().max(FEEDBACK_LIMITS.cliVersion),
      os: z.string().max(FEEDBACK_LIMITS.os),
      arch: z.string().max(FEEDBACK_LIMITS.arch),
    })
    .optional(),
});
type ConsoleFeedbackPreviewRequest = z.infer<typeof consoleFeedbackPreviewRequestSchema>;
export type { ConsoleFeedbackPreviewRequest };

export const consoleFeedbackPreviewResponseSchema = z.object({
  body: feedbackReportSchema,
  /** SHA-256 of the body's canonical JSON, lowercase hex. */
  digest: z.string().regex(/^[0-9a-f]{64}$/),
});
type ConsoleFeedbackPreviewResponse = z.infer<typeof consoleFeedbackPreviewResponseSchema>;
export type { ConsoleFeedbackPreviewResponse };

/** Send posts the preview's inputs plus its digest; the worker rebuilds the body and refuses a mismatch. */
export const consoleFeedbackSendRequestSchema = consoleFeedbackPreviewRequestSchema.extend({
  digest: z.string().regex(/^[0-9a-f]{64}$/),
});
type ConsoleFeedbackSendRequest = z.infer<typeof consoleFeedbackSendRequestSchema>;
export type { ConsoleFeedbackSendRequest };

export const consoleFeedbackDeclineRequestSchema = z.object({ runId: z.string().min(1) });
type ConsoleFeedbackDeclineRequest = z.infer<typeof consoleFeedbackDeclineRequestSchema>;
export type { ConsoleFeedbackDeclineRequest };
