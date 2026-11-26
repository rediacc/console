import { buildRediaccProfile, CREDIT_REFUSAL_MESSAGES } from '@rediacc/shared/ai';
import { WK_OPENAI_API_BASE } from '@rediacc/shared/config/well-known.generated';
import { streamText } from 'ai';
import { describe, expect, it } from 'vitest';
import { createProviderModel, ProviderProfileError } from '../provider.js';
import {
  AI_CONVERSATION_HEADER,
  AI_USER_HEADER,
  RediaccRefusalError,
  rediaccErrorEvent,
  rediaccFetch,
} from '../rediacc-provider.js';

const IDS = { userId: 'user-1', conversationId: 'conv-1' };

interface Seen {
  url: string;
  headers: Headers;
  body: Record<string, unknown>;
  redirect: RequestRedirect | undefined;
}

function recordingFetch(answer: () => Response): { fetch: typeof globalThis.fetch; seen: Seen[] } {
  const seen: Seen[] = [];
  const fetch: typeof globalThis.fetch = (input, init) => {
    seen.push({
      url: String(input),
      headers: new Headers(init?.headers),
      body: JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>,
      redirect: init?.redirect,
    });
    return Promise.resolve(answer());
  };
  return { fetch, seen };
}

function sseAnswer(): Response {
  const frames = [
    { choices: [{ index: 0, delta: { role: 'assistant', content: 'hi' }, finish_reason: null }] },
    { choices: [{ index: 0, delta: {}, finish_reason: 'stop' }] },
    { choices: [], usage: { prompt_tokens: 3, completion_tokens: 1, total_tokens: 4 } },
  ];
  const text = `${frames.map((f) => `data: ${JSON.stringify(f)}\n\n`).join('')}data: [DONE]\n\n`;
  return new Response(text, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

describe('rediacc tier model', () => {
  it('sends a chat to ai.internal with the id headers, no auth and no redirects', async () => {
    const { fetch, seen } = recordingFetch(sseAnswer);
    const model = createProviderModel(buildRediaccProfile('standard'), { fetch, rediacc: IDS });
    const result = streamText({ model, prompt: 'hello' });
    expect(await result.text).toBe('hi');
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe('http://ai.internal/compat/chat/completions');
    expect(seen[0]?.headers.get(AI_USER_HEADER)).toBe('user-1');
    expect(seen[0]?.headers.get(AI_CONVERSATION_HEADER)).toBe('conv-1');
    expect(seen[0]?.headers.get('authorization')).toBeNull();
    expect(seen[0]?.headers.get('x-api-key')).toBeNull();
    expect(seen[0]?.redirect).toBe('error');
    expect(seen[0]?.body).toMatchObject({
      model: 'workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast',
      stream: true,
    });
  });

  it('needs the user and conversation ids', () => {
    expect(() => createProviderModel(buildRediaccProfile('premium'))).toThrow(ProviderProfileError);
    expect(() =>
      createProviderModel(buildRediaccProfile('premium'), {
        rediacc: { userId: 'bad id', conversationId: 'c' },
      })
    ).toThrow(TypeError);
  });

  it('refuses a request outside the intercept base URL', async () => {
    const { fetch } = recordingFetch(sseAnswer);
    const guarded = rediaccFetch({ ...IDS, fetch });
    await expect(guarded(`${WK_OPENAI_API_BASE}/chat/completions`, {})).rejects.toThrow(
      /only reaches/
    );
    await expect(guarded('http://ai.internal.evil.example/compat/x', {})).rejects.toThrow(
      /only reaches/
    );
  });

  it('turns every known refusal code into a named error event', async () => {
    for (const code of Object.keys(CREDIT_REFUSAL_MESSAGES)) {
      const { fetch } = recordingFetch(() =>
        Response.json({ error: { code, message: code }, code }, { status: 402 })
      );
      const guarded = rediaccFetch({ ...IDS, fetch });
      const error = await guarded('http://ai.internal/compat/chat/completions', {
        method: 'POST',
        body: '{}',
      }).catch((e: unknown) => e);
      expect(error).toBeInstanceOf(RediaccRefusalError);
      expect(rediaccErrorEvent(error)).toEqual({
        type: 'error',
        message: CREDIT_REFUSAL_MESSAGES[code as keyof typeof CREDIT_REFUSAL_MESSAGES],
        code: `AI_CREDITS_${code}`,
      });
    }
  });

  it('passes a body with only a top-level refusal code through as the gateway answer', async () => {
    const code = Object.keys(CREDIT_REFUSAL_MESSAGES)[0];
    const { fetch } = recordingFetch(() => Response.json({ code }, { status: 402 }));
    const answer = await rediaccFetch({ ...IDS, fetch })(
      'http://ai.internal/compat/chat/completions',
      { method: 'POST', body: '{}' }
    );
    expect(answer.status).toBe(402);
  });

  it('passes a gateway error through untouched', async () => {
    const gateway = recordingFetch(() =>
      Response.json({ error: { message: 'upstream down' } }, { status: 502 })
    );
    const answer = await rediaccFetch({ ...IDS, fetch: gateway.fetch })(
      'http://ai.internal/compat/chat/completions',
      { method: 'POST', body: '{}' }
    );
    expect(answer.status).toBe(502);
    expect(rediaccErrorEvent(new Error('x'))).toBeUndefined();
  });
});
