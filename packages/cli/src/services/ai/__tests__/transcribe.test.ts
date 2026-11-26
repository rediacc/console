/**
 * Provider transcription (AI10 of agent/plans/PLAN-console-ai-assistant.md, D12): the request an
 * OpenAI-compatible profile sends, the refusal of profiles without a transcription endpoint, and
 * the executor route the account relays a recording to. The provider is a fake fetch; the profile
 * guard, the profile resolution and the route run for real.
 */

import { type AiConfig, buildRediaccProfile, type Profile } from '@rediacc/shared/ai';
import {
  WK_ANTHROPIC_API_BASE,
  WK_OPENAI_API_BASE,
} from '@rediacc/shared/config/well-known.generated';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { Hono } from 'hono';
import { describe, expect, it, vi } from 'vitest';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-ai-transcribe-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { AI_PROFILE_UNRESOLVED, AI_ROUTES, registerAiRoutes } from '../../serve/ai-routes.js';
import { AuthError, AuthVerifier } from '../../serve/auth.js';
import { serveCrypto } from '../../serve/crypto.js';
import type { ServeDeps } from '../../serve/deps.js';
import { authorize } from '../../serve/policy.js';
import { SessionStore } from '../../serve/sessions.js';
import { ProviderProfileError } from '../provider.js';
import {
  AI_TRANSCRIBE_FAILED,
  AI_TRANSCRIBE_UNSUPPORTED,
  MAX_TRANSCRIBE_BYTES,
  TRANSCRIPTION_MODEL,
  TranscriptionFailed,
  transcribeAudio,
} from '../transcribe.js';

const AUDIO = new Uint8Array([0x1a, 0x45, 0xdf, 0xa3, 1, 2, 3]);

function openai(overrides: Partial<Profile> = {}): Profile {
  return {
    format: 'openai-chat',
    baseURL: WK_OPENAI_API_BASE,
    key: 'sk-openai',
    authScheme: 'bearer',
    model: 'gpt-4.1',
    capabilities: { tools: true, streaming: true, parallelToolCalls: true, vision: false },
    ...overrides,
  };
}

function anthropic(): Profile {
  return {
    format: 'anthropic-messages',
    baseURL: WK_ANTHROPIC_API_BASE,
    key: 'sk-ant',
    authScheme: 'x-api-key',
    model: 'claude-test',
    capabilities: { tools: true, streaming: true, parallelToolCalls: false, vision: false },
  };
}

interface Sent {
  url: string;
  headers: Headers;
  form: FormData;
  redirect: RequestRedirect | undefined;
}

/** A provider that records what it was sent and answers `answer`. */
function provider(answer: () => Response = () => Response.json({ text: '  bring shop up  ' })) {
  const sent: Sent[] = [];
  const fetch = ((input: string | URL, init?: RequestInit) => {
    sent.push({
      url: String(input),
      headers: new Headers(init?.headers),
      form: init?.body as FormData,
      redirect: init?.redirect,
    });
    return Promise.resolve(answer());
  }) as typeof globalThis.fetch;
  return { sent, fetch };
}

describe('transcribeAudio', () => {
  it('posts the recording to the profile transcription endpoint with its own auth header', async () => {
    const p = provider();
    const text = await transcribeAudio(openai(), AUDIO, 'audio/webm', { fetch: p.fetch });
    expect(text).toBe('bring shop up');
    expect(p.sent).toHaveLength(1);
    const [sent] = p.sent;
    expect(sent.url).toBe(`${WK_OPENAI_API_BASE}/audio/transcriptions`);
    expect(sent.headers.get('authorization')).toBe('Bearer sk-openai');
    expect(sent.redirect).toBe('error');
    expect(sent.form.get('model')).toBe(TRANSCRIPTION_MODEL);
    const file = sent.form.get('file') as File;
    expect(file.type).toBe('audio/webm');
    expect(file.name).toBe('recording.webm');
    expect(new Uint8Array(await file.arrayBuffer())).toEqual(AUDIO);
  });

  it('refuses an Anthropic Messages profile without sending anything', async () => {
    const p = provider();
    await expect(
      transcribeAudio(anthropic(), AUDIO, 'audio/webm', { fetch: p.fetch })
    ).rejects.toBeInstanceOf(ProviderProfileError);
    expect(p.sent).toHaveLength(0);
  });

  it('refuses a Rediacc tier profile without sending anything', async () => {
    const p = provider();
    await expect(
      transcribeAudio(buildRediaccProfile('standard'), AUDIO, 'audio/ogg', { fetch: p.fetch })
    ).rejects.toThrow(/Rediacc tier profile has no transcription endpoint/);
    expect(p.sent).toHaveLength(0);
  });

  it('refuses a profile whose base URL fails the guard', async () => {
    const p = provider();
    await expect(
      transcribeAudio(openai({ baseURL: 'https://10.0.0.5/v1' }), AUDIO, 'audio/wav', {
        fetch: p.fetch,
      })
    ).rejects.toBeInstanceOf(ProviderProfileError);
    expect(p.sent).toHaveLength(0);
  });

  it('turns a provider refusal into TranscriptionFailed with its message', async () => {
    const p = provider(() =>
      Response.json({ error: { message: 'Invalid file format.' } }, { status: 400 })
    );
    const failure = await transcribeAudio(openai(), AUDIO, 'audio/mp4', { fetch: p.fetch }).catch(
      (e: unknown) => e
    );
    expect(failure).toBeInstanceOf(TranscriptionFailed);
    expect((failure as TranscriptionFailed).status).toBe(400);
    expect((failure as TranscriptionFailed).message).toBe('Invalid file format.');
  });

  it('refuses an answer without a transcript', async () => {
    const p = provider(() => Response.json({ segments: [] }));
    await expect(
      transcribeAudio(openai(), AUDIO, 'audio/mpeg', { fetch: p.fetch })
    ).rejects.toThrow(/without a transcript/);
  });
});

