/**
 * Types for heading-anchors.mjs, which stays plain .mjs so the search-index
 * generator can import it under bare node (no TypeScript loader).
 */
export interface ScannedHeading {
  depth: number;
  line: number;
  text: string;
}

export interface EnglishAnchor {
  depth: number;
  id: string;
}

export interface ContentFileInfo {
  collection: 'docs' | 'blog';
  locale: string;
  filename: string;
}

export function scanHeadings(markdownBody: string): ScannedHeading[];
export function stripFrontmatter(raw: string): string;
export function englishAnchorsFor(collection: string, filename: string): EnglishAnchor[];
export function contentFileInfo(absPath: string | undefined): ContentFileInfo | null;
