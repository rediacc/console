/**
 * The executor's bug-report offer (AF4 of agent/plans/PLAN-console-ai-feedback.md): the D1 origin
 * rule, the classify-only call for an ambiguous failure, the D2 draft from the opened tail with
 * `scrubText`, both settings, and the `feedback_offer` wire member.
 */

import type { Profile } from '@rediacc/shared/ai';
import { AiEventSchema } from '@rediacc/shared/cli-contract/wire';
import { WK_ANTHROPIC_API_BASE } from '@rediacc/shared/config/well-known.generated';
import { MockLanguageModelV4 } from 'ai/test';
import { describe, expect, it, vi } from 'vitest';
import {
  decideFeedbackOffer,
  type FeedbackOfferDeps,
  type FeedbackRunRecord,
  parseFeedbackClassification,
  runFeedbackClassify,
  runFeedbackDraft,
} from '../feedback-offer.js';

const TOKEN = 'abcdefgh12345678ZYXW';
const USAGE = {
  inputTokens: { total: 10, noCache: 10, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 5, text: 5, reasoning: undefined },
};

const PROFILE: Profile = {
  format: 'anthropic-messages',
  baseURL: WK_ANTHROPIC_API_BASE,
  key: 'sk-test',
  authScheme: 'x-api-key',
  model: 'claude-main',
  capabilities: { tools: true, streaming: true, parallelToolCalls: true, vision: false },
};

function failedRun(errorCode: string | undefined, over: Partial<FeedbackRunRecord> = {}) {
  return {
    runId: 'run-1',
    pathKey: 'repo up',
    state: 'failed',
    exitCode: 1,
    ...(errorCode === undefined ? {} : { errorCode }),
    sealedTail: 'sealed',
    ...over,
  } satisfies FeedbackRunRecord;
}

function setup(run: FeedbackRunRecord | undefined, over: Partial<FeedbackOfferDeps> = {}) {
  const classify = vi.fn(async () => ({ offer: true, reason: 'looks like a crash' }));
  const draft = vi.fn(async () => ({ message: 'repo up crashed', stderrTail: 'boom' }));
  const deps: FeedbackOfferDeps = {
    errorCodes: [
      { code: 'INVALID_ARGUMENT', origin: 'user' },
      { code: 'SSH_ERROR', origin: 'environment' },
      { code: 'INTERNAL_ERROR', origin: 'rediacc' },
    ],
    settings: {},
    env: { cliVersion: '1.2.3', os: 'linux', arch: 'x64' },
    loadRun: async () => run,
    openTail: async () => `error: Bearer ${TOKEN} rejected\nsecond line`,
    classify,
    draft,
    judged: new Set(),
    ...over,
  };
  return { deps, classify, draft };
}

describe('decideFeedbackOffer origin rule', () => {
  it('never offers for a user origin and calls no model', async () => {
    const { deps, classify, draft } = setup(failedRun('INVALID_ARGUMENT'));
    const verdict = await decideFeedbackOffer('run-1', deps);
    expect(verdict.offer).toBe(false);
    expect(classify).not.toHaveBeenCalled();
    expect(draft).not.toHaveBeenCalled();
  });

  it('never offers for an environment origin', async () => {
    const { deps, classify } = setup(failedRun('SSH_ERROR'));
    expect((await decideFeedbackOffer('run-1', deps)).offer).toBe(false);
    expect(classify).not.toHaveBeenCalled();
  });

  it('offers a rediacc origin without a classify call, and the event parses on the wire', async () => {
    const { deps, classify, draft } = setup(failedRun('INTERNAL_ERROR'));
    const verdict = await decideFeedbackOffer('run-1', deps);
    expect(classify).not.toHaveBeenCalled();
    expect(draft).toHaveBeenCalledTimes(1);
    expect(verdict.offer).toBe(true);
    if (!verdict.offer) return;
    expect(AiEventSchema.parse(verdict.event)).toEqual({
      type: 'feedback_offer',
      runId: 'run-1',
      draft: {
        message: 'repo up crashed',
        stderrTail: 'boom',
        env: { cliVersion: '1.2.3', os: 'linux', arch: 'x64' },
      },
    });
  });

  it('calls the classifier once for a failure with no error code', async () => {
    const { deps, classify } = setup(failedRun(undefined));
    const verdict = await decideFeedbackOffer('run-1', deps);
    expect(classify).toHaveBeenCalledTimes(1);
    expect(verdict.offer).toBe(true);
  });

  it('calls the classifier once for a code absent from the table', async () => {
    const { deps, classify } = setup(failedRun('SOMETHING_NEW'));
    await decideFeedbackOffer('run-1', deps);
    expect(classify).toHaveBeenCalledTimes(1);
  });

  it('offers nothing when the classifier says no, and drafts nothing', async () => {
    const { deps, draft } = setup(failedRun(undefined), {
      classify: async () => ({ offer: false, reason: 'a typo' }),
    });
    expect(await decideFeedbackOffer('run-1', deps)).toEqual({ offer: false, reason: 'a typo' });
    expect(draft).not.toHaveBeenCalled();
  });

  it('judges each run once', async () => {
    const { deps, classify } = setup(failedRun(undefined));
    await decideFeedbackOffer('run-1', deps);
    const again = await decideFeedbackOffer('run-1', deps);
    expect(again.offer).toBe(false);
    expect(classify).toHaveBeenCalledTimes(1);
  });

  it('offers nothing for a run that did not fail or has no record', async () => {
    expect(
      (
        await decideFeedbackOffer(
          'run-1',
          setup(failedRun('INTERNAL_ERROR', { state: 'succeeded' })).deps
        )
      ).offer
    ).toBe(false);
    expect((await decideFeedbackOffer('run-1', setup(undefined).deps)).offer).toBe(false);
  });

  it('is no offer when the draft call throws', async () => {
    const { deps } = setup(failedRun('INTERNAL_ERROR'), {
      draft: () => Promise.reject(new Error('provider down')),
    });
    expect((await decideFeedbackOffer('run-1', deps)).offer).toBe(false);
  });
});

