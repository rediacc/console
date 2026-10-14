import React, { useEffect, useRef, useState } from 'react';
import { EXTERNAL_LINKS } from '../config/constants';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import NewsletterSignup from './NewsletterSignup';
import Overlay from './Overlay';
import '../styles/newsletter.css';
import type { Language } from '../i18n/types';

const HIDE_THRESHOLD_MS = 30 * 1000;
const DISMISS_COOLDOWN_MS = 30 * 60 * 1000;
const DISMISSED_UNTIL_KEY = 'newsletterPopupDismissedUntil';
const SUBSCRIBED_KEY = 'newsletterPopupSubscribed';

const EXCLUDED_PATHS = ['/newsletter', '/privacy-policy', '/terms', '/cookies'] as const;

function hasAnyOpenDialog(): boolean {
  return Boolean(document.querySelector('[role="dialog"][aria-modal="true"]'));
}

function isEligiblePath(pathname: string): boolean {
  return !EXCLUDED_PATHS.some((segment) => pathname.includes(segment));
}

function shouldSuppress(): boolean {
  if (!isEligiblePath(window.location.pathname)) return true;
  if (localStorage.getItem(SUBSCRIBED_KEY) === '1') return true;

  const dismissedUntilRaw = localStorage.getItem(DISMISSED_UNTIL_KEY);
  if (!dismissedUntilRaw) return false;

  const dismissedUntil = Number(dismissedUntilRaw);
  return Number.isFinite(dismissedUntil) && dismissedUntil > Date.now();
}

/** True when the tab was hidden at `hiddenAt` and for at least the threshold since. */
function wasHiddenLongEnough(hiddenAt: number | null): boolean {
  if (!hiddenAt) return false;
  return Date.now() - hiddenAt >= HIDE_THRESHOLD_MS;
}

function shouldShowPopup(shownOnce: boolean, open: boolean, hiddenAt: number | null): boolean {
  if (shownOnce || open || shouldSuppress()) return false;
  return wasHiddenLongEnough(hiddenAt) && !hasAnyOpenDialog();
}

function trackPopup(event: string): void {
  window.plausible?.(event, {
    props: {
      source: 'tab-return-popup',
      path: window.location.pathname,
    },
  });
}

interface NewsletterReturnPopupProps {
  /** Locale from BaseLayout; authoritative on the server. See the note above. */
  lang?: Language;
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
const NewsletterReturnPopup: React.FC<NewsletterReturnPopupProps> = ({ lang }) => {
  const [open, setOpen] = useState(false);
  const hiddenAtRef = useRef<number | null>(null);
  const shownOnceRef = useRef(false);
  const detectedLang = useLanguage();
  const currentLang = lang ?? detectedLang;
  const { t } = useTranslation(currentLang);

  useEffect(() => {
    if (currentLang !== 'en') return;

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        hiddenAtRef.current = Date.now();
        return;
      }

      if (!shouldShowPopup(shownOnceRef.current, open, hiddenAtRef.current)) return;

      shownOnceRef.current = true;
      setOpen(true);
      trackPopup('newsletter_return_popup_shown');
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [currentLang, open]);

  /* Dismissal is the same three lines whether it came from Escape, the
     backdrop or the close button, so it is written once. It used to be
     written three times, and the Escape copy did not fire the
     `newsletter_return_popup_dismissed` event the button copy did. */
  const dismiss = (fromCloseButton: boolean) => {
    localStorage.setItem(DISMISSED_UNTIL_KEY, String(Date.now() + DISMISS_COOLDOWN_MS));
    setOpen(false);
    if (fromCloseButton) trackPopup('newsletter_return_popup_dismissed');
  };

  if (currentLang !== 'en') return null;

  return (
    <Overlay
      open={open}
      onClose={() => dismiss(true)}
      onBackdropClose={() => dismiss(false)}
      align="center"
      label={t('newsletter.returnPopup.title')}
      closeLabel={t('newsletter.returnPopup.close')}
      closeTrackLabel="newsletter-return-popup-close"
    >
      <div className="overlay-body newsletter-return-popup">
        <NewsletterSignup
          variant="modal"
          source="tab-return-popup"
          title={t('newsletter.returnPopup.title')}
          description={t('newsletter.returnPopup.description')}
          ctaLabel={t('newsletter.returnPopup.cta')}
          openOnSuccessUrl={EXTERNAL_LINKS.SCHEDULE_CONSULTATION}
          onSuccess={() => {
            localStorage.setItem(SUBSCRIBED_KEY, '1');
            setOpen(false);
            trackPopup('newsletter_return_popup_submitted');
          }}
        />
        <p className="newsletter-return-popup-note">{t('newsletter.returnPopup.note')}</p>
      </div>
    </Overlay>
  );
};

export default NewsletterReturnPopup;
