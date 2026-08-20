import React, { useCallback, useEffect, useRef } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import '../styles/persona-mega-menu.css';
import type { Language } from '../i18n/types';

interface PersonaMegaMenuProps {
  /** Locale from Navigation, which gets it from BaseLayout. Authoritative on the server:
   *  useLanguage() reads window.location and returns 'en' during SSR. */
  lang?: Language;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
}

const TerminalIcon = () => (
  <svg
    width="28"
    height="28"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <polyline points="4 17 10 11 4 5" />
    <line x1="12" y1="19" x2="20" y2="19" />
  </svg>
);

const BuildingIcon = () => (
  <svg
    width="28"
    height="28"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <path d="M9 22V12h6v10" />
    <path d="M8 6h.01M16 6h.01M12 6h.01M8 10h.01M16 10h.01M12 10h.01" />
  </svg>
);

const BriefcaseIcon = () => (
  <svg
    width="28"
    height="28"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <rect x="2" y="7" width="20" height="14" rx="2" />
    <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
    <path d="M2 13h20" />
  </svg>
);

const CpuIcon = () => (
  <svg
    width="28"
    height="28"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <rect x="9" y="9" width="6" height="6" />
    <path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3" />
  </svg>
);

const PERSONA_CARDS = [
  { slug: 'for-devops', titleKey: 'forDevops', personaKey: 'devops', Icon: TerminalIcon },
  { slug: 'for-ctos', titleKey: 'forCtos', personaKey: 'cto', Icon: BuildingIcon },
  { slug: 'for-ceos', titleKey: 'forCeos', personaKey: 'ceo', Icon: BriefcaseIcon },
  { slug: 'for-ai-agents', titleKey: 'forAiAgents', personaKey: 'ai-agent', Icon: CpuIcon },
] as const;

const PersonaMegaMenu: React.FC<PersonaMegaMenuProps> = ({ isOpen, onToggle, onClose, lang }) => {
  const detectedLang = useLanguage();
  const currentLang = lang ?? detectedLang;
  const { t, to } = useTranslation(currentLang);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLAnchorElement | null)[]>([]);

  const personas = to('navigation.personas') as
    | Record<string, { tagline: string; cta: string }>
    | undefined;

  // Dismissal is the browser's job now. The panel is an `auto` popover, so the UA gives us
  // light-dismiss, Esc, top-layer stacking (no z-index race), the ::backdrop that dims the
  // page, and mutual exclusion with the CTA menu, which is also an auto popover.
  //
  // `isOpen` stays the single source of truth because FOUR of Navigation's closes are not
  // dismissals the popover knows anything about: scroll past 80px, opening the sidebar,
  // opening search, and astro:after-swap. Those set React state, so state drives the
  // popover here, and the `toggle` event drives state back when the UA dismisses.
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    // Calling show/hide against the wrong current state throws InvalidStateError.
    const shown = panel.matches(':popover-open');
    if (isOpen && !shown) panel.showPopover();
    else if (!isOpen && shown) panel.hidePopover();
  }, [isOpen]);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const onToggleEvent = (event: Event) => {
      // Light-dismiss and Esc close the popover without telling React.
      if ((event as ToggleEvent).newState === 'closed') onClose();
    };
    panel.addEventListener('toggle', onToggleEvent);
    return () => panel.removeEventListener('toggle', onToggleEvent);
  }, [onClose]);

  // Keyboard navigation. The popover closes ITSELF on Esc, but roving focus across the
  // cards is a menu behaviour the Popover API does not provide, so this listener stays.
  // Deleting it wholesale (which the line count invites) would strip arrow-key navigation
  // from the nav on every page.
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!isOpen) return;
      switch (event.key) {
        case 'Escape':
          // Closing is the UA's; only the focus return is ours, and it must be explicit
          // because this popover is opened by showPopover() rather than by a
          // popovertarget invoker, so there is no invoker for the UA to restore to.
          triggerRef.current?.focus();
          break;
        case 'ArrowDown':
        case 'ArrowRight': {
          event.preventDefault();
          const focused = document.activeElement;
          const currentIdx = cardRefs.current.indexOf(focused as HTMLAnchorElement);
          const nextIdx = currentIdx < PERSONA_CARDS.length - 1 ? currentIdx + 1 : 0;
          cardRefs.current[nextIdx]?.focus();
          break;
        }
        case 'ArrowUp':
        case 'ArrowLeft': {
          event.preventDefault();
          const focused = document.activeElement;
          const currentIdx = cardRefs.current.indexOf(focused as HTMLAnchorElement);
          const prevIdx = currentIdx > 0 ? currentIdx - 1 : PERSONA_CARDS.length - 1;
          cardRefs.current[prevIdx]?.focus();
          break;
        }
        case 'Home':
          event.preventDefault();
          cardRefs.current[0]?.focus();
          break;
        case 'End':
          event.preventDefault();
          cardRefs.current[PERSONA_CARDS.length - 1]?.focus();
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

  // Hover-to-open is GONE, deliberately, and this is a behaviour change rather than a
  // refactor: the menu is now click-only, like claude.com's. The two hover timers carried
  // two bugs that had already been paid for in live waves (a hover-open whose own click
  // slammed it shut, and an orphaned 100ms timer that reopened what a click had closed),
  // and neither bug can exist without the feature. Hover also has no keyboard or touch
  // equivalent, so nothing that hover offered is lost for those users.

  return (
    <div className="persona-menu-wrapper">
      <button
        ref={triggerRef}
        type="button"
        className="nav-link persona-menu-trigger"
        onClick={onToggle}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls="persona-menu-panel"
        data-track="cta_click"
        data-track-label="persona-trigger"
      >
        {t('navigation.builtForYou')}
        <svg
          className={`persona-menu-chevron ${isOpen ? 'open' : ''}`}
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

      {/* Always rendered, unlike the old `isOpen && ...`: an auto popover has to BE in the
          DOM for showPopover() to have anything to show, and the UA hides it with
          `[popover]:not(:popover-open) { display: none }` until then. */}
      <div
        ref={panelRef}
        id="persona-menu-panel"
        className="persona-menu-panel"
        popover="auto"
        role="menu"
        aria-label={t('navigation.builtForYou')}
      >
        <div className="persona-menu-grid">
          {PERSONA_CARDS.map(({ slug, titleKey, personaKey, Icon }, idx) => {
            const persona = personas?.[personaKey];
            return (
              <a
                key={slug}
                ref={(el) => {
                  cardRefs.current[idx] = el;
                }}
                href={`/${currentLang}/${slug}`}
                className="persona-card"
                role="menuitem"
                tabIndex={0}
                onClick={onClose}
                data-track="cta_click"
                data-track-label="persona-card"
                data-track-dest={slug}
              >
                <div className="persona-card-icon">
                  <Icon />
                </div>
                <h3 className="persona-card-title">{t(`navigation.${titleKey}`)}</h3>
                <p className="persona-card-tagline">{persona?.tagline ?? ''}</p>
                <span className="persona-card-cta">
                  {persona?.cta ?? ''}
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d="M3 8h10m0 0L9 4m4 4L9 12"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              </a>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default PersonaMegaMenu;
