/**
 * AI provider profile (D1 and D2 of PLAN-console-ai-providers).
 *
 * A profile tells the loop host how to talk to one model endpoint: the wire
 * format, the base URL, how the key is presented, the model name and what the
 * endpoint supports. Profiles live under `ai.providers` of the encrypted config
 * (org level in the shared config, team level in the team config).
 *
 * `key` may be absent only on a `byokOnly` profile, where a gateway holds the
 * provider key (Cloudflare AI Gateway BYOK) and the profile carries the gateway
 * token in `headers`. The schema checks shape; `validateProfile` adds the base
 * URL guard of base-url.ts.
 */
import { z } from 'zod';
import { type BaseUrlRefusal, validateBaseUrl } from './base-url.js';

export const PROFILE_FORMATS = ['anthropic-messages', 'openai-chat'] as const;
export type ProfileFormat = (typeof PROFILE_FORMATS)[number];

export const AUTH_SCHEMES = ['x-api-key', 'bearer'] as const;
export type AuthScheme = (typeof AUTH_SCHEMES)[number];

export const CapabilitiesSchema = z.strictObject({
  tools: z.boolean(),
  streaming: z.boolean(),
  parallelToolCalls: z.boolean(),
  vision: z.boolean(),
});
type Capabilities = z.infer<typeof CapabilitiesSchema>;

export type { Capabilities };

export const ProfileSchema = z
  .strictObject({
    format: z.enum(PROFILE_FORMATS),
    baseURL: z.string().min(1),
    key: z.string().min(1).optional(),
    authScheme: z.enum(AUTH_SCHEMES),
    model: z.string().min(1),
    /** The model the Auto-mode judge runs on (D5 of PLAN-console-ai-assistant); `model` when absent. */
    judgeModel: z.string().min(1).optional(),
    headers: z.record(z.string().min(1), z.string()).optional(),
    capabilities: CapabilitiesSchema,
    preset: z.string().min(1).optional(),
    byokOnly: z.boolean().optional(),
  })
  .refine((profile) => profile.key !== undefined || profile.byokOnly === true, {
    path: ['key'],
    message: 'key may be absent only when byokOnly is true',
  });
type Profile = z.infer<typeof ProfileSchema>;

export type { Profile };

/** The `ai` leaf of the config: named profiles and the name used when none is chosen. */
export const AiConfigSchema = z.strictObject({
  providers: z.record(z.string().min(1), ProfileSchema),
  default: z.string().min(1).optional(),
});
type AiConfig = z.infer<typeof AiConfigSchema>;

export type { AiConfig };

export interface ProfileIssue {
  /** Where the problem is, as a pointer path inside the profile (`/baseURL`). */
  path: string;
  message: string;
  /** Set for a base URL the guard refused. */
  refusal?: BaseUrlRefusal;
}

export type ProfileCheck = { ok: true; profile: Profile } | { ok: false; issues: ProfileIssue[] };

/** Shape check plus the base URL guard. Every problem is reported, not only the first. */
export function validateProfile(input: unknown): ProfileCheck {
  const parsed = ProfileSchema.safeParse(input);
  if (!parsed.success) {
    return {
      ok: false,
      issues: parsed.error.issues.map((issue) => ({
        path: `/${issue.path.join('/')}`,
        message: issue.message,
      })),
    };
  }
  const url = validateBaseUrl(parsed.data.baseURL);
  if (!url.ok) {
    return {
      ok: false,
      issues: [{ path: '/baseURL', message: url.message, refusal: url.reason }],
    };
  }
  return { ok: true, profile: parsed.data };
}
