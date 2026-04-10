import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import { REGIONS, type Region } from '../config/regions';

const DEFAULT_TARGET_PATH = '/account/';

declare global {
  interface Window {
    openRegionPicker?: (targetPath?: string) => void;
    forceOpenRegionPicker?: (targetPath?: string) => void;
  }
}

function handleFocusTrap(e: KeyboardEvent, modal: HTMLDivElement, close: () => void): void {
  if (e.key === 'Escape') {
    close();
    return;
  }
  if (e.key !== 'Tab') return;

  const focusable = modal.querySelectorAll<HTMLElement>('button, [tabindex]:not([tabindex="-1"])');
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

function detectLikelyRegion(regions: Region[]): Region {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz.startsWith('Europe/') || tz.startsWith('Africa/')) {
      return regions.find((r) => r.id === 'eu') ?? regions[0];
    }
    if (tz.startsWith('America/')) {
      return regions.find((r) => r.id === 'us') ?? regions[0];
    }
    if (
      tz.startsWith('Asia/') ||
      tz.startsWith('Pacific/') ||
      tz.startsWith('Australia/') ||
      tz.startsWith('Indian/')
    ) {
      return regions.find((r) => r.id === 'asia') ?? regions[0];
    }
  } catch {
    // Fallback to default
  }
  return regions.find((r) => r.default) ?? regions[0];
}

const REGION_META: Partial<Record<string, { flagSrc: string; flagAlt: string; location: string }>> =
  {
    eu: {
      flagSrc: '/assets/images/flags/eu.svg',
      flagAlt: 'EU flag',
      location: 'Frankfurt, Germany',
    },
    us: { flagSrc: '/assets/images/flags/us.svg', flagAlt: 'US flag', location: 'Virginia, USA' },
    asia: {
      flagSrc: '/assets/images/flags/jp.svg',
      flagAlt: 'Japan flag',
      location: 'Tokyo, Japan',
    },
  };

const REGION_STORAGE_KEY = 'rediacc_region';

function getStoredRegion(): { region: string; timestamp: number } | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(REGION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.region === 'string' && typeof parsed.timestamp === 'number') {
      return parsed;
    }
  } catch {
    /* corrupted data */
  }
  return null;
}

const RegionPickerModal: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [targetPath, setTargetPath] = useState('/account/');
  const [selected, setSelected] = useState<string | null>(null);
  const [useStable, setUseStable] = useState(false);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const forceOpen = useCallback((path?: string) => {
    previousFocusRef.current = document.activeElement as HTMLElement;
    setTargetPath(path ?? DEFAULT_TARGET_PATH);
    setSelected(detectLikelyRegion(REGIONS).id);
    setUseStable(false);
    setIsOpen(true);
    window.plausible?.('region_picker_open', {
      props: { source: path?.includes('checkout') ? 'checkout' : 'nav' },
    });
  }, []);

  const open = useCallback(
    (path?: string) => {
      const stored = getStoredRegion();
      if (stored) {
        const region = REGIONS.find((r) => r.id === stored.region);
        if (region) {
          window.plausible?.('region_selected', { props: { region: region.id, source: 'stored' } });
          window.location.href = `https://${region.edgeDomain}${path ?? DEFAULT_TARGET_PATH}`;
          return;
        }
      }
      forceOpen(path);
    },
    [forceOpen]
  );

  const close = useCallback(() => {
    setIsOpen(false);
    previousFocusRef.current?.focus();
  }, []);

  const handleSelect = useCallback(
    (region: Region) => {
      try {
        window.localStorage.setItem(
          REGION_STORAGE_KEY,
          JSON.stringify({ region: region.id, timestamp: Date.now() })
        );
      } catch {
        /* quota exceeded or private mode */
      }
      const channel = useStable ? 'stable' : 'edge';
      window.plausible?.('region_selected', { props: { region: region.id, channel } });
      const domain = useStable ? region.domain : region.edgeDomain;
      window.location.href = `https://${domain}${targetPath}`;
    },
    [targetPath, useStable]
  );

  // Expose global functions
  useEffect(() => {
    window.openRegionPicker = open;
    window.forceOpenRegionPicker = forceOpen;
    return () => {
      delete window.openRegionPicker;
      delete window.forceOpenRegionPicker;
    };
  }, [open, forceOpen]);

  // Focus trap + Escape + body scroll lock
  useEffect(() => {
    if (!isOpen) return;

    document.body.style.overflow = 'hidden';
    requestAnimationFrame(() => {
      const firstBtn = modalRef.current?.querySelector<HTMLElement>('.region-picker-card');
      firstBtn?.focus();
    });

    const onKeyDown = (e: KeyboardEvent) => {
      const modal = modalRef.current;
      if (!modal) return;
      handleFocusTrap(e, modal, close);
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen, close]);

  if (!isOpen) return null;

  return (
    <div className="region-picker-backdrop" onClick={close}>
      <div
        className="region-picker-content"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('regionPicker.title')}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="region-picker-header">
          <h2 className="region-picker-title">{t('regionPicker.title')}</h2>
          <button
            className="region-picker-close"
            onClick={close}
            aria-label={t('common.close')}
            type="button"
            data-track="region_picker_close"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="region-picker-cards">
          {REGIONS.map((region) => (
            <button
              key={region.id}
              type="button"
              className={`region-picker-card ${selected === region.id ? 'region-picker-card--selected' : ''}`}
              onClick={() => handleSelect(region)}
              onMouseEnter={() => setSelected(region.id)}
              onFocus={() => setSelected(region.id)}
              data-track="region_select"
              data-track-label={region.id}
            >
              <div className="region-picker-card-flag">
                <img
                  src={REGION_META[region.id]?.flagSrc}
                  alt={REGION_META[region.id]?.flagAlt ?? ''}
                  width="32"
                  height="32"
                />
              </div>
              <div className="region-picker-card-label">{region.label}</div>
              <div className="region-picker-card-location">
                {REGION_META[region.id]?.location ?? region.domain}
              </div>
            </button>
          ))}
        </div>

        <div className="region-picker-channel-switch">
          <button
            type="button"
            className={`region-picker-channel-option ${!useStable ? 'region-picker-channel-option--active' : ''}`}
            onClick={() => setUseStable(false)}
            data-track="region_picker_channel"
            data-track-label="edge"
          >
            {t('regionPicker.channelEdge', 'Edge')}
          </button>
          <button
            type="button"
            className={`region-picker-channel-option ${useStable ? 'region-picker-channel-option--active' : ''}`}
            onClick={() => setUseStable(true)}
            data-track="region_picker_channel"
            data-track-label="stable"
          >
            {t('regionPicker.channelStable', 'Stable')}
          </button>
        </div>
        <p className="region-picker-channel-hint">
          {useStable
            ? t(
                'regionPicker.stableHint',
                'Reliable releases, promoted from edge after 7-day soak.'
              )
            : t('regionPicker.edgeHint', 'Latest features, 2X free limits. Recommended.')}
          <br />
          <span className="region-picker-channel-hint-note">
            {t('regionPicker.regionNote', "Region can't be changed after sign-up.")}
          </span>
        </p>
      </div>
    </div>
  );
};

export default RegionPickerModal;
