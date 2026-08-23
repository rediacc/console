import React, { useEffect, useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { SUPPORTED_LANGUAGES } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import LanguageMenu from './LanguageMenu';
import LearnMenu from './LearnMenu';
import NavCtaMenu from './NavCtaMenu';
import PersonaMegaMenu from './PersonaMegaMenu';
import SearchModal from './SearchModal';
import Sidebar from './Sidebar';
import type { Language } from '../i18n/types';

interface NavigationProps {
  /** Locale from BaseLayout; authoritative on the server. See the note above. */
  lang?: Language;
  origin?: string;
}

/**
 * `lang` is passed by BaseLayout and is AUTHORITATIVE on the server.
 *
 * `useLanguage()` reads `window.location.pathname`, and there is no `window` during SSR,
 * so it returns 'en' for every locale. That made this island server-render English on all
 * twelve non-English locales: crawlers and no-JS visitors saw an English nav, and everyone
 * else got a flash of English until hydration corrected it. Astro knows the locale, so it
 * hands it down; the hook stays as the fallback for any mount that does not.
 */
const Navigation: React.FC<NavigationProps> = ({ lang, origin }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isPersonaMenuOpen, setIsPersonaMenuOpen] = useState(false);
  const [isCtaMenuOpen, setIsCtaMenuOpen] = useState(false);
  const [isLearnMenuOpen, setIsLearnMenuOpen] = useState(false);
  // Where-you-are trail for the condensed bar. Server-rendered EMPTY on
  // purpose: it is invisible until the visitor scrolls, which cannot happen
  // before hydration, so deriving it client-side costs nothing and keeps the
  // SSR HTML free of a second locale-sensitive surface.
  const [trail, setTrail] = useState<Array<{ href: string; label: string }>>([]);
  const wordmarkRef = useRef<HTMLSpanElement>(null);
  const detectedLang = useLanguage();
  const currentLang = lang ?? detectedLang;
  const { t } = useTranslation(currentLang);

  // Drives `.nav-translate` groups: center nav + utility cluster slide up and
  // fade out 1:1 with the first 80px of scroll, then clamp. The icon and CTA
  // stay, and the breadcrumb cross-fades in, so the collapsed nav is a slim
  // context bar (mark, where-you-are, search, CTA) rather than an empty strip.
  // The WORDMARK fades and collapses on the same 80px range, so the brand is
  // still present at the top of a scrolled page without spending width on a
  // word the visitor has already read.
  // Opacity is paired with translate because the items would otherwise hide
  // behind the higher-z announcement banner mid-slide and look abrupt.
  // body[data-nav-collapsed] suppresses pointer events on faded items so they
  // don't intercept clicks meant for the page below.
  //
  // SCROLLING UP BRINGS THE FULL NAV BACK at any depth: any deliberate upward
  // motion (>2px, to filter scroll jitter) restores it, any downward motion
  // condenses it again. Near the top the fade stays position-linked so it
  // tracks the first 80px 1:1 like it always has.
  //
  // ONE listener, deliberately. Everything scroll-linked in this header goes
  // through this handler; a second listener would double the work per frame and
  // let the two states disagree mid-scroll. The direction detection lives in
  // the same handler and the same rAF for the same reason.
  //
  // The wordmark's natural width is REMEASURED at scrollY 0 rather than baked
  // into the stylesheet: `.nav-wordmark` steps down a font size below 48rem, so
  // a literal would be wrong on phones, and `scrollWidth` reports the content
  // width even while the box is clamped, which makes the reading self-correcting
  // instead of needing a resize listener.
  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    let frame = 0;
    let measured = 0;
    let lastY = window.scrollY;
    let returned = false; // full nav re-shown by an upward scroll while deep
    const update = () => {
      frame = 0;
      const rawY = window.scrollY;
      const dy = rawY - lastY;
      lastY = rawY;
      if (dy < -2) returned = true;
      else if (dy > 2) returned = false;
      const y = Math.min(Math.max(rawY, 0), 80);
      // Position-linked fade over the first 80px; a scroll-up return pins it
      // fully visible until the next downward motion.
      const fade = returned ? 1 : 1 - y / 80;
      // Translate range is half the scroll range so items progressively clip
      // against the nav top edge instead of jumping out of view in the first
      // few pixels (item center is ~16px from the nav's top edge).
      root.style.setProperty('--nav-scroll-y', `${-(1 - fade) * 40}px`);
      root.style.setProperty('--nav-scroll-fade', `${fade}`);
      if (rawY === 0 && wordmarkRef.current) {
        // Measure with the clamp OFF. `scrollWidth` on the clamped box returns
        // max(clientWidth, content), so it only ever corrects the stored width
        // UPWARD: at 390px the wordmark steps down a font size to ~96px of text
        // and the reading stayed pinned at the 120px fallback, padding a nav
        // that already overflows that viewport. Clearing the inline size first
        // costs one synchronous layout, and only on frames that land at
        // scrollY 0, where the width is not being animated anyway.
        const el = wordmarkRef.current;
        el.style.inlineSize = 'auto';
        const width = Math.ceil(el.getBoundingClientRect().width);
        el.style.inlineSize = '';
        if (width > 0 && width !== measured) {
          measured = width;
          root.style.setProperty('--nav-wordmark-w', `${width}px`);
        }
      }
      root.style.setProperty('--nav-wordmark-fade', `${fade}`);
      const collapsed = !returned && y >= 80;
      if (collapsed) {
        body.setAttribute('data-nav-collapsed', 'true');
        setIsPersonaMenuOpen(false);
        setIsCtaMenuOpen(false);
        setIsLearnMenuOpen(false);
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
      root.style.removeProperty('--nav-wordmark-fade');
      root.style.removeProperty('--nav-wordmark-w');
    };
  }, []);

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
    setIsPersonaMenuOpen(false);
    setIsCtaMenuOpen(false);
    setIsLearnMenuOpen(false);
  };

  const closeSidebar = () => {
    setIsSidebarOpen(false);
  };

  const openSearch = () => {
    setIsSearchOpen(true);
    setIsPersonaMenuOpen(false);
    setIsCtaMenuOpen(false);
    setIsLearnMenuOpen(false);
    // Tell the docs-scoped modal to close. Docs pages mount their own SearchModal, and
    // without this the two can be open at once via the CLICK paths (the CTA menu entry and
    // the mobile drawer row). The HOTKEY path was already covered, because both mounts
    // listen for this same event.
    document.dispatchEvent(new CustomEvent('search:open'));
  };

  const closeSearch = () => {
    setIsSearchOpen(false);
  };

  const togglePersonaMenu = () => {
    setIsPersonaMenuOpen((prev) => !prev);
    setIsCtaMenuOpen(false);
  };
  const closePersonaMenu = () => setIsPersonaMenuOpen(false);

  const toggleCtaMenu = () => {
    setIsCtaMenuOpen((prev) => !prev);
    setIsPersonaMenuOpen(false);
  };
  const closeCtaMenu = () => setIsCtaMenuOpen(false);

  // Native auto-popovers already close each other, so these siblings are
  // belt-and-braces for React state rather than the dismissal mechanism.
  const toggleLearnMenu = () => {
    setIsLearnMenuOpen((prev) => !prev);
    setIsPersonaMenuOpen(false);
    setIsCtaMenuOpen(false);
  };
  const closeLearnMenu = () => setIsLearnMenuOpen(false);

  // Build the condensed bar's breadcrumb from the path. Labels come from the
  // EXISTING navigation.* catalog entries where a segment has one (so the
  // trail is localized and no new i18n keys exist for the gates to police);
  // the last segment falls back to the document title's own name (the part
  // before the "| Rediacc"-style suffix), which is already localized per page,
  // and any remaining segment is de-slugged. The homepage renders no trail:
  // the mark is the breadcrumb there.
  useEffect(() => {
    const SEGMENT_KEYS: Record<string, string> = {
      'pricing': 'navigation.pricing',
      'blog': 'navigation.blog',
      'docs': 'navigation.docs',
      'solutions': 'navigation.solutions',
      'contact': 'navigation.contact',
      'install': 'navigation.install',
      'downloads': 'navigation.downloads',
      'partners': 'navigation.partners',
      'account': 'navigation.account',
      'for-devops': 'navigation.forDevops',
      'for-ctos': 'navigation.forCtos',
      'for-ceos': 'navigation.forCeos',
      'for-ai-agents': 'navigation.forAiAgents',
      'disaster-recovery': 'navigation.disasterRecovery',
      'roi-calculator': 'navigation.roiCalculator',
    };
    const deslug = (s: string) => {
      const words = s.replace(/-/g, ' ');
      return words.charAt(0).toUpperCase() + words.slice(1);
    };
    const compute = () => {
      const parts = window.location.pathname.split('/').filter(Boolean);
      const segments = parts.slice(1); // parts[0] is the locale
      let href = `/${parts[0] ?? currentLang}`;
      const next = segments.map((segment, i) => {
        href += `/${segment}`;
        const key = SEGMENT_KEYS[segment];
        let label: string;
        if (key) {
          label = t(key);
        } else if (i === segments.length - 1 && document.title.includes('|')) {
          label = document.title.split('|')[0].trim();
        } else {
          label = deslug(segment);
        }
        return { href, label };
      });
      setTrail(next);
    };
    compute();
    document.addEventListener('astro:after-swap', compute);
    return () => document.removeEventListener('astro:after-swap', compute);
  }, [t, currentLang]);

  // Close menus on Astro page navigation
  useEffect(() => {
    const handleNavigation = () => {
      setIsPersonaMenuOpen(false);
      setIsCtaMenuOpen(false);
      setIsLearnMenuOpen(false);
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
            <span ref={wordmarkRef} className="nav-wordmark" aria-label={t('common.logoAlt')}>
              rediacc
            </span>
          </a>
          {/* Condensed-bar breadcrumb; visible only under body[data-nav-collapsed].
              An <ol>, not a nested <nav>: the whole bar is already a navigation
              landmark, and the aria-label names the list. */}
          {trail.length > 0 && (
            <ol className="nav-breadcrumb" aria-label={t('common.aria.breadcrumbNavigation')}>
              {trail.map((crumb, i) => (
                <li key={crumb.href} className="nav-breadcrumb-item">
                  {i < trail.length - 1 ? (
                    <>
                      <a href={crumb.href}>{crumb.label}</a>
                      <span className="nav-breadcrumb-sep" aria-hidden="true">
                        /
                      </span>
                    </>
                  ) : (
                    <span aria-current="page">{crumb.label}</span>
                  )}
                </li>
              ))}
            </ol>
          )}
          <div className="nav-links nav-translate">
            <a
              href={`/${currentLang}#solutions`}
              className="nav-link"
              data-track="cta_click"
              data-track-label="nav-link"
              data-track-dest="solutions"
            >
              {t('navigation.solutions')}
            </a>
            <PersonaMegaMenu
              lang={currentLang}
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
            {/* Replaces a bare Docs link that pointed at /docs/quick-start, i.e. straight
                past the index into one article. Every entry deep-links into the browse
                page's category filter. */}
            <LearnMenu
              lang={currentLang}
              isOpen={isLearnMenuOpen}
              onToggle={toggleLearnMenu}
              onClose={closeLearnMenu}
            />
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
              <LanguageMenu
                variant="icon-only"
                currentLang={currentLang}
                languages={SUPPORTED_LANGUAGES}
                position="top"
                navigationMode="button"
                ariaLabel={t('navigation.selectLanguage')}
              />
            </div>
            <NavCtaMenu
              origin={origin}
              getStartedLabel={t('common.buttons.getStarted')}
              loginLabel={t('navigation.login')}
              searchLabel={t('navigation.search')}
              // navigation.moreOptions, not navigation.toggleMenu: the hamburger already
              // announces "Toggle menu" in this same bar, and two controls sharing one
              // accessible name is indistinguishable by ear. The panel takes its name from
              // this trigger via aria-labelledby, so this one prop names both.
              menuLabel={t('navigation.moreOptions')}
              isOpen={isCtaMenuOpen}
              onToggle={toggleCtaMenu}
              onClose={closeCtaMenu}
              onSearch={openSearch}
            />
          </div>
        </div>
      </nav>
      <Sidebar
        lang={currentLang}
        isOpen={isSidebarOpen}
        onClose={closeSidebar}
        origin={origin}
        onSearch={openSearch}
      />
      <SearchModal lang={currentLang} isOpen={isSearchOpen} onClose={closeSearch} />
    </>
  );
};

export default Navigation;
