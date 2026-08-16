/**
 * Card-grid splitter for cheat-sheet style documents.
 *
 * Takes a rendered HTML string (an Astro slot render of a markdown document)
 * and cuts it into "cards" at every TOP-LEVEL `<h2>` boundary.  Everything
 * before the first such heading becomes the leading card (the document title
 * plus its intro paragraph), which the stylesheet renders as the branding
 * header.
 *
 * The scanner is tag-aware rather than a naive `split()`, so an `<h2>` that
 * appears inside a code fence, inside a comment, or nested in another element
 * never starts a new card.
 */

/** Elements that never have a closing tag, so they must not change nesting depth. */
const VOID_ELEMENTS = new Set([
  'area',
  'base',
  'br',
  'col',
  'embed',
  'hr',
  'img',
  'input',
  'link',
  'meta',
  'param',
  'source',
  'track',
  'wbr',
]);

/** Elements whose content is text, not markup — anything tag-shaped inside is data. */
const RAW_TEXT_ELEMENTS = new Set(['pre', 'script', 'style', 'textarea']);

/** Matches an HTML comment, or a start/end tag with quote-aware attributes. */
const TOKEN_PATTERN = /<!--[\s\S]*?-->|<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>])*)>/g;

/**
 * Split rendered HTML into cards at top-level `<h2>` boundaries.
 *
 * @param html - Rendered HTML, typically `await Astro.slots.render('default')`
 * @returns One trimmed HTML fragment per card; empty fragments are dropped
 */
export function splitIntoCards(html: string): string[] {
  if (html.trim() === '') {
    return [];
  }

  const boundaries: number[] = [];
  const pattern = new RegExp(TOKEN_PATTERN.source, 'g');
  let depth = 0;
  let match = pattern.exec(html);

  while (match !== null) {
    const [token, closingSlash, rawName, attributes] = match;

    // Comments carry no structure.
    if (token.startsWith('<!--')) {
      match = pattern.exec(html);
      continue;
    }

    const name = rawName.toLowerCase();

    if (closingSlash === '/') {
      if (!VOID_ELEMENTS.has(name)) {
        depth = Math.max(0, depth - 1);
      }
      match = pattern.exec(html);
      continue;
    }

    if (name === 'h2' && depth === 0) {
      boundaries.push(match.index);
    }

    const selfClosing = attributes.trimEnd().endsWith('/');
    if (VOID_ELEMENTS.has(name) || selfClosing) {
      match = pattern.exec(html);
      continue;
    }

    depth += 1;

    if (RAW_TEXT_ELEMENTS.has(name)) {
      // Jump straight to the closing tag so fenced code cannot be read as markup.
      const closeIndex = html.toLowerCase().indexOf(`</${name}`, pattern.lastIndex);
      pattern.lastIndex = closeIndex === -1 ? html.length : closeIndex;
    }

    match = pattern.exec(html);
  }

  if (boundaries.length === 0) {
    return [html.trim()];
  }

  const cuts = boundaries[0] === 0 ? boundaries : [0, ...boundaries];
  const cards: string[] = [];

  for (let i = 0; i < cuts.length; i++) {
    const chunk = html.slice(cuts[i], cuts[i + 1] ?? html.length).trim();
    if (chunk !== '') {
      cards.push(chunk);
    }
  }

  return cards;
}
