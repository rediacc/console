/**
 * The executor's AI conversation recorder (D7 and D8 of agent/plans/PLAN-console-ai-assistant.md).
 *
 * Each message of a console AI chat is sealed here, in the executor, under the session's config
 * key (packages/shared/src/ai/seal.ts) and posted with the executor token to the account server's
 * `POST /console/ai/messages`, which stores ciphertext only. A message carries its parent id and its
 * seq, so an edit or a regeneration is a sibling in the tree rather than an overwrite. The first
 * message of a conversation may carry its sealed title.
 *
 * Delivery never fails a turn: a missing key, a message the store would refuse, an unreachable
 * account server and every refusal are reported to `onFailure` and dropped, and `record` always
 * resolves. Messages of one conversation are posted in order, so a child never reaches the account
 * server before its parent. Delivery retries twice on a network failure, a 5xx or a 429, the same
 * budget as the run recorder (serve/run-index.ts).
 *
 * {@link AiTranscripts} is what the chat route (serve/ai-routes.ts) records through. The chat body
 * carries the transcript as role and content pairs with no message ids, so the transcript is
 * recorded linearly: a message's id is fixed by its conversation and its position, its parent is
 * the message before it, and its seq is its position. Recording a position again is a replay the
 * store answers as a no-op, so an edited or regenerated message is not stored as a sibling: the
 * store keeps the first message recorded at that position. The route waits for a turn's opening
 * messages before the model runs, because the account's approval route answers a held call only in
 * a conversation whose row the first recorded message created.
 */

import { createHash, randomUUID } from 'node:crypto';
import { type AiMessageBody, sealAiMessage, sealAiTitle } from '@rediacc/shared/ai/seal';
import { deadlineFetch, describeFetchError } from '../serve/account-fetch.js';
import type { SessionPrincipal } from '../serve/sessions.js';

/** Why a message cannot be sealed when the session's config holds no key. */
const NO_CONFIG_KEY = 'the session holds no config key, so the message cannot be sealed';

/** Where the executor posts sealed messages, relative to the account server. */
const AI_MESSAGES_PATH = '/account/api/v1/console/ai/messages';

/** Deliveries per message: the first attempt and two retries. */
export const AI_MESSAGE_ATTEMPTS = 3;

export interface AiMessageRecord {
  principal: SessionPrincipal;
  conversationId: string;
  /** Minted when absent. */
  messageId?: string;
  /** The message this one answers or replaces a sibling under; null for a conversation's root. */
  parentId: string | null;
  seq: number;
  body: AiMessageBody;
  /** The conversation title, sealed beside the message; sent with the first message only. */
  title?: string;
  /** The generation of the config key `cek` returns, named by the session's store. */
  cekGeneration: number;
  /** The session's config key, read at sealing time so the recorder never holds key material. */
  cek: () => Promise<Uint8Array | undefined>;
}

interface AiRecordOutcome {
  messageId: string;
  /** Whether the account server accepted the message. */
  delivered: boolean;
}

export interface AiRecorder {
  /** Seal and post one message. Resolves once it was delivered or given up on; never rejects. */
  record(message: AiMessageRecord): Promise<AiRecordOutcome>;
  /** Conversations with a delivery still in flight; a settled conversation is not counted. */
  pendingConversations(): number;
}

/** How long a delivery waits for the session's config key before it gives up on the message. */
const AI_KEY_TIMEOUT_MS = 30_000;

export interface AiRecorderOptions {
  /** Bound on reading the config key, so a stuck key read settles its chain entry. */
  keyTimeoutMs?: number;
  accountUrl: string;
  executorToken: string;
  fetchImpl?: typeof globalThis.fetch;
  /** Called for a message that was not delivered, with why. */
  onFailure?: (reason: string, message: { conversationId: string; messageId: string }) => void;
}

interface AttemptFailure {
  reason: string;
  retry: boolean;
}

