import React, { useState, useRef, useEffect } from 'react';
import { getLanguageName, getLanguageFlag, SUPPORTED_LANGUAGES } from '../i18n/language-utils';
import { setLanguageCookie } from '../utils/language-cookie';
import type { Language } from '../i18n/types';
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
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

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

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        !triggerRef.current?.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen]);

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
      window.location.href = newPath;
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
      return languageList.map((lang) => (
        <a
          key={lang}
          href={getLanguageUrl(lang)}
          className={`language-option ${lang === currentLang ? 'active' : ''}`}
          onClick={() => handleLanguageSelect(lang)}
          role="menuitem"
        >
          <span className="flag">{getLanguageFlag(lang)}</span>
          <span className="name">{getLanguageName(lang)}</span>
          {lang === currentLang && <span className="checkmark">✓</span>}
        </a>
      ));
    }

    // Button mode
    return languageList.map((lang) => (
      <button
        type="button"
        key={lang}
        className={`language-option ${lang === currentLang ? 'active' : ''}`}
        onClick={() => handleLanguageSelect(lang)}
        role="menuitem"
      >
        <span className="flag">{getLanguageFlag(lang)}</span>
        <span className="name">{getLanguageName(lang)}</span>
        {lang === currentLang && <span className="checkmark">✓</span>}
      </button>
    ));
  };

  return (
    <div className={`language-selector ${className ?? ''}`} ref={dropdownRef}>
      {renderTrigger()}

      {isOpen && (
        <div className={`language-menu ${position}`} role="menu">
          {renderMenuItems()}
        </div>
      )}
    </div>
  );
};

export default LanguageMenu;
