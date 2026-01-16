/**
 * Shared Sidebar Behavior Utilities
 *
 * This module provides shared utilities for sidebar functionality across the documentation:
 * - Table of Contents generation (consolidates 3 duplicate implementations)
 * - Collapsible menu behavior
 * - Active state tracking
 */

interface WindowWithSidebarInit extends Window {
  rediaccDocsSidebarInitialized?: boolean;
}

interface CategoryDataset extends DOMStringMap {
  initialized?: string;
  category?: string;
  itemCount?: string;
  isActive?: string;
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
  let match;

  while ((match = headingRegex.exec(htmlContent)) !== null) {
    const level = parseInt(match[1]);

    // Skip headings outside the requested range
    if (level < minLevel || level > maxLevel) {
      continue;
    }

    let title = match[2];

    // Strip inner HTML tags if requested
    if (stripTags) {
      title = title.replace(/<[^>]+>/g, '');
    }

    // Generate ID from title
    const id = generateHeadingId(title);

    headings.push({ level, title, id });
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
  let match;

  while ((match = headingRegex.exec(markdownContent)) !== null) {
    const level = match[1].length;

    // Skip headings outside the requested range
    if (level < minLevel || level > maxLevel) {
      continue;
    }

    const title = match[2];

    // Generate ID from title
    const id = generateHeadingId(title);

    headings.push({ level, title, id });
  }

  return headings;
}

/**
 * Generate a URL-friendly ID from a heading title
 *
 * Converts heading text to a valid HTML id attribute:
 * - Converts to lowercase
 * - Removes special characters
 * - Replaces spaces with hyphens
 *
 * @param title - The heading title
 * @returns A URL-friendly ID
 *
 * @example
 * generateHeadingId('My Heading Title') // => 'my-heading-title'
 * generateHeadingId('API Reference') // => 'api-reference'
 */
export function generateHeadingId(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^\w\s-]/g, '') // Remove special characters
    .replace(/\s+/g, '-'); // Replace spaces with hyphens
}

/**
 * Initialize collapsible category menus in the sidebar
 *
 * Manages expand/collapse behavior for categorized navigation:
 * - Handles click events on category headers
 * - Manages aria-expanded attributes for accessibility
 * - Persists state to sessionStorage
 * - Supports keyboard navigation (Enter/Space)
 *
 * @example
 * // In an inline script in your Astro component:
 * initCollapsibleCategories();
 */
export function initCollapsibleCategories(): void {
  // Prevent multiple initialization
  const win = window as WindowWithSidebarInit;
  if (win.rediaccDocsSidebarInitialized) return;
  win.rediaccDocsSidebarInitialized = true;

  /**
   * Set collapsed/expanded state of a category
   */
  function setCollapsedState(categoryItem: Element, isCollapsed: boolean): void {
    const button = categoryItem.querySelector('.category-header');
    if (!button) return;

    if (isCollapsed) {
      button.setAttribute('aria-expanded', 'false');
      categoryItem.setAttribute('aria-expanded', 'false');
    } else {
      button.setAttribute('aria-expanded', 'true');
      categoryItem.setAttribute('aria-expanded', 'true');
    }
  }

  /**
   * Initialize all collapsible category menus
   */
  const categoryItems = document.querySelectorAll('[data-category][data-item-count]');

  categoryItems.forEach((item) => {
    // Skip if already initialized
    const dataset = (item as HTMLElement).dataset as CategoryDataset;
    if (dataset.initialized === 'true') return;
    dataset.initialized = 'true';

    const button = item.querySelector<HTMLButtonElement>('.category-header');
    const category = dataset.category ?? '';

    if (!button) return;

    // Check sessionStorage for saved state
    const storageKey = `rediacc_docs_cat_${category}`;
    const savedState = sessionStorage.getItem(storageKey);

    if (savedState !== null) {
      // Apply saved state
      const isExpanded = savedState === 'true';
      setCollapsedState(item, !isExpanded);
    }
    // Otherwise, keep the HTML's initial state (no flash)

    // Click handler
    button.addEventListener('click', (e: Event) => {
      e.preventDefault();
      const currentExpanded = item.getAttribute('aria-expanded') === 'true';
      const newExpanded = !currentExpanded;

      setCollapsedState(item, !newExpanded);
      sessionStorage.setItem(storageKey, newExpanded ? 'true' : 'false');
    });

    // Keyboard navigation
    button.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        button.click();
      }
    });
  });
}

