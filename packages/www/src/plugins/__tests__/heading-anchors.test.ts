import { describe, expect, it } from 'vitest';
import Slugger from 'github-slugger';
import { contentFileInfo, englishAnchorsFor, scanHeadings } from '../heading-anchors.mjs';

describe('scanHeadings', () => {
  it('finds ATX headings with depth and line', () => {
    expect(scanHeadings('# One\n\ntext\n\n## Two\n### Three')).toEqual([
      { depth: 1, line: 0, text: 'One' },
      { depth: 2, line: 4, text: 'Two' },
      { depth: 3, line: 5, text: 'Three' },
    ]);
  });

  it('ignores headings inside code fences, including longer closing fences', () => {
    const md = '```\n# not a heading\n```\n## real\n````md\n### also not\n````\n';
    expect(scanHeadings(md)).toEqual([{ depth: 2, line: 3, text: 'real' }]);
  });

  it('a shorter inner fence marker does not close an outer fence', () => {
    // A ```` fence showing a ``` example: the inner ``` must not end the block.
    const md = '````\n```\n# swallowed\n```\n````\n## after';
    expect(scanHeadings(md).map((h) => h.text)).toEqual(['after']);
  });

  it('strips a closing hash sequence', () => {
    expect(scanHeadings('## Closed ##')[0].text).toBe('Closed');
  });

  it('requires whitespace after the hashes', () => {
    expect(scanHeadings('#hashtag\n#\n# real')).toEqual([
      { depth: 1, line: 1, text: '' },
      { depth: 1, line: 2, text: 'real' },
    ]);
  });
});

describe('englishAnchorsFor', () => {
  it('produces github-slugger ids with dedupe, matching what Astro renders', () => {
    // The real English CLI reference: repeated command names (set, list, ...)
    // must come out numbered, exactly as rehypeHeadingIds numbers them.
    const anchors = englishAnchorsFor('docs', 'cli-application.md');
    const ids = anchors.map((a) => a.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.some((id) => id.endsWith('-1'))).toBe(true);
  });

  it('resolves {{t:...}} heading placeholders to their English values', () => {
    const anchors = englishAnchorsFor('docs', 'cli-application.md');
    // First heading is {{t:cli.docs.pageTitle}} = "Rediacc CLI Reference".
    expect(anchors[0].id).toBe('rediacc-cli-reference');
  });

  it('slugs an ampersand heading the way github-slugger does', () => {
    const anchors = englishAnchorsFor('docs', 'account-management.md');
    expect(anchors.map((a) => a.id)).toContain('members--roles');
  });

  it('throws for a document with no English source', () => {
    expect(() => englishAnchorsFor('docs', 'no-such-file.md')).toThrow(/No English source/);
  });

  it('matches a plain github-slugger run for simple text', () => {
    const slugger = new Slugger();
    expect(slugger.slug('Reclaim Space (trim)')).toBe('reclaim-space-trim');
  });
});

describe('contentFileInfo', () => {
  it('classifies docs and blog content paths', () => {
    expect(contentFileInfo('/x/src/content/docs/ar/quick-start.md')).toEqual({
      collection: 'docs',
      locale: 'ar',
      filename: 'quick-start.md',
    });
    expect(contentFileInfo('/x/src/content/blog/it/some-post.mdx')).toEqual({
      collection: 'blog',
      locale: 'it',
      filename: 'some-post.mdx',
    });
  });

  it('returns null for anything outside the collections', () => {
    expect(contentFileInfo('/x/src/pages/index.astro')).toBeNull();
    expect(contentFileInfo(undefined)).toBeNull();
    expect(contentFileInfo('/x/src/content/docs/en/nested/dir.md')).toBeNull();
  });
});
