import React, { useEffect, useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import { AccountCta } from './AccountCta';
import type { Language } from '../i18n/types';

interface SidebarProps {
  /** Locale from Navigation; authoritative on the server, where useLanguage() returns 'en'. */
  lang?: Language;
  isOpen: boolean;
  onClose: () => void;
  origin?: string;
  onSearch: () => void;
}

const normalizePath = (value: string): string => {
  const [pathOnly] = value.split('#');
  if (!pathOnly) return '/';
  return pathOnly.length > 1 && pathOnly.endsWith('/') ? pathOnly.slice(0, -1) : pathOnly;
};

const computeIsActive = (
  href: string,
  currentPath: string,
  currentHash: string,
  currentLang: string
): boolean => {
  if (!currentPath) return false;
  const normalizedHref = normalizePath(href);
  const normalizedPath = normalizePath(currentPath);
  // A hash link is active only when the FRAGMENT matches too. Path alone was
  // enough while every hash link pointed at a page of its own; once Solutions
  // became `/<lang>#solutions` it shares a path with Home, and a path-only test
  // put aria-current="page" on two rows of the same drawer at once.
  if (href.includes('#')) {
    const hash = href.slice(href.indexOf('#'));
    return normalizedPath === normalizedHref && currentHash === hash;
  }
  // Home should only be active on the exact home route.
  if (normalizedHref === `/${currentLang}`) return normalizedPath === normalizedHref;
  // Mark parent sections active on nested routes, e.g. /en/docs/* keeps Docs active.
  return normalizedPath === normalizedHref || normalizedPath.startsWith(`${normalizedHref}/`);
};

const FOCUSABLE_SELECTOR =
  'a[href]:not([tabindex="-1"]), button:not([tabindex="-1"]), [tabindex]:not([tabindex="-1"])';

const handleFocusTrap = (e: KeyboardEvent, sidebar: HTMLElement): void => {
  const focusableElements = sidebar.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
  if (focusableElements.length === 0) return;
  const firstEl = focusableElements[0];
  const lastEl = focusableElements[focusableElements.length - 1];
  if (e.shiftKey && document.activeElement === firstEl) {
    e.preventDefault();
    lastEl.focus();
  } else if (!e.shiftKey && document.activeElement === lastEl) {
    e.preventDefault();
    firstEl.focus();
  }
};

/** Lock body scroll while the sidebar is open and focus the first link on open. */
const useSidebarBodyLock = (isOpen: boolean, sidebarRef: React.RefObject<HTMLElement | null>) => {
  useEffect(() => {
    if (isOpen) {
      document.body.classList.add('sidebar-active');
      document.body.style.overflow = 'hidden';
      window.plausible?.('sidebar_toggle', { props: { action: 'open' } });
      // Focus the first interactive element in the visual order — usually the
      // Account CTA at the top of the sidebar, not the first .sidebar-link.
      const firstTabbable = sidebarRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      firstTabbable?.focus();
    } else {
      document.body.classList.remove('sidebar-active');
      document.body.style.overflow = '';
    }
    return () => {
      document.body.classList.remove('sidebar-active');
      document.body.style.overflow = '';
    };
  }, [isOpen, sidebarRef]);
};

/** Wire up Escape-to-close and Tab focus trapping while the sidebar is open. */
const useSidebarKeyboard = (
  isOpen: boolean,
  onClose: () => void,
  sidebarRef: React.RefObject<HTMLElement | null>
) => {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key === 'Tab' && sidebarRef.current) {
        handleFocusTrap(e, sidebarRef.current);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, sidebarRef]);
};

interface SidebarNavLinkProps {
  href: string;
  label: string;
  active: boolean;
  tabbable: boolean;
  onLinkClick: () => void;
  className?: string;
  trackLabel: string;
}

/** A single nav link with active/aria/tabIndex/data-track wired up. */
const SidebarNavLink: React.FC<SidebarNavLinkProps> = ({
  href,
  label,
  active,
  tabbable,
  onLinkClick,
  className = 'sidebar-link',
  trackLabel,
}) => (
  <a
    href={href}
    className={`${className}${active ? ' active' : ''}`}
    onClick={onLinkClick}
    tabIndex={tabbable ? 0 : -1}
    aria-current={active ? 'page' : undefined}
    data-track="cta_click"
    data-track-label={trackLabel}
  >
    {label}
  </a>
);

