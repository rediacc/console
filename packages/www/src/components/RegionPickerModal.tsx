import { Turnstile } from '@marsidev/react-turnstile';
import { WK_PRODUCT_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { REGIONS, type Region } from '../config/regions';
import { useCaptchaGuard } from '../hooks/useCaptchaGuard';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import { buildPortalRedirectUrl } from '../utils/marketing-host';
import Overlay from './Overlay';
import Sentences from './Sentences';

const DEFAULT_TARGET_PATH = '/account/';
const COUNTDOWN_SECONDS = 5;
const GEO_TIMEOUT_MS = 1500;

const turnstileSiteKey = import.meta.env.PUBLIC_TURNSTILE_SITE_KEY ?? '';
const ciMode =
  String(import.meta.env.PUBLIC_CI_MODE ?? '').toLowerCase() === 'true' ||
  String(import.meta.env.PUBLIC_CI_MODE ?? '') === '1';
const captchaEnabled = !!turnstileSiteKey && !ciMode;

export type PickerMode = 'login' | 'signup';

/**
 * Mode comes from the target path, since every caller passes only a path. A checkout
 * deep link and the sign-up routes create an account, so the region decides where its
 * data lives and the visitor must choose. Any other /account/* path is a login.
 */
export function modeFromPath(path: string): PickerMode {
  const lower = path.toLowerCase();
  if (lower.includes('checkout=') || /\/(signup|sign-up|register)(\/|\?|$)/.test(lower)) {
    return 'signup';
  }
  return 'login';
}

const EU_COUNTRIES = new Set(
  (
    'AD AL AT AX BA BE BG BY CH CY CZ DE DK EE ES FI FO FR GB GG GI GR HR HU IE IM IS IT JE LI LT LU LV MC MD ME MK MT NL NO PL PT RO RS RU SE SI SJ SK SM UA VA XK ' +
    'AE BH EG IL IQ IR JO KW LB OM PS QA SA SY TR YE ' +
    'DZ AO BF BI BJ BW CD CF CG CI CM CV DJ ER ET GA GH GM GN GQ GW KE KM LR LS LY MA MG ML MR MU MW MZ NA NE NG RE RW SC SD SL SN SO SS ST SZ TD TG TN TZ UG ZA ZM ZW'
  ).split(' ')
);
const ASIA_COUNTRIES = new Set(
  'AF AU BD BN BT CC CK CN CX FJ FM GU HK ID IN JP KG KH KI KP KR KZ LA LK MH MM MN MO MV MY NC NP NR NU NZ PF PG PH PK PW SB SG TH TJ TL TM TO TV TW UZ VN VU WF WS'.split(
    ' '
  )
);

/** Region for an ISO country code, or null when the code is unknown or empty. */
export function regionForCountry(
  regions: Region[],
  country: string | null | undefined
): Region | null {
  const code = (country ?? '').toUpperCase();
  if (code.length !== 2) return null;
  let id = 'us';
  if (EU_COUNTRIES.has(code)) id = 'eu';
  else if (ASIA_COUNTRIES.has(code)) id = 'asia';
  return regions.find((r) => r.id === id) ?? null;
}

const TZ_PREFIX_REGION: [string[], string][] = [
  [['Europe/', 'Africa/'], 'eu'],
  [['America/'], 'us'],
  [['Asia/', 'Pacific/', 'Australia/', 'Indian/'], 'asia'],
];

/** Time-zone guess, the fallback when /api/geo does not answer. */
export function regionForTimeZone(regions: Region[], tz: string): Region {
  for (const [prefixes, id] of TZ_PREFIX_REGION) {
    if (prefixes.some((p) => tz.startsWith(p))) {
      return regions.find((r) => r.id === id) ?? regions[0];
    }
  }
  return regions.find((r) => r.default) ?? regions[0];
}

function detectLikelyRegion(regions: Region[]): Region {
  try {
    return regionForTimeZone(regions, Intl.DateTimeFormat().resolvedOptions().timeZone);
  } catch {
    return regions.find((r) => r.default) ?? regions[0];
  }
}

/**
 * Country from the www Worker's /api/geo (request.cf.country, no third party).
 * Resolves to null on any failure or timeout so the caller falls back to the time zone.
 */
async function fetchGeoRegion(regions: Region[]): Promise<Region | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GEO_TIMEOUT_MS);
  try {
    const res = await fetch('/api/geo', { cache: 'no-store', signal: controller.signal });
    if (!res.ok) return null;
    const body = (await res.json()) as { country?: string | null };
    return regionForCountry(regions, body.country);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * The domain part of what the visitor typed, or null when it is not a domain. Only this
 * part ever leaves the browser: an address never does.
 */
export function extractDomain(input: string): string | null {
  const raw = input.trim().toLowerCase();
  const domain = raw.includes('@') ? raw.slice(raw.lastIndexOf('@') + 1) : raw;
  return /^(?=.{3,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/.test(domain)
    ? domain
    : null;
}

/**
 * The company host from a lookup answer, or null for a miss. A host outside the product
 * domain counts as a miss, so a bad answer can never send a visitor off-site.
 */
export function parseLookupHost(body: unknown): string | null {
  const host = (body as { host?: unknown } | null)?.host;
  if (typeof host !== 'string') return null;
  const lower = host.toLowerCase();
  return /^[a-z0-9-]+(\.[a-z0-9-]+)*$/.test(lower) && lower.endsWith(`.${WK_PRODUCT_DOMAIN}`)
    ? lower
    : null;
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

function getStoredRegion(): Region | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(REGION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.region === 'string') {
      return REGIONS.find((r) => r.id === parsed.region) ?? null;
    }
  } catch {
    /* corrupted data */
  }
  return null;
}

/** Captured utm_* params from the behavioral tracker, if it has any. */
function capturedUtm(): Record<string, string> {
  return window.__pa_get_utm?.() ?? {};
}

/** Cross-origin handoff to a portal host; captured utm_* params ride along. */
function forwardToHost(host: string, targetPath: string): void {
  window.location.href = buildPortalRedirectUrl(host, targetPath, capturedUtm());
}

/** Whole seconds left, ticking once a second while `active`; calls `onDone` at zero. */
function useCountdown(active: boolean, onDone: () => void): number {
  const [remaining, setRemaining] = useState(COUNTDOWN_SECONDS);
  const doneRef = useRef(onDone);
  useEffect(() => {
    doneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (!active) return;
    let left = COUNTDOWN_SECONDS;
    setRemaining(left);
    const id = setInterval(() => {
      left -= 1;
      setRemaining(left);
      if (left <= 0) {
        clearInterval(id);
        doneRef.current();
      }
    }, 1000);
    return () => clearInterval(id);
  }, [active]);

  return remaining;
}

/** POST the domain (never an address) to the www Worker; the company host, or null for a miss. Throws on a failed request. */
async function lookupCompanyHost(
  domain: string,
  turnstileToken: string | null
): Promise<string | null> {
  const res = await fetch('/api/enterprise-lookup', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ domain, turnstileToken }),
  });
  if (!res.ok) throw new Error(String(res.status));
  return parseLookupHost(await res.json());
}

