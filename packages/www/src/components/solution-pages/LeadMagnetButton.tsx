import React, { useEffect, useRef, useState } from 'react';
import { useLanguage } from '../../hooks/useLanguage';
import { useTranslation } from '../../i18n/react';

interface Props {
  /** Magnet slug from the backend registry (e.g. "ransomware-survival-cto"). */
  magnetName: string;
  /** Analytics source tag (e.g. "solution-immutable-backups-30scroll"). */
  source: string;
  /** Optional pre-resolved label to show inside the modal. */
  label?: string;
  /**
   * When true, gate the button behind a 30vh scroll trigger using an
   * IntersectionObserver sentinel. Used on solution pages to mirror the
   * old SPDownloadGated behavior.
   * Defaults to false (button visible immediately) — used on resource pages.
   */
  scrollGate?: boolean;
}

const DISMISS_KEY_PREFIX = 'leadMagnetButtonDismissed:';

const LeadMagnetButton: React.FC<Props> = ({ magnetName, source, label, scrollGate = false }) => {
  const lang = useLanguage();
  const { t } = useTranslation(lang);

  const sessionKey = `${DISMISS_KEY_PREFIX}${magnetName}`;
  const [visible, setVisible] = useState(!scrollGate);
  const [dismissed, setDismissed] = useState(() => {
    if (!scrollGate || typeof window === 'undefined') return false;
    return sessionStorage.getItem(sessionKey) !== null;
  });

  // Scroll-trigger: show when sentinel at ~30vh scrolls out of view.
  useEffect(() => {
    if (!scrollGate || dismissed) return;
    const sentinel = document.createElement('div');
    sentinel.style.position = 'absolute';
    sentinel.style.top = '30vh';
    sentinel.style.height = '1px';
    sentinel.style.width = '1px';
    sentinel.style.pointerEvents = 'none';
    document.body.appendChild(sentinel);
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) setVisible(true);
      },
      { threshold: 0 }
    );
    observer.observe(sentinel);
    return () => {
      observer.disconnect();
      sentinel.remove();
    };
  }, [scrollGate, dismissed, sessionKey]);

  const wrapperRef = useRef<HTMLDivElement>(null);

  if (dismissed || !visible) return null;

  const handleClick = () => {
    window.dispatchEvent(
      new CustomEvent('lead-magnet:open', {
        detail: { magnetName, source, label },
      })
    );
  };

  const handleDismiss = () => {
    setDismissed(true);
    if (typeof window !== 'undefined') {
      sessionStorage.setItem(sessionKey, '1');
    }
  };

  const title = t('pages.solutionPages.leadMagnetButton.title');
  const description = t('pages.solutionPages.leadMagnetButton.description');
  const buttonLabel = t('pages.solutionPages.leadMagnetButton.buttonLabel');

  return (
    <div
      ref={wrapperRef}
      className={`sp-lead-magnet-button${scrollGate ? ' sp-lead-magnet-button--gated' : ''}`}
    >
      {scrollGate && (
        <button
          type="button"
          className="sp-lead-magnet-button__close"
          aria-label={t('pages.solutionPages.leadMagnetButton.dismissLabel') || 'Dismiss'}
          onClick={handleDismiss}
          data-track="cta_click"
          data-track-label={`lead-magnet-button-dismiss-${magnetName}`}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M4.646 4.646a.5.5 0 01.708 0L8 7.293l2.646-2.647a.5.5 0 01.708.708L8.707 8l2.647 2.646a.5.5 0 01-.708.708L8 8.707l-2.646 2.647a.5.5 0 01-.708-.708L7.293 8 4.646 5.354a.5.5 0 010-.708z" />
          </svg>
        </button>
      )}
      <h3 className="sp-lead-magnet-button__title">{title}</h3>
      <p className="sp-lead-magnet-button__description">{description}</p>
      <button
        type="button"
        className="sp-lead-magnet-button__cta"
        onClick={handleClick}
        data-track="cta_click"
        data-track-label={`lead-magnet-button-open-${magnetName}`}
      >
        {buttonLabel}
      </button>
    </div>
  );
};

export default LeadMagnetButton;
