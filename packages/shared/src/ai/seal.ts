/**
 * Sealed AI conversation messages (D7 of agent/plans/PLAN-console-ai-assistant.md).
 *
 * The executor seals every message of a console AI chat with AES-GCM under an HKDF subkey of the
 * session's config key (info `rediacc/ai-conversation/v1`) before it posts the message to the
 * account server, which stores ciphertext only. The unlocked browser opens it again. The AAD binds
 * a body to its org, user, conversation, message and CEK generation, so a body copied onto another
 * row, another user's conversation or a rotated generation fails to open. A conversation title is
 * sealed the same way under its own AAD tag, so a title never opens as a message or the reverse.
 *
 * A body never carries command output: the strict schema has no output field, and a command is
 * named by the plan-4 run id whose sealed tail the browser opens on demand.
 *
 * Web Crypto only, so it runs in Node, Workers and browsers.
 */

import { z } from 'zod';
import { aesDecryptFromString, aesEncryptToString } from '../config-crypto/aes.js';
import { hkdfDeriveKey } from '../config-crypto/hkdf.js';

/** HKDF info string of the conversation subkey. */
export const AI_CONVERSATION_INFO = 'rediacc/ai-conversation/v1';

/** IV (12 bytes) plus the GCM tag (16 bytes) that sealing adds to a plaintext. */
const SEAL_OVERHEAD_BYTES = 28;

/** Largest sealed message the account server stores, in bytes (iv + ciphertext + tag). */
export const AI_SEALED_BODY_MAX_BYTES = 64 * 1024;
/** Largest message plaintext, in UTF-8 bytes, that seals within {@link AI_SEALED_BODY_MAX_BYTES}. */
export const AI_MESSAGE_MAX_BYTES = AI_SEALED_BODY_MAX_BYTES - SEAL_OVERHEAD_BYTES;
/**
 * Largest title plaintext, in UTF-8 bytes. The account server keeps at most 1024 base64 characters
 * of sealed title (768 bytes); a longer title is cut at a character boundary rather than refused.
 */
export const AI_TITLE_MAX_BYTES = 512;

/** The row a sealed value belongs to; every field is part of the AAD. */
export interface AiSealContext {
  orgId: string;
  userId: string;
  conversationId: string;
  /** The config key's generation the value is sealed under; a rotation retires older values. */
  cekGeneration: number;
}

/** One command the assistant ran in a turn, named by its plan-4 run id, never by its output. */
const AiRunRefSchema = z.strictObject({
  toolCallId: z.string().min(1),
  runId: z.string().min(1),
  pathKey: z.string().min(1),
});

/**
 * The plaintext of one message. Strict, so a field the schema does not name (command output, a
 * provider key) is refused at sealing and at opening alike.
 */
export const AiMessageBodySchema = z.strictObject({
  role: z.enum(['user', 'assistant']),
  text: z.string(),
  runs: z.array(AiRunRefSchema).optional(),
  /** The model that wrote an assistant message. */
  model: z.string().min(1).optional(),
});
type AiMessageBody = z.infer<typeof AiMessageBodySchema>;

export type { AiMessageBody };

/** A message whose plaintext exceeds {@link AI_MESSAGE_MAX_BYTES}. */
export class AiMessageTooLargeError extends Error {
  readonly bytes: number;

  constructor(bytes: number) {
    super(
      `An AI message of ${bytes} bytes exceeds the ${AI_MESSAGE_MAX_BYTES}-byte limit of the conversation store`
    );
    this.name = 'AiMessageTooLargeError';
    this.bytes = bytes;
  }
}

const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });

function conversationKey(cek: Uint8Array): Promise<CryptoKey> {
  return hkdfDeriveKey(cek, new Uint8Array(0), AI_CONVERSATION_INFO);
}

function assertGeneration(cekGeneration: number): void {
  if (!Number.isInteger(cekGeneration) || cekGeneration < 0) {
    throw new RangeError(`cekGeneration must be a non-negative integer, got ${cekGeneration}`);
  }
}

/**
 * The AAD of a message or a title. JSON keeps the tuple unambiguous when an id contains a
 * separator, and the leading tag keeps a title and a message apart.
 */
function aad(kind: 'message' | 'title', ctx: AiSealContext, messageId: string): Uint8Array {
  assertGeneration(ctx.cekGeneration);
  return encoder.encode(
    JSON.stringify([kind, ctx.orgId, ctx.userId, ctx.conversationId, messageId, ctx.cekGeneration])
  );
}

/** Keep at most `max` bytes of `bytes`, moving the cut back so it ends on a character boundary. */
function cutToBytes(bytes: Uint8Array, max: number): Uint8Array {
  if (bytes.length <= max) return bytes;
  let end = max;
  while (end > 0 && (bytes[end] & 0xc0) === 0x80) end--;
  return bytes.subarray(0, end);
}

/**
 * Seal one message: base64(iv + ciphertext + tag). Throws a zod error for a body outside the
 * schema and {@link AiMessageTooLargeError} for one over the store's limit.
 */
export async function sealAiMessage(
  cek: Uint8Array,
  ctx: AiSealContext,
  messageId: string,
  body: AiMessageBody
): Promise<string> {
  const plaintext = encoder.encode(JSON.stringify(AiMessageBodySchema.parse(body)));
  if (plaintext.length > AI_MESSAGE_MAX_BYTES) throw new AiMessageTooLargeError(plaintext.length);
  return aesEncryptToString(await conversationKey(cek), plaintext, aad('message', ctx, messageId));
}

/**
 * Open a sealed message. Throws when the key, any AAD field or the ciphertext differ from the
 * sealing call's, and when the opened body is outside the schema.
 */
export async function openAiMessage(
  cek: Uint8Array,
  ctx: AiSealContext,
  messageId: string,
  sealed: string
): Promise<AiMessageBody> {
  const plaintext = await aesDecryptFromString(
    await conversationKey(cek),
    sealed,
    aad('message', ctx, messageId)
  );
  return AiMessageBodySchema.parse(JSON.parse(decoder.decode(plaintext)));
}

/** Seal a conversation title; one over {@link AI_TITLE_MAX_BYTES} is cut at a character boundary. */
export async function sealAiTitle(
  cek: Uint8Array,
  ctx: AiSealContext,
  title: string
): Promise<string> {
  const plaintext = cutToBytes(encoder.encode(title), AI_TITLE_MAX_BYTES);
  return aesEncryptToString(await conversationKey(cek), plaintext, aad('title', ctx, ''));
}

/** Open a sealed conversation title. Throws on any key, AAD or ciphertext mismatch. */
export async function openAiTitle(
  cek: Uint8Array,
  ctx: AiSealContext,
  sealed: string
): Promise<string> {
  const plaintext = await aesDecryptFromString(
    await conversationKey(cek),
    sealed,
    aad('title', ctx, '')
  );
  return decoder.decode(plaintext);
}