type Translate = ReturnType<typeof useTranslation>['t'];
type LookupError = 'invalid' | 'captcha' | 'miss' | 'error';

interface LookupFormProps {
  t: Translate;
  targetPath: string;
  onBack: () => void;
}

const LOOKUP_MESSAGE_KEY: Record<LookupError, string> = {
  invalid: 'regionPicker.lookup.invalid',
  captcha: 'captchaRequired',
  miss: 'regionPicker.lookup.miss',
  error: 'regionPicker.lookup.error',
};

/** Company-domain form. The answer is a host or a neutral miss, the same for every address at a domain. */
const LookupForm: React.FC<LookupFormProps> = ({ t, targetPath, onBack }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [lookupError, setLookupError] = useState<LookupError | null>(null);
  const captcha = useCaptchaGuard();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const domain = extractDomain(inputRef.current?.value ?? '');
    if (!domain) return setLookupError('invalid');
    if (captchaEnabled && !captcha.token) return setLookupError('captcha');
    setLookupError(null);
    setLoading(true);
    try {
      const host = await lookupCompanyHost(domain, captcha.token);
      if (host) {
        window.plausible?.('region_selected', {
          props: { region: 'enterprise', source: 'lookup' },
        });
        return forwardToHost(host, targetPath);
      }
      setLookupError('miss');
    } catch {
      setLookupError('error');
    }
    setLoading(false);
    captcha.reset();
  };

  // A widget that failed to load is told apart from one that is merely unsolved, so the visitor is never asked to complete a captcha that is not on screen.
  const messageKey = lookupError && LOOKUP_MESSAGE_KEY[lookupError];

  return (
    <form className="region-picker-lookup" onSubmit={submit} noValidate>
      <p className="region-picker-subtitle">{t('regionPicker.lookup.description')}</p>
      <label htmlFor="region-picker-domain" className="form-label">
        {t('regionPicker.lookup.label')}
      </label>
      <input
        id="region-picker-domain"
        className="form-input"
        type="text"
        inputMode="url"
        autoComplete="off"
        autoCapitalize="none"
        spellCheck={false}
        placeholder={t('regionPicker.lookup.placeholder')}
        ref={inputRef}
        disabled={loading}
      />
      <p className="region-picker-footer-note">{t('regionPicker.lookup.privacy')}</p>
      {messageKey && !(lookupError === 'captcha' && captcha.failed) && (
        <p className="form-error" role="alert">
          {t(messageKey)}
        </p>
      )}
      {captchaEnabled && (
        <Turnstile
          key={captcha.nonce}
          siteKey={turnstileSiteKey}
          options={{ action: 'enterprise_lookup' }}
          onSuccess={captcha.onSuccess}
          onExpire={captcha.onExpire}
          onError={captcha.onError}
        />
      )}
      {captchaEnabled && captcha.failed && (
        <p className="form-error" role="status">
          {t('captchaUnavailable')}{' '}
          <button
            type="button"
            className="form-inline-action"
            onClick={captcha.retry}
            data-track="captcha_retry"
          >
            {t('captchaRetry')}
          </button>
        </p>
      )}
      <div className="region-picker-actions">
        <button type="submit" className="btn btn--primary" disabled={loading}>
          {loading ? t('regionPicker.lookup.checking') : t('regionPicker.lookup.submit')}
        </button>
        <button
          type="button"
          className="btn btn--secondary"
          onClick={onBack}
          data-track="region_lookup_back"
        >
          {t('regionPicker.lookup.back')}
        </button>
      </div>
    </form>
  );
};

