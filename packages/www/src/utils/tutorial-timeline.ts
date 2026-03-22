import { LOCALE_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { Language } from '../i18n/types';
import type { TutorialTimelineDocument } from '../types/tutorial-timeline';

const timelineModules = import.meta.glob<{ default: TutorialTimelineDocument }>(
  '../data/tutorial-timeline/*/*.json',
  {
    eager: true,
  }
) as Partial<Record<string, { default: TutorialTimelineDocument }>>;

function normalizeLang(lang: string | undefined | null): Language {
  const short = String(lang ?? LOCALE_DEFAULTS.LANGUAGE)
    .toLowerCase()
    .split('-')[0] as Language;
  return short;
}

function lookupTimeline(castKey: string, lang: Language): TutorialTimelineDocument | null {
  const key = `../data/tutorial-timeline/${lang}/${castKey}.json`;
  return timelineModules[key]?.default ?? null;
}

export function loadTutorialTimeline(
  castKey: string,
  lang?: string
): TutorialTimelineDocument | null {
  const requestedLang = normalizeLang(lang);
  return lookupTimeline(castKey, requestedLang) ?? lookupTimeline(castKey, 'en');
}
