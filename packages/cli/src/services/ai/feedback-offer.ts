/**
 * The executor's bug-report offer (D1, D2 and D5 of agent/plans/PLAN-console-ai-feedback.md).
 *
 * Whether to offer is code: the failed run's error code is looked up in the contract's `errorCodes`,
 * `rediacc` offers, `user` and `environment` never do, and only a failure with no code or a code
 * the table does not know is ambiguous and goes to one classify-only model call. Each run is judged
 * once. The draft comes from the server run record and its opened sealed tail, never from the
 * conversation or the local ring buffer, and every text that leaves this module has passed
 * `scrubText`. The offer is a typed `feedback_offer` event; the send is the account worker's route
 * on the user's click, so nothing here holds a feedback credential or posts a report.
 */

import { FEEDBACK_LIMITS, scrubText } from '@rediacc/shared';
import type { Profile } from '@rediacc/shared/ai';
import type { ContractErrorCode, ErrorOrigin } from '@rediacc/shared/cli-contract';
import type { AiEvent } from '@rediacc/shared/cli-contract/wire';
import { generateText, type LanguageModel } from 'ai';
import { z } from 'zod';
import { createProviderModel, type ProviderModelOptions } from './provider.js';

/** The `feedback_offer` member of the wire's `AiEventSchema`. */
type FeedbackOfferEvent = Extract<AiEvent, { type: 'feedback_offer' }>;

/** The run row of plan 4, as far as the offer reads it: never params, the tail still sealed. */
export interface FeedbackRunRecord {
  readonly runId: string;
  readonly pathKey: string;
  readonly state: string;
  readonly exitCode?: number;
  readonly errorCode?: string;
  readonly sealedTail?: string;
}

/** What a model sees and writes about: the redacted record. */
export interface RedactedRunRecord {
  readonly pathKey: string;
  readonly exitCode?: number;
  readonly errorCode?: string;
  /** The opened tail after `scrubText`, empty when the row has none or it would not open. */
  readonly tail: string;
}

export interface FeedbackDraft {
  readonly message?: string;
  readonly stderrTail?: string;
}

export interface FeedbackClassification {
  readonly offer: boolean;
  readonly reason: string;
}

/** The two switches of D5. `undefined` means the default, which is on. */
interface FeedbackOfferSettings {
  /** The user's own `offerBugReports`. */
  readonly offerBugReports?: boolean;
  /** The org owner's override: true means no offers for anyone in the org. */
  readonly offersOff?: boolean;
}

export interface FeedbackOfferDeps {
  readonly errorCodes: readonly ContractErrorCode[];
  readonly settings: FeedbackOfferSettings;
  readonly env: { readonly cliVersion: string; readonly os: string; readonly arch: string };
  /** Plan 4's row for the run, scoped to the caller; undefined when there is none. */
  readonly loadRun: (runId: string) => Promise<FeedbackRunRecord | undefined>;
  /** Opens a sealed tail with the session key; may throw. */
  readonly openTail: (sealed: string) => Promise<string>;
  /** The classify-only call for an ambiguous failure. */
  readonly classify: (record: RedactedRunRecord) => Promise<FeedbackClassification>;
  /** The model's draft over the redacted record. */
  readonly draft: (record: RedactedRunRecord) => Promise<FeedbackDraft>;
  /** Runs already judged, so a run is judged once. */
  readonly judged: Set<string>;
}

export type FeedbackOfferVerdict =
  | { readonly offer: true; readonly event: FeedbackOfferEvent }
  | { readonly offer: false; readonly reason: string };

const none = (reason: string): FeedbackOfferVerdict => ({ offer: false, reason });

/** `text` cut from the front to `max` characters: the end of an output is the part that matters. */
function lastChars(text: string, max: number): string {
  return text.length <= max ? text : text.slice(text.length - max);
}

async function redact(run: FeedbackRunRecord, deps: FeedbackOfferDeps): Promise<RedactedRunRecord> {
  let tail = '';
  if (run.sealedTail) {
    try {
      tail = scrubText(await deps.openTail(run.sealedTail));
    } catch {
      tail = '';
    }
  }
  return {
    pathKey: run.pathKey,
    ...(run.exitCode === undefined ? {} : { exitCode: run.exitCode }),
    ...(run.errorCode === undefined ? {} : { errorCode: run.errorCode }),
    tail,
  };
}

/** The refusal the two settings and the once-per-run rule give, if any; a run that passes is marked judged. */
function refusedBeforeLookup(
  runId: string,
  deps: FeedbackOfferDeps
): FeedbackOfferVerdict | undefined {
  if (deps.settings.offerBugReports === false) {
    return none('The user turned bug-report offers off.');
  }
  if (deps.settings.offersOff === true) {
    return none('The organization turned bug-report offers off.');
  }
  if (deps.judged.has(runId)) return none('The run was judged already.');
  deps.judged.add(runId);
  return undefined;
}

/** The origin the contract gives the run's error code; undefined for no code or an unknown one. */
function originOf(run: FeedbackRunRecord, deps: FeedbackOfferDeps): ErrorOrigin | undefined {
  if (!run.errorCode) return undefined;
  return deps.errorCodes.find((entry) => entry.code === run.errorCode)?.origin;
}