const Sidebar: React.FC<SidebarProps> = ({ lang, isOpen, onClose, origin, onSearch }) => {
  const detectedLang = useLanguage();
  const currentLang = lang ?? detectedLang;
  const { t } = useTranslation(currentLang);
  const sidebarRef = useRef<HTMLElement>(null);
  const [currentPath, setCurrentPath] = useState('');
  const [currentHash, setCurrentHash] = useState('');

  // The solutions accordion (6 category groups x 21 titles) is gone: the
  // constellation is the one browse surface, so the sidebar links to it like
  // any other top-level destination. It moved onto the homepage under
  // `#solutions` when the `/[lang]/solutions` index route was deleted.
  const topNavItems = [
    { href: `/${currentLang}`, label: t('navigation.home') },
    { href: `/${currentLang}#solutions`, label: t('navigation.solutions') },
  ];

  const personaItems = [
    { href: `/${currentLang}/for-devops`, label: t('navigation.forDevops') },
    { href: `/${currentLang}/for-ctos`, label: t('navigation.forCtos') },
    { href: `/${currentLang}/for-ceos`, label: t('navigation.forCeos') },
    { href: `/${currentLang}/for-ai-agents`, label: t('navigation.forAiAgents') },
  ];

  const bottomNavItems = [
    { href: `/${currentLang}/pricing`, label: t('navigation.pricing') },
    { href: `/${currentLang}/roi-calculator`, label: t('navigation.roiCalculator') },
    { href: `/${currentLang}/disaster-recovery`, label: t('navigation.disasterRecovery') },
    { href: `/${currentLang}/partners`, label: t('navigation.partners') },
    { href: `/${currentLang}/blog`, label: t('navigation.blog') },
    { href: `/${currentLang}/docs/quick-start`, label: t('navigation.docs') },
    { href: `/${currentLang}/contact`, label: t('navigation.contact') },
  ];

  useEffect(() => {
    requestAnimationFrame(() => {
      setCurrentPath(window.location.pathname);
      setCurrentHash(window.location.hash);
    });
  }, []);

  const isActive = (href: string) => computeIsActive(href, currentPath, currentHash, currentLang);

  useSidebarBodyLock(isOpen, sidebarRef);
  useSidebarKeyboard(isOpen, onClose, sidebarRef);

  const handleLinkClick = () => {
    onClose();
  };

  // Search lives in the header's split-button menu, and that whole control is
  // `display: none` below 30rem (main.css, the .nav-cta-split block), so on the
  // narrowest phones this drawer is the ONLY way to reach it. The label reuses
  // navigation.search, already in the client catalog: a second key for the same
  // word in thirteen locales would be the cost of not looking.
  const handleSearchClick = () => {
    onClose();
    onSearch();
  };

  return (
    <>
      {/* Backdrop overlay */}
      <div
        className={`sidebar-overlay ${isOpen ? 'sidebar-overlay-visible' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Sidebar */}
      <aside
        ref={sidebarRef}
        id="navigation-sidebar"
        className={`sidebar ${isOpen ? 'sidebar-open' : ''}`}
        role="navigation"
        aria-label={t('common.aria.mainNavigation')}
        aria-hidden={!isOpen}
      >
        <div className="sidebar-header">
          <button
            type="button"
            className="sidebar-close-btn"
            onClick={onClose}
            tabIndex={isOpen ? 0 : -1}
            aria-label={t('common.buttons.close')}
            data-track="cta_click"
            data-track-label="sidebar-close"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <nav className="sidebar-nav">
          {/* Get Started (primary) above Account (secondary). */}
          <AccountCta
            origin={origin}
            label={t('common.buttons.getStarted')}
            className="sidebar-account-cta"
            ariaLabel={t('common.buttons.getStarted')}
            tabIndex={isOpen ? 0 : -1}
            track={{ event: 'cta_click', label: 'sidebar-get-started', dest: 'account' }}
            onClick={onClose}
          />
          <AccountCta
            origin={origin}
            label={t('navigation.login')}
            className="sidebar-account-cta sidebar-account-cta--secondary"
            ariaLabel={t('navigation.login')}
            tabIndex={isOpen ? 0 : -1}
            track={{ event: 'cta_click', label: 'sidebar-login', dest: 'account' }}
            onClick={onClose}
          />
          <button
            type="button"
            className="sidebar-link sidebar-search-btn"
            onClick={handleSearchClick}
            tabIndex={isOpen ? 0 : -1}
            data-track="cta_click"
            data-track-label="sidebar-search"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 20 20"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" />
              <path
                d="M12.5 12.5L17 17"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
            {t('navigation.search')}
          </button>
          {/* Home */}
          {topNavItems.map((item) => (
            <SidebarNavLink
              key={item.href}
              href={item.href}
              label={item.label}
              active={isActive(item.href)}
              tabbable={isOpen}
              onLinkClick={handleLinkClick}
              trackLabel="sidebar-nav"
            />
          ))}

          {/* Persona links */}
          <div className="sidebar-personas-group">
            <span className="sidebar-personas-label">{t('navigation.builtForYourRole')}</span>
            {personaItems.map((item) => (
              <SidebarNavLink
                key={item.href}
                href={item.href}
                label={item.label}
                active={isActive(item.href)}
                tabbable={isOpen}
                onLinkClick={handleLinkClick}
                className="sidebar-link sidebar-persona-link"
                trackLabel="sidebar-persona"
              />
            ))}
          </div>

          {/* Blog, Docs, Contact */}
          {bottomNavItems.map((item) => (
            <SidebarNavLink
              key={item.href}
              href={item.href}
              label={item.label}
              active={isActive(item.href)}
              tabbable={isOpen}
              onLinkClick={handleLinkClick}
              trackLabel="sidebar-nav"
            />
          ))}
        </nav>
      </aside>
    </>
  );
};

export default Sidebar;
