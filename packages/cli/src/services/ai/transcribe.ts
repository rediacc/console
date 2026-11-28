/**
 * Provider transcription (D12 of agent/plans/PLAN-console-ai-assistant.md, operator ruling C38):
 * one recording sent to the `/audio/transcriptions` endpoint of an OpenAI-compatible profile.
 *
 * The request goes through the same guarded fetch as the profile's chat calls, so the base URL
 * guard, the profile's own auth header and the refusal of redirects apply. An Anthropic Messages
 * profile has no transcription endpoint and the Rediacc tier offers none, so both are refused
 * before anything is sent. The audio is never written anywhere.
 */
import { isRediaccProfile, type Profile, validateProfile } from '@rediacc/shared/ai';
import { guardedFetch, ProviderProfileError } from './provider.js';

/** The model an OpenAI-compatible transcription endpoint is asked for. */
export const TRANSCRIPTION_MODEL = 'whisper-1';

/** The audio types the account relays (`AUDIO_TYPES` in private/account/src/routes/console-ai.ts). */
export const TRANSCRIBE_AUDIO_TYPES = [
  'audio/webm',
  'audio/ogg',
  'audio/wav',
  'audio/mpeg',
  'audio/mp4',
] as const;

/** The largest recording the account relays, and so the largest this side accepts. */
export const MAX_TRANSCRIBE_BYTES = 10 * 1024 * 1024;

export const AI_TRANSCRIBE_UNSUPPORTED = 'AI_TRANSCRIBE_UNSUPPORTED';
export const AI_TRANSCRIBE_FAILED = 'AI_TRANSCRIBE_FAILED';

/** A transcription the provider refused or answered with something other than text. */
export class TranscriptionFailed extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'TranscriptionFailed';
    this.status = status;
  }
}

/** The body's bytes, or undefined once it exceeds `max`: the read stops there, so an oversized upload is never held whole. */
export async function readCapped(
  body: ReadableStream<Uint8Array> | null,
  max: number
): Promise<Uint8Array<ArrayBuffer> | undefined> {
  if (!body) return new Uint8Array(0);
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > max) {
      await reader.cancel().catch(() => undefined);
      return undefined;
    }
    chunks.push(value);
  }
  const audio = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    audio.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return audio;
}

/** Whether a profile can transcribe at all. */
export function supportsTranscription(profile: Profile): boolean {
  return profile.format === 'openai-chat' && !isRediaccProfile(profile);
}

const EXTENSIONS: Record<(typeof TRANSCRIBE_AUDIO_TYPES)[number], string> = {
  'audio/webm': 'webm',
  'audio/ogg': 'ogg',
  'audio/wav': 'wav',
  'audio/mpeg': 'mp3',
  'audio/mp4': 'm4a',
};

/** The provider's error message, or a fixed one; the body is never echoed whole. */
async function providerMessage(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as {
    error?: { message?: unknown } | string;
  } | null;
  const message = typeof body?.error === 'string' ? body.error : body?.error?.message;
  return typeof message === 'string' && message.length > 0
    ? message.slice(0, 500)
    : `the provider answered HTTP ${response.status}`;
}

/**
 * Transcribe one recording on `profile`. Throws ProviderProfileError for a profile that cannot
 * transcribe or fails its checks, and TranscriptionFailed for a provider refusal.
 */
export async function transcribeAudio(
  profile: Profile,
  audio: Uint8Array<ArrayBuffer>,
  type: (typeof TRANSCRIBE_AUDIO_TYPES)[number],
  options: { fetch?: typeof globalThis.fetch; signal?: AbortSignal } = {}
): Promise<string> {
  if (!supportsTranscription(profile)) {
    throw new ProviderProfileError([
      {
        path: '/format',
        message: `a ${isRediaccProfile(profile) ? 'Rediacc tier' : profile.format} profile has no transcription endpoint`,
      },
    ]);
  }
  const checked = validateProfile(profile);
  if (!checked.ok) throw new ProviderProfileError(checked.issues);
  const valid = checked.profile;
  const fetch = guardedFetch(valid, options.fetch);
  const form = new FormData();
  form.append('file', new Blob([audio], { type }), `recording.${EXTENSIONS[type]}`);
  form.append('model', TRANSCRIPTION_MODEL);
  form.append('response_format', 'json');
  const base = valid.baseURL.endsWith('/') ? valid.baseURL : `${valid.baseURL}/`;
  const response = await fetch(new URL('audio/transcriptions', base).href, {
    method: 'POST',
    body: form,
    ...(options.signal ? { signal: options.signal } : {}),
  });
  if (!response.ok) {
    throw new TranscriptionFailed(response.status, await providerMessage(response));
  }
  const body = (await response.json().catch(() => null)) as { text?: unknown } | null;
  if (typeof body?.text !== 'string') {
    throw new TranscriptionFailed(502, 'the provider answered without a transcript');
  }
  return body.text.trim();
}