describe('decideFeedbackOffer settings', () => {
  it('honours the user switch before any lookup', async () => {
    const loadRun = vi.fn();
    const { deps } = setup(failedRun('INTERNAL_ERROR'), {
      settings: { offerBugReports: false },
      loadRun,
    });
    expect((await decideFeedbackOffer('run-1', deps)).offer).toBe(false);
    expect(loadRun).not.toHaveBeenCalled();
  });

  it('honours the org override', async () => {
    const { deps, draft } = setup(failedRun('INTERNAL_ERROR'), { settings: { offersOff: true } });
    expect((await decideFeedbackOffer('run-1', deps)).offer).toBe(false);
    expect(draft).not.toHaveBeenCalled();
  });

  it('treats absent settings as on', async () => {
    const { deps } = setup(failedRun('INTERNAL_ERROR'), { settings: { offerBugReports: true } });
    expect((await decideFeedbackOffer('run-1', deps)).offer).toBe(true);
  });
});

describe('the draft is redacted', () => {
  it('hands the models the scrubbed tail, never the raw one', async () => {
    const seen: string[] = [];
    const { deps } = setup(failedRun('INTERNAL_ERROR'), {
      draft: (record) => {
        seen.push(record.tail);
        return Promise.resolve({});
      },
    });
    await decideFeedbackOffer('run-1', deps);
    expect(seen[0]).not.toContain(TOKEN);
    expect(seen[0]).toContain('second line');
  });

  it('scrubs a bearer token the draft carries into the message or the tail', async () => {
    const { deps } = setup(failedRun('INTERNAL_ERROR'), {
      draft: async () => ({
        message: `It failed with Bearer ${TOKEN}`,
        stderrTail: `Authorization: Bearer ${TOKEN}`,
      }),
    });
    const verdict = await decideFeedbackOffer('run-1', deps);
    expect(verdict.offer).toBe(true);
    if (!verdict.offer) return;
    expect(JSON.stringify(verdict.event)).not.toContain(TOKEN);
  });

  it('cuts the texts to their limits, keeping the end of the tail', async () => {
    const { deps } = setup(failedRun('INTERNAL_ERROR'), {
      draft: async () => ({ message: 'm '.repeat(5000), stderrTail: `${'x '.repeat(5000)}END` }),
    });
    const verdict = await decideFeedbackOffer('run-1', deps);
    if (!verdict.offer) throw new Error('expected an offer');
    expect(verdict.event.draft.message?.length).toBeLessThanOrEqual(2048);
    expect(verdict.event.draft.stderrTail?.length).toBeLessThanOrEqual(4096);
    expect(verdict.event.draft.stderrTail?.endsWith('END')).toBe(true);
    expect(AiEventSchema.safeParse(verdict.event).success).toBe(true);
  });

  it('drafts without a tail when the sealed one will not open', async () => {
    const seen: string[] = [];
    const { deps } = setup(failedRun('INTERNAL_ERROR'), {
      openTail: () => Promise.reject(new Error('wrong key')),
      draft: (record) => {
        seen.push(record.tail);
        return Promise.resolve({ message: 'crash' });
      },
    });
    expect((await decideFeedbackOffer('run-1', deps)).offer).toBe(true);
    expect(seen).toEqual(['']);
  });
});

function answering(text: string) {
  const prompts: string[] = [];
  const model = new MockLanguageModelV4({
    doGenerate: (options) => {
      prompts.push(JSON.stringify(options.prompt));
      return Promise.resolve({
        content: [{ type: 'text', text }],
        finishReason: { unified: 'stop', raw: 'stop' },
        usage: USAGE,
        warnings: [],
      });
    },
  });
  return { model, prompts };
}

describe('the model calls', () => {
  const record = { pathKey: 'repo up', exitCode: 1, tail: 'boom' };

  it('parses an exact classification and refuses anything else', async () => {
    const { model, prompts } = answering('{"offer":true,"reason":"crash"}');
    expect(await runFeedbackClassify(PROFILE, record, { model })).toEqual({
      offer: true,
      reason: 'crash',
    });
    expect(prompts[0]).toContain('boom');
    expect(parseFeedbackClassification('yes').offer).toBe(false);
    expect(parseFeedbackClassification('{"offer":true,"reason":"x","extra":1}').offer).toBe(false);
    expect(
      (await runFeedbackClassify(PROFILE, record, { model: answering('nope').model })).offer
    ).toBe(false);
  });

  it('a classifier outage is no offer', async () => {
    const model = new MockLanguageModelV4({
      doGenerate: () => Promise.reject(new Error('503')),
    });
    const verdict = await runFeedbackClassify(PROFILE, record, { model });
    expect(verdict.offer).toBe(false);
    expect(verdict.reason).toContain('503');
  });

  it('parses a draft and throws on a malformed one', async () => {
    const { model } = answering('{"message":"it crashed","stderrTail":"boom"}');
    expect(await runFeedbackDraft(PROFILE, record, { model })).toEqual({
      message: 'it crashed',
      stderrTail: 'boom',
    });
    await expect(
      runFeedbackDraft(PROFILE, record, { model: answering('{}').model })
    ).rejects.toThrow();
  });
});
