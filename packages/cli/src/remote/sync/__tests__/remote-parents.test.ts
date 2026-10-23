import { existsSync, statSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { planMissingParents, skeletonDestination, writeSkeleton } from '../remote-parents.js';

const probeOf = (present: string[]) => async (p: string) => present.includes(p);

describe('planMissingParents', () => {
  it('plans every segment when none exist', async () => {
    const plan = await planMissingParents('/m', 'a/b/f.txt', probeOf([]));
    expect(plan).toEqual({ existingAncestor: '/m', missing: ['a', 'b'] });
  });

  it('plans only the missing tail when a prefix exists', async () => {
    const plan = await planMissingParents('/m', 'a/b/f.txt', probeOf(['/m/a']));
    expect(plan).toEqual({ existingAncestor: '/m/a', missing: ['b'] });
  });

  it('plans nothing when every parent exists', async () => {
    const plan = await planMissingParents('/m', 'a/b/f.txt', probeOf(['/m/a', '/m/a/b']));
    expect(plan.missing).toEqual([]);
    expect(plan.existingAncestor).toBe('/m/a/b');
  });

  it('plans nothing for a path with no parent segment', async () => {
    const plan = await planMissingParents('/m/', 'f.txt', probeOf([]));
    expect(plan).toEqual({ existingAncestor: '/m', missing: [] });
  });

  it('treats a probe error as existing', async () => {
    const plan = await planMissingParents('/m', 'a/b/f.txt', async () => {
      throw new Error('sftp down');
    });
    expect(plan.missing).toEqual([]);
  });

  it('leaves the last component of a directory destination to the transfer', async () => {
    const plan = await planMissingParents('/m', 'a/b/c/', probeOf([]));
    expect(plan.missing).toEqual(['a', 'b']);
  });
});

describe('writeSkeleton and skeletonDestination', () => {
  it('nests every segment after the first under a 0775 root', () => {
    const sk = writeSkeleton(['a', 'b', 'c']);
    try {
      expect(sk.source.endsWith('/')).toBe(true);
      expect(statSync(`${sk.source}b/c`).isDirectory()).toBe(true);
      expect(statSync(`${sk.source}b`).mode & 0o777).toBe(0o775);
      expect(statSync(sk.source).mode & 0o777).toBe(0o775);
    } finally {
      sk.cleanup();
    }
    expect(existsSync(sk.source)).toBe(false);
  });

  it('builds an empty tree for a single missing segment', () => {
    const sk = writeSkeleton(['a']);
    try {
      expect(existsSync(`${sk.source}a`)).toBe(false);
    } finally {
      sk.cleanup();
    }
  });

  it('points the destination at the first missing segment with a trailing slash', () => {
    expect(skeletonDestination('u@h', '/m/x', ['a', 'b'])).toBe('u@h:/m/x/a/');
  });
});
