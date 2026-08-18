/**
 * Language identification for locale and documentation gates.
 *
 * WHY IT IS A LIBRARY AND NOT A COPY. This detector was built inside
 * scripts/check-i18n-cross-locale.ts and fought a long false-positive battle to get here:
 * a first version that compared values across locales reported 136 false positives on the
 * es/pt pair alone, and the two-independent-signals design below is what survived. When
 * scripts/check-docs-untranslated-text.ts was found to be PROVEN DEAD -- a wholly English
 * paragraph appended to packages/www/src/content/docs/de/quick-start.md exited 0 -- the
 * fix needed exactly this detector at paragraph granularity. Copying it would have given
 * the repo two stopword tables to drift apart, which is the shape that produced the
 * 31-copy locale list @rediacc/locales exists to replace.
 *
 * THE TWO SIGNALS, and why neither is enough alone:
 *   FUNCTION WORDS identify the language a piece of text IS. High precision, Latin-script
 *     only, because a stopword list is a Latin-alphabet instrument.
 *   WRITING SYSTEM answers whether any of a locale's own script is present at all. This is
 *     the only instrument available for ar/ja/ko/ru/zh.
 * A finding requires another language's function words to be present AND the locale's own
 * evidence to be absent, so a shared loanword, a cognate or a bare product name cannot
 * trip it.
 */

import { isSiteLocale, NON_ENGLISH_LOCALES, SITE_LOCALES } from '@rediacc/locales';

/**
 * A site locale with no way to judge it. Thrown AT STARTUP, before any scanning.
 *
 * WHY STARTUP AND NOT PER-VALUE. The skip this replaces (`if (!STOPWORDS[locale])
 * continue`) is how 379 German values lived in account-web's ar, ja, ru and zh while the
 * cross-locale gate reported a checkmark. Checking coverage lazily, as each locale is
 * reached, has the same shape of hole: a locale absent from every tree on the day would
 * never reach the check. Deriving the requirement from @rediacc/locales and asserting it
 * before the first file is opened makes "we shipped a fourteenth locale and forgot its
 * detection data" a red gate on day one, with no tree needed to trigger it.
 */
export class UnmodelledLocaleError extends Error {
  constructor(readonly locales: string[]) {
    super(
      `${locales.length} site locale(s) have no detection data: ${locales.join(', ')}.\n` +
        `Every non-English site locale needs a function-word list in STOPWORDS (Latin ` +
        `script) or a writing system in NATIVE_SCRIPT (non-Latin).\n` +
        `Skipping a locale silently is how ar/ja/ru/zh carried 379 German values through ` +
        `a green gate.`
    );
    this.name = 'UnmodelledLocaleError';
  }
}

/**
 * Function words that are frequent in one language and rare in the others we ship.
 * Deliberately small and high-precision: this answers "is this text German?", which is
 * the question that matters, rather than "do two locales match?" — the latter is useless
 * here because Spanish and Portuguese legitimately share whole strings ("cancelado",
 * "Máquinas"), as do German and French for loanwords ("Abonnement"). Matching on identical
 * values produced 136 false positives on the es/pt pair alone.
 */