interface CountdownBarProps {
  t: Translate;
  lang: Language;
  region: Region;
  remaining: number;
  onCancel: () => void;
  onChange: () => void;
}

/** Visible countdown with Cancel and Change. Screen readers hear one stable message, not a tick per second. */
const CountdownBar: React.FC<CountdownBarProps> = ({
  t,
  lang,
  region,
  remaining,
  onCancel,
  onChange,
}) => (
  <div className="region-picker-countdown">
    <p className="sr-only" role="status" aria-live="polite">
      <Sentences
        text={t('regionPicker.countdownAnnounce', {
          region: region.label,
          seconds: COUNTDOWN_SECONDS,
        })}
        lang={lang}
      />
    </p>
    <p className="region-picker-subtitle" aria-hidden="true">
      {t('regionPicker.countdown', { region: region.label, seconds: remaining })}
    </p>
    <div className="region-picker-actions">
      <button
        type="button"
        className="btn btn--secondary"
        onClick={onCancel}
        data-track="region_countdown_cancel"
      >
        {t('regionPicker.cancel')}
      </button>
      <button
        type="button"
        className="btn btn--primary"
        onClick={onChange}
        data-track="region_countdown_change"
      >
        {t('regionPicker.change')}
      </button>
    </div>
  </div>
);

interface RegionPickerModalProps {
  /** Locale from BaseLayout; authoritative on the server. See the note above. */
  lang?: Language;
}

type Phase = 'resolving' | 'counting' | 'choosing';

/**
 * `lang` is passed by BaseLayout and is AUTHORITATIVE on the server.
 *
 * `useLanguage()` reads `window.location.pathname`, and there is no `window` during SSR,
 * so it returns 'en' for every locale. That made this island server-render English on all
 * twelve non-English locales: crawlers and no-JS visitors saw an English nav, and everyone
 * else got a flash of English until hydration corrected it. Astro knows the locale, so it
 * hands it down; the hook stays as the fallback for any mount that does not.
 *
 * Flow. Login: the region comes from a stored choice, else /api/geo, else the time zone,
 * and a visible 5-second countdown (Cancel, Change) runs before the forward. Sign-up:
 * the region is only preselected, because it decides where the account's data lives.
 */
