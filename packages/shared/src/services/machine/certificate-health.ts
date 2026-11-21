/**
 * Certificate expiry (G5) and shared-CNAME ACME challenge (G6) checks over the machine listing's `certificates` section.
 * Split from parsing-health.ts, which holds the per-listing health checks.
 */

// Certificate expiry (G5, D-certs): the proxy's ACME certificates from the listing's `certificates` section. Traefik renews 30 days ahead, so a certificate under 21 days means at least nine days of failed renewals.

/** Days left below which a certificate is a warning. */
export const CERT_EXPIRY_WARNING_DAYS = 21;
/** Days left below which a certificate is an error. */
export const CERT_EXPIRY_ERROR_DAYS = 7;

/** The listing's `certificates` section (renet pkg/list CertificatesSection). */
export interface CertificatesSectionInput {
  status: string;
  certificates: { main: string; sans?: string[]; not_after: string }[] | null;
  error?: string;
}

/** One certificate finding: `cert.expiry.near`, or `cert.store.unreadable` when acme.json (or one certificate's expiry) could not be read. */
export interface CertificateFinding {
  code: 'cert.expiry.near' | 'cert.store.unreadable';
  severity: 'warning' | 'error';
  subject: string;
  detail: string;
  daysLeft?: number;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function certificateFinding(
  cert: { main: string; not_after: string },
  now: Date
): CertificateFinding | null {
  const notAfter = Date.parse(cert.not_after);
  if (Number.isNaN(notAfter)) {
    // An expiry that cannot be read is never a clean certificate.
    return {
      code: 'cert.store.unreadable',
      severity: 'warning',
      subject: cert.main,
      detail: `Certificate ${cert.main} has an unreadable expiry (${cert.not_after})`,
    };
  }
  const daysLeft = Math.floor((notAfter - now.getTime()) / DAY_MS);
  if (daysLeft >= CERT_EXPIRY_WARNING_DAYS) return null;
  return {
    code: 'cert.expiry.near',
    severity: daysLeft < CERT_EXPIRY_ERROR_DAYS ? 'error' : 'warning',
    subject: cert.main,
    daysLeft,
    detail:
      daysLeft < 0
        ? `Certificate ${cert.main} expired ${-daysLeft} day(s) ago (${cert.not_after})`
        : `Certificate ${cert.main} expires in ${daysLeft} day(s) (${cert.not_after})`,
  };
}

/**
 * Judge each certificate's expiry: under 21 days a warning, under 7 an error, each naming the certificate. An absent section (no proxy on the machine) raises nothing; a section renet could not read is one warning, never a clean machine.
 */
export function checkCertificateExpiry(
  section: CertificatesSectionInput | null | undefined,
  now: Date = new Date()
): CertificateFinding[] {
  if (!section) return [];
  if (section.status !== 'ok') {
    return [
      {
        code: 'cert.store.unreadable',
        severity: 'warning',
        subject: 'acme.json',
        detail: `proxy certificate store unreadable: ${section.error ?? section.status}`,
      },
    ];
  }
  return (section.certificates ?? [])
    .map((cert) => certificateFinding(cert, now))
    .filter((f): f is CertificateFinding => f !== null);
}

// The ACME shared-CNAME class (G6, D-certs, F17): lego follows a CNAME on `_acme-challenge.<name>` and writes the challenge TXT at the chain's end, so one end shared by several names makes those renewals collide, and an end that is not itself an `_acme-challenge.` name puts the challenge record there instead of at the name.

/**
 * A certificates section that carries where each name's challenge lands (renet pkg/list ChallengeInfo). `unknown` is set
 * when no resolver answered for the name, so renet could not resolve the chain, which is neither "no CNAME" nor a clean check.
 */
export interface ChallengeSectionInput {
  status: string;
  certificates:
    | { main: string; challenges?: { name: string; cname?: string; unknown?: boolean }[] }[]
    | null;
  delegated_names?: string[];
}

/**
 * One ACME challenge finding: `acme.challenge.cname-shared` names the chain end and the certificate names landing there;
 * `acme.challenge.unknown` names the certificate names whose chain renet could not resolve.
 */
export interface AcmeChallengeFinding {
  code: 'acme.challenge.cname-shared' | 'acme.challenge.unknown';
  severity: 'warning';
  subject: string;
  names: string[];
  detail: string;
}

const stripWildcard = (name: string): string => name.replace(/^\*\./, '').toLowerCase();

/**
 * Map each challenge chain end to the (wildcard-stripped) names landing there, and collect the names whose chain could
 * not be resolved. Delegated names (and ends) are left out of both.
 */
function challengeEnds(section: ChallengeSectionInput): {
  ends: Map<string, Set<string>>;
  unknown: Set<string>;
} {
  const delegated = new Set((section.delegated_names ?? []).map(stripWildcard));
  const isDelegated = (name: string, end: string): boolean =>
    delegated.has(name) || delegated.has(end);
  const ends = new Map<string, Set<string>>();
  const unknown = new Set<string>();
  const challenges = (section.certificates ?? []).flatMap((cert) => cert.challenges ?? []);
  for (const ch of challenges) {
    const name = stripWildcard(ch.name);
    const end = (ch.cname ?? '').toLowerCase();
    if (isDelegated(name, end)) continue;
    if (ch.unknown === true) unknown.add(name);
    else if (end !== '') addToEnd(ends, end, name);
  }
  return { ends, unknown };
}

function addToEnd(ends: Map<string, Set<string>>, end: string, name: string): void {
  ends.set(end, (ends.get(end) ?? new Set<string>()).add(name));
}

const byName = (a: string, b: string): number => a.localeCompare(b);

/**
 * Report the F17 shape: a challenge chain that ends at a name not beginning `_acme-challenge.`, or two names sharing
 * one end. A name (or end) in the proxy's `delegated_names` is a deliberate delegation and never reported; a name with
 * no CNAME raises nothing. A name whose chain renet could not resolve is `acme.challenge.unknown`: never counted toward
 * a shared end and never read as clean.
 */
export function checkAcmeChallengeCnames(
  section: ChallengeSectionInput | null | undefined
): AcmeChallengeFinding[] {
  if (section?.status !== 'ok') return [];
  const { ends, unknown } = challengeEnds(section);
  return [...sharedEndFindings(ends), ...unknownChainFindings(unknown)];
}

/** The F17 findings: an end outside `_acme-challenge.`, or one end several names share. */
function sharedEndFindings(ends: Map<string, Set<string>>): AcmeChallengeFinding[] {
  const findings: AcmeChallengeFinding[] = [];
  for (const [end, nameSet] of ends) {
    const names = [...nameSet].sort(byName);
    if (end.startsWith('_acme-challenge.') && names.length < 2) continue;
    findings.push({
      code: 'acme.challenge.cname-shared',
      severity: 'warning',
      subject: end,
      names,
      detail:
        names.length > 1
          ? `ACME challenge for ${names.join(', ')} follows a CNAME to ${end}; renewals there collide`
          : `ACME challenge for ${names.join(', ')} follows a CNAME to ${end}, which is not an _acme-challenge name; the challenge record lands there, not at the name`,
    });
  }
  return findings;
}

/** One `acme.challenge.unknown` finding naming every name whose chain renet could not resolve. */
function unknownChainFindings(unknown: Set<string>): AcmeChallengeFinding[] {
  if (unknown.size === 0) return [];
  const names = [...unknown].sort(byName);
  return [
    {
      code: 'acme.challenge.unknown',
      severity: 'warning',
      subject: names.join(', '),
      names,
      detail: `ACME challenge chain of ${names.join(', ')} could not be resolved; the shared-CNAME check is unknown for them`,
    },
  ];
}
