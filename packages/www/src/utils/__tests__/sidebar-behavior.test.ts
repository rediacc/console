import { describe, expect, it } from 'vitest';
import { generateTOCFromHtml } from '../sidebar-behavior';

// The TOC must consume the id the page renders, never re-derive one. The site
// shipped two slug algorithms over one heading for years: rendered ids came
// from github-slugger while the TOC re-slugged the text ASCII-only, which left
// 8,013 in-page links dead across 963 pages. These tests pin the contract that
// killed that class: the id attribute is the single source.
describe('generateTOCFromHtml', () => {
  it('reads the id attribute instead of re-deriving it from the text', () => {
    const toc = generateTOCFromHtml('<h2 id="members--roles">Members &amp; Roles</h2>');
    expect(toc).toEqual([{ level: 2, title: 'Members & Roles', id: 'members--roles' }]);
  });

  it('preserves non-ASCII ids verbatim', () => {
    const toc = generateTOCFromHtml('<h2 id="مقدمة">مقدمة</h2>');
    expect(toc[0].id).toBe('مقدمة');
  });

  it('keeps deduplicated ids distinct for repeated headings', () => {
    const toc = generateTOCFromHtml('<h3 id="set">set</h3><h3 id="set-1">set</h3>');
    expect(toc.map((h) => h.id)).toEqual(['set', 'set-1']);
  });

  it('is independent of attribute order and quoting', () => {
    const html = '<h2 class="x" id="alpha">A</h2>' + '<h2 id=\'beta\' data-y="z">B</h2>';
    expect(generateTOCFromHtml(html).map((h) => h.id)).toEqual(['alpha', 'beta']);
  });

  it('skips a heading with no id rather than emitting a dead href', () => {
    const toc = generateTOCFromHtml('<h2>no anchor</h2><h2 id="ok">ok</h2>');
    expect(toc.map((h) => h.id)).toEqual(['ok']);
  });

  it('respects the level range and strips inner tags from titles', () => {
    const html = '<h2 id="a"><code>rdc</code> up</h2><h6 id="deep">deep</h6>';
    const toc = generateTOCFromHtml(html, { maxLevel: 3 });
    expect(toc).toEqual([{ level: 2, title: 'rdc up', id: 'a' }]);
  });
});