const RegionPickerModal: React.FC<RegionPickerModalProps> = ({ lang }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [targetPath, setTargetPath] = useState(DEFAULT_TARGET_PATH);
  const [mode, setMode] = useState<PickerMode>('login');
  const [phase, setPhase] = useState<Phase>('choosing');
  const [view, setView] = useState<'regions' | 'lookup'>('regions');
  const [selected, setSelected] = useState<string | null>(null);
  const [countdownRegion, setCountdownRegion] = useState<Region | null>(null);
  const detectedLang = useLanguage();
  const currentLang = lang ?? detectedLang;
  const { t } = useTranslation(currentLang);

  const firstCardRef = useRef<HTMLButtonElement>(null);
  // Bumped on every open, close and stop, so a late /api/geo answer cannot restart a countdown the visitor ended.
  const runRef = useRef(0);

  const begin = useCallback((path?: string) => {
    const target = path ?? DEFAULT_TARGET_PATH;
    const nextMode = modeFromPath(target);
    const run = ++runRef.current;
    const stored = getStoredRegion();
    const guess = stored ?? detectLikelyRegion(REGIONS);
    setTargetPath(target);
    setMode(nextMode);
    setView('regions');
    setSelected(guess.id);
    setCountdownRegion(null);
    setIsOpen(true);
    window.plausible?.('region_picker_open', {
      props: { source: target.includes('checkout') ? 'checkout' : 'nav', mode: nextMode },
    });
    if (nextMode === 'signup') {
      setPhase('choosing');
      return;
    }
    setPhase('resolving');
    const settle = (region: Region) => {
      if (runRef.current !== run) return;
      setSelected(region.id);
      setCountdownRegion(region);
      setPhase('counting');
    };
    if (stored) {
      settle(stored);
      return;
    }
    void fetchGeoRegion(REGIONS).then((geo) => settle(geo ?? guess));
  }, []);

  const close = useCallback(() => {
    runRef.current += 1;
    setIsOpen(false);
  }, []);

  const change = useCallback(() => {
    runRef.current += 1;
    setPhase('choosing');
    requestAnimationFrame(() => firstCardRef.current?.focus());
  }, []);

  const openLookup = useCallback(() => {
    runRef.current += 1;
    setPhase('choosing');
    setView('lookup');
  }, []);

  const finishCountdown = useCallback(() => {
    if (!countdownRegion) return;
    window.plausible?.('region_selected', {
      props: { region: countdownRegion.id, source: 'countdown' },
    });
    forwardToHost(countdownRegion.domain, targetPath);
  }, [countdownRegion, targetPath]);

  const remaining = useCountdown(isOpen && phase === 'counting', finishCountdown);

  const handleSelect = useCallback(
    (region: Region) => {
      runRef.current += 1;
      try {
        window.localStorage.setItem(
          REGION_STORAGE_KEY,
          JSON.stringify({ region: region.id, timestamp: Date.now() })
        );
      } catch {
        /* quota exceeded or private mode */
      }
      window.plausible?.('region_selected', { props: { region: region.id, source: 'card' } });
      forwardToHost(region.domain, targetPath);
    },
    [targetPath]
  );

  // Expose global functions. Both open the picker; a stored region preselects and never forwards silently.
  useEffect(() => {
    window.openRegionPicker = begin;
    window.forceOpenRegionPicker = begin;
    return () => {
      delete window.openRegionPicker;
      delete window.forceOpenRegionPicker;
    };
  }, [begin]);

  const showCountdown = view === 'regions' && phase === 'counting' && countdownRegion;

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
        {view === 'lookup' ? (
          <LookupForm t={t} targetPath={targetPath} onBack={() => setView('regions')} />
        ) : (
          <>
            {showCountdown ? (
              <CountdownBar
                t={t}
                lang={currentLang}
                region={countdownRegion}
                remaining={remaining}
                onCancel={close}
                onChange={change}
              />
            ) : (
              <p className="region-picker-subtitle">
                {phase === 'resolving' ? t('regionPicker.resolving') : t('regionPicker.subtitle')}
              </p>
            )}
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
            {mode === 'signup' && (
              <p className="region-picker-footer-note">{t('regionPicker.footerNote')}</p>
            )}
            <button
              type="button"
              className="btn btn--ghost"
              onClick={openLookup}
              data-track="region_enterprise_lookup"
            >
              {t('regionPicker.enterprise')}
            </button>
          </>
        )}
      </div>
    </Overlay>
  );
};

export default RegionPickerModal;
