/**
 * ESLint rule to detect untranslated tutorial transcript event text in non-English locale files.
 * Compares events[].text against English transcript with the same cast filename.
 */

import fs from 'node:fs';
import path from 'node:path';

let englishCache = new Map();

function loadEnglishTranscript(transcriptsDir, castFile) {
  const cacheKey = `${transcriptsDir}:${castFile}`;
  if (englishCache.has(cacheKey)) return englishCache.get(cacheKey);

  const enFile = path.join(transcriptsDir, 'en', castFile);
  try {
    const content = JSON.parse(fs.readFileSync(enFile, 'utf-8'));
    const map = new Map();
    const events = Array.isArray(content?.events) ? content.events : [];
    for (let i = 0; i < events.length; i += 1) {
      const text = typeof events[i]?.text === 'string' ? events[i].text : '';
      map.set(i, text);
    }
    englishCache.set(cacheKey, map);
    return map;
  } catch {
    return new Map();
  }
}

/** @type {import('eslint').Rule.RuleModule} */
export const noUntranslatedTutorialTranscriptValues = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Detect untranslated tutorial transcript events in non-English locale files',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          transcriptsDir: {
            type: 'string',
            description: 'Path to tutorial transcript root directory',
          },
          minLength: {
            type: 'number',
            default: 3,
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      untranslated:
        'events[{{index}}].text is identical to English and appears untranslated: "{{value}}"',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const transcriptsDir = options.transcriptsDir || 'packages/www/src/data/tutorial-transcripts';
    const minLength = options.minLength ?? 3;

    const projectRoot = process.cwd();
    const absoluteTranscriptsDir = path.isAbsolute(transcriptsDir)
      ? transcriptsDir
      : path.join(projectRoot, transcriptsDir);

    const filename = context.filename;
    const castFile = path.basename(filename);
    const lang = path.basename(path.dirname(filename));

    if (lang === 'en') return {};

    const englishEvents = loadEnglishTranscript(absoluteTranscriptsDir, castFile);

    function visitObjectNode(node, onMember) {
      if (!node || node.type !== 'Object') return;
      const members = node.members || [];
      for (const member of members) {
        if (member.type === 'Member') onMember(member);
      }
    }

    function getStringMemberValue(objNode, keyName) {
      let result = null;
      visitObjectNode(objNode, (member) => {
        const key = member.name?.type === 'String' ? member.name.value : member.name?.name;
        if (key !== keyName) return;
        if (member.value?.type === 'String') result = member.value.value;
      });
      return result;
    }

    return {
      Document(node) {
        if (!node?.body || node.body.type !== 'Object') return;

        let eventsArray = null;
        visitObjectNode(node.body, (member) => {
          const key = member.name?.type === 'String' ? member.name.value : member.name?.name;
          if (key === 'events' && member.value?.type === 'Array') {
            eventsArray = member.value;
          }
        });

        if (!eventsArray || !Array.isArray(eventsArray.elements)) return;

        for (let i = 0; i < eventsArray.elements.length; i += 1) {
          const eventNode = eventsArray.elements[i];
          if (!eventNode || eventNode.type !== 'Object') continue;

          const text = getStringMemberValue(eventNode, 'text');
          if (typeof text !== 'string' || text.trim().length < minLength) continue;

          const enText = englishEvents.get(i);
          if (typeof enText !== 'string' || enText.trim().length < minLength) continue;

          if (text.trim() === enText.trim()) {
            context.report({
              node: eventNode,
              messageId: 'untranslated',
              data: {
                index: String(i),
                value: text.length > 50 ? `${text.slice(0, 47)}...` : text,
              },
            });
          }
        }
      },
    };
  },
};

export default noUntranslatedTutorialTranscriptValues;
