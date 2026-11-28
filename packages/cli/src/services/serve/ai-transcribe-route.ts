/** The transcription route's recording intake and provider call (split from ai-routes.ts). */

import type { Profile } from '@rediacc/shared/ai';
import type { Context } from 'hono';
import { z } from 'zod';
import { ProviderProfileError } from '../ai/provider.js';
import {
  AI_TRANSCRIBE_FAILED,
  AI_TRANSCRIBE_UNSUPPORTED,
  MAX_TRANSCRIBE_BYTES,
  readCapped,
  supportsTranscription,
  TRANSCRIBE_AUDIO_TYPES,
  TranscriptionFailed,
  transcribeAudio,
} from '../ai/transcribe.js';
import { BadAiRequest } from './ai-approval.js';
import { AI_PROFILE_UNRESOLVED } from './ai-route-types.js';

/** A `?profile=` of the transcription route, as the chat body's `profile` is checked. */
const TranscribeProfileSchema = z.string().min(1).max(128);

function audioTypeOf(header: string | undefined) {
  const type = (header ?? '').split(';')[0]?.trim().toLowerCase() ?? '';
  return TRANSCRIBE_AUDIO_TYPES.find((known) => known === type);
}

export interface Recording {
  type: (typeof TRANSCRIBE_AUDIO_TYPES)[number];
  profile: string | undefined;
  audio: Uint8Array<ArrayBuffer>;
}

/** The answer to a profile the transcription guard refused or a provider refusal; anything else is rethrown. */
function transcriptionRefusal(error: unknown): { body: Record<string, string>; status: 422 | 502 } {
  if (error instanceof ProviderProfileError) {
    return { status: 422, body: { error: error.message, code: AI_PROFILE_UNRESOLVED } };
  }
  if (!(error instanceof TranscriptionFailed)) throw error;
  return { status: 502, body: { error: error.message, code: AI_TRANSCRIBE_FAILED } };
}

/** The recording of a transcription request, or the refusal of a malformed one. */
export async function readRecording(
  c: Context
): Promise<Recording | { refusal: { error: string; code?: string }; status: 413 | 415 }> {
  const type = audioTypeOf(c.req.header('content-type'));
  if (!type) {
    return {
      status: 415,
      refusal: {
        error: `Transcription takes ${TRANSCRIBE_AUDIO_TYPES.join(', ')}`,
        code: AI_TRANSCRIBE_UNSUPPORTED,
      },
    };
  }
  const raw = c.req.query('profile');
  const name = raw === undefined ? undefined : TranscribeProfileSchema.safeParse(raw);
  if (name && !name.success) throw new BadAiRequest('Malformed AI request: profile: invalid');
  const declared = Number(c.req.header('content-length'));
  const audio =
    Number.isFinite(declared) && declared > MAX_TRANSCRIBE_BYTES
      ? undefined
      : await readCapped(c.req.raw.body, MAX_TRANSCRIBE_BYTES);
  if (!audio || audio.byteLength === 0) {
    return { status: 413, refusal: { error: `A recording is 1 to ${MAX_TRANSCRIBE_BYTES} bytes` } };
  }
  return { type, profile: name?.data, audio };
}

/** The provider's transcript of one recording, or the refusal that answers it. */
export async function transcription(
  profile: Profile,
  recording: Recording,
  signal: AbortSignal,
  fetch: typeof globalThis.fetch | undefined
): Promise<{ body: Record<string, string>; status: 200 | 422 | 502 }> {
  if (!supportsTranscription(profile)) {
    return {
      status: 422,
      body: {
        error: 'This profile has no transcription endpoint; pick an OpenAI-compatible profile.',
        code: AI_TRANSCRIBE_UNSUPPORTED,
      },
    };
  }
  try {
    const text = await transcribeAudio(profile, recording.audio, recording.type, {
      ...(fetch ? { fetch } : {}),
      signal,
    });
    return { status: 200, body: { text } };
  } catch (error) {
    return transcriptionRefusal(error);
  }
}
