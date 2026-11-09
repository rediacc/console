import React from 'react';
import type { Language } from '../i18n/types';
import { splitSentences } from '../utils/sentences';

interface SentencesProps {
  text: string;
  lang: Language;
}

/**
 * React twin of Sentences.astro: each sentence of a multi-sentence catalog value becomes
 * an atomic `.sentence` line-breaking unit. A single sentence renders as plain text with
 * no markup.
 */
const Sentences: React.FC<SentencesProps> = ({ text, lang }) => {
  const parts = splitSentences(text, lang);
  if (parts.length < 2) return <>{text}</>;
  return (
    <>
      {parts.map((sentence, i) => (
        <React.Fragment key={sentence}>
          {i > 0 && ' '}
          <span className="sentence">{sentence}</span>
        </React.Fragment>
      ))}
    </>
  );
};

export default Sentences;
