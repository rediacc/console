import React, { useEffect, useRef, useState } from 'react';
import { SOLUTION_PAGES, type SolutionCategory } from '../config/solution-pages';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const CATEGORY_ORDER = [
  'ransomware',
  'multi-cloud',
  'backups',
  'encryption',
  'dev-env',
  'defense',
] as const satisfies readonly SolutionCategory[];

const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const currentLang = useLanguage();
  const { t, to } = useTranslation(currentLang);
  const sidebarRef = useRef<HTMLElement>(null);
  const [currentPath, setCurrentPath] = useState('');
  const [isSolutionsExpanded, setIsSolutionsExpanded] = useState(false);

  const topNavItems = [{ href: `/${currentLang}/`, label: t('navigation.home') }];

  const categories = to('solutions.categories') as Record<string, string>;
  const solutionCategories = React.useMemo(() => {
    const slugs = Object.keys(SOLUTION_PAGES);
    return CATEGORY_ORDER.map((cat) => ({
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

  const bottomNavItems = [
    { href: `/${currentLang}/#pricing`, label: t('navigation.pricing') },
    { href: `/${currentLang}/disaster-recovery`, label: t('navigation.disasterRecovery') },
    { href: `/${currentLang}/install`, label: t('navigation.install') },
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

  const normalizePath = (value: string) => {
    const [pathOnly] = value.split('#');
    if (!pathOnly) return '/';
    return pathOnly.length > 1 && pathOnly.endsWith('/') ? pathOnly.slice(0, -1) : pathOnly;
  };

  const isActive = (href: string) => {
    if (!currentPath) return false;

    const normalizedHref = normalizePath(href);
    const normalizedPath = normalizePath(currentPath);

    // Home should only be active on the exact home route.
    if (normalizedHref === `/${currentLang}`) {
      return normalizedPath === normalizedHref;
    }

    // Hash-based links should match exact base path only.
    if (href.includes('#')) {
      return normalizedPath === normalizedHref;
    }

    // Mark parent sections active on nested routes, e.g. /en/docs/* keeps Docs active.
    return normalizedPath === normalizedHref || normalizedPath.startsWith(`${normalizedHref}/`);
  };

  const activeSolutionHref = allSolutionItems.find((item) => isActive(item.href))?.href;

  const toggleSolutions = () => setIsSolutionsExpanded((prev) => !prev);

  useEffect(() => {
    if (isOpen) {
      document.body.classList.add('sidebar-active');
      document.body.style.overflow = 'hidden';
      // Focus the first link when sidebar opens
      const firstLink = sidebarRef.current?.querySelector<HTMLAnchorElement>('.sidebar-link');
      firstLink?.focus();
    } else {
      document.body.classList.remove('sidebar-active');
      document.body.style.overflow = '';
    }

    return () => {
      document.body.classList.remove('sidebar-active');
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      // Focus trap
      if (e.key === 'Tab' && sidebarRef.current) {
        const focusableElements = sidebarRef.current.querySelectorAll<HTMLElement>(
          'a[href], button, [tabindex]:not([tabindex="-1"])'
        );
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
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

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
        <nav className="sidebar-nav">
          {/* Home */}
          {topNavItems.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className={`sidebar-link${isActive(item.href) ? ' active' : ''}`}
              onClick={handleLinkClick}
              tabIndex={isOpen ? 0 : -1}
              aria-current={isActive(item.href) ? 'page' : undefined}
            >
              {item.label}
            </a>
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
                  <span className="sidebar-category-label">{group.label}</span>
                  <ul role="list">
                    {group.items.map((item) => {
                      const active = isActive(item.href);
                      return (
                        <li key={item.href}>
                          <a
                            href={item.href}
                            className={`sidebar-link sidebar-sublink${active ? ' active' : ''}`}
                            onClick={handleLinkClick}
                            tabIndex={isOpen && isSolutionsExpanded ? 0 : -1}
                            aria-current={active ? 'page' : undefined}
                          >
                            {item.label}
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          </div>

          {/* Blog, Docs, Contact */}
          {bottomNavItems.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className={`sidebar-link${isActive(item.href) ? ' active' : ''}`}
              onClick={handleLinkClick}
              tabIndex={isOpen ? 0 : -1}
              aria-current={isActive(item.href) ? 'page' : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </aside>
    </>
  );
};

export default Sidebar;
