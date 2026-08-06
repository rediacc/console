/**
 * ESLint rule to detect untranslated tutorial transcript event text in non-English locale files.
 * Compares events[].text against English transcript with the same cast filename.
 */

import fs from 'node:fs';
import path from 'node:path';
import { memberKey, objectMembers } from './shared/json-ast.js';

const englishCache = new Map();

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

// Rule-option default: values shorter than this are too small to judge as
// "identical to English" (product names, "OK", punctuation).
const DEFAULT_MIN_LENGTH = 3;

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
        'events[{{index}}].text is identical to English and appears untranslated: "{{value}}". See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const transcriptsDir = options.transcriptsDir || 'packages/www/src/data/tutorial-transcripts';
    const minLength = options.minLength ?? DEFAULT_MIN_LENGTH;

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
      for (const member of objectMembers(node)) {
        if (member.type === 'Member') onMember(member);
      }
    }

    function getStringMemberValue(objNode, keyName) {
      let result = null;
      visitObjectNode(objNode, (member) => {
        if (memberKey(member) !== keyName) return;
        if (member.value?.type === 'String') result = member.value.value;
      });
      return result;
    }

    /** The `events` array of a transcript document, or null. */
    function findEventsArray(objNode) {
      let eventsArray = null;
      visitObjectNode(objNode, (member) => {
        if (memberKey(member) === 'events' && member.value?.type === 'Array') {
          eventsArray = member.value;
        }
      });
      return eventsArray;
    }

    /** Report one event whose text is byte-identical to the English cast. */
    function checkEvent(element, index) {
      // @eslint/json wraps every array entry in an `Element` node whose
      // `value` is the real node. Comparing the WRAPPER against 'Object' made
      // this rule inert: `element.type` is 'Element' for every entry, so the
      // walk returned before it ever looked at an event.
      const eventNode = element?.type === 'Element' ? element.value : element;
      if (!eventNode || eventNode.type !== 'Object') return;

      const text = getStringMemberValue(eventNode, 'text');
      if (typeof text !== 'string' || text.trim().length < minLength) return;

      const enText = englishEvents.get(index);
      if (typeof enText !== 'string' || enText.trim().length < minLength) return;

      if (text.trim() !== enText.trim()) return;

      context.report({
        node: eventNode,
        messageId: 'untranslated',
        data: {
          index: String(index),
          value: text.length > 50 ? `${text.slice(0, 47)}...` : text,
        },
      });
    }

    return {
      Document(node) {
        if (!node?.body || node.body.type !== 'Object') return;

        const eventsArray = findEventsArray(node.body);
        if (!eventsArray || !Array.isArray(eventsArray.elements)) return;

        eventsArray.elements.forEach(checkEvent);
      },
    };
  },
};

export default noUntranslatedTutorialTranscriptValues;
