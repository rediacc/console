/**
 * The executor's AI conversation recorder (D7 and D8 of agent/plans/PLAN-console-ai-assistant.md).
 *
 * Each message of a console AI chat is sealed here, in the executor, under the session's config
 * key (packages/shared/src/ai/seal.ts) and posted with the executor token to the account server's
 * `POST /console/ai/messages`, which stores ciphertext only. A message carries its parent id and its
 * seq, so an edit or a regeneration is a sibling in the tree rather than an overwrite. The first
 * message of a conversation may carry its sealed title.
 *
 * Delivery never fails or delays a turn: a missing key, a message the store would refuse, an
 * unreachable account server and every refusal are reported to `onFailure` and dropped, and
 * `record` always resolves. Messages of one conversation are posted in order, so a child never
 * reaches the account server before its parent. Delivery retries twice on a network failure, a
 * 5xx or a 429, the same budget as the run recorder (serve/run-index.ts).
 */

import { randomUUID } from 'node:crypto';
import { type AiMessageBody, sealAiMessage, sealAiTitle } from '@rediacc/shared/ai/seal';
import { deadlineFetch, describeFetchError } from '../serve/account-fetch.js';
import type { SessionPrincipal } from '../serve/sessions.js';

/** Where the executor posts sealed messages, relative to the account server. */
export const AI_MESSAGES_PATH = '/account/api/v1/console/ai/messages';

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

export interface AiRecordOutcome {
  messageId: string;
  /** Whether the account server accepted the message. */
  delivered: boolean;
}

export interface AiRecorder {
  /** Seal and post one message. Resolves once it was delivered or given up on; never rejects. */
  record(message: AiMessageRecord): Promise<AiRecordOutcome>;
}

export interface AiRecorderOptions {
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
    try {
      return (
        (await message.cek()) ?? 'the session holds no config key, so the message cannot be sealed'
      );
    } catch (error) {
      return `the session's config key could not be read: ${describeFetchError(error)}`;
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
