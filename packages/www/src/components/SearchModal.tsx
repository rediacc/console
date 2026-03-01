import Fuse from 'fuse.js';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';

interface SearchItem {
  id: string;
  content: string;
  excerpt: string;
  category: string;
  page: string;
  path: string;
  priority: number;
}

interface SearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SearchModal: React.FC<SearchModalProps> = ({ isOpen, onClose }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchItem[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [fuse, setFuse] = useState<Fuse<SearchItem> | null>(null);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsContainerRef = useRef<HTMLDivElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  // Load search index once
  useEffect(() => {
    const loadSearchData = async () => {
      try {
        setHasError(false);
        const response = await fetch('/search-index.json');
        if (!response.ok) {
          throw new Error(`Failed to fetch search index: ${response.status}`);
        }
        const data: SearchItem[] = await response.json();

        // Initialize Fuse.js with the data
        const fuseInstance = new Fuse<SearchItem>(data, {
          keys: ['content', 'excerpt', 'category'],
          threshold: 0.3,
          minMatchCharLength: 2,
          shouldSort: true,
          includeScore: true,
        });
        setFuse(fuseInstance);
      } catch (error) {
        setHasError(true);
        // Log error in development mode only
        if (import.meta.env.DEV) {
          console.error('Failed to load search index:', error);
        }
      }
    };

    void loadSearchData();
  }, []);

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
        const searchResults = fuse
          .search(value)
          .slice(0, 50) // Limit to 50 results
          .map((result) => result.item);
        setResults(searchResults);
      } finally {
        setIsLoading(false);
      }
    },
    [fuse]
  );

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
    window.location.href = result.page;
    onClose();
  };

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
              aria-label="Close search"
              type="button"
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
          aria-label="Search results"
        >
          {hasError && (
            <div className="search-modal-error" role="alert" aria-live="assertive">
              <h3>Search Unavailable</h3>
              <p>
                Unable to load search index. Please try refreshing the page or contact support if
                the issue persists.
              </p>
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
