import React, { useCallback, useEffect, useRef } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import '../styles/persona-mega-menu.css';

interface PersonaMegaMenuProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
}

const TerminalIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="4 17 10 11 4 5" />
    <line x1="12" y1="19" x2="20" y2="19" />
  </svg>
);

const BuildingIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <path d="M9 22V12h6v10" />
    <path d="M8 6h.01M16 6h.01M12 6h.01M8 10h.01M16 10h.01M12 10h.01" />
  </svg>
);

const BriefcaseIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="2" y="7" width="20" height="14" rx="2" />
    <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
    <path d="M2 13h20" />
  </svg>
);

const PERSONA_CARDS = [
  { slug: 'for-devops', titleKey: 'forDevops', personaKey: 'devops', Icon: TerminalIcon },
  { slug: 'for-ctos', titleKey: 'forCtos', personaKey: 'cto', Icon: BuildingIcon },
  { slug: 'for-ceos', titleKey: 'forCeos', personaKey: 'ceo', Icon: BriefcaseIcon },
] as const;

const PersonaMegaMenu: React.FC<PersonaMegaMenuProps> = ({ isOpen, onToggle, onClose }) => {
  const currentLang = useLanguage();
  const { t, to } = useTranslation(currentLang);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const personas = to('navigation.personas') as Record<string, { tagline: string; cta: string }> | undefined;

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
    [onClose],
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
    [isOpen, onClose],
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

  return (
    <div
      className="persona-menu-wrapper"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        ref={triggerRef}
        type="button"
        className="nav-link persona-menu-trigger"
        onClick={onToggle}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls="persona-menu-panel"
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

      {isOpen && (
        <div
          ref={panelRef}
          id="persona-menu-panel"
          className="persona-menu-panel"
          role="menu"
          aria-label={t('navigation.builtForYou')}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          <div className="persona-menu-grid">
            {PERSONA_CARDS.map(({ slug, titleKey, personaKey, Icon }, idx) => {
              const persona = personas?.[personaKey];
              return (
                <a
                  key={slug}
                  ref={(el) => { cardRefs.current[idx] = el; }}
                  href={`/${currentLang}/${slug}`}
                  className="persona-card"
                  role="menuitem"
                  tabIndex={0}
                  onClick={onClose}
                >
                  <div className="persona-card-icon">
                    <Icon />
                  </div>
                  <h3 className="persona-card-title">{t(`navigation.${titleKey}`)}</h3>
                  <p className="persona-card-tagline">{persona?.tagline ?? ''}</p>
                  <span className="persona-card-cta">
                    {persona?.cta ?? ''}
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <path d="M3 8h10m0 0L9 4m4 4L9 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                </a>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default PersonaMegaMenu;