const OWNER_TOKEN = 'rdt_owner';
const OWNER = {
  active: true,
  scopes: ['proxy:exec'],
  orgId: 'org-1',
  teamId: null,
  createdByUserId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
  tokenId: 'tok-owner',
};

const fakeAccount = ((_url: string | URL, init?: RequestInit) => {
  const { token } = JSON.parse(String(init?.body ?? '{}')) as { token: string };
  return Promise.resolve(Response.json(token === OWNER_TOKEN ? OWNER : { active: false }));
}) as typeof fetch;

function configWith(ai: AiConfig): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000cc',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: { machines: {}, repositories: {} },
    state: { repos: {} },
    encryption: { mode: 'plaintext' },
    ai,
  } as RdcConfig;
}

function app(config: RdcConfig, transcribeFetch: typeof globalThis.fetch): Hono {
  const deps: ServeDeps = {
    mode: 'container',
    auth: new AuthVerifier({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      fetchImpl: fakeAccount,
    }),
    sessions: new SessionStore(),
    crypto: serveCrypto,
    executor: { execute: () => Promise.reject(new Error('transcription runs nothing')) },
    loadConfig: () => Promise.resolve(config),
    authorize,
  };
  const hono = new Hono();
  registerAiRoutes(
    hono,
    deps,
    {
      authenticate: (header) => {
        const token = header?.replace(/^Bearer\s+/i, '').trim() ?? '';
        if (!token) return Promise.reject(new AuthError('no token', 401));
        return deps.auth.verify(token);
      },
      statusFor: (error) =>
        error instanceof AuthError
          ? { status: error.status, message: error.message }
          : { status: 500 as const, message: error instanceof Error ? error.message : 'failed' },
      requestScopedConfig: (c) => c,
      withRequestConfig: (_c, fn) => fn(),
      configSession: (header) => header?.trim() || undefined,
    },
    {
      modes: {
        set: () => undefined,
        get: () => 'ask',
        allowExact: () => undefined,
        allowsExact: () => false,
      },
      approvals: {
        submit: () => Promise.resolve({ ok: true }),
        issue: () => 'tok',
        takeGrant: () => false,
        revokeGrant: () => undefined,
      },
      chat: { transcribeFetch },
    }
  );
  return hono;
}

