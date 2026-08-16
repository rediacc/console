import { describe, expect, it } from 'vitest';
import { parseBrowseResult } from '../backup-storage.js';

const listing = {
  source: 'repository demo',
  entries: [
    { path: '/app', type: 'dir', size: 0, modTime: '2026-08-16T06:36:28Z' },
    { path: '/readme.txt', type: 'file', size: 6, modTime: '2026-08-16T06:36:28Z' },
  ],
  truncated: false,
  totalSize: 6,
};

describe('parseBrowseResult', () => {
  it('reads a bare JSON line', () => {
    const got = parseBrowseResult(JSON.stringify(listing));
    expect(got?.source).toBe('repository demo');
    expect(got?.entries).toHaveLength(2);
  });

  // THE CASE THIS WAVE ALREADY PAID FOR. `renet functions once` swallows a
  // verb's stdout and re-emits it on STDERR inside its own log line, with the
  // quotes escaped. A parser that accepts only the bare form reports "no
  // listing" for a listing that was produced perfectly, and the failure reads
  // as a broken product rather than a broken parser.
  it('reads a listing wrapped in a log line with escaped quotes', () => {
    const wrapped = `time="2026-08-16T06:36:28Z" level=info msg="[backup_browse] ${JSON.stringify(
      listing
    ).replaceAll('"', '\\"')}"`;
    const got = parseBrowseResult(wrapped);
    expect(got, 'the wrapped form was not recognised').toBeDefined();
    expect(got?.entries.map((e) => e.path)).toEqual(['/app', '/readme.txt']);
  });

  // THE REVIEW'S NIT, kept as a test rather than a comment. The wrapped form was
  // unescaped with replaceAll('\\"', '"'), which handled escaped QUOTES and
  // nothing else -- so a filename containing a newline or a backslash, both
  // legal on Linux, decoded into invalid JSON. It failed safe, but "safe" there
  // meant refusing a repository that was perfectly fine, and an operator could
  // not tell that from a real fault.
  it('decodes a wrapped payload whose filenames contain backslashes and newlines', () => {
    const awkward = {
      source: 'repository demo',
      entries: [
        { path: '/weird\\name', type: 'file', size: 1, modTime: '2026-08-16T06:36:28Z' },
        { path: '/two\nlines.txt', type: 'file', size: 2, modTime: '2026-08-16T06:36:28Z' },
      ],
      truncated: false,
      totalSize: 3,
    };
    const wrapped = `time="..." level=info msg="[backup_browse] ${JSON.stringify(
      JSON.stringify(awkward)
    ).slice(1, -1)}"`;
    const got = parseBrowseResult(wrapped);
    expect(got, 'a legal filename made the listing undecodable').toBeDefined();
    expect(got?.entries.map((e) => e.path)).toEqual(['/weird\\name', '/two\nlines.txt']);
  });

  it('finds the listing among surrounding log noise', () => {
    const noisy = [
      'time="..." level=info msg="Starting..."',
      'some non-JSON chatter {not json at all',
      JSON.stringify(listing),
      'time="..." level=info msg="Complete"',
    ].join('\n');
    expect(parseBrowseResult(noisy)?.entries).toHaveLength(2);
  });

  it('keeps the LAST listing when several appear', () => {
    const second = { ...listing, source: 'repository other', entries: [], totalSize: 0 };
    const both = `${JSON.stringify(listing)}\n${JSON.stringify(second)}`;
    expect(parseBrowseResult(both)?.source).toBe('repository other');
  });

  it('carries the truncation flag through, which is the one field that must not be lost', () => {
    const truncated = { ...listing, truncated: true };
    expect(parseBrowseResult(JSON.stringify(truncated))?.truncated).toBe(true);
  });

  it('returns undefined rather than throwing on unusable input', () => {
    expect(parseBrowseResult(undefined)).toBeUndefined();
    expect(parseBrowseResult('')).toBeUndefined();
    expect(parseBrowseResult('no json here')).toBeUndefined();
    expect(parseBrowseResult('{"broken":')).toBeUndefined();
  });

  // A verify verdict and a browse listing travel the same pipe. Accepting a
  // verdict as a listing would print an empty table and call it a repository
  // with no files, which is the same wrong answer as a truncation that does
  // not admit itself.
  it('does not mistake another verb’s JSON for a listing', () => {
    expect(parseBrowseResult('{"status":"verified","level":"full"}')).toBeUndefined();
    expect(parseBrowseResult('{"entries":[]}')).toBeUndefined();
    expect(parseBrowseResult('{"source":"x"}')).toBeUndefined();
  });
});
