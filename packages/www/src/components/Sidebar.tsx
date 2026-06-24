import React, { useEffect, useRef, useState } from 'react';
import { CATEGORY_ORDER, SOLUTION_PAGES } from '../config/solution-pages';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import { AccountCta } from './AccountCta';
import { CATEGORY_ICONS } from './CategoryIcons';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  origin?: string;
}

const normalizePath = (value: string): string => {
  const [pathOnly] = value.split('#');
  if (!pathOnly) return '/';
  return pathOnly.length > 1 && pathOnly.endsWith('/') ? pathOnly.slice(0, -1) : pathOnly;
};

const computeIsActive = (href: string, currentPath: string, currentLang: string): boolean => {
  if (!currentPath) return false;
  const normalizedHref = normalizePath(href);
  const normalizedPath = normalizePath(currentPath);
  // Home should only be active on the exact home route.
  if (normalizedHref === `/${currentLang}`) return normalizedPath === normalizedHref;
  // Hash-based links should match exact base path only.
  if (href.includes('#')) return normalizedPath === normalizedHref;
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

const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose, origin }) => {
  const currentLang = useLanguage();
  const { t, to } = useTranslation(currentLang);
  const sidebarRef = useRef<HTMLElement>(null);
  const [currentPath, setCurrentPath] = useState('');
  const [isSolutionsExpanded, setIsSolutionsExpanded] = useState(false);

  const topNavItems = [{ href: `/${currentLang}`, label: t('navigation.home') }];

  const categories = to('solutions.categories') as Record<string, string>;
  const solutionCategories = React.useMemo(() => {
    const slugs = Object.keys(SOLUTION_PAGES);
    return CATEGORY_ORDER.map((cat) => ({
      category: cat,
      label: categories[cat] ?? cat,
      items: slugs
        .filter((slug) => SOLUTION_PAGES[slug].category === cat)
        .map((slug) => {
          const config = SOLUTION_PAGES[slug];
          const content = to(`pages.solutionPages.${config.contentKey}`) as
            | { hero?: { title?: string } }
            | undefined;
          return {
            href: `/${currentLang}/solutions/${slug}`,
            label: content?.hero?.title ?? slug,
          };
        }),
    }));
  }, [categories, currentLang, to]);

  const allSolutionItems = solutionCategories.flatMap((cat) => cat.items);

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
    { href: `/${currentLang}/blog`, label: t('navigation.blog') },
    { href: `/${currentLang}/docs/quick-start`, label: t('navigation.docs') },
    { href: `/${currentLang}/contact`, label: t('navigation.contact') },
  ];

  useEffect(() => {
    requestAnimationFrame(() => {
      const path = window.location.pathname;
      setCurrentPath(path);
      if (path.includes('/solutions/')) {
        setIsSolutionsExpanded(true);
      }
    });
  }, []);

  const isActive = (href: string) => computeIsActive(href, currentPath, currentLang);

  const activeSolutionHref = allSolutionItems.find((item) => isActive(item.href))?.href;

  const toggleSolutions = () => setIsSolutionsExpanded((prev) => !prev);

  useSidebarBodyLock(isOpen, sidebarRef);
  useSidebarKeyboard(isOpen, onClose, sidebarRef);

  const handleLinkClick = () => {
    onClose();
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

          {/* Solutions Accordion */}
          <div className="sidebar-solutions-group">
            <button
              type="button"
              className={`sidebar-solutions-toggle${activeSolutionHref ? ' has-active-child' : ''}`}
              onClick={toggleSolutions}
              aria-expanded={isSolutionsExpanded}
              aria-controls="sidebar-solutions-list"
              tabIndex={isOpen ? 0 : -1}
              data-track="cta_click"
              data-track-label="sidebar-solutions-toggle"
            >
              <span>{t('navigation.solutions')}</span>
              <svg
                className={`sidebar-solutions-chevron${isSolutionsExpanded ? ' expanded' : ''}`}
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
            <ul
              id="sidebar-solutions-list"
              className={`sidebar-solutions-list${isSolutionsExpanded ? ' expanded' : ''}`}
              role="list"
            >
              {solutionCategories.map((group) => (
                <li key={group.label} className="sidebar-category-group">
                  <span className="sidebar-category-label">
                    {React.createElement(CATEGORY_ICONS[group.category], {
                      size: 16,
                      className: 'sidebar-category-icon',
                    })}
                    {group.label}
                  </span>
                  <ul role="list">
                    {group.items.map((item) => (
                      <li key={item.href}>
                        <SidebarNavLink
                          href={item.href}
                          label={item.label}
                          active={isActive(item.href)}
                          tabbable={isOpen && isSolutionsExpanded}
                          onLinkClick={handleLinkClick}
                          className="sidebar-link sidebar-sublink"
                          trackLabel="sidebar-solution"
                        />
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </div>

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
