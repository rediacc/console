import { describe, expect, it } from 'vitest';
import { type MountOps, withMount } from '../withMount';

const ops = (over: Partial<MountOps> = {}): { ops: MountOps; calls: string[] } => {
  const calls: string[] = [];
  return {
    calls,
    ops: {
      mount: () => Promise.resolve(void calls.push('mount')),
      sync: () => Promise.resolve(void calls.push('sync')),
      unmount: () => Promise.resolve(void calls.push('unmount')),
      ...over,
    },
  };
};

describe('withMount', () => {
  it('mounts, runs the body, syncs and unmounts in order', async () => {
    const t = ops();
    await withMount(t.ops, () => Promise.resolve(void t.calls.push('body')));
    expect(t.calls).toEqual(['mount', 'body', 'sync', 'unmount']);
  });

  it('unmounts and names the body error first, the unmount error second', async () => {
    const t = ops({
      unmount: () => {
        t.calls.push('unmount');
        return Promise.reject(new Error('umount: target is busy'));
      },
    });
    const err = await withMount(t.ops, () => Promise.reject(new Error('dd: no space left'))).then(
      () => undefined,
      (e: Error) => e
    );
    expect(t.calls).toContain('unmount');
    expect(t.calls).not.toContain('sync');
    expect(err?.message).toContain('dd: no space left');
    expect(err?.message).toContain('umount: target is busy');
    expect(err?.message.indexOf('dd: no space left')).toBeLessThan(
      err?.message.indexOf('umount: target is busy') ?? -1
    );
  });

  it('throws the body error alone when the unmount succeeds', async () => {
    const t = ops();
    await expect(withMount(t.ops, () => Promise.reject(new Error('body failed')))).rejects.toThrow(
      'body failed'
    );
    expect(t.calls).toContain('unmount');
  });

  it('throws the unmount error when the body succeeded', async () => {
    const t = ops({
      unmount: () => Promise.reject(new Error('umount failed')),
    });
    await expect(withMount(t.ops, () => Promise.resolve())).rejects.toThrow('umount failed');
  });

  it('does not unmount when the mount itself failed', async () => {
    const t = ops({
      mount: () => Promise.reject(new Error('mount failed')),
    });
    await expect(withMount(t.ops, () => Promise.resolve())).rejects.toThrow('mount failed');
    expect(t.calls).not.toContain('unmount');
  });
});
