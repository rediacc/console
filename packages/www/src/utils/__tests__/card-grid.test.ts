import { describe, expect, it } from 'vitest';

import { splitIntoCards } from '../card-grid';

describe('splitIntoCards', () => {
  it('returns nothing for empty input', () => {
    expect(splitIntoCards('')).toEqual([]);
    expect(splitIntoCards('   \n  ')).toEqual([]);
  });

  it('returns a single card when the document has no h2', () => {
    const html = '<h1>Title</h1>\n<p>Intro paragraph.</p>';
    expect(splitIntoCards(html)).toEqual([html.trim()]);
  });

  it('splits the preamble away from a single h2 section', () => {
    const html = '<h1>Title</h1><p>Intro.</p><h2 id="a">A</h2><p>Body of A.</p>';

    expect(splitIntoCards(html)).toEqual([
      '<h1>Title</h1><p>Intro.</p>',
      '<h2 id="a">A</h2><p>Body of A.</p>',
    ]);
  });

  it('starts at the first h2 when there is no preamble', () => {
    const html = '<h2>A</h2><p>a</p>';
    expect(splitIntoCards(html)).toEqual(['<h2>A</h2><p>a</p>']);
  });

  it('splits every top-level h2 into its own card', () => {
    const html = [
      '<h1>Title</h1>',
      '<h2 id="one">One</h2><p>1</p>',
      '<h2 id="two">Two</h2><table><tr><td>2</td></tr></table>',
      '<h2 id="three">Three</h2><p>3</p>',
    ].join('\n');

    const cards = splitIntoCards(html);

    expect(cards).toHaveLength(4);
    expect(cards[0]).toBe('<h1>Title</h1>');
    expect(cards[1]).toBe('<h2 id="one">One</h2><p>1</p>');
    expect(cards[2]).toBe('<h2 id="two">Two</h2><table><tr><td>2</td></tr></table>');
    expect(cards[3]).toBe('<h2 id="three">Three</h2><p>3</p>');
  });

  it('does NOT split on an h2 inside a pre fence', () => {
    const html =
      '<h2 id="real">Real</h2><pre><code><h2>not a heading</h2>\nmore code</code></pre><p>after</p>';

    const cards = splitIntoCards(html);

    expect(cards).toHaveLength(1);
    expect(cards[0]).toBe(html);
  });

  it('does NOT split on an h2 nested inside another element', () => {
    const html = '<h2>Real</h2><div class="callout"><h2>nested</h2></div><p>after</p>';

    const cards = splitIntoCards(html);

    expect(cards).toHaveLength(1);
    expect(cards[0]).toBe(html);
  });

  it('is not confused by void elements or self-closing tags at top level', () => {
    const html = '<h2>A</h2><p>a</p><hr><img src="x.png" alt=""><br/><h2>B</h2><p>b</p>';

    expect(splitIntoCards(html)).toEqual([
      '<h2>A</h2><p>a</p><hr><img src="x.png" alt=""><br/>',
      '<h2>B</h2><p>b</p>',
    ]);
  });

  it('ignores an h2 that only appears as escaped text', () => {
    const html = '<h2>A</h2><p>write &lt;h2&gt; to open a heading</p>';
    expect(splitIntoCards(html)).toEqual([html]);
  });

  it('drops whitespace-only chunks between sections', () => {
    const html = '\n  <h2>A</h2>\n\n  <h2>B</h2>\n';
    expect(splitIntoCards(html)).toEqual(['<h2>A</h2>', '<h2>B</h2>']);
  });
});