/**
 * Initialize Table of Contents active state tracking using Intersection Observer
 *
 * Automatically highlights the currently visible section in the TOC as user scrolls.
 * Uses Intersection Observer API for efficient scroll monitoring.
 *
 * @param options - Configuration options
 * @returns Cleanup function to unobserve all elements
 *
 * @example
 * // In an inline script in your Astro component:
 * initTOCActiveState({ selector: '.article-body h2, .article-body h3' });
 */
export interface TOCActiveStateOptions {
  selector?: string; // CSS selector for elements to observe (default: headings in article)
  containerSelector?: string; // CSS selector for TOC container
  rootMargin?: string; // Intersection observer root margin (default: '-100px 0px -66%')
}

export function initTOCActiveState(options: TOCActiveStateOptions = {}): () => void {
  const {
    selector = '.article-body h2, .article-body h3, .article-body h4',
    containerSelector = '.toc-sidebar',
    rootMargin = '-100px 0px -66%',
  } = options;

  const container = document.querySelector(containerSelector);
  if (!container) return () => {}; // No-op if TOC container not found

  const headings = document.querySelectorAll(selector);
  if (headings.length === 0) return () => {}; // No-op if no headings found

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const id = entry.target.id;
        if (!id) return;

        const tocLink = container.querySelector(`a[href="#${id}"]`);
        if (!tocLink) return;

        if (entry.isIntersecting) {
          // Remove active class from all links
          container.querySelectorAll('a').forEach((link) => {
            link.classList.remove('active');
          });

          // Add active class to current link
          tocLink.classList.add('active');
        }
      });
    },
    { rootMargin }
  );

  // Start observing all headings
  headings.forEach((heading) => {
    observer.observe(heading);
  });

  // Return cleanup function
  return () => {
    observer.disconnect();
  };
}

/**
 * Initialize search/filter functionality for sidebar navigation
 *
 * Adds search input to filter documentation navigation items.
 * Filters both category headers and doc links based on search term.
 *
 * @param options - Configuration options
 *
 * @example
 * // In your Astro component:
 * initSidebarSearch({ selector: '.docs-sidebar' });
 */
export interface SidebarSearchOptions {
  selector?: string; // CSS selector for sidebar container
  inputSelector?: string; // CSS selector for search input
  highlightMatches?: boolean; // Highlight matching text (default: true)
}

export function initSidebarSearch(options: SidebarSearchOptions = {}): void {
  const {
    selector = '.docs-sidebar',
    inputSelector = '.sidebar-search-input',
    highlightMatches: _highlightMatches = true,
  } = options;

  const sidebar = document.querySelector(selector);
  const input = document.querySelector(inputSelector);

  if (!sidebar || !input) return;

  input.addEventListener('input', (e: Event) => {
    const searchTerm = (e.target as HTMLInputElement).value.toLowerCase();

    // Get all items to filter
    const categoryItems = sidebar.querySelectorAll('[data-category]');
    const docLinks = sidebar.querySelectorAll('.doc-link');

    if (searchTerm.length === 0) {
      // Reset view
      categoryItems.forEach((item) => {
        (item as HTMLElement).style.display = '';
      });
      docLinks.forEach((link) => {
        (link as HTMLElement).style.display = '';
        link.classList.remove('search-match');
      });
      return;
    }

    // Filter and highlight
    categoryItems.forEach((item) => {
      const links = item.querySelectorAll('.doc-link');
      let hasMatch = false;

      for (const link of links) {
        const text = String(link.textContent).toLowerCase();
        const matches = text.includes(searchTerm);

        if (matches) {
          hasMatch = true;
          (link as HTMLElement).style.display = '';
          link.classList.add('search-match');
        } else {
          (link as HTMLElement).style.display = 'none';
          link.classList.remove('search-match');
        }
      }

      // Show category if it has matching items
      (item as HTMLElement).style.display = hasMatch ? '' : 'none';
    });
  });
}

/**
 * Type definitions for storing sidebar configuration
 */
export interface SidebarConfig {
  persistState?: boolean; // Persist sidebar state to localStorage (default: true)
  allowKeyboardNav?: boolean; // Allow keyboard navigation (default: true)
  highlightCurrentSection?: boolean; // Highlight current section in TOC (default: true)
}