export const STOPWORDS: Record<string, string[]> = {
  // `en` is never scanned as a TARGET (it is SOURCE_LOCALE), only ever as a DETECTED
  // language. Without it, English left sitting in a translated locale — the single most
  // common failure of a half-finished translation pass — was undetectable by
  // construction, exactly like German was before the de/fr/es/it/pt/tr lists existed.
  en: [
    'the',
    'and',
    'you',
    'your',
    'this',
    'that',
    'these',
    'those',
    'with',
    'from',
    'have',
    'has',
    'been',
    'will',
    'not',
    'are',
    'was',
    'were',
    'they',
    'their',
    'there',
    'which',
    'when',
    'while',
    'because',
    'before',
    'after',
    'about',
    'into',
    'only',
    'also',
    'than',
    'then',
    'each',
    'both',
    'such',
    'please',
    'cannot',
    'should',
    'would',
    'could',
    'must',
  ],
  de: [
    'nach',
    'nicht',
    'oder',
    'wird',
    'werden',
    'einen',
    'eine',
    'sie',
    'ihre',
    'mit',
    'für',
    'sind',
    'auf',
    'aus',
    'kann',
    'muss',
    'noch',
    'wenn',
    'durch',
    'bitte',
    'keine',
    'dieser',
    'diese',
  ],
  fr: [
    'vous',
    'votre',
    'les',
    'des',
    'une',
    'est',
    'pas',
    'pour',
    'avec',
    'dans',
    'sur',
    'par',
    'que',
    'qui',
    'aux',
    'ete',
    'sont',
    'cette',
    'plus',
  ],
  // 'more' used to sit here. It is an ENGLISH word, and it was the Spanish list's only
  // non-Spanish entry, so an English string anywhere scored one point towards "this is
  // Spanish". With an `en` list now present it would also have been pruned as
  // non-discriminative, silently weakening both lists. Removed rather than deduplicated.
  es: [
    'los',
    'las',
    'una',
    'para',
    'con',
    'por',
    'que',
    'del',
    'esta',
    'este',
    'son',
    'como',
    'pero',
    'todos',
  ],
  it: [
    'gli',
    'una',
    'per',
    'con',
    'che',
    'del',
    'della',
    'sono',
    'questo',
    'questa',
    'nel',
    'alla',
  ],
  pt: [
    'dos',
    'das',
    'uma',
    'para',
    'com',
    'por',
    'que',
    'nao',
    'sao',
    'este',
    'esta',
    'pelo',
    'tua',
    'teu',
    'isto',
    'muito',
    'ainda',
    'onde',
  ],
  tr: ['ve', 'bir', 'icin', 'ile', 'bu', 'olarak', 'veya', 'daha', 'gerekli'],
  // Estonian. Deliberately excludes 'on' and 'see', which are ordinary English words:
  // an English string carrying them would have scored towards Estonian and been reported
  // under the wrong source language, blunting the diagnostic the operator acts on.
  et: [
    'ja',
    'ei',
    'ning',
    'kõik',
    'peab',
    'saab',
    'tuleb',
    'palun',
    'juba',
    'ainult',
    'nende',
    'selle',
    'kuid',
    'või',
    'siis',
    'ega',
    'pole',
    'oma',
    'kas',
    'sest',
  ],
};
/**
 * The writing system each non-Latin locale is supposed to use.
 *
 * These five have no function-word list and cannot get a useful one: a stopword list is
 * a Latin-alphabet instrument, and the words that would populate it are written in a
 * script the tokenizer does not split on. For them the evidence runs the other way — a
 * value holding not one character of its own script is not a translation into it, whatever
 * language it turns out to be. Same predicate as check-locale-de-contamination.ts, which
 * proved it against the 379 real findings; here it is paired with the function-word
 * signal so a Latin PRODUCT NAME standing alone cannot trip it.
 */
export const NATIVE_SCRIPT: Record<string, RegExp> = {
  ar: /[؀-ۿݐ-ݿ]/,
  ja: /[぀-ヿ一-鿿]/,
  ko: /[가-힯ᄀ-ᇿ]/,
  ru: /[Ѐ-ӿ]/,
  zh: /[一-鿿]/,
};
/**
 * Terms that legitimately stay in Latin script in every locale. They are stripped BEFORE
 * function words are counted, because several of them tokenize into words that also sit
 * in a stopword list — "Copy-on-Write" and "Restart=on-failure" both yield "on", and a
 * value made of nothing but product syntax must score zero, not two.
 */
const TECHNICAL_TERMS = new Set([
  'rediacc',
  'renet',
  'docker',
  'compose',
  'btrfs',
  'luks',
  'ceph',
  'rbd',
  'osd',
  'mon',
  'mgr',
  'k3s',
  'kubernetes',
  'kubectl',
  'systemd',
  'ssh',
  'sftp',
  'rsync',
  'rclone',
  'criu',
  'traefik',
  'http',
  'https',
  'tcp',
  'udp',
  'dns',
  'tls',
  'ssl',
  'json',
  'yaml',
  'toml',
  'api',
  'url',
  'uri',
  'cli',
  'sdk',
  'guid',
  'uuid',
  'sha',
  'crc',
  'pem',
  'vlan',
  'nat',
  'wireguard',
  'vpn',
  'cpu',
  'gpu',
  'ram',
  'ssd',
  'nvme',
  'iops',
  'linux',
  'windows',
  'macos',
  'ubuntu',
  'debian',
  'fedora',
  'github',
  'gitlab',
  'nextcloud',
  'postgres',
  'postgresql',
  'mysql',
  'redis',
  'mongodb',
  'nginx',
  'copy',
  'write',
  'read',
  'root',
  'sudo',
  'bash',
  'git',
  'npm',
  'node',
  'python',
  'golang',
]);

