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
 * The popover contract is `PersonaMegaMenu`'s, deliberately, down to the
 * `hoverOpenedRef` guard: click-outside, Escape restores focus to the trigger,
 * roving arrows/Home/End, and `aria-haspopup`/`aria-expanded`/`aria-controls`.
 * Open state is LIFTED into `Navigation` for the same reason the persona menu
 * lifts it - that is what puts this menu under the existing close-on-scroll,
 * close-on-hamburger and `astro:after-swap` handlers instead of giving it three
 * more of its own.
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
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
      const focused = document.activeElement as HTMLElement | null;
      const currentIdx = itemRefs.current.indexOf(focused);
      switch (event.key) {
        case 'Escape':
          onClose();
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

  // Hover intent on the caret segment only. `hoverOpenedRef` marks an open that
  // hover initiated so the first CLICK after it pins the menu instead of
  // slamming it shut. Hover never covers the primary segment: a pointer on its
  // way to `Get Started` must not be answered with a menu.
  const clearHoverTimeout = () => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
  };

  const hoverOpenedRef = useRef(false);

  const handleMouseEnter = () => {
    clearHoverTimeout();
    if (!isOpen) {
      hoverTimeoutRef.current = setTimeout(() => {
        hoverOpenedRef.current = true;
        onToggle();
      }, 100);
    }
  };

  const handleTriggerClick = () => {
    // Cancel any hover-open still in flight. Without this a click that lands
    // inside the 100ms hover delay opens the menu and the timer then fires and
    // toggles it straight back shut: the pointer moves onto the caret, the timer
    // starts, the click opens, 100ms later the timeout still sees the isOpen it
    // captured (false) and calls onToggle() a second time. It is deterministic
    // under automation and merely intermittent for a fast human, which is the
    // worst combination to leave in.
    clearHoverTimeout();
    if (isOpen && hoverOpenedRef.current) {
      hoverOpenedRef.current = false;
      return;
    }
    hoverOpenedRef.current = false;
    onToggle();
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

  const handleSearchClick = () => {
    onClose();
    onSearch();
  };

  return (
    <div className="nav-cta-split" onMouseLeave={handleMouseLeave}>
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
        onClick={handleTriggerClick}
        onMouseEnter={handleMouseEnter}
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

      {isOpen && (
        <div
          ref={panelRef}
          id="nav-cta-menu"
          className="nav-cta-menu"
          role="menu"
          aria-labelledby={TRIGGER_ID}
          onMouseEnter={clearHoverTimeout}
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
      )}
    </div>
  );
};

export default NavCtaMenu;
