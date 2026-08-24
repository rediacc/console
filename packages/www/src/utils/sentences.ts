import type { Language } from '../i18n/types';

/**
 * Split a catalog value into sentences, for the wrapping rule.
 *
 * THE RULE, which is not the literal one. "A line must not both end one sentence and begin
 * another" is unsatisfiable: two whole sentences sharing a line end one and begin another,
 * so read literally it forces one line per sentence. What is actually wrong is a sentence
 * BROKEN across a line boundary while SHARING either of those lines with a neighbour:
 *
 *     Most tools copy one          <- ends mid-sentence
 *     piece. We copy all of it.    <- tail of A plus the whole of B
 *
 * `Intl.Segmenter` rather than a regex on `.!?`, because the terminator is
 * language-specific: Arabic ends questions with `؟`, and Japanese with `。`. A regex would
 * have to enumerate them and would still split `e.g.` and `rediacc.com` mid-sentence.
 *
 * THROWS when Intl.Segmenter is missing instead of returning one segment. A silent
 * single-segment fallback would wrap nothing and report success, which is the shape of
 * failure this repo keeps paying for: the mechanism appears present and does nothing.
 */
export function splitSentences(text: string, lang: Language): string[] {
  if (typeof Intl.Segmenter !== 'function') {
    throw new Error(
      'Intl.Segmenter is unavailable, so sentence splitting cannot run. Failing loudly ' +
        'rather than silently emitting unwrapped text that would look correct.'
    );
  }
  const seg = new Intl.Segmenter(lang, { granularity: 'sentence' });
  const out: string[] = [];
  for (const { segment } of seg.segment(text)) {
    const trimmed = segment.trimEnd();
    if (trimmed !== '') out.push(trimmed);
  }
  return out;
}