async function decide(runId: string, deps: FeedbackOfferDeps): Promise<FeedbackOfferVerdict> {
  const run = await deps.loadRun(runId);
  if (!run) return none('The run has no record.');
  if (run.state !== 'failed') return none('The run did not fail.');
  const origin = originOf(run, deps);
  if (origin === 'user' || origin === 'environment') {
    return none(`The failure has ${origin} origin.`);
  }
  const record = await redact(run, deps);
  if (origin === undefined) {
    const verdict = await deps.classify(record);
    if (!verdict.offer) return none(verdict.reason);
  }
  const draft = await deps.draft(record);
  return { offer: true, event: buildEvent(run.runId, draft, deps.env) };
}

/** The offer decision for one finished run. Never throws: any failure to decide is no offer. */
export async function decideFeedbackOffer(
  runId: string,
  deps: FeedbackOfferDeps
): Promise<FeedbackOfferVerdict> {
  const refused = refusedBeforeLookup(runId, deps);
  if (refused) return refused;
  try {
    return await decide(runId, deps);
  } catch {
    return none('The offer could not be decided.');
  }
}

/** The event: both texts scrubbed again and cut to their limits, the environment from the executor. */
function buildEvent(
  runId: string,
  draft: FeedbackDraft,
  env: FeedbackOfferDeps['env']
): FeedbackOfferEvent {
  const message = draft.message ? scrubText(draft.message).slice(0, FEEDBACK_LIMITS.message) : '';
  const stderrTail = draft.stderrTail
    ? lastChars(scrubText(draft.stderrTail), FEEDBACK_LIMITS.stderrTail)
    : '';
  return {
    type: 'feedback_offer',
    runId,
    draft: {
      ...(message ? { message } : {}),
      ...(stderrTail ? { stderrTail } : {}),
      env: { cliVersion: env.cliVersion, os: env.os, arch: env.arch },
    },
  };
}

const ClassificationSchema = z.strictObject({
  offer: z.boolean(),
  reason: z.string().max(2000),
});

const DraftSchema = z.strictObject({
  message: z.string(),
  stderrTail: z.string(),
});

/** Parse the classifier's answer; anything but the exact shape is no offer. */
export function parseFeedbackClassification(text: string): FeedbackClassification {
  try {
    const parsed = ClassificationSchema.safeParse(JSON.parse(text));
    if (parsed.success) return parsed.data;
  } catch {
    // falls through to the refusal below
  }
  return { offer: false, reason: 'The classifier answered outside the offer shape.' };
}

/** Parse the drafter's answer; anything but the exact shape throws, which is no offer. */
function parseFeedbackDraft(text: string): FeedbackDraft {
  return DraftSchema.parse(JSON.parse(text));
}

const FEEDBACK_CLASSIFY_PROMPT = [
  'A command run by the Rediacc CLI failed without an error code that says whose fault it is.',
  'The input is JSON: the command path, exit code, error code and the redacted end of its output.',
  'Offer a bug report only when the output points to a defect or outage on the Rediacc side: a crash, an internal error, an unhandled exception or a broken contract.',
  'Do not offer for a mistake in the arguments, a missing permission, the network, a machine, SSH, Docker or disk.',
  'Answer with JSON only, exactly {"offer":true|false,"reason":"<one sentence>"}, and nothing else.',
].join('\n');

const FEEDBACK_DRAFT_PROMPT = [
  'Write a bug report for a failed Rediacc CLI command.',
  'The input is JSON: the command path, exit code, error code and the redacted end of its output.',
  `Answer with JSON only, exactly {"message":"<what failed and what the user was likely doing, at most ${FEEDBACK_LIMITS.message} characters>","stderrTail":"<the output lines that matter, copied unchanged, at most ${FEEDBACK_LIMITS.stderrTail} characters>"}, and nothing else.`,
  'Never add a secret, a hostname, an address or a path that the input does not already show redacted.',
].join('\n');

export interface FeedbackModelOptions extends ProviderModelOptions {
  /** A ready model, used in place of the profile's (tests). */
  model?: LanguageModel;
  abortSignal?: AbortSignal;
}

async function ask(
  profile: Profile,
  system: string,
  record: RedactedRunRecord,
  options: FeedbackModelOptions
): Promise<string> {
  const model =
    options.model ?? createProviderModel(profile, options.fetch ? { fetch: options.fetch } : {});
  const result = await generateText({
    model,
    system,
    prompt: JSON.stringify(record),
    maxOutputTokens: 1200,
    ...(options.abortSignal ? { abortSignal: options.abortSignal } : {}),
  });
  return result.text.trim();
}

/** The classify-only call. A provider failure is no offer; this never throws. */
export async function runFeedbackClassify(
  profile: Profile,
  record: RedactedRunRecord,
  options: FeedbackModelOptions = {}
): Promise<FeedbackClassification> {
  try {
    return parseFeedbackClassification(
      await ask(profile, FEEDBACK_CLASSIFY_PROMPT, record, options)
    );
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return { offer: false, reason: `The classifier could not be asked: ${detail}`.slice(0, 2000) };
  }
}

/** The drafting call. A failure throws, and {@link decideFeedbackOffer} turns that into no offer. */
export async function runFeedbackDraft(
  profile: Profile,
  record: RedactedRunRecord,
  options: FeedbackModelOptions = {}
): Promise<FeedbackDraft> {
  return parseFeedbackDraft(await ask(profile, FEEDBACK_DRAFT_PROMPT, record, options));
}
