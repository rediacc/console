/** The request bodies of the serve AI routes (ai-routes.ts), and the id shape every route body shares. */
import { z } from 'zod';

export const IdSchema = z
  .string()
  .min(1)
  .max(128)
  .regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/);

const MAX_MESSAGES = 200;
const MAX_MESSAGE_CHARS = 100_000;
const GRANT_ID = /^[A-Za-z0-9_-]{1,128}$/;
const ProfileNameSchema = z.string().min(1).max(128);

/**
 * What the browser sends. Not strict on purpose: a field this schema does not name (a `kind`, a
 * `principal`, an `agentGrant`) is dropped before anything reads the body, so none of them can
 * reach the principal the tools run as.
 */
export const ChatRequestSchema = z.object({
  conversationId: IdSchema,
  messages: z
    .array(
      z.object({ role: z.enum(['user', 'assistant']), content: z.string().max(MAX_MESSAGE_CHARS) })
    )
    .min(1)
    .max(MAX_MESSAGES)
    .refine((messages) => messages.at(-1)?.role === 'user', {
      message: "the last message must be the user's",
    }),
  profile: ProfileNameSchema.optional(),
  grant: z
    .strictObject({ grantId: z.string().regex(GRANT_ID), secret: z.string().min(1).max(256) })
    .optional(),
  /** The single-use forensics read ticket the Investigate page minted for this turn (D8). */
  forensicsTicket: z.string().min(1).max(2048).optional(),
});

type ChatRequest = z.infer<typeof ChatRequestSchema>;

export type { ChatRequest };

export const TestRequestSchema = z.object({ profile: ProfileNameSchema.optional() });