/** The body `POST /console/ai/messages` takes: the message and its title sealed, ids in the clear. */
async function sealedWrite(
  message: AiMessageRecord,
  messageId: string,
  cek: Uint8Array,
  onBehalfOfTokenId: string
) {
  const ctx = {
    orgId: message.principal.orgId,
    userId: message.principal.userId,
    conversationId: message.conversationId,
    cekGeneration: message.cekGeneration,
  };
  const titleSealed =
    message.title === undefined ? undefined : await sealAiTitle(cek, ctx, message.title);
  return {
    conversationId: message.conversationId,
    messageId,
    parentId: message.parentId,
    seq: message.seq,
    body: await sealAiMessage(cek, ctx, messageId, message.body),
    cekGeneration: message.cekGeneration,
    ...(titleSealed === undefined ? {} : { titleSealed }),
    onBehalfOfTokenId,
  };
}

export function createAiRecorder(options: AiRecorderOptions): AiRecorder {
  const fetchImpl = deadlineFetch(options.fetchImpl ?? globalThis.fetch);
  const url = `${options.accountUrl.replace(/\/+$/, '')}${AI_MESSAGES_PATH}`;
  const chains = new Map<string, Promise<unknown>>();

  const report = (reason: string, conversationId: string, messageId: string): void => {
    try {
      options.onFailure?.(reason, { conversationId, messageId });
    } catch {
      // A reporter that throws must not reach the turn.
    }
  };

  async function attempt(body: string): Promise<AttemptFailure | undefined> {
    try {
      const response = await fetchImpl(url, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${options.executorToken}`,
          'content-type': 'application/json',
        },
        body,
      });
      if (response.ok) return undefined;
      const detail = await response.text().catch(() => '');
      return {
        reason: `the account server answered ${response.status}${detail ? `: ${detail.slice(0, 200)}` : ''}`,
        retry: response.status >= 500 || response.status === 429,
      };
    } catch (error) {
      return { reason: describeFetchError(error), retry: true };
    }
  }

  /** The session's config key, or why there is none. */
  async function readKey(message: AiMessageRecord): Promise<Uint8Array | string> {
    let timer: NodeJS.Timeout | undefined;
    try {
      const limit = new Promise<string>((resolve) => {
        timer = setTimeout(
          () => resolve('the session config key read timed out, so the message cannot be sealed'),
          options.keyTimeoutMs ?? AI_KEY_TIMEOUT_MS
        );
      });
      const read = message.cek().then((key) => key ?? NO_CONFIG_KEY);
      return await Promise.race([read, limit]);
    } catch (error) {
      return `the session's config key could not be read: ${describeFetchError(error)}`;
    } finally {
      clearTimeout(timer);
    }
  }

  /** Seal the message; a reason string when it cannot be sealed. */
  async function seal(message: AiMessageRecord, messageId: string) {
    const tokenId = message.principal.tokenId;
    if (!tokenId) return 'the principal carries no token id to write on behalf of';
    const cek = await readKey(message);
    if (typeof cek === 'string') return cek;
    try {
      return await sealedWrite(message, messageId, cek, tokenId);
    } catch (error) {
      return `the message could not be sealed: ${error instanceof Error ? error.message : String(error)}`;
    }
  }

  async function deliver(message: AiMessageRecord, messageId: string): Promise<AiRecordOutcome> {
    const sealed = await seal(message, messageId);
    if (typeof sealed === 'string') {
      report(sealed, message.conversationId, messageId);
      return { messageId, delivered: false };
    }
    const body = JSON.stringify(sealed);
    let failed: AttemptFailure | undefined;
    for (let n = 1; n <= AI_MESSAGE_ATTEMPTS; n++) {
      failed = await attempt(body);
      if (!failed?.retry) break;
    }
    if (failed) report(failed.reason, message.conversationId, messageId);
    return { messageId, delivered: !failed };
  }

  return {
    pendingConversations: () => chains.size,
    record(message) {
      const messageId = message.messageId ?? randomUUID();
      const previous = chains.get(message.conversationId) ?? Promise.resolve();
      const next = previous.then(() => deliver(message, messageId));
      chains.set(message.conversationId, next);
      // A chain is kept while its delivery is pending, so ordering never depends on a size cap, and
      // dropped once it settles and is still the newest, so the map holds only in-flight work.
      const settle = (): void => {
        if (chains.get(message.conversationId) === next) chains.delete(message.conversationId);
      };
      next.then(settle, settle);
      return next.catch((error: unknown) => {
        report(describeFetchError(error), message.conversationId, messageId);
        return { messageId, delivered: false };
      });
    },
  };
}

/** How the messages of one turn are sealed: the session key's generation and a reader for the key. */
export interface TranscriptKey {
  cekGeneration: number;
  cek: () => Promise<Uint8Array | undefined>;
}

/** One chat turn as the route received it. */
export interface TranscriptTurn {
  principal: SessionPrincipal;
  conversationId: string;
  /** The transcript so far, the user's message last. */
  messages: readonly { role: 'user' | 'assistant'; content: string }[];
  key: TranscriptKey;
}

/** The longest title taken from a conversation's first message, in characters. */
const TITLE_CHARS = 120;

/** Conversations whose delivered length this executor remembers before it forgets the oldest. */
const REMEMBERED_CONVERSATIONS = 1000;

/** The id of the message at `index` of a conversation's linear transcript. */
export function transcriptMessageId(conversationId: string, index: number): string {
  const digest = createHash('sha256').update(`${conversationId}\u0000${index}`).digest('hex');
  return `m${digest.slice(0, 32)}`;
}

/** The first line of a conversation's first message, as its title. */
function titleOf(text: string): string {
  return (text.split('\n')[0] ?? '').trim().slice(0, TITLE_CHARS);
}

/**
 * The linear transcripts of the chats this executor hosts (see the module doc). It remembers how
 * many leading messages of each conversation were delivered, so a turn posts only the messages a
 * previous turn on this executor did not; a restarted executor replays the whole transcript once,
 * and the store answers each replay as a no-op.
 */
export class AiTranscripts {
  /** `${orgId}\0${userId}\0${conversationId}` -> leading messages known delivered. */
  private readonly delivered = new Map<string, number>();

  constructor(
    private readonly recorder: AiRecorder,
    private readonly remembered = REMEMBERED_CONVERSATIONS
  ) {}

  private keyOf(turn: TranscriptTurn): string {
    return `${turn.principal.orgId}\u0000${turn.principal.userId}\u0000${turn.conversationId}`;
  }

  private known(turn: TranscriptTurn): number {
    return this.delivered.get(this.keyOf(turn)) ?? 0;
  }

  private advance(turn: TranscriptTurn, length: number): void {
    const key = this.keyOf(turn);
    if ((this.delivered.get(key) ?? 0) >= length) return;
    this.delivered.delete(key);
    this.delivered.set(key, length);
    while (this.delivered.size > this.remembered) {
      const oldest = this.delivered.keys().next().value;
      if (oldest === undefined) break;
      this.delivered.delete(oldest);
    }
  }

  private record(
    turn: TranscriptTurn,
    index: number,
    body: AiMessageBody,
    firstText: string | undefined
  ): Promise<AiRecordOutcome> {
    return this.recorder.record({
      principal: turn.principal,
      conversationId: turn.conversationId,
      messageId: transcriptMessageId(turn.conversationId, index),
      parentId: index === 0 ? null : transcriptMessageId(turn.conversationId, index - 1),
      seq: index,
      body,
      ...(index === 0 && firstText !== undefined ? { title: titleOf(firstText) } : {}),
      cekGeneration: turn.key.cekGeneration,
      cek: turn.key.cek,
    });
  }

  /**
   * Record the turn's messages this executor has not delivered yet. Resolves once each was
   * delivered or given up on, so the conversation row exists before the turn can hold a call for
   * approval; never rejects.
   */
  async opening(turn: TranscriptTurn): Promise<void> {
    const from = Math.min(this.known(turn), turn.messages.length);
    const first = turn.messages[0]?.content;
    const pending = turn.messages
      .slice(from)
      .map((message, offset) =>
        this.record(turn, from + offset, { role: message.role, text: message.content }, first)
      );
    const outcomes = await Promise.all(pending);
    const failed = outcomes.findIndex((outcome) => !outcome.delivered);
    this.advance(turn, failed === -1 ? turn.messages.length : from + failed);
  }

  /** Record the assistant's reply after the turn's messages; never rejects. */
  async reply(turn: TranscriptTurn, text: string, model: string | undefined): Promise<void> {
    if (text === '') return;
    const index = turn.messages.length;
    const outcome = await this.record(
      turn,
      index,
      { role: 'assistant', text, ...(model ? { model } : {}) },
      undefined
    );
    if (outcome.delivered && this.known(turn) >= index) this.advance(turn, index + 1);
  }
}
