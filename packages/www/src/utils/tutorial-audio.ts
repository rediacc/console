import { LOCALE_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { Language } from '../i18n/types';
import type { TutorialAudioManifestDocument } from '../types/tutorial-audio';

const audioModules = import.meta.glob<{ default: TutorialAudioManifestDocument }>(
  '../data/tutorial-audio/*/*.json',
  {
    eager: true,
  }
) as Partial<Record<string, { default: TutorialAudioManifestDocument }>>;

function normalizeLang(lang: string | undefined | null): Language {
  const short = String(lang ?? LOCALE_DEFAULTS.LANGUAGE)
    .toLowerCase()
    .split('-')[0] as Language;
  return short;
}

function lookupAudioManifest(
  castKey: string,
  lang: Language
): TutorialAudioManifestDocument | null {
  const key = `../data/tutorial-audio/${lang}/${castKey}.json`;
  return audioModules[key]?.default ?? null;
}

export function loadTutorialAudio(
  castKey: string,
  lang?: string
): TutorialAudioManifestDocument | null {
  const requestedLang = normalizeLang(lang);
  return lookupAudioManifest(castKey, requestedLang) ?? lookupAudioManifest(castKey, 'en');
}
