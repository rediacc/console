/**
 * Shared ref-grammar tests (spec/03 §2.1). Ports the CLI parser cases (now
 * asserting RefGrammarError instead of the CLI's CliExitError), plus the lenient
 * splitRef cases and composeRef round-trips.
 */

import { describe, expect, it } from 'vitest';
import {
  composeRef,
  isValidLabel,
  LABEL_MAX_LENGTH,
  parseRef,
  RESERVED_TAG,
  RefGrammarError,
  splitRef,
  validateLabel,
  validateTag,
} from '../index.js';

/** Assert `fn` throws a RefGrammarError whose message includes `needle`. */
function expectGrammarError(fn: () => unknown, needle?: string): void {
  let thrown: unknown;
  try {
    fn();
  } catch (error) {
    thrown = error;
  }
  expect(thrown, 'expected a throw').toBeInstanceOf(RefGrammarError);
  if (needle !== undefined) expect((thrown as RefGrammarError).message).toContain(needle);
}

describe('parseRef — valid grammar', () => {
  it('parses a bare name as tag-undefined (the reserved base tag)', () => {
    expect(parseRef('shop')).toEqual({ name: 'shop' });
  });

  it('parses name:tag', () => {
    expect(parseRef('shop:test')).toEqual({ name: 'shop', tag: 'test' });
  });

  it('parses name@place', () => {
    expect(parseRef('shop@prod-1')).toEqual({ name: 'shop', place: 'prod-1' });
  });

  it('parses name:tag@place (@ binds looser than :)', () => {
    expect(parseRef('shop:test@prod-1')).toEqual({ name: 'shop', tag: 'test', place: 'prod-1' });
  });

  it('accepts hyphenated and digit-bearing labels', () => {
    expect(parseRef('my-repo-2:v1-2@node-3')).toEqual({
      name: 'my-repo-2',
      tag: 'v1-2',
      place: 'node-3',
    });
  });

  it('accepts a maximum-length (63) label', () => {
    const max = `a${'b'.repeat(LABEL_MAX_LENGTH - 1)}`;
    expect(max.length).toBe(LABEL_MAX_LENGTH);
    expect(parseRef(max)).toEqual({ name: max });
  });

  it('treats `latest` as an ordinary legal tag (magic default retired)', () => {
    expect(parseRef('shop:latest')).toEqual({ name: 'shop', tag: 'latest' });
  });
});

describe('parseRef — label charset violations (offending char named)', () => {
  it('rejects uppercase and names the character', () => {
    expectGrammarError(() => parseRef('Shop'), "'S'");
  });

  it('rejects underscore and names the character', () => {
    expectGrammarError(() => parseRef('my_repo'), "'_'");
  });

  it('rejects a dot and names the character', () => {
    expectGrammarError(() => parseRef('a.b'), "'.'");
  });

  it('rejects a leading hyphen', () => {
    expectGrammarError(() => parseRef('-shop'), 'hyphen');
  });

  it('rejects a trailing hyphen', () => {
    expectGrammarError(() => parseRef('shop-'), 'hyphen');
  });

  it('rejects an over-length (64) label', () => {
    const tooLong = 'a'.repeat(LABEL_MAX_LENGTH + 1);
    expectGrammarError(() => parseRef(tooLong), '64 characters');
  });

  it('rejects an empty input', () => {
    expectGrammarError(() => parseRef(''), 'reference is required');
  });
});

describe('parseRef — separator grammar', () => {
  it('rejects two colons', () => {
    expectGrammarError(() => parseRef('shop::test'), "more than one ':'");
  });

  it('rejects two at-signs', () => {
    expectGrammarError(() => parseRef('shop@a@b'), "more than one '@'");
  });

  it('rejects an empty tag', () => {
    expectGrammarError(() => parseRef('shop:'), 'tag is empty');
  });

  it('rejects an empty place', () => {
    expectGrammarError(() => parseRef('shop@'), 'place is empty');
  });

  it('rejects a colon inside the place segment (tag after place is illegal)', () => {
    expectGrammarError(() => parseRef('shop@a:b'), "':'");
  });
});

describe('parseRef — reserved tag `base`', () => {
  it('refuses an explicit :base with the teaching error', () => {
    expectGrammarError(() => parseRef('shop:base'), 'base names the original repository');
  });

  it('exposes the reserved tag name', () => {
    expect(RESERVED_TAG).toBe('base');
  });
});

describe('validateTag', () => {
  it('refuses base', () => {
    expectGrammarError(() => validateTag('base'), 'base names the original repository');
  });

  it('accepts an ordinary tag', () => {
    expect(() => validateTag('staging')).not.toThrow();
  });

  it('rejects an invalid tag label', () => {
    expectGrammarError(() => validateTag('Bad_Tag'));
  });
});

describe('isValidLabel / validateLabel', () => {
  it('isValidLabel is true for a DNS label and false otherwise', () => {
    expect(isValidLabel('shop-1')).toBe(true);
    expect(isValidLabel('Shop')).toBe(false);
    expect(isValidLabel('a_b')).toBe(false);
    expect(isValidLabel('-a')).toBe(false);
    expect(isValidLabel('')).toBe(false);
  });

  it('validateLabel names the role in the message', () => {
    expectGrammarError(() => validateLabel('BAD', 'name'), 'name');
    expectGrammarError(() => validateLabel('BAD', 'place'), 'place');
  });
});

describe('splitRef — lenient name:tag', () => {
  it('splits a bare name with no default tag', () => {
    expect(splitRef('marketing')).toEqual({ name: 'marketing' });
  });

  it('applies the default tag to a bare name', () => {
    expect(splitRef('marketing', 'latest')).toEqual({ name: 'marketing', tag: 'latest' });
  });

  it('keeps an explicit tag over the default', () => {
    expect(splitRef('marketing:staging', 'latest')).toEqual({
      name: 'marketing',
      tag: 'staging',
    });
  });

  it('collapses an empty tag to the default', () => {
    expect(splitRef('marketing:', 'latest')).toEqual({ name: 'marketing', tag: 'latest' });
    expect(splitRef('marketing:')).toEqual({ name: 'marketing' });
  });

  it('does NOT validate the label charset (lenient by design)', () => {
    expect(splitRef('My_Repo:V1')).toEqual({ name: 'My_Repo', tag: 'V1' });
  });

  it('rejects more than one colon', () => {
    expectGrammarError(() => splitRef('a:b:c'));
  });

  it('rejects an empty name', () => {
    expectGrammarError(() => splitRef(''));
    expectGrammarError(() => splitRef(':x'));
  });
});

describe('composeRef — inverse of parseRef', () => {
  it('emits a bare name for a tag-undefined ref', () => {
    expect(composeRef('shop')).toBe('shop');
  });

  it('emits name:tag', () => {
    expect(composeRef('shop', 'test')).toBe('shop:test');
  });

  it('emits name@place', () => {
    expect(composeRef('shop', undefined, 'prod-1')).toBe('shop@prod-1');
  });

  it('emits name:tag@place', () => {
    expect(composeRef('shop', 'test', 'prod-1')).toBe('shop:test@prod-1');
  });

  it('omits the reserved base tag (it is implicit)', () => {
    expect(composeRef('shop', RESERVED_TAG)).toBe('shop');
  });

  it('round-trips composeRef ∘ parseRef for every ref shape', () => {
    for (const ref of ['shop', 'shop:test', 'shop@prod-1', 'shop:test@prod-1']) {
      const p = parseRef(ref);
      expect(composeRef(p.name, p.tag, p.place)).toBe(ref);
    }
  });
});
