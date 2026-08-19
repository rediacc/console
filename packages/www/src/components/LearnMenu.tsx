import React, { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from '../i18n/react';
import { CATEGORY_ORDER, CATEGORY_KEYS } from '../utils/docs-categories';
import '../styles/learn-menu.css';
import type { Language } from '../i18n/types';

/**
 * The header's `Learn` menu: the six docs categories, then `Browse all docs`.
 *
 * It replaces a bare `Docs` link that pointed at `/docs/quick-start`, i.e. straight past
 * the index into one article. Every entry here deep-links into the browse page's category
 * filter via `?category=`, which is why that page had to grow URL state first: without it
 * all seven entries would have landed on the same unfiltered list.
 *
 * The popover contract is `PersonaMegaMenu`'s and `NavCtaMenu`'s, deliberately the same
 * one: a native `popover="auto"` panel, so the UA supplies light-dismiss, Escape, top-layer
 * stacking, the dimming `::backdrop`, and mutual exclusion with the other two menus. What
 * stays hand-written is only what the Popover API does not provide: roving arrow/Home/End
 * focus, and the focus return to the trigger on Escape.
 *
 * Open state is LIFTED into `Navigation` for the same reason its siblings lift it: that is
 * what puts this menu under the existing close-on-scroll, close-on-sidebar, close-on-search
 * and `astro:after-swap` handlers, none of which is a dismissal a popover can see.
 *
 * Category identifiers are English in every locale (see utils/docs-categories); only their
 * LABELS are translated. A translated identifier in a query string would filter nothing.
 */
interface LearnMenuProps {
  lang: Language;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
}

const PANEL_ID = 'learn-menu-panel';
const TRIGGER_ID = 'learn-menu-trigger';

const LearnMenu: React.FC<LearnMenuProps> = ({ lang, isOpen, onToggle, onClose }) => {
  const { t } = useTranslation(lang);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);

  const entries = [
    ...CATEGORY_ORDER.map((category) => ({
      key: category as string,
      label: t(CATEGORY_KEYS[category]),
      href: `/${lang}/docs?category=${encodeURIComponent(category)}`,
    })),
    {
      key: 'all',
      label: t('navigation.browseAllDocs'),
      href: `/${lang}/docs`,
    },
  ];

  // State drives the popover; the UA's own dismissals drive state back.
  //
  // The inline `left` is NOT laziness about CSS. A popover renders in the top layer, whose
  // containing block is the VIEWPORT, so the panel does not inherit its wrapper's position
  // and a purely declarative rule cannot know where the trigger sits. Measured before this
  // existed: panel at left 0 with its trigger at left 855. The same mistake had already
  // been made twice in this header, so it is measured from the trigger at open time and
  // clamped to the viewport so a narrow window cannot push it off-screen.
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const shown = panel.matches(':popover-open');
    if (isOpen && !shown) {
      const trigger = triggerRef.current;
      if (trigger) {
        const rect = trigger.getBoundingClientRect();
        panel.style.left = '0px'; // measure the panel's own width unpositioned first
        const width = panel.offsetWidth || 224;
        const maxLeft = Math.max(8, document.documentElement.clientWidth - width - 8);
        panel.style.left = `${Math.round(Math.min(Math.max(8, rect.left), maxLeft))}px`;
      }
      panel.showPopover();
    } else if (!isOpen && shown) {
      panel.hidePopover();
    }
  }, [isOpen]);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const onToggleEvent = (event: Event) => {
      if ((event as ToggleEvent).newState === 'closed') onClose();
    };
    panel.addEventListener('toggle', onToggleEvent);
    return () => panel.removeEventListener('toggle', onToggleEvent);
  }, [onClose]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!isOpen) return;
      const count = itemRefs.current.length;
      const current = itemRefs.current.indexOf(document.activeElement as HTMLAnchorElement);
      switch (event.key) {
        case 'Escape':
          // The UA closes it; the focus return is ours, because a popover opened via
          // showPopover() has no invoker for the UA to restore focus to.
          triggerRef.current?.focus();
          break;
        case 'ArrowDown':
        case 'ArrowRight':
          event.preventDefault();
          itemRefs.current[current < count - 1 ? current + 1 : 0]?.focus();
          break;
        case 'ArrowUp':
        case 'ArrowLeft':
          event.preventDefault();
          itemRefs.current[current > 0 ? current - 1 : count - 1]?.focus();
          break;
        case 'Home':
          event.preventDefault();
          itemRefs.current[0]?.focus();
          break;
        case 'End':
          event.preventDefault();
          itemRefs.current[count - 1]?.focus();
          break;
      }
    },
    [isOpen]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  return (
    <div className="learn-menu-wrapper">
      <button
        ref={triggerRef}
        id={TRIGGER_ID}
        type="button"
        className="nav-link learn-menu-trigger"
        onClick={onToggle}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={PANEL_ID}
        data-track="cta_click"
        data-track-label="learn-trigger"
      >
        {t('navigation.learn')}
        <svg
          className={`learn-menu-chevron ${isOpen ? 'open' : ''}`}
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

      {/* Always in the DOM: an auto popover must exist for showPopover() to reveal it. */}
      <div
        ref={panelRef}
        id={PANEL_ID}
        className="learn-menu-panel"
        popover="auto"
        role="menu"
        aria-labelledby={TRIGGER_ID}
      >
        {entries.map((entry, idx) => (
          <a
            key={entry.key}
            ref={(el) => {
              itemRefs.current[idx] = el;
            }}
            href={entry.href}
            className={`learn-menu-item${entry.key === 'all' ? ' learn-menu-item-all' : ''}`}
            role="menuitem"
            onClick={onClose}
            data-track="cta_click"
            data-track-label="learn-item"
            data-track-dest={entry.key}
          >
            {entry.label}
          </a>
        ))}
      </div>
    </div>
  );
};

export default LearnMenu;
