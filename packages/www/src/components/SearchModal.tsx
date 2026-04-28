import Fuse, { type FuseResultMatch } from 'fuse.js';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface SearchItem {
  id: string;
  content: string;
  body?: string;
  excerpt: string;
  category: string;
  page: string;
  path: string;
  priority: number;
  language?: string;
}

interface SearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const EXCERPT_RADIUS = 60;
const EXCERPT_MAX = 160;

// When a Fuse match lands in the body field, replace the pre-computed excerpt
// with a window centered on the first match — so users see the relevant
// paragraph for buried terms (e.g. REDIACC_ALLOW_GRAND_REPO) instead of the
// section's opening sentence.
function buildResultExcerpt(item: SearchItem, matches?: readonly FuseResultMatch[]): SearchItem {
  if (!item.body || !matches?.length) return item;
  const bodyMatch = matches.find((m) => m.key === 'body');
  if (!bodyMatch?.indices?.length) return item;
  const [start, end] = bodyMatch.indices[0];
  const before = Math.max(0, start - EXCERPT_RADIUS);
  const after = Math.min(item.body.length, end + 1 + EXCERPT_RADIUS);
  let excerpt = item.body.slice(before, after);
  if (before > 0) excerpt = '…' + excerpt;
  if (after < item.body.length) excerpt = excerpt + '…';
  if (excerpt.length > EXCERPT_MAX) excerpt = excerpt.slice(0, EXCERPT_MAX - 1) + '…';
  return { ...item, excerpt };
}

