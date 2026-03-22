import { LOCALE_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { Language } from '../i18n/types';
import type { TutorialTranscriptDocument } from '../types/tutorial-transcripts';

const transcriptModules = import.meta.glob<{ default: TutorialTranscriptDocument }>(
  '../data/tutorial-transcripts/*/*.json',
  {
    eager: true,
  }
) as Partial<Record<string, { default: TutorialTranscriptDocument }>>;

function normalizeLang(lang: string | undefined | null): Language {
  const short = String(lang ?? LOCALE_DEFAULTS.LANGUAGE)
    .toLowerCase()
    .split('-')[0] as Language;
  return short;
}

function lookupTranscript(castKey: string, lang: Language): TutorialTranscriptDocument | null {
  const key = `../data/tutorial-transcripts/${lang}/${castKey}.json`;
  return transcriptModules[key]?.default ?? null;
}

export function loadTranscript(castKey: string, lang?: string): TutorialTranscriptDocument | null {
  const requestedLang = normalizeLang(lang);
  return lookupTranscript(castKey, requestedLang) ?? lookupTranscript(castKey, 'en');
}
