import React, { useEffect, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { SUPPORTED_LANGUAGES } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import { AccountCta } from './AccountCta';
import LanguageMenu from './LanguageMenu';
import MegaMenu from './MegaMenu';
import PersonaMegaMenu from './PersonaMegaMenu';
import SearchModal from './SearchModal';
import Sidebar from './Sidebar';
import ThemeToggle from './ThemeToggle';

interface NavigationProps {
  origin?: string;
}

const Navigation: React.FC<NavigationProps> = ({ origin }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isMegaMenuOpen, setIsMegaMenuOpen] = useState(false);
  const [isPersonaMenuOpen, setIsPersonaMenuOpen] = useState(false);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  // Drives `.nav-translate` groups: center nav + utility cluster slide up and
  // fade out 1:1 with the first 80px of scroll, then clamp. Brand and CTA stay.
  // Opacity is paired with translate because the items would otherwise hide
  // behind the higher-z announcement banner mid-slide and look abrupt.
  // body[data-nav-collapsed] suppresses pointer events on faded items so they
  // don't intercept clicks meant for the page below.
  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    let frame = 0;
    const update = () => {
      frame = 0;
      const y = Math.min(Math.max(window.scrollY, 0), 80);
      // Translate range is half the scroll range so items progressively clip
      // against the nav top edge instead of jumping out of view in the first
      // few pixels (item center is ~16px from the nav's top edge).
      root.style.setProperty('--nav-scroll-y', `${-y * 0.5}px`);
      root.style.setProperty('--nav-scroll-fade', `${1 - y / 80}`);
      const collapsed = y >= 80;
      if (collapsed) {
        body.setAttribute('data-nav-collapsed', 'true');
        setIsMegaMenuOpen(false);
        setIsPersonaMenuOpen(false);
      } else {
        body.removeAttribute('data-nav-collapsed');
      }
    };
    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (frame) cancelAnimationFrame(frame);
      body.removeAttribute('data-nav-collapsed');
    };
  }, []);

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
    setIsMegaMenuOpen(false);
    setIsPersonaMenuOpen(false);
  };

  const closeSidebar = () => {
    setIsSidebarOpen(false);
  };

  const openSearch = () => {
    setIsSearchOpen(true);
    setIsMegaMenuOpen(false);
    setIsPersonaMenuOpen(false);
  };

  const closeSearch = () => {
    setIsSearchOpen(false);
  };

  const toggleMegaMenu = () => {
    setIsMegaMenuOpen((prev) => !prev);
    setIsPersonaMenuOpen(false);
  };
  const closeMegaMenu = () => setIsMegaMenuOpen(false);
  const togglePersonaMenu = () => {
    setIsPersonaMenuOpen((prev) => !prev);
    setIsMegaMenuOpen(false);
  };
  const closePersonaMenu = () => setIsPersonaMenuOpen(false);

  // Close menus on Astro page navigation
  useEffect(() => {
    const handleNavigation = () => {
      setIsMegaMenuOpen(false);
      setIsPersonaMenuOpen(false);
    };
    document.addEventListener('astro:after-swap', handleNavigation);
    return () => document.removeEventListener('astro:after-swap', handleNavigation);
  }, []);

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
        className="nav"
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
            aria-controls="navigation-sidebar"
            data-track="cta_click"
            data-track-label="nav-hamburger"
          >
            <span className="hamburger-icon" />
          </button>
          <a
            href={`/${currentLang}`}
            className="nav-icon-link"
            aria-label={t('common.logoAlt')}
            data-track="cta_click"
            data-track-label="nav-logo"
          >
            <img
              src="/assets/images/icon-rediacc.svg"
              alt="Rediacc"
              className="logo-icon"
              loading="eager"
              decoding="async"
              fetchPriority="high"
              width="36"
              height="36"
            />
          </a>
          <a
            href={`/${currentLang}`}
            className="nav-brand"
            data-track="cta_click"
            data-track-label="nav-brand"
          >
            <span className="nav-wordmark" aria-label={t('common.logoAlt')}>
              rediacc
            </span>
          </a>
          <div className="nav-links nav-translate">
            <MegaMenu isOpen={isMegaMenuOpen} onToggle={toggleMegaMenu} onClose={closeMegaMenu} />
            <PersonaMegaMenu
              isOpen={isPersonaMenuOpen}
              onToggle={togglePersonaMenu}
              onClose={closePersonaMenu}
            />
            <a
              href={`/${currentLang}/pricing`}
              className="nav-link"
              data-track="cta_click"
              data-track-label="nav-link"
              data-track-dest="pricing"
            >
              {t('navigation.pricing')}
            </a>
            <a
              href={`/${currentLang}/docs/quick-start`}
              className="nav-link"
              data-track="cta_click"
              data-track-label="nav-link"
              data-track-dest="docs"
            >
              {t('navigation.docs')}
            </a>
            <a
              href={`/${currentLang}/blog`}
              className="nav-link"
              data-track="cta_click"
              data-track-label="nav-link"
              data-track-dest="blog"
            >
              {t('navigation.blog')}
            </a>
          </div>
          <div className="nav-right">
            <div className="nav-utilities nav-translate">
              <button
                type="button"
                className="search-btn"
                onClick={openSearch}
                aria-label={t('navigation.search')}
                aria-expanded={isSearchOpen}
                aria-controls="search-modal"
                data-track="cta_click"
                data-track-label="nav-search"
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
              <ThemeToggle label={t('navigation.toggleTheme')} />
              <LanguageMenu
                variant="icon-only"
                currentLang={currentLang}
                languages={SUPPORTED_LANGUAGES}
                position="top"
                navigationMode="button"
                ariaLabel={t('navigation.selectLanguage')}
              />
            </div>
            <AccountCta
              origin={origin}
              label={t('common.buttons.getStarted')}
              className="nav-cta-btn nav-install-btn"
              ariaLabel={t('common.buttons.getStarted')}
              track={{ event: 'cta_click', label: 'nav-get-started', dest: 'account' }}
            />
            <AccountCta
              origin={origin}
              label={t('navigation.login')}
              className="nav-cta-btn nav-cta-btn--secondary nav-account-btn"
              ariaLabel={t('navigation.login')}
              track={{ event: 'cta_click', label: 'nav-login', dest: 'account' }}
            />
          </div>
        </div>
      </nav>
      <Sidebar isOpen={isSidebarOpen} onClose={closeSidebar} origin={origin} />
      <SearchModal isOpen={isSearchOpen} onClose={closeSearch} />
    </>
  );
};

export default Navigation;
