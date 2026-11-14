/**
 * Terms acceptance for the anonymous Free License (PLAN-terms-acceptance Design 5).
 *
 * The acceptance is the CLI's half of the contract: a terminal asks y/N (default N), an unattended
 * run (agent, non-TTY or `--yes`) needs `--accept-terms` or `RDC_ACCEPT_TERMS=1`, and `--yes` alone
 * never accepts. The accepted version is cached in the config's `state.terms` (host-local, never
 * pushed), so later fetches send it without asking until the latest material version changes.
 * The notice texts come from the shared legal module and are never written here.
 */

import {
  CONSENT_NOTICES,
  consentNotice,
  LEGAL_ENTITY,
  LEGAL_URLS,
  satisfies,
  termsAt,
} from '@rediacc/shared/legal';
import i18n from 'i18next';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { t } from '../../i18n/index.js';
import { isAgentEnvironment } from '../../utils/agent-guard.js';
import { ValidationError } from '../../utils/errors.js';
import { askConfirm } from '../../utils/prompt.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { configService } from '../config/config-resources.js';

/** The two methods the CLI gives an acceptance by. */
type CliTermsMethod = 'cli-prompt' | 'cli-flag-unattended';

/** The acceptance a FREE request carries (`termsAcceptance` in the POST /licenses/free body). */
export interface TermsAcceptance {
  version: string;
  sha256: string;
  locale: string;
  method: CliTermsMethod;
}

/** The cached acceptance, as stored in `state.terms`. */
interface StoredTermsAcceptance {
  version: string;
  sha256: string;
  acceptedAt: string;
  method: CliTermsMethod;
}

type SiteLocale = keyof typeof CONSENT_NOTICES;

/** Set by the global `--accept-terms` option for this process. */
let acceptTermsFlag = false;
/** The acceptance in force for this process, so one run asks once. */
let processAcceptance: TermsAcceptance | undefined;

/** Record the global `--accept-terms` option. */
export function setAcceptTermsFlag(value: boolean): void {
  acceptTermsFlag = value;
}

/** Test seam: forget the process-wide flag and acceptance. */
export function resetTermsStateForTests(): void {
  acceptTermsFlag = false;
  processAcceptance = undefined;
}

/** Whether `--accept-terms` or `RDC_ACCEPT_TERMS=1` is set. `--yes` is deliberately not consulted. */
function acceptsTermsUnattended(): boolean {
  return acceptTermsFlag || process.env.RDC_ACCEPT_TERMS === '1';
}

function currentLocale(): SiteLocale {
  const lang = (i18n.language || 'en').split('-')[0];
  return lang in CONSENT_NOTICES ? (lang as SiteLocale) : 'en';
}

/** The newest Terms version: what a FREE request must have accepted. */
function latestTerms() {
  return termsAt(new Date()).latest;
}

function fillTokens(text: string): string {
  return text
    .replaceAll('{{termsUrl}}', LEGAL_URLS.terms)
    .replaceAll('{{privacyUrl}}', LEGAL_URLS.privacy)
    .replaceAll('{{legalName}}', LEGAL_ENTITY.legalName);
}

/** The canonical notice for `method` in the CLI language, else English; a catalog with neither is a build defect. */
function noticeFor(method: CliTermsMethod): string {
  const text = consentNotice(method, currentLocale()) || consentNotice(method, 'en');
  if (!text) throw new Error(`legal: no ${method} consent notice in the shared legal module`);
  return fillTokens(text);
}

/** The refusal an unattended run without the flag gets: it names the flag, the env var and the URL. */
function termsRefusalMessage(): string {
  return noticeFor('cli-flag-unattended');
}

function toBody(
  stored: Pick<StoredTermsAcceptance, 'version' | 'sha256' | 'method'>
): TermsAcceptance {
  return {
    version: stored.version,
    sha256: stored.sha256,
    locale: currentLocale(),
    method: stored.method,
  };
}

/** The cached acceptance when it still satisfies the latest version, else undefined. */
async function cachedAcceptance(): Promise<StoredTermsAcceptance | undefined> {
  const stored = (await configService.getCurrent())?.state?.terms;
  if (!stored) return undefined;
  return satisfies(stored.version, latestTerms().version) ? stored : undefined;
}

async function storeAcceptance(stored: StoredTermsAcceptance): Promise<void> {
  const configName = getEffectiveConfigName();
  if (!(await configFileStorage.exists(configName))) return;
  await configFileStorage.updateState(configName, (config) => ({
    ...config,
    state: { ...(config.state ?? {}), terms: stored },
  }));
}

function isInteractiveHuman(): boolean {
  return (
    process.stdin.isTTY === true &&
    process.stdout.isTTY === true &&
    !isAgentEnvironment() &&
    process.env.REDIACC_YES !== '1'
  );
}

/**
 * Settle the acceptance a FREE licence needs, before any network call.
 *
 * - A cached acceptance that still satisfies the latest version: sent again, nothing asked.
 * - `--accept-terms` or `RDC_ACCEPT_TERMS=1`: accepted without asking, recorded as `cli-flag-unattended`.
 * - A terminal with no agent and no `--yes`: the `cliPrompt` notice, y/N, default N. N throws.
 * - Anything else: the `cliRefusal` notice is thrown.
 */
export async function ensureTermsAcceptance(): Promise<TermsAcceptance> {
  if (processAcceptance) return processAcceptance;
  const cached = await cachedAcceptance();
  if (cached) {
    processAcceptance = toBody(cached);
    return processAcceptance;
  }
  let method: CliTermsMethod;
  if (acceptsTermsUnattended()) {
    method = 'cli-flag-unattended';
  } else if (isInteractiveHuman()) {
    if (!(await askConfirm(noticeFor('cli-prompt'), false))) {
      throw new ValidationError(t('errors.terms.declined'));
    }
    method = 'cli-prompt';
  } else {
    throw new ValidationError(termsRefusalMessage());
  }
  const latest = latestTerms();
  const stored: StoredTermsAcceptance = {
    version: latest.version,
    sha256: latest.sha256,
    acceptedAt: new Date().toISOString(),
    method,
  };
  await storeAcceptance(stored);
  processAcceptance = toBody(stored);
  return processAcceptance;
}
