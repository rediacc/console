/**
 * Free-text scrubber for feedback reports.
 *
 * Pure and platform-agnostic: the CLI scrubs before preview and send, and the
 * account service re-runs it on every text field as defence in depth.
 */
import { isSensitiveKey } from '../telemetry/utils.js';

const TLDS =
  'com|net|org|io|dev|cloud|app|co|edu|gov|mil|int|info|biz|xyz|me|us|eu|uk|de|fr|nl|ch|se|no|fi|es|it|pl|ru|cn|jp|kr|in|br|ca|au|nz|tr|asia|online|site|tech|ai|sh';

const PEM = /-----BEGIN [A-Z0-9 ]+-----[\s\S]*?(?:-----END [A-Z0-9 ]+-----|$)/g;
const URL_RE = /\b[a-z][a-z0-9+.-]*:\/\/[^\s'"<>)\]]+/gi;
const EMAIL = /[^\s@'"<>]+@[^\s@'"<>]+\.[^\s@'"<>.,;:)]+/g;
const JWT = /\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b/g;
const PREFIXED_TOKEN = /\b(?:rdt_|sk-|ghp_|gho_|xox[abprs]-)[A-Za-z0-9_-]{8,}/g;
const BEARER = /\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}/gi;
const LONG_RUN = /(?<![A-Za-z0-9+/_=-])[A-Za-z0-9+/_-]{32,}={0,2}(?![A-Za-z0-9+/_=-])/g;
const KEY_VALUE = /\b([A-Za-z][A-Za-z0-9_.-]*)(\s*[=:]\s*)("[^"]*"|'[^']*'|[^\s,;&"']+)/g;
const IPV4 = /\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b/g;
const IPV6_FULL = /\b(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}\b/gi;
const IPV6_COMPRESSED =
  /(?<![0-9a-z:])(?:[0-9a-f]{1,4}:){1,6}(?::[0-9a-f]{1,4}){1,6}(?![0-9a-z:])|(?<![0-9a-z:])(?:[0-9a-f]{1,4}:){1,7}:(?![0-9a-z:])|(?<![0-9a-z:])::(?:[0-9a-f]{1,4}:){0,6}[0-9a-f]{1,4}(?![0-9a-z:])/gi;
const HOSTNAME = new RegExp(
  `\\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\\.)+(?:${TLDS}|local|lan|internal)\\b`,
  'gi'
);
const HOME_UNIX = /\/(?:home|Users)\/[^/\s'"]+/g;
const HOME_WIN = /[A-Za-z]:\\Users\\[^\\\s'"]+/gi;

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export interface ScrubOptions {
  /** Effective home directory to replace (for example os.homedir()). */
  homeDir?: string;
}

function scrubKeyValues(text: string): string {
  return text.replace(KEY_VALUE, (match, key: string, sep: string) =>
    isSensitiveKey(key) ? `${key}${sep}<redacted>` : match
  );
}

/**
 * Redact tokens, keys, passwords, hostnames, IPs, emails, URLs and home paths.
 * Order matters: structured shapes go before the generic ones so that a URL is
 * replaced as a whole rather than piecewise.
 */
export function scrubText(input: string, options: ScrubOptions = {}): string {
  let out = input;
  out = out.replace(PEM, '<pem>');
  out = out.replace(URL_RE, '<url:host-redacted>');
  out = out.replace(BEARER, '$1 <token>');
  out = out.replace(JWT, '<token>');
  out = out.replace(PREFIXED_TOKEN, '<token>');
  out = scrubKeyValues(out);
  out = out.replace(EMAIL, '<email>');
  if (options.homeDir && options.homeDir.length > 1) {
    out = out.replace(new RegExp(escapeRegExp(options.homeDir), 'g'), '<home>');
  }
  out = out.replace(HOME_UNIX, '<home>').replace(HOME_WIN, '<home>');
  out = out.replace(IPV6_FULL, '<ip>').replace(IPV6_COMPRESSED, '<ip>');
  out = out.replace(IPV4, '<ip>');
  out = out.replace(HOSTNAME, '<host>');
  out = out.replace(LONG_RUN, '<token>');
  return out;
}
