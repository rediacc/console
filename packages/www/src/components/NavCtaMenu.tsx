import React, { useCallback, useEffect, useRef } from 'react';
import { AccountCta } from './AccountCta';

/**
 * The header's one call to action: a split button. `Get Started` is the wide
 * segment, an attached caret segment opens a small menu holding `Log in` and
 * `Search`.
 *
 * It replaces two side-by-side `AccountCta` mounts. The pair asked the visitor
 * to choose between two account destinations before the page had said anything,
 * and the secondary one carried the same brand outline as the primary, so the
 * header opened with two competing greens.
 *
 * The popover contract is `PersonaMegaMenu`'s, deliberately: both are now NATIVE
 * `popover="auto"` panels, so the UA supplies light-dismiss, Escape, top-layer
 * stacking, the dimming `::backdrop`, and mutual exclusion between the two menus.
 * What stays hand-written is what the Popover API does not provide: roving
 * arrows/Home/End, the focus return to the trigger on Escape, and
 * `aria-haspopup`/`aria-expanded`/`aria-controls`.
 * Open state is LIFTED into `Navigation` for the same reason the persona menu
 * lifts it - that is what puts this menu under the existing close-on-scroll,
 * close-on-hamburger and `astro:after-swap` handlers instead of giving it three
 * more of its own. Those four closes are precisely why the popover cannot own the
 * state outright: none of them is a dismissal the popover can see.
 *
 * `Log in` stays an `AccountCta`, so the region-picker interception in that
 * component (`window.openRegionPicker`) is reached by exactly the same path it
 * was before. Rebuilding the link here would have quietly dropped it.
 *
 * The PANEL carries no label of its own. Per the ARIA menu-button pattern it
 * takes its accessible name from its trigger through `aria-labelledby`, which
 * means one string instead of two across thirteen locales, no second string to
 * drift out of sync, and no need to invent a name for a menu that holds Log in
 * AND Search - "account menu" would have been wrong about half its contents.
 */
interface NavCtaMenuProps {
  origin?: string;
  /** Label of the wide primary segment. */
  getStartedLabel: string;
  loginLabel: string;
  searchLabel: string;
  /** Accessible name for the caret segment. The panel inherits it. */
  menuLabel: string;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  onSearch: () => void;
}

const MENU_ITEM_COUNT = 2;

/** The panel points at this with aria-labelledby, so it must be stable. */
const TRIGGER_ID = 'nav-cta-caret';

const NavCtaMenu: React.FC<NavCtaMenuProps> = ({
  origin,
  getStartedLabel,
  loginLabel,
  searchLabel,
  menuLabel,
  isOpen,
  onToggle,
  onClose,
  onSearch,
}) => {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLElement | null)[]>([]);

  // Dismissal is the UA's, exactly as in PersonaMegaMenu: light-dismiss, Esc, top layer,
  // the dimming ::backdrop, and mutual exclusion with the persona menu, which is the other
  // auto popover. `isOpen` remains the source of truth because Navigation closes both menus
  // on scroll, sidebar, search and astro:after-swap, none of which the popover can see.
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const shown = panel.matches(':popover-open');
    if (isOpen && !shown) panel.showPopover();
    else if (!isOpen && shown) panel.hidePopover();
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

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!isOpen) return;
      const focused = document.activeElement as HTMLElement | null;
      const currentIdx = itemRefs.current.indexOf(focused);
      switch (event.key) {
        case 'Escape':
          // The UA closes the popover; only the focus return is ours, because a popover
          // opened via showPopover() has no invoker for the UA to restore focus to.
          triggerRef.current?.focus();
          break;
        case 'ArrowDown':
        case 'ArrowRight': {
          event.preventDefault();
          const nextIdx = currentIdx < MENU_ITEM_COUNT - 1 ? currentIdx + 1 : 0;
          itemRefs.current[nextIdx]?.focus();
          break;
        }
        case 'ArrowUp':
        case 'ArrowLeft': {
          event.preventDefault();
          const prevIdx = currentIdx > 0 ? currentIdx - 1 : MENU_ITEM_COUNT - 1;
          itemRefs.current[prevIdx]?.focus();
          break;
        }
        case 'Home':
          event.preventDefault();
          itemRefs.current[0]?.focus();
          break;
        case 'End':
          event.preventDefault();
          itemRefs.current[MENU_ITEM_COUNT - 1]?.focus();
          break;
      }
    },
    [isOpen, onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  // Hover-to-open is gone here too, for the same reason as in PersonaMegaMenu: the two
  // timers existed only to serve hover, and both carried bugs that had already been paid
  // for. Click-only also removes the special case this menu needed on top of the persona
  // one, where hover had to cover the caret segment but NOT the primary `Get Started`
  // button, so a pointer travelling to the CTA was not answered with a menu.

  const handleSearchClick = () => {
    onClose();
    onSearch();
  };

  return (
    <div className="nav-cta-split">
      <AccountCta
        origin={origin}
        label={getStartedLabel}
        className="nav-cta-btn nav-install-btn"
        ariaLabel={getStartedLabel}
        track={{ event: 'cta_click', label: 'nav-get-started', dest: 'account' }}
      />
      <button
        ref={triggerRef}
        id={TRIGGER_ID}
        type="button"
        className="nav-cta-btn nav-cta-caret"
        onClick={onToggle}
        aria-label={menuLabel}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls="nav-cta-menu"
        data-track="cta_click"
        data-track-label="nav-cta-caret"
      >
        <svg
          className={`nav-cta-chevron ${isOpen ? 'open' : ''}`}
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
        id="nav-cta-menu"
        className="nav-cta-menu"
        popover="auto"
        role="menu"
        aria-labelledby={TRIGGER_ID}
      >
        <AccountCta
          origin={origin}
          label={loginLabel}
          className="nav-cta-menu-item nav-account-btn"
          ariaLabel={loginLabel}
          role="menuitem"
          elementRef={(el) => {
            itemRefs.current[0] = el;
          }}
          onClick={onClose}
          track={{ event: 'cta_click', label: 'nav-login', dest: 'account' }}
        />
        <button
          ref={(el) => {
            itemRefs.current[1] = el;
          }}
          type="button"
          className="nav-cta-menu-item"
          role="menuitem"
          onClick={handleSearchClick}
          data-track="cta_click"
          data-track-label="nav-cta-search"
        >
          <svg
            width="16"
            height="16"
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
          {searchLabel}
        </button>
      </div>
    </div>
  );
};

export default NavCtaMenu;
