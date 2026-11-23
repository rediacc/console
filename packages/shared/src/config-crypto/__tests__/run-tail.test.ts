import { describe, expect, it } from 'vitest';
import { randomBytes } from '../aes.js';
import { openRunTail, RUN_TAIL_MAX_BYTES, sealRunTail } from '../run-tail.js';

const cek = randomBytes(32);

describe('run tail sealing', () => {
  it('round-trips a tail', async () => {
    const sealed = await sealRunTail(cek, 'org1', 'run1', 'step 1\nstep 2 é\n');
    expect(sealed).not.toContain('step');
    expect(await openRunTail(cek, 'org1', 'run1', sealed)).toBe('step 1\nstep 2 é\n');
  });

  it('fails to open under a changed run_id or org_id (the AAD)', async () => {
    const sealed = await sealRunTail(cek, 'org1', 'run1', 'secret output');
    await expect(openRunTail(cek, 'org1', 'run2', sealed)).rejects.toThrow();
    await expect(openRunTail(cek, 'org2', 'run1', sealed)).rejects.toThrow();
  });

  it('fails to open without the sealing CEK', async () => {
    const sealed = await sealRunTail(cek, 'org1', 'run1', 'secret output');
    await expect(openRunTail(randomBytes(32), 'org1', 'run1', sealed)).rejects.toThrow();
  });

  it('cuts a tail over 8 KiB from the front, keeping the end', async () => {
    const text = `${'a'.repeat(RUN_TAIL_MAX_BYTES)}${'b'.repeat(100)}`;
    const opened = await openRunTail(cek, 'o', 'r', await sealRunTail(cek, 'o', 'r', text));
    expect(new TextEncoder().encode(opened).length).toBe(RUN_TAIL_MAX_BYTES);
    expect(opened.endsWith('b'.repeat(100))).toBe(true);
    expect(opened.startsWith('a')).toBe(true);
  });

  it('keeps a tail of exactly 8 KiB whole (control)', async () => {
    const text = 'x'.repeat(RUN_TAIL_MAX_BYTES);
    expect(await openRunTail(cek, 'o', 'r', await sealRunTail(cek, 'o', 'r', text))).toBe(text);
  });

  it('cuts on a character boundary when the cut lands inside a multi-byte character', async () => {
    // The euro sign is 3 bytes and the cut lands inside it, so the whole character is dropped.
    const text = `€${'a'.repeat(RUN_TAIL_MAX_BYTES - 1)}`;
    const opened = await openRunTail(cek, 'o', 'r', await sealRunTail(cek, 'o', 'r', text));
    expect(opened).toBe('a'.repeat(RUN_TAIL_MAX_BYTES - 1));
  });
});
