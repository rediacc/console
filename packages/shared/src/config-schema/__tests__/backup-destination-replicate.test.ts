/**
 * A backup destination is `upload` (absent mode) or `replicate`. `from` names the store a replicate destination copies
 * from: required for replicate, refused for upload.
 */
import { describe, expect, it } from 'vitest';
import { BackupDestinationSchema } from '../schemas.js';

const base = { kind: 'hosted-service', name: 'd', target: 'eu-west' };

describe('BackupDestinationSchema mode and from', () => {
  it('admits replicate with a store-id source', () => {
    expect(
      BackupDestinationSchema.safeParse({ ...base, mode: 'replicate', from: 'home' }).success
    ).toBe(true);
  });

  it('refuses replicate without from', () => {
    expect(BackupDestinationSchema.safeParse({ ...base, mode: 'replicate' }).success).toBe(false);
  });

  it('refuses from without replicate', () => {
    expect(BackupDestinationSchema.safeParse({ ...base, from: 'home' }).success).toBe(false);
    expect(
      BackupDestinationSchema.safeParse({ ...base, mode: 'upload', from: 'home' }).success
    ).toBe(false);
  });

  it('refuses a source that is not a store id and an unknown mode', () => {
    expect(
      BackupDestinationSchema.safeParse({ ...base, mode: 'replicate', from: 'Bad Id' }).success
    ).toBe(false);
    expect(BackupDestinationSchema.safeParse({ ...base, mode: 'mirror' }).success).toBe(false);
  });

  it('keeps a destination without mode an upload destination', () => {
    expect(BackupDestinationSchema.safeParse(base).success).toBe(true);
  });
});
