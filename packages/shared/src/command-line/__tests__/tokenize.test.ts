import { describe, expect, it } from 'vitest';
import { isFlagLike, tokenize, unclosedQuote } from '../tokenize.js';

const texts = (line: string): string[] => tokenize(line).map((t) => t.text);

describe('tokenize', () => {
  it('splits on spaces and tabs and records spans', () => {
    const tokens = tokenize('rdc  repo\tfork');
    expect(tokens.map((t) => [t.text, t.start, t.end])).toEqual([
      ['rdc', 0, 3],
      ['repo', 5, 9],
      ['fork', 10, 14],
    ]);
  });

  it('returns no tokens for an empty or blank line', () => {
    expect(tokenize('')).toEqual([]);
    expect(tokenize('   \t ')).toEqual([]);
  });

  it('strips quotes and keeps their spans and raw text', () => {
    const line = `rdc run "a b" 'c d'`;
    const tokens = tokenize(line);
    expect(tokens.map((t) => t.text)).toEqual(['rdc', 'run', 'a b', 'c d']);
    expect(tokens[2]).toMatchObject({ start: 8, end: 13, raw: '"a b"', quote: '"', closed: true });
    expect(tokens[3]).toMatchObject({ raw: "'c d'", quote: "'" });
    for (const t of tokens) expect(line.slice(t.start, t.end)).toBe(t.raw);
  });

  it('keeps an empty quoted token', () => {
    expect(texts(`--tag ""`)).toEqual(['--tag', '']);
  });

  it('joins adjacent quoted and unquoted pieces', () => {
    expect(texts(`a"b c"d`)).toEqual(['ab cd']);
  });

  it('handles escapes: double quotes honour \\" and \\\\, single quotes are literal, bare \\ escapes', () => {
    expect(texts(String.raw`"say \"hi\" \\ done"`)).toEqual([String.raw`say "hi" \ done`]);
    expect(texts(String.raw`'a\"b'`)).toEqual([String.raw`a\"b`]);
    expect(texts(String.raw`a\ b c`)).toEqual(['a b', 'c']);
    expect(texts(String.raw`"a\nb"`)).toEqual([String.raw`a\nb`]);
  });

  it('keeps a lone trailing backslash', () => {
    expect(texts('a\\')).toEqual(['a\\']);
  });

  it('reports an unclosed quote with its span and keeps the text typed so far', () => {
    const line = 'rdc repo fork "my re';
    const tokens = tokenize(line);
    const open = unclosedQuote(tokens);
    expect(open).toMatchObject({ text: 'my re', start: 14, end: line.length, closed: false });
    expect(tokens.slice(0, 3).every((t) => t.closed)).toBe(true);
  });

  it('control: a balanced line has no unclosed quote', () => {
    expect(unclosedQuote(tokenize(`rdc "a b" 'c'`))).toBeUndefined();
  });

  it('keeps Arabic text inside quotes whole, with UTF-16 spans', () => {
    const line = 'rdc note "مرحبا بالعالم" ok';
    const tokens = tokenize(line);
    expect(tokens.map((t) => t.text)).toEqual(['rdc', 'note', 'مرحبا بالعالم', 'ok']);
    expect(tokens[2].raw).toBe('"مرحبا بالعالم"');
    expect(line.slice(tokens[3].start, tokens[3].end)).toBe('ok');
  });

  it('spans stay UTF-16 offsets across astral characters', () => {
    const line = '😀 x';
    const tokens = tokenize(line);
    expect(tokens.map((t) => [t.text, t.start, t.end])).toEqual([
      ['😀', 0, 2],
      ['x', 3, 4],
    ]);
  });
});

describe('isFlagLike', () => {
  it('is true for a flag, false for a bare dash, a value and a quoted dash', () => {
    const [flag, dash, word, quoted] = tokenize(`--tag - word "--tag"`);
    expect(isFlagLike(flag)).toBe(true);
    expect(isFlagLike(dash)).toBe(false);
    expect(isFlagLike(word)).toBe(false);
    expect(isFlagLike(quoted)).toBe(false);
  });
});
