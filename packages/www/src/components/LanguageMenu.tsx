import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getLanguageFlag, getLanguageName, SUPPORTED_LANGUAGES } from '../i18n/language-utils';
import type { Language } from '../i18n/types';
import { setLanguageCookie } from '../utils/language-cookie';
import '../styles/language-switcher.css';

interface LanguageMenuProps {
  // Visual variant
  variant?: 'icon-only' | 'flag-name' | 'full-list';

  // Current language
  currentLang: Language;

  // Languages to show in dropdown
  languages?: Language[] | { lang: Language; url: string }[];

  // Dropdown position
  position?: 'top' | 'bottom';

  // Navigation mode: 'link' for <a> tags, 'button' for redirects
  navigationMode?: 'link' | 'button';

  // Custom handler for language selection
  onLanguageChange?: (lang: Language) => void;

  // CSS class name for custom styling
  className?: string;

  // Aria label for the button
  ariaLabel?: string;

  // Icon SVG for icon-only variant (optional, uses globe by default)
  icon?: React.ReactNode;
}

const LanguageMenu: React.FC<LanguageMenuProps> = ({
  variant = 'flag-name',
  currentLang,
  languages = SUPPORTED_LANGUAGES,
  position = 'top',
  navigationMode = 'button',
  onLanguageChange,
  className,
  ariaLabel = 'Select language',
  icon,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [pendingNavigation, setPendingNavigation] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuItemsRef = useRef<(HTMLButtonElement | HTMLAnchorElement | null)[]>([]);

  // Normalize languages to Language[] format
  const languageList: Language[] = languages.map((lang) =>
    typeof lang === 'string' ? lang : lang.lang
  );

  // Get URL for a language if using link mode
  const getLanguageUrl = (lang: Language): string => {
    if (navigationMode === 'link') {
      const langData = languages.find((l) =>
        typeof l === 'string' ? l === lang : l.lang === lang
      );
      if (langData && typeof langData !== 'string' && 'url' in langData) {
        return langData.url;
      }
    }
    return '#';
  };

  // Close dropdown when clicking outside - memoized for performance
  const handleClickOutside = useCallback((event: MouseEvent) => {
    if (
      dropdownRef.current &&
      !dropdownRef.current.contains(event.target as Node) &&
      !triggerRef.current?.contains(event.target as Node)
    ) {
      setIsOpen(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen, handleClickOutside]);

  // Compute initial active index based on current language
  const initialIndex = useMemo(
    () => languageList.indexOf(currentLang),
    [languageList, currentLang]
  );

  // Handle keyboard navigation - memoized for performance
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!isOpen) return;

      switch (event.key) {
        case 'Escape':
          setIsOpen(false);
          setActiveIndex(-1);
          triggerRef.current?.focus();
          break;
        case 'ArrowDown': {
          event.preventDefault();
          const nextIndex = activeIndex < languageList.length - 1 ? activeIndex + 1 : 0;
          setActiveIndex(nextIndex);
          menuItemsRef.current[nextIndex]?.focus();
          break;
        }
        case 'ArrowUp': {
          event.preventDefault();
          const prevIndex = activeIndex > 0 ? activeIndex - 1 : languageList.length - 1;
          setActiveIndex(prevIndex);
          menuItemsRef.current[prevIndex]?.focus();
          break;
        }
        case 'Home':
          event.preventDefault();
          setActiveIndex(0);
          menuItemsRef.current[0]?.focus();
          break;
        case 'End':
          event.preventDefault();
          setActiveIndex(languageList.length - 1);
          menuItemsRef.current[languageList.length - 1]?.focus();
          break;
      }
    },
    [isOpen, activeIndex, languageList.length]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  // Focus the current language item when menu opens
  useEffect(() => {
    if (isOpen) {
      const idx = initialIndex >= 0 ? initialIndex : 0;
      // Defer state update to avoid cascading renders
      requestAnimationFrame(() => {
        setActiveIndex(idx);
        menuItemsRef.current[idx]?.focus();
      });
    }
  }, [isOpen, initialIndex]);

  // Handle pending navigation
  useEffect(() => {
    if (pendingNavigation) {
      window.location.href = pendingNavigation;
    }
  }, [pendingNavigation]);

  // Handle language selection
  const handleLanguageSelect = (lang: Language) => {
    setLanguageCookie(lang);

    if (onLanguageChange) {
      onLanguageChange(lang);
    } else if (navigationMode === 'button') {
      // Handle button-based navigation
      const currentPath = window.location.pathname;
      const pathWithoutLang = currentPath.replace(/^\/[a-z]{2}/, '');
      const newPath = `/${lang}${pathWithoutLang || '/'}`;
      setPendingNavigation(newPath);
    }

    setIsOpen(false);
  };

  // Render trigger button based on variant
  const renderTrigger = () => {
    if (variant === 'icon-only') {
      return (
        <button
          type="button"
          ref={triggerRef}
          className={`language-trigger-icon ${className ?? ''}`}
          onClick={() => setIsOpen(!isOpen)}
          aria-label={ariaLabel}
          aria-expanded={isOpen}
          aria-haspopup="menu"
        >
          {icon ?? (
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M12 3c-2.5 3-2.5 15 0 18M12 3c2.5 3 2.5 15 0 18" />
              <path d="M3 12h18" />
            </svg>
          )}
        </button>
      );
    }

    // flag-name and full-list variants
    return (
      <button
        type="button"
        ref={triggerRef}
        className={`language-trigger ${className ?? ''}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-label={ariaLabel}
        aria-expanded={isOpen}
        aria-haspopup="menu"
      >
        {variant !== 'full-list' && (
          <span className="language-flag">{getLanguageFlag(currentLang)}</span>
        )}
        <span className="language-name">{getLanguageName(currentLang)}</span>
        <svg
          className={`language-chevron ${isOpen ? 'open' : ''}`}
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
    );
  };

  // Render menu items
  const renderMenuItems = () => {
    if (navigationMode === 'link') {
      return languageList.map((lang, index) => (
        <a
          key={lang}
          ref={(el) => {
            menuItemsRef.current[index] = el;
          }}
          href={getLanguageUrl(lang)}
          className={`language-option ${lang === currentLang ? 'active' : ''}`}
          onClick={() => handleLanguageSelect(lang)}
          role="menuitem"
          tabIndex={index === activeIndex ? 0 : -1}
          aria-current={lang === currentLang ? 'true' : undefined}
        >
          <span className="flag">{getLanguageFlag(lang)}</span>
          <span className="name">{getLanguageName(lang)}</span>
          {lang === currentLang && (
            <svg
              className="checkmark"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          )}
        </a>
      ));
    }

    // Button mode
    return languageList.map((lang, index) => (
      <button
        type="button"
        key={lang}
        ref={(el) => {
          menuItemsRef.current[index] = el;
        }}
        className={`language-option ${lang === currentLang ? 'active' : ''}`}
        onClick={() => handleLanguageSelect(lang)}
        role="menuitem"
        tabIndex={index === activeIndex ? 0 : -1}
        aria-current={lang === currentLang ? 'true' : undefined}
      >
        <span className="flag">{getLanguageFlag(lang)}</span>
        <span className="name">{getLanguageName(lang)}</span>
        {lang === currentLang && (
          <svg
            className="checkmark"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        )}
      </button>
    ));
  };

  return (
    <div className={`language-selector ${className ?? ''}`} ref={dropdownRef}>
      {renderTrigger()}

      {isOpen && (
        <div className={`language-menu ${position}`} role="menu" aria-label={ariaLabel}>
          {renderMenuItems()}
        </div>
      )}
    </div>
  );
};

export default LanguageMenu;
