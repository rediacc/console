/**
 * Ref parser tests (spec/03 §2.1). Exhaustive over the label charset, the tag
 * grammar, the place grammar, the reserved `base` tag, and the exit-2 error
 * texts (offending character named).
 */

import { describe, expect, it } from 'vitest';
import { CliExitError } from '../../../utils/cli-exit-error.js';
import {
  isValidLabel,
  LABEL_MAX_LENGTH,
  parseRef,
  RESERVED_TAG,
  validateLabel,
  validateTag,
} from '../ref-parser.js';

/** Assert `fn` throws a VALIDATION exit-2 CliExitError whose message includes `needle`. */
function expectExit2(fn: () => unknown, needle?: string): void {
  let thrown: unknown;
  try {
    fn();
  } catch (error) {
    thrown = error;
  }
  expect(thrown, 'expected a throw').toBeInstanceOf(CliExitError);
  const err = thrown as CliExitError;
  expect(err.exitCode).toBe(2);
  expect(err.code).toBe('VALIDATION_ERROR');
  if (needle !== undefined) expect(err.message).toContain(needle);
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

describe('parseRef — label charset violations (exit 2, offending char named)', () => {
  it('rejects uppercase and names the character', () => {
    expectExit2(() => parseRef('Shop'), "'S'");
  });

  it('rejects underscore and names the character', () => {
    expectExit2(() => parseRef('my_repo'), "'_'");
  });

  it('rejects a dot and names the character', () => {
    expectExit2(() => parseRef('a.b'), "'.'");
  });

  it('rejects a leading hyphen', () => {
    expectExit2(() => parseRef('-shop'), 'hyphen');
  });

  it('rejects a trailing hyphen', () => {
    expectExit2(() => parseRef('shop-'), 'hyphen');
  });

  it('rejects an over-length (64) label', () => {
    const tooLong = 'a'.repeat(LABEL_MAX_LENGTH + 1);
    expectExit2(() => parseRef(tooLong), '64 characters');
  });

  it('rejects an empty input', () => {
    expectExit2(() => parseRef(''), 'reference is required');
  });
});

describe('parseRef — separator grammar', () => {
  it('rejects two colons', () => {
    expectExit2(() => parseRef('shop::test'), "more than one ':'");
  });

  it('rejects two at-signs', () => {
    expectExit2(() => parseRef('shop@a@b'), "more than one '@'");
  });

  it('rejects an empty tag', () => {
    expectExit2(() => parseRef('shop:'), 'tag is empty');
  });

  it('rejects an empty place', () => {
    expectExit2(() => parseRef('shop@'), 'place is empty');
  });

  it('rejects a colon inside the place segment (tag after place is illegal)', () => {
    // `shop@a:b` splits @ first: place = "a:b", whose ':' is an illegal label char.
    expectExit2(() => parseRef('shop@a:b'), "':'");
  });
});

describe('parseRef — reserved tag `base`', () => {
  it('refuses an explicit :base with the teaching error', () => {
    expectExit2(() => parseRef('shop:base'), 'base names the original repository');
  });

  it('exposes the reserved tag name', () => {
    expect(RESERVED_TAG).toBe('base');
  });
});

describe('validateTag', () => {
  it('refuses base', () => {
    expectExit2(() => validateTag('base'), 'base names the original repository');
  });

  it('accepts an ordinary tag', () => {
    expect(() => validateTag('staging')).not.toThrow();
  });

  it('rejects an invalid tag label', () => {
    expectExit2(() => validateTag('Bad_Tag'));
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
    expectExit2(() => validateLabel('BAD', 'name'), 'name');
    expectExit2(() => validateLabel('BAD', 'place'), 'place');
  });
});
