import { describe, expect, it } from 'vitest';
import { assertNoSlugCollision, repoDisplayKey } from '../repo-slug-collision.js';

describe('repoDisplayKey', () => {
  it('shows a latest grand bare and a fork as name:tag', () => {
    expect(repoDisplayKey('shop:latest')).toBe('shop');
    expect(repoDisplayKey('shop:test')).toBe('shop:test');
  });
});

describe('assertNoSlugCollision', () => {
  it('refuses fork shop:test beside grand shop-test', () => {
    expect(() => assertNoSlugCollision('shop:test', ['shop-test'])).toThrow(/shop-test/);
  });

  it('refuses grand shop-test beside fork shop:test', () => {
    expect(() => assertNoSlugCollision('shop-test', ['shop:test'])).toThrow(/shop:test/);
  });

  it('refuses shop-test:x against shop:test-x', () => {
    expect(() => assertNoSlugCollision('shop-test:x', ['shop:test-x'])).toThrow(/shop:test-x/);
  });

  it('passes an unrelated pair and a repeat of the same key', () => {
    expect(() =>
      assertNoSlugCollision('shop:test', ['shop', 'shop:prod', 'blog-test'])
    ).not.toThrow();
    expect(() => assertNoSlugCollision('shop:test', ['shop:test'])).not.toThrow();
  });
});
