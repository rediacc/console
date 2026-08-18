import React, { useCallback, useEffect, useRef, useState } from 'react';
import { REGIONS, type Region } from '../config/regions';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import { buildPortalRedirectUrl, getHostKind } from '../utils/marketing-host';
import Overlay from './Overlay';
import type { Language } from '../i18n/types';

const DEFAULT_TARGET_PATH = '/account/';

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

/** Release channel implied by the current host (stable only on www). */
function hostChannel(): 'stable' | 'edge' {
  return getHostKind(window.location.hostname) === 'marketing-stable' ? 'stable' : 'edge';
}

/** Captured utm_* params from the behavioral tracker, if it has any. */
function capturedUtm(): Record<string, string> {
  return window.__pa_get_utm?.() ?? {};
}

/**
 * Cross-origin handoff to the regional portal. The channel is derived from
 * the current host (www → stable domains, edge/localhost → edge domains) and
 * captured utm_* params ride along so attribution survives the hop.
 */
function forwardToPortal(region: Region, targetPath: string): void {
  window.location.href = buildPortalRedirectUrl(
    window.location.hostname,
    region,
    targetPath,
    capturedUtm()
  );
}

interface RegionPickerModalProps {
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
const RegionPickerModal: React.FC<RegionPickerModalProps> = ({ lang }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [targetPath, setTargetPath] = useState('/account/');
  const [selected, setSelected] = useState<string | null>(null);
  const detectedLang = useLanguage();
  const currentLang = lang ?? detectedLang;
  const { t } = useTranslation(currentLang);

  const firstCardRef = useRef<HTMLButtonElement>(null);

  const forceOpen = useCallback((path?: string) => {
    setTargetPath(path ?? DEFAULT_TARGET_PATH);
    setSelected(detectLikelyRegion(REGIONS).id);
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
          window.plausible?.('region_selected', {
            props: { region: region.id, channel: hostChannel(), source: 'stored' },
          });
          forwardToPortal(region, path ?? DEFAULT_TARGET_PATH);
          return;
        }
      }
      forceOpen(path);
    },
    [forceOpen]
  );

  const close = useCallback(() => {
    setIsOpen(false);
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
      window.plausible?.('region_selected', {
        props: { region: region.id, channel: hostChannel() },
      });
      forwardToPortal(region, targetPath);
    },
    [targetPath]
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

  return (
    <Overlay
      open={isOpen}
      onClose={close}
      align="center"
      width="wide"
      label={t('regionPicker.title')}
      title={t('regionPicker.title')}
      closeLabel={t('common.close')}
      closeTrackLabel="region_picker_close"
      initialFocusRef={firstCardRef}
    >
      <div className="overlay-body region-picker">
        <p className="region-picker-subtitle">{t('regionPicker.subtitle')}</p>
        <p className="region-picker-reassurance">{t('regionPicker.reassurance')}</p>

        <div className="region-picker-cards">
          {REGIONS.map((region, index) => (
            <button
              key={region.id}
              type="button"
              ref={index === 0 ? firstCardRef : undefined}
              className={`card region-picker-card ${selected === region.id ? 'card--raised' : ''}`}
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

        <p className="region-picker-footer">{t('regionPicker.footer')}</p>
        <p className="region-picker-footer-note">{t('regionPicker.footerNote')}</p>
      </div>
    </Overlay>
  );
};

export default RegionPickerModal;
