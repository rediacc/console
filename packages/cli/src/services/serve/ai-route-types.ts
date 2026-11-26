/** The AI routes' wire types, request schemas and refusal codes (split from ai-routes.ts). */

import type { AiConfigs, Profile } from '@rediacc/shared/ai';
import { STEP_UP_METHODS } from '@rediacc/shared/auth';
import type { AiApprovalCommand } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { LanguageModel } from 'ai';
import { z } from 'zod';
import type { AiApprovals } from '../ai/approvals.js';
import type { JudgeInput, JudgeVerdict } from '../ai/judge.js';
import type { ProviderModelOptions } from '../ai/provider.js';
import type { AiTranscripts, TranscriptKey } from '../ai/recorder.js';
import { IdSchema } from './ai-request-schemas.js';
import type { BusyCounter } from './busy.js';
import type { SessionPrincipal } from './sessions.js';

const AI_MODES = ['ask', 'auto', 'skip'] as const;
export type AiMode = (typeof AI_MODES)[number];

/** Refusal codes these routes answer with. */
export const AI_MODE_DISABLED = 'AI_MODE_DISABLED';

export const ModeRequestSchema = z.strictObject({
  conversationId: IdSchema,
  mode: z.enum(AI_MODES),
});

const ApprovedCommandSchema = z.strictObject({
  pathKey: z.string().min(1).max(256),
  params: z.record(z.string(), z.unknown()).default({}),
  positionals: z.record(z.string(), z.unknown()).default({}),
});

/** What the account forwards: its own `grand` input is not among the fields, the executor decides it. */
export const ApprovalRequestSchema = z.strictObject({
  conversationId: IdSchema,
  toolCallId: z.string().min(1).max(256),
  approvalToken: z.string().min(1).max(4096),
  decision: z.enum(['approve', 'reject']),
  command: ApprovedCommandSchema,
  stepUpMethod: z.enum(STEP_UP_METHODS).nullable(),
  /** Remember an exact allow rule for this argv in this conversation (a `caution` command only). */
  remember: z.boolean().optional(),
});

type ApprovalRequest = z.infer<typeof ApprovalRequestSchema>;

export type { ApprovalRequest };

/** Where the loop keeps each conversation's mode (D4) and exact allow rules; the autonomy gate reads both. */
interface AiConversationModes {
  set(principal: SessionPrincipal, conversationId: string, mode: AiMode): void;
  get(principal: SessionPrincipal, conversationId: string): AiMode;
  allowExact(principal: SessionPrincipal, conversationId: string, command: AiApprovalCommand): void;
  allowsExact(
    principal: SessionPrincipal,
    conversationId: string,
    command: AiApprovalCommand
  ): boolean;
}

/** One approval answer as the executor verified it. */
export interface AiApprovalSubmit extends Omit<ApprovalRequest, 'stepUpMethod' | 'remember'> {
  principal: SessionPrincipal;
  stepUpMethod: ApprovalRequest['stepUpMethod'];
  /** The command is destructive and the run is not a preview. */
  destructive: boolean;
  /** The executor resolved the target to a grand repo (or an unresolved one) off the ops VMs. */
  grand: boolean;
}

export type AiApprovalVerdict =
  | { ok: true }
  | { ok: false; status: 403 | 404 | 409; code: string; message: string };

/** The chat host's own seams; every one has a production default. */
export interface AiChatDeps {
  /** The AI SDK model of a profile; `createProviderModel` when absent. Tests pass a mock model. */
  createModel?: (profile: Profile, options?: ProviderModelOptions) => LanguageModel;
  /**
   * The profile sources of a request, team over shared (D3). Absent: the session's own config is the
   * only source. The container tier lends the second config when it loads both.
   */
  aiConfigs?: (
    principal: SessionPrincipal,
    config: RdcConfig,
    configSessionId?: string
  ) => Promise<AiConfigs>;
  /** Counts a running tool as a running dispatch, as `/v1/command` does. */
  busy?: BusyCounter;
  /** The per-turn output token cap when the profile names none; the loop's default when absent. */
  maxOutputTokens?: number;
  /** The Auto-mode judge of a profile; `runJudge` on the profile's judge model when absent. */
  judge?: (profile: Profile, input: JudgeInput) => Promise<JudgeVerdict>;
  /** Records each turn of a chat on the caller's own session; absent, no turn is recorded. */
  recording?: AiChatRecording;
  /** `renet job cancel` of one job, run inside the turn's config scope; `cancelOnMachine` when absent. */
  cancelJob?: (machine: string, jobId: string) => Promise<unknown>;
  /** The fetch provider transcription goes out through, behind the profile guard; `fetch` when absent. */
  transcribeFetch?: typeof globalThis.fetch;
}

/** Where a chat's turns are recorded, and the session key each is sealed under. */
export interface AiChatRecording {
  transcripts: AiTranscripts;
  /** The key a turn of this session is sealed under, or why the session has none. */
  keyOf: (
    principal: SessionPrincipal,
    config: RdcConfig,
    configSessionId: string | undefined
  ) => TranscriptKey | string;
  /** Told why a turn was not recorded. */
  onUnrecorded?: (reason: string, conversationId: string) => void;
}

export interface AiRouteDeps {
  modes: AiConversationModes;
  approvals: AiApprovals;
  chat?: AiChatDeps;
}

/** Refusal codes of the chat and test routes. */
export const AI_PROFILE_UNRESOLVED = 'AI_PROFILE_UNRESOLVED';
