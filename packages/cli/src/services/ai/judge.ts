/**
 * The Auto-mode judge (D4 and D5 of agent/plans/PLAN-console-ai-assistant.md).
 *
 * In Auto mode a command decide() would let through but that is not read-only goes to a second
 * model call that answers allow or block. The judge is never handed command output: its input is
 * the user and assistant text of the conversation and the proposed command (argv, target,
 * severity, decide() verdict), and the input type has no field that could carry output.
 * `buildJudgeInput` copies those fields one by one, so a tool result, a tool call or an extra
 * property the caller smuggled in never reaches the prompt. That narrows prompt injection through
 * output but does not close it: assistant text that quotes or summarises what a command printed
 * is kept like any other assistant text, so the defence is partial.
 *
 * The answer is strict JSON, `{"verdict":"allow"|"block","reason":"..."}`; anything else, a
 * provider failure included, is a block. The model is the profile's `judgeModel`, else its `model`.
 *
 * Three consecutive blocks, or twenty blocks since the conversation's last fallback, switch it back
 * to Ask. Both counts start over at each fallback and at no other time (a manual switch to Ask and back keeps them).
 */

import type { Profile } from '@rediacc/shared/ai';
import type { ModelMessage } from 'ai';
import { generateText, type LanguageModel } from 'ai';
import { z } from 'zod';
import { createProviderModel, type ProviderModelOptions } from './provider.js';

/** Consecutive blocks (since the last allow or fallback) that switch the conversation back to Ask. */
export const JUDGE_CONSECUTIVE_BLOCK_LIMIT = 3;
/** Blocks in total since the conversation's last fallback (or its first block) that switch it back to Ask. */
export const JUDGE_TOTAL_BLOCK_LIMIT = 20;

/** Characters of conversation text the judge reads, newest kept. */
const JUDGE_MAX_TRANSCRIPT_CHARS = 32_000;

/** One line of the conversation as the judge reads it: who spoke, and the text alone. */
export interface JudgeMessage {
  readonly role: 'user' | 'assistant';
  readonly content: string;
}

/** The command the assistant proposes, as decide() and the contract described it. */
export interface JudgeCommand {
  readonly pathKey: string;
  readonly argv: readonly string[];
  readonly target: {
    readonly machine?: string;
    readonly repo?: { readonly name: string; readonly state: 'grand' | 'fork' | 'unresolved' };
  };
  readonly severity: 'none' | 'caution' | 'destructive';
  readonly decision: { readonly allowed: boolean; readonly code?: string };
}

/**
 * Everything the judge is shown. There is deliberately no output, result or tool field here, at any
 * depth: the type-level test in judge.test.ts fails if one is added.
 */
export interface JudgeInput {
  readonly messages: readonly JudgeMessage[];
  readonly command: JudgeCommand;
}

const JudgeVerdictSchema = z.strictObject({
  verdict: z.enum(['allow', 'block']),
  reason: z.string().min(1).max(2000),
});
type JudgeVerdict = z.infer<typeof JudgeVerdictSchema>;

export type { JudgeVerdict };

/** The text of a message's content: a string as is, a part list's text parts joined; never tool parts. */
function textOf(content: ModelMessage['content']): string {
  if (typeof content === 'string') return content;
  return content
    .map((part) => (part.type === 'text' ? part.text : ''))
    .filter(Boolean)
    .join('\n');
}

/**
 * The judge's input: the user and assistant text of `conversation`, newest kept within
 * {@link JUDGE_MAX_TRANSCRIPT_CHARS}, and the command copied field by field.
 */
export function buildJudgeInput(
  conversation: readonly ModelMessage[],
  command: JudgeCommand
): JudgeInput {
  return { messages: transcriptOf(conversation), command: copyCommand(command) };
}

/** The user and assistant text lines of `conversation`, newest kept within the budget. */
function transcriptOf(conversation: readonly ModelMessage[]): JudgeMessage[] {
  const lines: JudgeMessage[] = [];
  for (const message of conversation) {
    if (message.role !== 'user' && message.role !== 'assistant') continue;
    const content = textOf(message.content);
    if (content) lines.push({ role: message.role, content });
  }
  const kept: JudgeMessage[] = [];
  let budget = JUDGE_MAX_TRANSCRIPT_CHARS;
  for (const line of lines.reverse()) {
    if (line.content.length > budget) break;
    budget -= line.content.length;
    kept.unshift(line);
  }
  return kept;
}

/** The command, field by field: nothing the type does not name survives the copy. */
function copyCommand(command: JudgeCommand): JudgeCommand {
  const { machine, repo } = command.target;
  const { allowed, code } = command.decision;
  return {
    pathKey: command.pathKey,
    argv: [...command.argv],
    target: {
      ...(machine === undefined ? {} : { machine }),
      ...(repo === undefined ? {} : { repo: { name: repo.name, state: repo.state } }),
    },
    severity: command.severity,
    decision: { allowed, ...(code === undefined ? {} : { code }) },
  };
}

