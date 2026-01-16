import React, { useState, useEffect } from 'react';
import LanguageMenu from './LanguageMenu';
import SearchModal from './SearchModal';
import Sidebar from './Sidebar';
import { getConsoleUrl } from '../config/constants';
import { SUPPORTED_LANGUAGES, getLanguageFromPath } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface NavigationProps {
  origin?: string;
}

const Navigation: React.FC<NavigationProps> = ({ origin }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [currentLang, setCurrentLang] = useState<Language>('en');
  const [isVisible, setIsVisible] = useState(false);
  const { t } = useTranslation(currentLang);

  // Get current language from URL
  useEffect(() => {
    const lang = getLanguageFromPath(window.location.pathname);
    setCurrentLang(lang);
  }, []);

  // Get console URL (use origin from server-side if provided)
  const consoleUrl = getConsoleUrl(origin);

  // Handle scroll to show/hide navigation (only on solutions page)
  useEffect(() => {
    const isOnSolutionsPage = window.location.pathname.includes('/solutions');

    if (isOnSolutionsPage) {
      // On solutions page: hide nav at top, show when scrolled
      const handleScroll = () => {
        const scrollTop = window.scrollY || document.documentElement.scrollTop;
        setIsVisible(scrollTop > 0);
      };

      // Set initial state
      handleScroll();

      // Listen to scroll events
      window.addEventListener('scroll', handleScroll, { passive: true });
      return () => window.removeEventListener('scroll', handleScroll);
    }
    // On all other pages: always show nav
    setIsVisible(true);
  }, []);

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
  };

  const closeSidebar = () => {
    setIsSidebarOpen(false);
  };

  const openSearch = () => {
    setIsSearchOpen(true);
  };

  const closeSearch = () => {
    setIsSearchOpen(false);
  };

  // Listen for global search hotkey event
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const eventName = (window as any).SEARCH_HOTKEY_EVENT ?? 'search:open';
    const handleSearchHotkey = () => {
      setIsSearchOpen(true);
    };

    document.addEventListener(eventName, handleSearchHotkey);
    return () => {
      document.removeEventListener(eventName, handleSearchHotkey);
    };
  }, []);

  return (
    <>
      <nav
        id="navigation"
        className={`nav ${isVisible ? 'nav-visible' : 'nav-hidden'}`}
        role="navigation"
        aria-label={t('common.aria.mainNavigation')}
      >
        <div className="nav-container">
          <button
            type="button"
            className="hamburger-btn"
            onClick={toggleSidebar}
            aria-label={t('navigation.toggleMenu')}
            aria-expanded={isSidebarOpen}
          >
            <span className="hamburger-icon" />
          </button>
          <a href={`/${currentLang}/`} className="nav-brand">
            <img
              src="/assets/images/logo_black.png"
              alt={t('common.logoAlt')}
              className="logo"
              loading="eager"
              decoding="async"
              width="120"
              height="40"
            />
          </a>
          <div className="nav-right">
            <button
              type="button"
              className="search-btn"
              onClick={openSearch}
              aria-label={t('navigation.search')}
            >
              <svg
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
            </button>
            <LanguageMenu
              variant="icon-only"
              currentLang={currentLang}
              languages={SUPPORTED_LANGUAGES}
              position="top"
              navigationMode="button"
              ariaLabel={t('navigation.selectLanguage')}
            />
            <a href={consoleUrl} className="login-btn" target="_blank" rel="noopener noreferrer">
              {t('navigation.login')}
            </a>
          </div>
        </div>
      </nav>
      <Sidebar isOpen={isSidebarOpen} onClose={closeSidebar} />
      <SearchModal isOpen={isSearchOpen} onClose={closeSearch} />
    </>
  );
};

export default Navigation;
