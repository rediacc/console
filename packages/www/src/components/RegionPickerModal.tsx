import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import { REGIONS, type Region } from '../config/regions';

const DEFAULT_TARGET_PATH = '/account/';

declare global {
  interface Window {
    openRegionPicker?: (targetPath?: string) => void;
    plausible: (event: string, opts?: { props: Record<string, string> }) => void;
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
  } catch {
    // Fallback to default
  }
  return regions.find((r) => r.default) ?? regions[0];
}

const REGION_LOCATIONS: Record<string, string> = {
  eu: 'Frankfurt, Germany',
  us: 'Virginia, USA',
};

const RegionPickerModal: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [targetPath, setTargetPath] = useState('/account/');
  const [selected, setSelected] = useState<string | null>(null);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const open = useCallback((path?: string) => {
    previousFocusRef.current = document.activeElement as HTMLElement;
    setTargetPath(path ?? DEFAULT_TARGET_PATH);
    setSelected(detectLikelyRegion(REGIONS).id);
    setIsOpen(true);
    window.plausible('region_picker_open', {
      props: { source: path?.includes('checkout') ? 'checkout' : 'nav' },
    });
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    previousFocusRef.current?.focus();
  }, []);

  const handleSelect = useCallback(
    (region: Region) => {
      window.plausible('region_selected', { props: { region: region.id } });
      window.location.href = `https://${region.domain}${targetPath}`;
    },
    [targetPath]
  );

  // Expose global function
  useEffect(() => {
    window.openRegionPicker = open;
    return () => {
      delete window.openRegionPicker;
    };
  }, [open]);

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
          <div>
            <h2 className="region-picker-title">{t('regionPicker.title')}</h2>
            <p className="region-picker-description">{t('regionPicker.subtitle')}</p>
          </div>
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
              <div className="region-picker-card-label">{region.label}</div>
              <div className="region-picker-card-location">
                {REGION_LOCATIONS[region.id] ?? region.domain}
              </div>
            </button>
          ))}
        </div>

        <p className="region-picker-footer">{t('regionPicker.footer')}</p>
      </div>
    </div>
  );
};

export default RegionPickerModal;
