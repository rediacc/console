import Fuse from 'fuse.js';
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { getLanguageFromPath } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

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

export const SearchModal: React.FC<SearchModalProps> = ({ isOpen, onClose }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchItem[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const [fuse, setFuse] = useState<Fuse<SearchItem> | null>(null);
  const [currentLang, setCurrentLang] = useState<Language>('en');
  const { t } = useTranslation(currentLang);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsContainerRef = useRef<HTMLDivElement>(null);

  // Get current language from URL
  useEffect(() => {
    const lang = getLanguageFromPath(window.location.pathname);
    setCurrentLang(lang);
  }, []);

  // Load search index once
  useEffect(() => {
    const loadSearchData = async () => {
      try {
        const response = await fetch('/search-index.json');
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
        console.error('Failed to load search index:', error);
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

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
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

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  // Group results by category
  const groupedResults: Record<string, SearchItem[]> = {};
  for (const item of results) {
    if (Object.hasOwn(groupedResults, item.category)) {
      groupedResults[item.category].push(item);
    } else {
      groupedResults[item.category] = [item];
    }
  }

  // Highlight matching text with proper escaping
  const highlightMatch = (text: string, query: string): React.ReactNode => {
    if (!query.trim()) return text;

    try {
      // Escape special regex characters
      const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(${escaped})`, 'gi');
      const parts = text.split(regex);

      return parts.map((part, i) => {
        if (part.toLowerCase() === query.toLowerCase()) {
          return <mark key={i}>{part}</mark>;
        }
        return <span key={i}>{part}</span>;
      });
    } catch {
      return text;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="search-modal-backdrop" onClick={handleBackdropClick}>
      <div className="search-modal-content">
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
            />
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

        <div className="search-modal-results" ref={resultsContainerRef}>
          {isLoading && <div className="search-modal-loading">{t('common.search.searching')}</div>}

          {!isLoading && query.trim() && results.length === 0 && (
            <div className="search-modal-no-results">
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

          {!isLoading &&
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
                        key={result.id}
                        className={`search-modal-result-item ${
                          selectedIndex === overallIndex ? 'selected' : ''
                        }`}
                        onClick={() => navigateToResult(result)}
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