async function transcribe(
  hono: Hono,
  {
    query = '',
    type = 'audio/webm;codecs=opus',
    body = AUDIO as BodyInit,
    token = OWNER_TOKEN,
  } = {}
) {
  const response = await hono.request(`${AI_ROUTES.transcribe}${query}`, {
    method: 'POST',
    headers: { 'content-type': type, ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body,
  });
  return { status: response.status, body: (await response.json()) as Record<string, unknown> };
}

const TWO_PROFILES: AiConfig = {
  providers: { claude: anthropic(), whisper: openai() },
  default: 'claude',
};

describe('POST /v1/ai/transcribe', () => {
  it('answers the transcript of the named OpenAI-compatible profile', async () => {
    const p = provider();
    const hono = app(configWith(TWO_PROFILES), p.fetch);
    const answer = await transcribe(hono, { query: '?profile=whisper' });
    expect(answer).toEqual({ status: 200, body: { text: 'bring shop up' } });
    expect(p.sent[0]?.url).toBe(`${WK_OPENAI_API_BASE}/audio/transcriptions`);
  });

  it('refuses an Anthropic Messages profile with AI_TRANSCRIBE_UNSUPPORTED and sends nothing', async () => {
    const p = provider();
    const answer = await transcribe(app(configWith(TWO_PROFILES), p.fetch));
    expect(answer.status).toBe(422);
    expect(answer.body.code).toBe(AI_TRANSCRIBE_UNSUPPORTED);
    expect(p.sent).toHaveLength(0);
  });

  it('refuses an unknown profile', async () => {
    const p = provider();
    const answer = await transcribe(app(configWith(TWO_PROFILES), p.fetch), {
      query: '?profile=missing',
    });
    expect(answer.status).toBe(404);
    expect(answer.body.code).toBe(AI_PROFILE_UNRESOLVED);
  });

  it('refuses a body that is not audio, and an empty or oversized recording', async () => {
    const p = provider();
    const hono = app(configWith(TWO_PROFILES), p.fetch);
    const json = await transcribe(hono, { query: '?profile=whisper', type: 'application/json' });
    expect(json.status).toBe(415);
    expect(json.body.code).toBe(AI_TRANSCRIBE_UNSUPPORTED);
    expect(
      (await transcribe(hono, { query: '?profile=whisper', body: new Uint8Array(0) })).status
    ).toBe(413);
    const big = new Uint8Array(MAX_TRANSCRIBE_BYTES + 1);
    expect((await transcribe(hono, { query: '?profile=whisper', body: big })).status).toBe(413);
    expect(p.sent).toHaveLength(0);
  });

  it('stops reading an oversized upload at the cap instead of holding it whole', async () => {
    const p = provider();
    const hono = app(configWith(TWO_PROFILES), p.fetch);
    const chunk = new Uint8Array(1024 * 1024);
    const chunks = Math.ceil(MAX_TRANSCRIBE_BYTES / chunk.byteLength) + 90;
    let pulled = 0;
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (pulled >= chunks) return controller.close();
        pulled += 1;
        controller.enqueue(chunk);
      },
    });
    const response = await hono.request(`${AI_ROUTES.transcribe}?profile=whisper`, {
      method: 'POST',
      headers: { 'content-type': 'audio/webm', authorization: `Bearer ${OWNER_TOKEN}` },
      body,
      duplex: 'half',
    } as RequestInit);
    expect(response.status).toBe(413);
    // The cap is 10 chunks of 1 MiB; a small read-ahead is the stream's, never the 100 of the whole upload.
    expect(pulled).toBeLessThan(chunks - 50);
    expect(p.sent).toHaveLength(0);
  });

  it('refuses a declared oversized upload before reading any of it', async () => {
    const p = provider();
    const hono = app(configWith(TWO_PROFILES), p.fetch);
    const response = await hono.request(`${AI_ROUTES.transcribe}?profile=whisper`, {
      method: 'POST',
      headers: {
        'content-type': 'audio/webm',
        'content-length': String(MAX_TRANSCRIBE_BYTES + 1),
        authorization: `Bearer ${OWNER_TOKEN}`,
      },
      body: AUDIO as BodyInit,
    });
    expect(response.status).toBe(413);
    expect(p.sent).toHaveLength(0);
  });

  it('answers a profile that fails the guard as unresolved (404 AI_PROFILE_UNRESOLVED) and sends nothing', async () => {
    const p = provider();
    const config = configWith({
      providers: { bad: openai({ baseURL: 'https://10.0.0.5/v1' }) },
      default: 'bad',
    });
    const answer = await transcribe(app(config, p.fetch));
    expect(answer.status).toBe(404);
    expect(answer.body.code).toBe(AI_PROFILE_UNRESOLVED);
    expect(p.sent).toHaveLength(0);
  });

  it('refuses a config session the caller does not own, as every other AI route does', async () => {
    const p = provider();
    const hono = app(configWith(TWO_PROFILES), p.fetch);
    const response = await hono.request(`${AI_ROUTES.transcribe}?profile=whisper`, {
      method: 'POST',
      headers: {
        'content-type': 'audio/webm',
        'x-config-session': 'someone-elses',
        authorization: `Bearer ${OWNER_TOKEN}`,
      },
      body: AUDIO as BodyInit,
    });
    expect(response.status).not.toBe(200);
    expect(p.sent).toHaveLength(0);
  });

  it('refuses a caller without a token', async () => {
    const p = provider();
    const answer = await transcribe(app(configWith(TWO_PROFILES), p.fetch), {
      query: '?profile=whisper',
      token: '',
    });
    expect(answer.status).toBe(401);
    expect(p.sent).toHaveLength(0);
  });

  it('answers a provider refusal as 502 AI_TRANSCRIBE_FAILED', async () => {
    const p = provider(() =>
      Response.json({ error: { message: 'quota exceeded' } }, { status: 429 })
    );
    const answer = await transcribe(app(configWith(TWO_PROFILES), p.fetch), {
      query: '?profile=whisper',
    });
    expect(answer).toEqual({
      status: 502,
      body: { error: 'quota exceeded', code: AI_TRANSCRIBE_FAILED },
    });
  });
});
