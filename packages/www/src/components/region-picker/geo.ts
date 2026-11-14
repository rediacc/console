import { WK_PRODUCT_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import { REGIONS, type Region } from '../../config/regions';

const GEO_TIMEOUT_MS = 1500;

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

export function detectLikelyRegion(regions: Region[]): Region {
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
export async function fetchGeoRegion(regions: Region[]): Promise<Region | null> {
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
 * Whether the visitor has chosen a card in the current open. `pick` records the choice and selects the card, `reset`
 * starts a new open, and `isFree` is what a late /api/geo answer asks before it may move the highlight.
 */
export function createPickTracker() {
  let picked = false;
  return {
    pick(id: string, select: (id: string) => void): void {
      picked = true;
      select(id);
    },
    reset(): void {
      picked = false;
    },
    isFree(): boolean {
      return !picked;
    },
  };
}

/** Preselects the /api/geo region while the cards show, when `needed` (no stored region), unless the lookup failed or `live` is false when the answer arrives (the run ended, or the visitor already pointed at a card). */
export function preselectFromGeo(
  needed: boolean,
  live: () => boolean,
  select: (id: string) => void
): void {
  if (!needed) return;
  void fetchGeoRegion(REGIONS).then((geo) => {
    if (geo && live()) select(geo.id);
  });
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