/** Parse the judge's answer. Anything but the exact JSON shape is a block that says so. */
export function parseJudgeVerdict(text: string): JudgeVerdict {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return { verdict: 'block', reason: 'The judge answered something other than JSON.' };
  }
  const parsed = JudgeVerdictSchema.safeParse(raw);
  return parsed.success
    ? parsed.data
    : { verdict: 'block', reason: 'The judge answered JSON outside the verdict shape.' };
}

/** The model name the judge runs on. */
export function judgeModelOf(profile: Profile): string {
  return profile.judgeModel ?? profile.model;
}

export const JUDGE_SYSTEM_PROMPT = [
  'You review one command an AI assistant proposes to run on infrastructure the user owns.',
  'The input is JSON: the user and assistant messages of the conversation, and the proposed command with its target, severity and policy decision.',
  'Allow the command only when the user clearly asked for this action on this target. Block when the request is ambiguous, when the target differs from what the user named, or when the command does more than was asked.',
  'Answer with JSON only, exactly {"verdict":"allow"|"block","reason":"<one sentence>"}, and nothing else.',
].join('\n');

export interface RunJudgeOptions extends ProviderModelOptions {
  /** A ready model, used in place of the profile's (tests). */
  model?: LanguageModel;
  abortSignal?: AbortSignal;
}

/** Ask the judge. A provider failure or an unparseable answer is a block; this never throws. */
export async function runJudge(
  profile: Profile,
  input: JudgeInput,
  options: RunJudgeOptions = {}
): Promise<JudgeVerdict> {
  try {
    const model =
      options.model ??
      createProviderModel(
        { ...profile, model: judgeModelOf(profile) },
        options.fetch ? { fetch: options.fetch } : {}
      );
    const result = await generateText({
      model,
      system: JUDGE_SYSTEM_PROMPT,
      prompt: JSON.stringify(input),
      maxOutputTokens: 400,
      ...(options.abortSignal ? { abortSignal: options.abortSignal } : {}),
    });
    return parseJudgeVerdict(result.text.trim());
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return { verdict: 'block', reason: `The judge could not be asked: ${detail}`.slice(0, 2000) };
  }
}

interface JudgeTallyEntry {
  /** Blocks since the last allow or the last fallback. */
  consecutive: number;
  /** Blocks since the last fallback. */
  total: number;
}

export type JudgeFallbackReason = 'consecutive' | 'total';

export interface JudgeTally {
  /**
   * Count one verdict. Answers the reason when this verdict switches the conversation back to Ask;
   * both counts start over then, so re-entering Auto is not undone by the next block.
   */
  record(conversationId: string, verdict: JudgeVerdict): JudgeFallbackReason | undefined;
  get(conversationId: string): JudgeTallyEntry;
}

/** Which block limit a tally that just counted a block has reached, if any. */
function fallbackReason(entry: JudgeTallyEntry): JudgeFallbackReason | undefined {
  if (entry.consecutive >= JUDGE_CONSECUTIVE_BLOCK_LIMIT) return 'consecutive';
  if (entry.total >= JUDGE_TOTAL_BLOCK_LIMIT) return 'total';
  return undefined;
}

/** Conversations whose tally is remembered; the oldest is dropped beyond this. */
const MAX_TALLIES = 10_000;

/** The tally after one verdict, and the limit it reached; a fallback starts the run over. */
function counted(
  before: JudgeTallyEntry,
  verdict: JudgeVerdict
): { entry: JudgeTallyEntry; reason?: JudgeFallbackReason } {
  if (verdict.verdict === 'allow') return { entry: { consecutive: 0, total: before.total } };
  const entry = { consecutive: before.consecutive + 1, total: before.total + 1 };
  const reason = fallbackReason(entry);
  return reason ? { entry: { consecutive: 0, total: 0 }, reason } : { entry };
}

export function createJudgeTally(): JudgeTally {
  const tallies = new Map<string, JudgeTallyEntry>();
  const get = (id: string): JudgeTallyEntry => tallies.get(id) ?? { consecutive: 0, total: 0 };
  const remember = (id: string, entry: JudgeTallyEntry): void => {
    tallies.delete(id);
    if (tallies.size >= MAX_TALLIES) {
      const oldest = tallies.keys().next().value;
      if (oldest !== undefined) tallies.delete(oldest);
    }
    tallies.set(id, entry);
  };
  return {
    get,
    record(id, verdict) {
      const { entry, reason } = counted(get(id), verdict);
      remember(id, entry);
      return reason;
    },
  };
}

export interface AutoModeJudgment {
  verdict: JudgeVerdict;
  /** Set when this verdict switched the conversation back to Ask. */
  fallback?: JudgeFallbackReason;
}

/**
 * Judge one proposed command of an Auto-mode conversation, count the verdict, and switch the
 * conversation to Ask through `setAskMode` when the block limits are reached.
 */
export async function judgeInAutoMode(args: {
  conversationId: string;
  input: JudgeInput;
  judge: (input: JudgeInput) => Promise<JudgeVerdict>;
  tally: JudgeTally;
  setAskMode: (reason: JudgeFallbackReason) => void;
}): Promise<AutoModeJudgment> {
  const verdict = await args.judge(args.input);
  const fallback = args.tally.record(args.conversationId, verdict);
  if (fallback) args.setAskMode(fallback);
  return { verdict, ...(fallback ? { fallback } : {}) };
}
