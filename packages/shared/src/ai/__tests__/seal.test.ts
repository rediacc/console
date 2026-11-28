import { describe, expect, it } from 'vitest';
import { fromBase64, randomBytes } from '../../config-crypto/aes.js';
import {
  AI_MESSAGE_MAX_BYTES,
  AI_SEALED_BODY_MAX_BYTES,
  AI_TITLE_MAX_BYTES,
  type AiMessageBody,
  AiMessageTooLargeError,
  type AiSealContext,
  openAiMessage,
  openAiTitle,
  sealAiMessage,
  sealAiTitle,
} from '../seal.js';

const cek = randomBytes(32);
const ctx: AiSealContext = {
  orgId: 'org-1',
  userId: 'user-1',
  conversationId: 'conv-1',
  cekGeneration: 3,
};
const body: AiMessageBody = {
  role: 'assistant',
  text: 'Two machines are listed. é',
  runs: [{ toolCallId: 'call-1', runId: 'run-1', pathKey: 'machine list' }],
  model: 'claude-sonnet',
};

describe('sealed AI messages', () => {
  it('round-trips a message without the plaintext in the sealed value', async () => {
    const sealed = await sealAiMessage(cek, ctx, 'msg-1', body);
    expect(sealed).not.toContain('machines');
    expect(atob(sealed)).not.toContain('machines');
    expect(await openAiMessage(cek, ctx, 'msg-1', sealed)).toEqual(body);
  });

  it('fails to open when any AAD field is swapped', async () => {
    const sealed = await sealAiMessage(cek, ctx, 'msg-1', body);
    await expect(openAiMessage(cek, ctx, 'msg-2', sealed)).rejects.toThrow();
    await expect(openAiMessage(cek, { ...ctx, orgId: 'org-2' }, 'msg-1', sealed)).rejects.toThrow();
    await expect(
      openAiMessage(cek, { ...ctx, userId: 'user-2' }, 'msg-1', sealed)
    ).rejects.toThrow();
    await expect(
      openAiMessage(cek, { ...ctx, conversationId: 'conv-2' }, 'msg-1', sealed)
    ).rejects.toThrow();
    await expect(
      openAiMessage(cek, { ...ctx, cekGeneration: 4 }, 'msg-1', sealed)
    ).rejects.toThrow();
  });

  it('opens under the identical AAD (control for the swap case)', async () => {
    const sealed = await sealAiMessage(cek, ctx, 'msg-1', body);
    await expect(openAiMessage(cek, { ...ctx }, 'msg-1', sealed)).resolves.toEqual(body);
  });

  it('keeps (conversation a|b, message c) apart from (conversation a, message b|c)', async () => {
    const sealed = await sealAiMessage(cek, { ...ctx, conversationId: 'a|b' }, 'c', body);
    await expect(
      openAiMessage(cek, { ...ctx, conversationId: 'a' }, 'b|c', sealed)
    ).rejects.toThrow();
  });

  it('fails to open under another config key and on a flipped ciphertext byte', async () => {
    const sealed = await sealAiMessage(cek, ctx, 'msg-1', body);
    await expect(openAiMessage(randomBytes(32), ctx, 'msg-1', sealed)).rejects.toThrow();
    const bytes = fromBase64(sealed);
    bytes[bytes.length - 1] ^= 1;
    const flipped = btoa(String.fromCharCode(...bytes));
    await expect(openAiMessage(cek, ctx, 'msg-1', flipped)).rejects.toThrow();
  });

  it('refuses a body carrying a field outside the schema, such as command output', async () => {
    const withOutput = { ...body, output: 'root:x:0:0' } as unknown as AiMessageBody;
    await expect(sealAiMessage(cek, ctx, 'msg-1', withOutput)).rejects.toThrow();
  });

  it('refuses a body over the store limit and seals one at the limit within 64 KiB', async () => {
    const overhead = new TextEncoder().encode(JSON.stringify({ role: 'user', text: '' })).length;
    const atLimit: AiMessageBody = {
      role: 'user',
      text: 'x'.repeat(AI_MESSAGE_MAX_BYTES - overhead),
    };
    const sealed = await sealAiMessage(cek, ctx, 'msg-1', atLimit);
    expect(fromBase64(sealed).length).toBe(AI_SEALED_BODY_MAX_BYTES);

    const over: AiMessageBody = { role: 'user', text: `${atLimit.text}x` };
    await expect(sealAiMessage(cek, ctx, 'msg-1', over)).rejects.toBeInstanceOf(
      AiMessageTooLargeError
    );
  });

  it('refuses a negative or fractional CEK generation', async () => {
    await expect(sealAiMessage(cek, { ...ctx, cekGeneration: -1 }, 'm', body)).rejects.toThrow(
      RangeError
    );
    await expect(sealAiMessage(cek, { ...ctx, cekGeneration: 1.5 }, 'm', body)).rejects.toThrow(
      RangeError
    );
  });
});

describe('sealed AI titles', () => {
  it('round-trips a title and never opens as a message', async () => {
    const sealed = await sealAiTitle(cek, ctx, 'Disk usage on hostinger');
    expect(await openAiTitle(cek, ctx, sealed)).toBe('Disk usage on hostinger');
    await expect(openAiMessage(cek, ctx, '', sealed)).rejects.toThrow();
    await expect(openAiTitle(cek, { ...ctx, conversationId: 'conv-2' }, sealed)).rejects.toThrow();
  });

  it('cuts a long title at a character boundary within the stored ceiling', async () => {
    const title = 'é'.repeat(AI_TITLE_MAX_BYTES);
    const sealed = await sealAiTitle(cek, ctx, title);
    expect(sealed.length).toBeLessThanOrEqual(1024);
    const opened = await openAiTitle(cek, ctx, sealed);
    expect(new TextEncoder().encode(opened).length).toBe(AI_TITLE_MAX_BYTES);
    expect(opened).toBe('é'.repeat(AI_TITLE_MAX_BYTES / 2));
  });
});
