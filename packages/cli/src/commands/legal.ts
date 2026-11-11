import { SITE_LOCALES } from '@rediacc/locales';
import {
  LEGAL_DOCUMENTS,
  LEGAL_ENTITY,
  LEGAL_URLS,
  type LegalDocumentId,
  termsAt,
} from '@rediacc/shared/legal';
import type { Command } from 'commander';
import i18n from 'i18next';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { handleError } from '../utils/errors.js';

const TERMS_STATUS_PATH = '/account/api/v1/terms/status';
/** Where third-party notices live; `rdc legal` only points at it. */
const CREDITS_COMMAND = 'rdc credits --licenses';

interface AcceptedTerms {
  version: string;
  acceptedAt: string | null;
  method: string | null;
  /** Where the answer came from: the account server (logged in) or this config's state (anonymous). */
  source: 'account' | 'config';
}

export interface LegalInfo {
  documents: { id: LegalDocumentId; url: string; bindingUrl: string }[];
  terms: { version: string; sha256: string; effective: string; archiveUrl: string };
  /** The newest announced version that is not yet in force. */
  upcoming?: { version: string; effective: string };
  /** The acceptance on record, or null when none. */
  accepted: AcceptedTerms | null;
  entity: {
    legalName: string;
    registryCode: string;
    registerName: string;
    vatNumber: string;
    registeredAddress: string;
  };
  thirdPartyNotices: string;
}

function documentLanguage(): (typeof SITE_LOCALES)[number] {
  const lang = (i18n.language || 'en').split('-')[0];
  return (SITE_LOCALES as readonly string[]).includes(lang)
    ? (lang as (typeof SITE_LOCALES)[number])
    : 'en';
}

interface TermsStatusResponse {
  accepted?: { version?: string; acceptedAt?: string; method?: string } | null;
}

/** The acceptance on record: the account server's answer when logged in, this config's state when anonymous. A server that cannot answer leaves it unknown, reported as not accepted. */
async function acceptedTerms(): Promise<AcceptedTerms | null> {
  if (getSubscriptionTokenState().kind === 'ready') {
    try {
      const status = await accountServerFetch<TermsStatusResponse>(TERMS_STATUS_PATH);
      const accepted = status.accepted;
      return accepted?.version
        ? {
            version: accepted.version,
            acceptedAt: accepted.acceptedAt ?? null,
            method: accepted.method ?? null,
            source: 'account',
          }
        : null;
    } catch {
      return null;
    }
  }
  const stored = (await configService.getCurrent())?.state?.terms;
  return stored
    ? {
        version: stored.version,
        acceptedAt: stored.acceptedAt,
        method: stored.method,
        source: 'config',
      }
    : null;
}

export async function collectLegalInfo(now = new Date()): Promise<LegalInfo> {
  const lang = documentLanguage();
  const state = termsAt(now);
  const documents = Object.values(LEGAL_DOCUMENTS)
    .filter((doc) => doc !== undefined)
    .map((doc) => ({
      id: doc.id,
      url: LEGAL_URLS.documentUrl(doc.page, lang),
      bindingUrl: LEGAL_URLS.documentUrl(doc.page, 'en'),
    }));
  return {
    documents,
    terms: {
      version: state.current.version,
      sha256: state.current.sha256,
      effective: state.current.effective,
      archiveUrl: state.current.archiveUrl,
    },
    ...(state.upcoming
      ? { upcoming: { version: state.upcoming.version, effective: state.upcoming.effective } }
      : {}),
    accepted: await acceptedTerms(),
    entity: {
      legalName: LEGAL_ENTITY.legalName,
      registryCode: LEGAL_ENTITY.registryCode,
      registerName: LEGAL_ENTITY.registerName,
      vatNumber: LEGAL_ENTITY.vatNumber,
      registeredAddress: LEGAL_ENTITY.registeredAddress,
    },
    thirdPartyNotices: CREDITS_COMMAND,
  };
}

export function renderLegal(info: LegalInfo): string {
  const lines = [t('commands.legal.documentsTitle')];
  for (const doc of info.documents) {
    lines.push(
      doc.url === doc.bindingUrl
        ? `  ${doc.id}: ${doc.url}`
        : `  ${doc.id}: ${doc.url} (${t('commands.legal.binding')}: ${doc.bindingUrl})`
    );
  }
  lines.push(
    '',
    t('commands.legal.terms', { version: info.terms.version, effective: info.terms.effective }),
    `  sha256: ${info.terms.sha256}`,
    `  ${info.terms.archiveUrl}`
  );
  if (info.upcoming) {
    lines.push(
      t('commands.legal.upcoming', {
        version: info.upcoming.version,
        effective: info.upcoming.effective,
      })
    );
  }
  lines.push(
    info.accepted
      ? t('commands.legal.accepted', {
          version: info.accepted.version,
          at: info.accepted.acceptedAt ?? '-',
          method: info.accepted.method ?? '-',
        })
      : t('commands.legal.notAccepted'),
    '',
    t('commands.legal.entity', {
      name: info.entity.legalName,
      code: info.entity.registryCode,
      register: info.entity.registerName,
      vat: info.entity.vatNumber,
      address: info.entity.registeredAddress,
    }),
    t('commands.legal.credits', { command: info.thirdPartyNotices })
  );
  return lines.join('\n');
}

export function registerLegalCommand(program: Command): void {
  program
    .command('legal')
    .summary(t('commands.legal.descriptionShort'))
    .description(t('commands.legal.description'))
    .option('--json', t('options.json'))
    .action(async (options: { json?: boolean }) => {
      try {
        const info = await collectLegalInfo();
        const json = options.json === true || program.opts().output === 'json';
        outputService.print(json ? JSON.stringify(info, null, 2) : renderLegal(info));
      } catch (error) {
        handleError(error);
      }
    });
}