/**
 * Every non-English site locale must be judgeable by one instrument or the other, and
 * every piece of detection data must name a real site locale.
 *
 * Runs AT MODULE LOAD, so it fires with no locale tree present at all. That is the point:
 * the locale universe comes from `@rediacc/locales`, which is the same declaration the
 * rest of the repo builds against, so adding a fourteenth locale there turns this gate red
 * immediately rather than the next time someone happens to look.
/**
 * Every non-English site locale must be judgeable by one instrument or the other, and
 * every piece of detection data must name a real site locale.
 *
 * Runs AT MODULE LOAD, so it fires with no locale tree present at all. That is the point:
 * the locale universe comes from `@rediacc/locales`, which is the same declaration the
 * rest of the repo builds against, so adding a fourteenth locale there turns this gate red
 * immediately rather than the next time someone happens to look.
 */
export function assertDetectionCoverage(
  stopwords: Record<string, string[]>,
  nativeScript: Record<string, RegExp>
): void {
  // A typo in a detection key is silent otherwise: `NATIVE_SCRIPT.jp` would simply never
  // match the `ja` directory, and the locale would read as covered while being skipped.
  for (const key of [...Object.keys(stopwords), ...Object.keys(nativeScript)]) {
    if (!isSiteLocale(key)) {
      throw new Error(
        `Detection data names "${key}", which is not a site locale.\n` +
          `Known: ${SITE_LOCALES.join(', ')}. Fix the typo, or declare the locale in ` +
          `packages/locales/index.js.`
      );
    }
  }
  const uncovered = NON_ENGLISH_LOCALES.filter((l) => !stopwords[l] && !nativeScript[l]);
  if (uncovered.length > 0) throw new UnmodelledLocaleError([...uncovered]);
}

/** Drop every span that carries no natural language, then every protected technical term. */
export function stripNonLanguage(value: string): string {
  return value
    .replace(/\{\{[^}]*\}\}/g, ' ')
    .replace(/%[-+ #0]*[\d.*]*(?:\[\d+\])?[a-zA-Z]/g, ' ')
    .replace(/<[^>]*>/g, ' ')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/`[^`]*`/g, ' ')
    .replace(/(?:^|[^\w-])--?[A-Za-z][\w-]*/g, ' ')
    .replace(/[A-Za-z_][\w.]*=[^\s,)]+/g, ' ')
    .replace(/[A-Za-z]\w*(?:-\w+)+/g, ' ')
    .replace(/\d+/g, ' ');
}

/** Flatten a nested catalog to dotted keys, keeping string leaves only. */
export function flatten(
  obj: unknown,
  prefix = '',
  out: Record<string, string> = {}
): Record<string, string> {
  if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const q = prefix ? `${prefix}.${k}` : k;
      if (v && typeof v === 'object') flatten(v, q, out);
      else if (typeof v === 'string') out[q] = v;
    }
  }
  return out;
}

/**
 * Words claimed by more than one language are useless for telling those languages apart,
 * and they are exactly what produced the first round of false positives: "por" and "todos"
 * sat in both the Spanish and Portuguese lists, so correct Portuguese scored as Spanish.
 * Rather than hand-curate the overlap away and get it wrong again, drop it mechanically.
 */
export const DISCRIMINATIVE: Record<string, Set<string>> = (() => {
  const counts = new Map<string, number>();
  for (const words of Object.values(STOPWORDS)) {
    for (const w of new Set(words)) counts.set(w, (counts.get(w) ?? 0) + 1);
  }
  return Object.fromEntries(
    Object.entries(STOPWORDS).map(([lang, words]) => [
      lang,
      new Set(words.filter((w) => counts.get(w) === 1)),
    ])
  );
})();

// STARTUP, not lazily. Nothing that imports this module runs if a site locale is unmodellable.
assertDetectionCoverage(STOPWORDS, NATIVE_SCRIPT);

export const norm = (s: string) =>
  s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');

/** The prose words of a value: markup, syntax and protected technical terms removed. */
export function contentWords(text: string): string[] {
  return norm(text)
    .split(/[^a-z]+/)
    .filter((w) => w.length > 1 && !TECHNICAL_TERMS.has(w));
}

/** Score how strongly a string looks like each language. Returns the best match, or null. */
export function identify(text: string): { lang: string; score: number } | null {
  const words = contentWords(text);
  if (words.length < 3) return null;
  const set = new Set(words);
  let best: { lang: string; score: number } | null = null;
  for (const [lang, stops] of Object.entries(DISCRIMINATIVE)) {
    const score = [...stops].filter((w) => set.has(norm(w))).length;
    if (score > 0 && (!best || score > best.score)) best = { lang, score };
  }
  return best;
}
