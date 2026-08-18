import Fuse, { type FuseResultMatch } from 'fuse.js';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import Overlay from './Overlay';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface SearchItem {
  id: string;
  content: string;
  body?: string;
  excerpt: string;
  category: string;
  page: string;
  /** Stable English heading fragment of the matched section, when it has one. */
  fragment?: string;
  path: string;
  priority: number;
  language?: string;
}

interface SearchModalProps {
  /** Locale from Navigation; authoritative on the server, where useLanguage() returns 'en'. */
  lang?: Language;
  isOpen: boolean;
  onClose: () => void;
  /**
   * Restrict results to these index `category` values. Left undefined by the
   * site-wide mount, which returns everything.
   *
   * This is a post-filter over the ONE Fuse index, not a second index built
   * from a filtered corpus. A second index would mean fetching and parsing the
   * same ~1.3 MB payload twice on a docs page, to save one Array.includes per
   * hit. The cost of the filter is that a query whose first 50 hits are all
   * blog posts returns fewer than 50 docs hits, which is why the loop below
   * filters before it counts rather than after.
   */
  categories?: readonly string[];
  /**
   * Which surface this modal is. Every Plausible event carries it, because
   * without it the docs search and the site-wide search are one undifferen-
   * tiated funnel and neither can be judged.
   */
  scope?: string;
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
  if (!bodyMatch?.indices.length) return item;
  const [start, end] = bodyMatch.indices[0];
  const before = Math.max(0, start - EXCERPT_RADIUS);
  const after = Math.min(item.body.length, end + 1 + EXCERPT_RADIUS);
  let excerpt = item.body.slice(before, after);
  if (before > 0) excerpt = `…${excerpt}`;
  if (after < item.body.length) excerpt = `${excerpt}…`;
  if (excerpt.length > EXCERPT_MAX) excerpt = `${excerpt.slice(0, EXCERPT_MAX - 1)}…`;
  return { ...item, excerpt };
}

