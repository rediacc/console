import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import type { SolutionCategory } from '../config/solution-pages';
import { CATEGORY_ORDER, SOLUTION_PAGES } from '../config/solution-pages';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import { CATEGORY_ICONS } from './CategoryIcons';
import '../styles/mega-menu.css';

interface MegaMenuProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
}

const MegaMenu: React.FC<MegaMenuProps> = ({ isOpen, onToggle, onClose }) => {
  const currentLang = useLanguage();
  const { t, to } = useTranslation(currentLang);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const menuItemsRef = useRef<(HTMLAnchorElement | null)[]>([]);
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const categories = to('solutions.categories') as Record<string, string>;

  const solutionCategories = useMemo(() => {
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

  const allItems = useMemo(
    () => solutionCategories.flatMap((cat) => cat.items),
    [solutionCategories]
  );

  // Trim stale refs
  useEffect(() => {
    menuItemsRef.current = menuItemsRef.current.slice(0, allItems.length);
  }, [allItems.length]);

  // Click-outside
  const handleClickOutside = useCallback(
    (event: MouseEvent) => {
      if (
        panelRef.current &&
        !panelRef.current.contains(event.target as Node) &&
        !triggerRef.current?.contains(event.target as Node)
      ) {
        onClose();
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen, handleClickOutside]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!isOpen) return;
      switch (event.key) {
        case 'Escape':
          onClose();
          triggerRef.current?.focus();
          break;
        case 'ArrowDown': {
          event.preventDefault();
          const focused = document.activeElement;
          const currentIdx = menuItemsRef.current.indexOf(focused as HTMLAnchorElement);
          const nextIdx = currentIdx < allItems.length - 1 ? currentIdx + 1 : 0;
          menuItemsRef.current[nextIdx]?.focus();
          break;
        }
        case 'ArrowUp': {
          event.preventDefault();
          const focused = document.activeElement;
          const currentIdx = menuItemsRef.current.indexOf(focused as HTMLAnchorElement);
          const prevIdx = currentIdx > 0 ? currentIdx - 1 : allItems.length - 1;
          menuItemsRef.current[prevIdx]?.focus();
          break;
        }
        case 'Home':
          event.preventDefault();
          menuItemsRef.current[0]?.focus();
          break;
        case 'End':
          event.preventDefault();
          menuItemsRef.current[allItems.length - 1]?.focus();
          break;
      }
    },
    [isOpen, allItems.length, onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  // Hover intent
  const clearHoverTimeout = () => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
  };

  const handleMouseEnter = () => {
    clearHoverTimeout();
    if (!isOpen) {
      hoverTimeoutRef.current = setTimeout(onToggle, 100);
    }
  };

  const handleMouseLeave = () => {
    clearHoverTimeout();
    if (isOpen) {
      hoverTimeoutRef.current = setTimeout(onClose, 150);
    }
  };

  useEffect(() => {
    return () => clearHoverTimeout();
  }, []);

  // Build flat ref index
  let flatIndex = 0;

  return (
    <div
      className="mega-menu-wrapper"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        ref={triggerRef}
        type="button"
        className="nav-link mega-menu-trigger"
        onClick={onToggle}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls="mega-menu-panel"
      >
        {t('navigation.solutions')}
        <svg
          className={`mega-menu-chevron ${isOpen ? 'open' : ''}`}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          aria-hidden="true"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <div
          ref={panelRef}
          id="mega-menu-panel"
          className="mega-menu-panel"
          role="menu"
          aria-label={t('navigation.solutionsMegaMenu')}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          <div className="mega-menu-grid">
            {solutionCategories.map((group) => (
              <div
                key={group.category}
                className="mega-menu-category"
                role="group"
                aria-label={group.label}
              >
                <span className="mega-menu-category-label">
                  {React.createElement(CATEGORY_ICONS[group.category as SolutionCategory], {
                    size: 16,
                    className: 'mega-menu-category-icon',
                  })}
                  {group.label}
                </span>
                <ul className="mega-menu-items">
                  {group.items.map((item) => {
                    const idx = flatIndex++;
                    return (
                      <li key={item.href}>
                        <a
                          ref={(el) => {
                            menuItemsRef.current[idx] = el;
                          }}
                          href={item.href}
                          className="mega-menu-item"
                          role="menuitem"
                          tabIndex={0}
                          onClick={onClose}
                        >
                          {item.label}
                        </a>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
          <div className="mega-menu-footer">
            <a href={`/${currentLang}/#solutions`} className="mega-menu-view-all" onClick={onClose}>
              {t('navigation.viewAllSolutions')}
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path
                  d="M6 12l4-4-4-4"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </a>
          </div>
        </div>
      )}
    </div>
  );
};

export default MegaMenu;
