import { describe, expect, it } from 'vitest';
import type { ExecResult } from '../../renet-functions/types';
import { type DatastoreSizeOps, ensureDatastoreSize, parseSizeBytes } from '../chunkCliHarness';

const GIB = 1024 ** 3;
const res = (code: number, stdout = '', stderr = ''): ExecResult =>
  ({ code, stdout, stderr }) as ExecResult;

const fake = (over: Partial<DatastoreSizeOps> = {}): { ops: DatastoreSizeOps; calls: string[] } => {
  const calls: string[] = [];
  return {
    calls,
    ops: {
      init: () => {
        calls.push('init');
        return Promise.resolve(res(1, '', 'datastore already exists'));
      },
      sizeBytes: () => {
        calls.push('size');
        return Promise.resolve(res(0, `${10 * GIB}\n`));
      },
      expand: () => {
        calls.push('expand');
        return Promise.resolve(res(0));
      },
      output: (r) => `${r.stdout}${r.stderr}`,
      ...over,
    },
  };
};

describe('parseSizeBytes', () => {
  it('reads renet size strings', () => {
    expect(parseSizeBytes('32G')).toBe(32 * GIB);
    expect(parseSizeBytes('500M')).toBe(500 * 1024 ** 2);
    expect(parseSizeBytes('1024')).toBe(1024);
  });
});

describe('ensureDatastoreSize', () => {
  it('stops after a fresh init', async () => {
    const t = fake({ init: () => Promise.resolve(res(0)) });
    await ensureDatastoreSize(t.ops, 'w1', '32G');
    expect(t.calls).toEqual([]);
  });

  it('does not expand an existing store that is large enough', async () => {
    const t = fake();
    await ensureDatastoreSize(t.ops, 'w1', '10G');
    expect(t.calls).toEqual(['init', 'size']);
  });

  it('expands an existing store smaller than requested', async () => {
    const t = fake();
    await ensureDatastoreSize(t.ops, 'w1', '32G');
    expect(t.calls).toEqual(['init', 'size', 'expand']);
  });

  it('names both sizes when the expansion fails', async () => {
    const t = fake({ expand: () => Promise.resolve(res(1, '', 'no space on host')) });
    const err = await ensureDatastoreSize(t.ops, 'w1', '32G').then(
      () => undefined,
      (e: Error) => e
    );
    expect(err?.message).toContain(String(10 * GIB));
    expect(err?.message).toContain('32G');
    expect(err?.message).toContain('no space on host');
  });

  it('fails loudly and never expands when the size probe prints no number', async () => {
    const t = fake({
      sizeBytes: () => Promise.resolve(res(1, '', 'df: /mnt/rediacc: No such file')),
    });
    await expect(ensureDatastoreSize(t.ops, 'w1', '32G')).rejects.toThrow(
      /could not read the size of the existing datastore on w1: df: \/mnt\/rediacc: No such file/
    );
    expect(t.calls).toEqual(['init']);
  });

  it('rejects an init failure that is not "already exists"', async () => {
    const t = fake({ init: () => Promise.resolve(res(1, '', 'permission denied')) });
    await expect(ensureDatastoreSize(t.ops, 'w1', '32G')).rejects.toThrow(/permission denied/);
  });
});