const SearchModal: React.FC<SearchModalProps> = ({
  lang,
  isOpen,
  onClose,
  categories,
  scope = 'global',
}) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchItem[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const [hasError, setHasError] = useState(false);
  const detectedLang = useLanguage();
  const currentLang = lang ?? detectedLang;
  const { t } = useTranslation(currentLang);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsContainerRef = useRef<HTMLDivElement>(null);

  // Per-locale Fuse cache. The combined index was 1.6 MB gzipped; per-locale
  // files are ~167-247 KB. We fetch on first modal open for the current
  // locale, then cache so locale switches don't re-pay the cost.
  //
  // Three pieces of locale-keyed state, each with a distinct job:
  //   - fuseByLang (state)     — drives `fuse` for handleSearch (must be reactive).
  //   - loadingLocales (state) — drives the "Searching…" UI state and suppresses
  //                              the no-results message during the in-flight fetch
  //                              (must be reactive).
  //   - inFlight (ref)         — prevents duplicate fetches when the load effect
  //                              re-runs synchronously between fetch start and
  //                              setFuseByLang completion. Read-only inside the
  //                              effect, so a ref is fine and avoids an extra render.
  const [fuseByLang, setFuseByLang] = useState<Map<Language, Fuse<SearchItem>>>(() => new Map());
  const [loadingLocales, setLoadingLocales] = useState<Set<Language>>(() => new Set());
  const inFlight = useRef<Map<Language, Promise<void>>>(new Map());
  const fuse = fuseByLang.get(currentLang) ?? null;
  const isLoadingIndex = loadingLocales.has(currentLang);

  // Memoized on the array's CONTENTS, not its identity: a caller writing
  // `categories={['Documentation']}` inline would otherwise hand us a fresh
  // array on every render and rebuild handleSearch on each one.
  const categoryKey = categories === undefined ? undefined : JSON.stringify(categories);
  const allowedCategories = useMemo(
    () => (categoryKey === undefined ? null : new Set<string>(JSON.parse(categoryKey) as string[])),
    [categoryKey]
  );

  // Lazy-load the locale-specific index the first time the user opens search
  // for that locale. No fetch happens for visitors who never open search.
  // While the fetch is in flight we mark the locale as loading so the UI
  // shows "Searching…" instead of a misleading "No results" if the user
  // types ahead of the network round-trip.
  useEffect(() => {
    if (!isOpen) return;
    if (fuseByLang.has(currentLang)) return;
    if (inFlight.current.has(currentLang)) return;

    const lang = currentLang;
    setLoadingLocales((prev) => {
      if (prev.has(lang)) return prev;
      const next = new Set(prev);
      next.add(lang);
      return next;
    });
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
        setFuseByLang((prev) => new Map(prev).set(lang, fuseInstance));
      } catch (error) {
        setHasError(true);
        if (import.meta.env.DEV) {
          console.error(`Failed to load search index for ${lang}:`, error);
        }
      } finally {
        inFlight.current.delete(lang);
        setLoadingLocales((prev) => {
          if (!prev.has(lang)) return prev;
          const next = new Set(prev);
          next.delete(lang);
          return next;
        });
      }
    })();
    inFlight.current.set(lang, promise);
  }, [isOpen, currentLang, fuseByLang]);

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
        // here; we dedupe by destination and slice to 50. The destination
        // includes the section fragment: two sections of one page are two
        // different places to land, and deduping by bare page collapsed every
        // section hit into a link to the top of the page.
        const seenDestinations = new Set<string>();
        const searchResults: SearchItem[] = [];
        for (const result of fuse.search(value)) {
          const item = result.item;
          if (allowedCategories && !allowedCategories.has(item.category)) continue;
          const destination = `${item.page}#${item.fragment ?? ''}`;
          if (seenDestinations.has(destination)) continue;
          seenDestinations.add(destination);
          searchResults.push(buildResultExcerpt(item, result.matches));
          if (searchResults.length >= 50) break;
        }
        setResults(searchResults);
        if (value.trim().length >= 2) {
          window.plausible?.('search_query', {
            props: { query: value.trim(), results: String(searchResults.length), scope },
          });
          if (searchResults.length === 0) {
            window.plausible?.('search_no_results', { props: { query: value.trim(), scope } });
          }
        }
      } finally {
        setIsLoading(false);
      }
    },
    [fuse, allowedCategories, scope]
  );

  // Re-run the active query when the user switches locale OR when the
  // locale's Fuse index lands (so a query typed during the first fetch
  // gets results as soon as the index arrives). Uses the previous-value
  // pattern in render so we don't trip react-hooks/set-state-in-effect —
  // calling handleSearch during render is legitimate derived state, the
  // cycle converges in one extra render.
  const [prevLang, setPrevLang] = useState(currentLang);
  const [prevFuse, setPrevFuse] = useState<Fuse<SearchItem> | null>(fuse);
  if (prevLang !== currentLang || prevFuse !== fuse) {
    setPrevLang(currentLang);
    setPrevFuse(fuse);
    if (query.trim()) handleSearch(query);
  }

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
      props: {
        query: query.trim(),
        result_path: result.path,
        category: result.category,
        scope,
      },
    });
    window.location.href = result.fragment ? `${result.page}#${result.fragment}` : result.page;
    onClose();
  };

  // Track search open
  useEffect(() => {
    if (isOpen) {
      window.plausible?.('search_open', { props: { source: 'click', scope } });
    }
  }, [isOpen, scope]);

  // Scroll selected item into view
  useEffect(() => {
    if (selectedIndex >= 0 && resultsContainerRef.current) {
      const selectedElement = resultsContainerRef.current.children[selectedIndex] as
        | HTMLElement
        | undefined;
      selectedElement?.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

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

  return (
    <Overlay
      open={isOpen}
      onClose={onClose}
      label={t('navigation.search')}
      panelClassName="search-panel"
      initialFocusRef={inputRef}
    >
      <div className="search-header">
        <div className="search-input-wrapper" id="search-modal">
          <div className="search-field">
            <input
              ref={inputRef}
              type="text"
              className="form-input search-input"
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
            {/* The magnifier is anchored to the INPUT, not to the row. It used
                to be a sibling of the close button and absolutely positioned
                against the whole row, so it sat on top of the Esc key. */}
            <svg
              className="icon search-icon"
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              aria-hidden="true"
              xmlns="http://www.w3.org/2000/svg"
            >
              <circle cx="8" cy="8" r="6" />
              <path d="M12.5 12.5L17 17" />
            </svg>
          </div>
          <button
            className="btn btn--secondary btn--sm"
            onClick={onClose}
            aria-label={t('common.search.closeModal')}
            type="button"
            data-track="cta_click"
            data-track-label="search-close"
          >
            <kbd>Esc</kbd>
          </button>
        </div>
      </div>

      <div
        id="search-results"
        className="overlay-body--flush search-results"
        ref={resultsContainerRef}
        role="listbox"
        aria-label={t('common.search.results')}
      >
        {hasError && (
          <div className="search-message" role="alert" aria-live="assertive">
            <h3>{t('common.search.unavailable')}</h3>
            <p>{t('common.search.unavailableMessage')}</p>
          </div>
        )}

        {(isLoading || isLoadingIndex) && !hasError && (
          <div className="search-message" role="status" aria-live="polite">
            {t('common.search.searching')}
          </div>
        )}

        {!isLoading && !isLoadingIndex && !hasError && query.trim() && results.length === 0 && (
          <div className="search-message" role="status" aria-live="polite">
            <h3>
              {t('common.search.noResults')} for &quot;{query}&quot;
            </h3>
            <div className="search-suggestions">
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
            <div key={category} className="search-category">
              <h4 className="search-category-title">{category}</h4>
              <ul className="search-results-list">
                {categoryResults.map((result, index) => {
                  const overallIndex =
                    Object.entries(groupedResults)
                      .slice(0, Object.keys(groupedResults).indexOf(category))
                      .reduce((sum, [, items]) => sum + items.length, 0) + index;

                  return (
                    <li
                      id={`search-result-${overallIndex}`}
                      key={result.id}
                      className={`search-result ${
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
                      <div className="search-result-title">
                        {highlightMatch(result.content, query)}
                      </div>
                      <div className="search-result-excerpt">
                        {highlightMatch(result.excerpt, query)}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
      </div>
    </Overlay>
  );
};

export default SearchModal;
