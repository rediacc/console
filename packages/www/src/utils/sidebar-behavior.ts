/**
 * Shared Sidebar Behavior Utilities
 *
 * This module provides shared utilities for sidebar functionality across the documentation:
 * - Table of Contents generation (consolidates 3 duplicate implementations)
 * - Collapsible menu behavior
 * - Active state tracking
 */

const NAMED_ENTITIES: Record<string, string> = {
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
};

function decodeHtmlEntities(str: string): string {
  return str
    .replaceAll(/&#x([0-9a-fA-F]+);/g, (_, hex) => String.fromCodePoint(Number.parseInt(hex, 16)))
    .replaceAll(/&#(\d+);/g, (_, dec) => String.fromCodePoint(Number.parseInt(dec, 10)))
    .replaceAll(/&(?:lt|gt|quot|#39|amp);/g, (m) => NAMED_ENTITIES[m]);
}

/**
 * Represents a heading for table of contents
 */
export interface TOCHeading {
  level: number;
  title: string;
  id: string;
}

/**
 * Options for TOC generation
 */
export interface TOCOptions {
  minLevel?: number; // Minimum heading level to include (default: 2)
  maxLevel?: number; // Maximum heading level to include (default: 6)
  stripTags?: boolean; // Strip HTML tags from titles (default: true)
}

/**
 * Generate Table of Contents from HTML content
 *
 * Parses rendered HTML content to extract headings for the table of contents.
 * This is used when content is already rendered to HTML (Astro slots).
 *
 * @param htmlContent - The rendered HTML content
 * @param options - TOC generation options
 * @returns Array of heading objects with level, title, and id
 *
 * @example
 * const toc = generateTOCFromHtml(renderedContent);
 * // => [{ level: 2, title: 'Introduction', id: 'introduction' }, ...]
 */
export function generateTOCFromHtml(htmlContent: string, options: TOCOptions = {}): TOCHeading[] {
  const { minLevel = 2, maxLevel = 6, stripTags = true } = options;

  const headingRegex = /<h([2-6])([^>]*)>(.*?)<\/h\1>/gis;
  const headings: TOCHeading[] = [];

  let match = headingRegex.exec(htmlContent);
  while (match !== null) {
    const level = Number.parseInt(match[1]);

    // Skip headings outside the requested range
    if (level < minLevel || level > maxLevel) {
      match = headingRegex.exec(htmlContent);
      continue;
    }

    // The heading tag already carries the id the page will render, written by the
    // rehype pipeline. Read it instead of re-deriving one: re-derivation is how the
    // TOC and the document ended up running two different slug algorithms, which
    // left half the site's in-page links dead. Attribute order is not guaranteed,
    // so parse the attribute soup rather than assuming a position.
    const idMatch = /\bid\s*=\s*(?:"([^"]*)"|'([^']*)')/.exec(match[2]);
    const id = idMatch ? idMatch[1] || idMatch[2] || '' : '';

    // A heading without an id cannot be linked to; emitting href="#" would be a
    // dead link by construction, so skip it.
    if (!id) {
      match = headingRegex.exec(htmlContent);
      continue;
    }

    let title = match[3];

    // Strip inner HTML tags if requested
    if (stripTags) {
      title = title.replaceAll(/<[^>]+>/g, '');
    }

    // Decode HTML entities so rendered text doesn't double-encode (e.g. "Fork & Backup" not "Fork &#x26; Backup")
    title = decodeHtmlEntities(title);

    headings.push({ level, title, id });
    match = headingRegex.exec(htmlContent);
  }

  return headings;
}