const SearchModal: React.FC<SearchModalProps> = ({ isOpen, onClose }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchItem[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const [hasError, setHasError] = useState(false);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsContainerRef = useRef<HTMLDivElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  // Per-locale Fuse cache. The combined index was 1.6 MB gzipped; per-locale
  // files are ~167-247 KB. We fetch on first modal open for the current
  // locale, then cache so locale switches don't re-pay the cost.
  const fuseCache = useRef<Map<Language, Fuse<SearchItem>>>(new Map());
  const inFlight = useRef<Map<Language, Promise<void>>>(new Map());
  const [, bumpCacheVersion] = useState(0);
  const fuse = fuseCache.current.get(currentLang) ?? null;

  // Lazy-load the locale-specific index the first time the user opens search
  // for that locale. No fetch happens for visitors who never open search.
  useEffect(() => {
    if (!isOpen) return;
    if (fuseCache.current.has(currentLang)) {
      setHasError(false);
      return;
    }
    if (inFlight.current.has(currentLang)) return;

    const lang = currentLang;
    const promise = (async () => {
      try {
        setHasError(false);
        const response = await fetch(`/search-index-${lang}.json`);
        if (!response.ok) {
          throw new Error(`Failed to fetch search index: ${response.status}`);
        }
        const data: SearchItem[] = await response.json();
        const fuseInstance = new Fuse<SearchItem>(data, {
          keys: [
            { name: 'content', weight: 0.5 },
            { name: 'body', weight: 0.4 },
            { name: 'category', weight: 0.1 },
          ],
          threshold: 0.3,
          minMatchCharLength: 2,
          shouldSort: true,
          includeScore: true,
          includeMatches: true,
          ignoreLocation: true,
        });
        fuseCache.current.set(lang, fuseInstance);
        bumpCacheVersion((v) => v + 1);
      } catch (error) {
        setHasError(true);
        if (import.meta.env.DEV) {
          console.error(`Failed to load search index for ${lang}:`, error);
        }
      } finally {
        inFlight.current.delete(lang);
      }
    })();
    inFlight.current.set(lang, promise);
  }, [isOpen, currentLang]);

  // Handle search input changes
  const handleSearch = useCallback(
    (value: string) => {
      setQuery(value);
      setSelectedIndex(-1);

      if (!fuse || !value.trim()) {
        setResults([]);
        return;
      }

      setIsLoading(true);
      try {
        // Each per-locale file is pre-filtered, so no language check needed
        // here — we only dedupe by page and slice to 50.
        const seenPages = new Set<string>();
        const searchResults: SearchItem[] = [];
        for (const result of fuse.search(value)) {
          const item = result.item;
          if (seenPages.has(item.page)) continue;
          seenPages.add(item.page);
          searchResults.push(buildResultExcerpt(item, result.matches));
          if (searchResults.length >= 50) break;
        }
        setResults(searchResults);
        if (value.trim().length >= 2) {
          window.plausible?.('search_query', {
            props: { query: value.trim(), results: String(searchResults.length) },
          });
          if (searchResults.length === 0) {
            window.plausible?.('search_no_results', { props: { query: value.trim() } });
          }
        }
      } finally {
        setIsLoading(false);
      }
    },
    [fuse]
  );

  // Re-run the active query when the user switches locale (e.g. via the
  // language picker triggering an astro:after-swap View Transition). Reads
  // query from a ref so this effect only fires when handleSearch's identity
  // changes (when fuse loads or currentLang changes).
  const queryRef = useRef(query);
  queryRef.current = query;
  useEffect(() => {
    if (queryRef.current.trim()) handleSearch(queryRef.current);
  }, [handleSearch]);

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < results.length - 1 ? prev + 1 : prev));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : -1));
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      const selected = results[selectedIndex];
      navigateToResult(selected);
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  // Navigate to result
  const navigateToResult = (result: SearchItem) => {
    window.plausible?.('search_result_click', {
      props: { query: query.trim(), result_path: result.path, category: result.category },
    });
    window.location.href = result.page;
    onClose();
  };

  // Track search open
  useEffect(() => {
    if (isOpen) {
      window.plausible?.('search_open', { props: { source: 'click' } });
    }
  }, [isOpen]);

  // Focus input and lock body scroll when modal opens
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  // Scroll selected item into view
  useEffect(() => {
    if (selectedIndex >= 0 && resultsContainerRef.current) {
      const selectedElement = resultsContainerRef.current.children[selectedIndex] as
        | HTMLElement
        | undefined;
      selectedElement?.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

  // Focus trap - keep focus within modal
  useEffect(() => {
    if (!isOpen || !modalRef.current) return;

    const modal = modalRef.current;
    const focusableElements = modal.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );

    if (focusableElements.length === 0) return;

    const firstElement = focusableElements[0] as HTMLElement;
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

    const handleTabKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else if (document.activeElement === lastElement) {
        e.preventDefault();
        firstElement.focus();
      }
    };

    modal.addEventListener('keydown', handleTabKey);

    return () => {
      modal.removeEventListener('keydown', handleTabKey);
    };
  }, [isOpen]);

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  // Group results by category - memoized to prevent re-computation on every render
  const groupedResults = useMemo(() => {
    const grouped: Record<string, SearchItem[]> = {};
    for (const item of results) {
      if (Object.hasOwn(grouped, item.category)) {
        grouped[item.category].push(item);
      } else {
        grouped[item.category] = [item];
      }
    }
    return grouped;
  }, [results]);

  // Highlight matching text with proper escaping
  const highlightMatch = (text: string, query: string): React.ReactNode => {
    if (!query.trim()) return text;

    try {
      // Escape special regex characters
      const escaped = query.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(${escaped})`, 'gi');
      const parts = text.split(regex);

      return parts.map((part, i) => {
        if (part.toLowerCase() === query.toLowerCase()) {
          return <mark key={`mark-${i}-${part}`}>{part}</mark>;
        }
        return <span key={`span-${i}-${part}`}>{part}</span>;
      });
    } catch {
      return text;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="search-modal-backdrop" onClick={handleBackdropClick}>
      <div
        id="search-modal"
        className="search-modal-content"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('navigation.search')}
      >
        <div className="search-modal-header">
          <div className="search-modal-input-wrapper">
            <input
              ref={inputRef}
              type="text"
              className="search-modal-input"
              placeholder={t('common.search.placeholder')}
              value={query}
              onChange={(e) => handleSearch(e.target.value)}
              onKeyDown={handleKeyDown}
              aria-label={t('navigation.search')}
              role="combobox"
              aria-controls="search-results"
              aria-autocomplete="list"
              aria-expanded={results.length > 0}
              aria-activedescendant={
                selectedIndex >= 0 ? `search-result-${selectedIndex}` : undefined
              }
            />
            <button
              className="search-modal-close"
              onClick={onClose}
              aria-label={t('common.search.closeModal')}
              type="button"
              data-track="cta_click"
              data-track-label="search-close"
            >
              <kbd>Esc</kbd>
            </button>
            <svg
              className="search-modal-icon"
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" />
              <path
                d="M12.5 12.5L17 17"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </div>
        </div>

        <div
          id="search-results"
          className="search-modal-results"
          ref={resultsContainerRef}
          role="listbox"
          aria-label={t('common.search.results')}
        >
          {hasError && (
            <div className="search-modal-error" role="alert" aria-live="assertive">
              <h3>{t('common.search.unavailable')}</h3>
              <p>{t('common.search.unavailableMessage')}</p>
            </div>
          )}

          {isLoading && !hasError && (
            <div className="search-modal-loading" role="status" aria-live="polite">
              {t('common.search.searching')}
            </div>
          )}

          {!isLoading && !hasError && query.trim() && results.length === 0 && (
            <div className="search-modal-no-results" role="status" aria-live="polite">
              <h3>
                {t('common.search.noResults')} for &quot;{query}&quot;
              </h3>
              <div className="search-modal-suggestions">
                <p>{t('common.search.suggestions.title')}</p>
                <ul>
                  <li>{t('common.search.suggestions.differentKeywords')}</li>
                  <li>{t('common.search.suggestions.checkSpelling')}</li>
                  <li>{t('common.search.suggestions.browseSolutions')}</li>
                  <li>{t('common.search.suggestions.contactSupport')}</li>
                </ul>
              </div>
            </div>
          )}

          {!isLoading && !hasError && results.length > 0 && (
            <div className="sr-only" role="status" aria-live="polite">
              {results.length} {results.length === 1 ? 'result' : 'results'} found
            </div>
          )}

          {!isLoading &&
            !hasError &&
            Object.entries(groupedResults).map(([category, categoryResults]) => (
              <div key={category} className="search-modal-category">
                <h4 className="search-modal-category-title">{category}</h4>
                <ul className="search-modal-results-list">
                  {categoryResults.map((result, index) => {
                    const overallIndex =
                      Object.entries(groupedResults)
                        .slice(0, Object.keys(groupedResults).indexOf(category))
                        .reduce((sum, [, items]) => sum + items.length, 0) + index;

                    return (
                      <li
                        id={`search-result-${overallIndex}`}
                        key={result.id}
                        className={`search-modal-result-item ${
                          selectedIndex === overallIndex ? 'selected' : ''
                        }`}
                        role="option"
                        aria-selected={selectedIndex === overallIndex}
                        onClick={() => navigateToResult(result)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            navigateToResult(result);
                          }
                        }}
                        tabIndex={-1}
                      >
                        <div className="search-modal-result-title">
                          {highlightMatch(result.content, query)}
                        </div>
                        <div className="search-modal-result-excerpt">
                          {highlightMatch(result.excerpt, query)}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
};

export default SearchModal;
