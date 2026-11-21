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

export const feedbackKindSchema = z.enum(FEEDBACK_KINDS);
export const feedbackStatusSchema = z.enum(FEEDBACK_STATUSES);

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

export const feedbackSettingsSchema = z.object({ shareWithOrgAdmins: z.boolean() });
type FeedbackSettings = z.infer<typeof feedbackSettingsSchema>;
export type { FeedbackSettings };

export const feedbackLimitErrorSchema = z.object({
  code: z.literal('FEEDBACK_DAILY_LIMIT'),
  subjectKind: z.enum(['user', 'org', 'machine']),
  resetAt: z.string(),
});
type FeedbackLimitError = z.infer<typeof feedbackLimitErrorSchema>;
export type { FeedbackLimitError };
