import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { catalogDigest } from '../translation-keys.mjs';

describe('catalogDigest', () => {
  let root: string;
  beforeEach(() => {
    root = mkdtempSync(path.join(tmpdir(), 'catalog-digest-'));
    mkdirSync(path.join(root, 'en'));
    mkdirSync(path.join(root, 'de'));
    writeFileSync(path.join(root, 'en', 'cli.json'), '{"a":"1"}');
    writeFileSync(path.join(root, 'de', 'cli.json'), '{"a":"2"}');
  });
  afterEach(() => rmSync(root, { recursive: true, force: true }));

  it('is stable for unchanged catalogs and changes with any catalog byte', () => {
    const before = catalogDigest(root);
    expect(catalogDigest(root)).toBe(before);
    writeFileSync(path.join(root, 'de', 'cli.json'), '{"a":"3"}');
    expect(catalogDigest(root)).not.toBe(before);
  });

  it('binds each catalog to its language directory', () => {
    const single = (lang: string) => {
      const dir = mkdtempSync(path.join(tmpdir(), 'catalog-digest-'));
      mkdirSync(path.join(dir, lang));
      writeFileSync(path.join(dir, lang, 'cli.json'), '{"b":"1"}');
      return dir;
    };
    const inEn = single('en');
    const inDe = single('de');
    try {
      expect(catalogDigest(inEn)).not.toBe(catalogDigest(inDe));
    } finally {
      rmSync(inEn, { recursive: true, force: true });
      rmSync(inDe, { recursive: true, force: true });
    }
  });

  it('reads only .json files', () => {
    const before = catalogDigest(root);
    writeFileSync(path.join(root, 'en', 'notes.txt'), 'ignored');
    expect(catalogDigest(root)).toBe(before);
    writeFileSync(path.join(root, 'en', 'extra.json'), '{}');
    expect(catalogDigest(root)).not.toBe(before);
  });

  it('digests the same catalogs identically however they were created', () => {
    const other = mkdtempSync(path.join(tmpdir(), 'catalog-digest-'));
    try {
      // Created in the opposite order, so only the sort makes the digests agree.
      mkdirSync(path.join(other, 'de'));
      mkdirSync(path.join(other, 'en'));
      writeFileSync(path.join(other, 'de', 'cli.json'), '{"a":"2"}');
      writeFileSync(path.join(other, 'en', 'cli.json'), '{"a":"1"}');
      expect(catalogDigest(other)).toBe(catalogDigest(root));
    } finally {
      rmSync(other, { recursive: true, force: true });
    }
  });

  it('digests a missing locales directory as empty instead of throwing', () => {
    const missing = path.join(root, 'absent');
    expect(() => catalogDigest(missing)).not.toThrow();
    expect(catalogDigest(missing)).not.toBe(catalogDigest(root));
  });

  it('skips a dangling symlink entry instead of throwing', () => {
    const before = catalogDigest(root);
    symlinkSync(path.join(root, 'nowhere'), path.join(root, 'broken'));
    expect(catalogDigest(root)).toBe(before);
  });
});
