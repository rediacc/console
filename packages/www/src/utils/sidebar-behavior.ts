/**
 * Shared Sidebar Behavior Utilities
 *
 * This module provides shared utilities for sidebar functionality across the documentation:
 * - Table of Contents generation (consolidates 3 duplicate implementations)
 * - Collapsible menu behavior
 * - Active state tracking
 */

import { stringToSlug } from './slug';

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

  const headingRegex = /<h([2-6])[^>]*>(.*?)<\/h\1>/gi;
  const headings: TOCHeading[] = [];

  let match = headingRegex.exec(htmlContent);
  while (match !== null) {
    const level = Number.parseInt(match[1]);

    // Skip headings outside the requested range
    if (level < minLevel || level > maxLevel) {
      match = headingRegex.exec(htmlContent);
      continue;
    }

    let title = match[2];

    // Strip inner HTML tags if requested
    if (stripTags) {
      title = title.replaceAll(/<[^>]+>/g, '');
    }

    // Decode HTML entities so rendered text doesn't double-encode (e.g. "Fork & Backup" not "Fork &#x26; Backup")
    title = decodeHtmlEntities(title);

    // Generate ID from title
    const id = stringToSlug(title);

    headings.push({ level, title, id });
    match = headingRegex.exec(htmlContent);
  }

  return headings;
}

/**
 * Generate Table of Contents from Markdown content
 *
 * Parses markdown-formatted content to extract headings for the table of contents.
 * This is used when content is in markdown format before rendering.
 *
 * @param markdownContent - The raw markdown content
 * @param options - TOC generation options
 * @returns Array of heading objects with level, title, and id
 *
 * @example
 * const toc = generateTOCFromMarkdown(markdownContent);
 * // => [{ level: 2, title: 'Introduction', id: 'introduction' }, ...]
 */
export function generateTOCFromMarkdown(
  markdownContent: string,
  options: TOCOptions = {}
): TOCHeading[] {
  const { minLevel = 2, maxLevel = 6 } = options;

  const headingRegex = /^(#{1,6})\s+(.+)$/gm;
  const headings: TOCHeading[] = [];

  let match = headingRegex.exec(markdownContent);
  while (match !== null) {
    const level = match[1].length;

    // Skip headings outside the requested range
    if (level < minLevel || level > maxLevel) {
      match = headingRegex.exec(markdownContent);
      continue;
    }

    const title = match[2];

    // Generate ID from title
    const id = stringToSlug(title);

    headings.push({ level, title, id });
    match = headingRegex.exec(markdownContent);
  }

  return headings;
}
