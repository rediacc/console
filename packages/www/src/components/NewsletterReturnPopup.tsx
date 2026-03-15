import React, { useEffect, useRef, useState } from 'react';
import { EXTERNAL_LINKS } from '../config/constants';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import NewsletterSignup from './NewsletterSignup';
import '../styles/newsletter.css';

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

const NewsletterReturnPopup: React.FC = () => {
  const [open, setOpen] = useState(false);
  const hiddenAtRef = useRef<number | null>(null);
  const shownOnceRef = useRef(false);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const shouldSuppress = () => {
    if (!isEligiblePath(window.location.pathname)) return true;
    if (localStorage.getItem(SUBSCRIBED_KEY) === '1') return true;

    const dismissedUntilRaw = localStorage.getItem(DISMISSED_UNTIL_KEY);
    if (!dismissedUntilRaw) return false;

    const dismissedUntil = Number(dismissedUntilRaw);
    return Number.isFinite(dismissedUntil) && dismissedUntil > Date.now();
  };

  useEffect(() => {
    if (currentLang !== 'en') return;

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        hiddenAtRef.current = Date.now();
        return;
      }

      if (shownOnceRef.current || open || shouldSuppress()) return;

      const hiddenAt = hiddenAtRef.current;
      if (!hiddenAt) return;

      const hiddenFor = Date.now() - hiddenAt;
      if (hiddenFor < HIDE_THRESHOLD_MS) return;
      if (hasAnyOpenDialog()) return;

      shownOnceRef.current = true;
      setOpen(true);
      window.plausible?.('newsletter_return_popup_shown', {
        props: {
          source: 'tab-return-popup',
          path: window.location.pathname,
        },
      });
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [currentLang, open]);

  useEffect(() => {
    if (!open) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        localStorage.setItem(DISMISSED_UNTIL_KEY, String(Date.now() + DISMISS_COOLDOWN_MS));
        setOpen(false);
      }
    };

    document.addEventListener('keydown', onEsc);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  if (currentLang !== 'en' || !open) return null;

  return (
    <div
      className="newsletter-return-popup-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={t('newsletter.returnPopup.title')}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        localStorage.setItem(DISMISSED_UNTIL_KEY, String(Date.now() + DISMISS_COOLDOWN_MS));
        setOpen(false);
      }}
    >
      <div className="newsletter-return-popup-card">
        <button
          type="button"
          className="newsletter-return-popup-close"
          aria-label={t('newsletter.returnPopup.close')}
          data-track="cta_click"
          data-track-label="newsletter-return-popup-close"
          data-track-dest="dismiss"
          onClick={() => {
            localStorage.setItem(DISMISSED_UNTIL_KEY, String(Date.now() + DISMISS_COOLDOWN_MS));
            setOpen(false);
            window.plausible?.('newsletter_return_popup_dismissed', {
              props: {
                source: 'tab-return-popup',
                path: window.location.pathname,
              },
            });
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M4.646 4.646a.5.5 0 01.708 0L8 7.293l2.646-2.647a.5.5 0 01.708.708L8.707 8l2.647 2.646a.5.5 0 01-.708.708L8 8.707l-2.646 2.647a.5.5 0 01-.708-.708L7.293 8 4.646 5.354a.5.5 0 010-.708z" />
          </svg>
        </button>

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
            window.plausible?.('newsletter_return_popup_submitted', {
              props: {
                source: 'tab-return-popup',
                path: window.location.pathname,
              },
            });
          }}
        />
        <p className="newsletter-return-popup-note">{t('newsletter.returnPopup.note')}</p>
      </div>
    </div>
  );
};

export default NewsletterReturnPopup;
