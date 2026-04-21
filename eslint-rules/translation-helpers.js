import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const cachedResourcesByDir = new Map();

const loadResources = (localeDir) => {
  const resources = new Map();
  if (!fs.existsSync(localeDir)) {
    return resources;
  }

  const files = fs.readdirSync(localeDir);
  files.forEach((file) => {
    if (!file.endsWith('.json')) return;
    const namespace = path.basename(file, '.json');
    const filePath = path.join(localeDir, file);
    try {
      const contents = fs.readFileSync(filePath, 'utf8');
      resources.set(namespace, JSON.parse(contents));
    } catch {
      resources.set(namespace, null);
    }
  });

  return resources;
};

export const getResources = (localeDir) => {
  let cached = cachedResourcesByDir.get(localeDir);
  if (!cached) {
    cached = loadResources(localeDir);
    cachedResourcesByDir.set(localeDir, cached);
  }
  return cached;
};

export const getStringValue = (node) => {
  if (!node) return null;
  if (node.type === 'Literal' && typeof node.value === 'string') {
    return node.value;
  }
  if (node.type === 'TemplateLiteral' && node.expressions.length === 0) {
    return node.quasis[0]?.value?.cooked ?? null;
  }
  return null;
};

export const splitKey = (key) => {
  const colonIndex = key.indexOf(':');
  if (colonIndex === -1) {
    return { namespace: null, path: key };
  }
  return {
    namespace: key.slice(0, colonIndex),
    path: key.slice(colonIndex + 1),
  };
};

export const isNotTranslationKey = (key) => {
  if (key.startsWith('shared:')) return true;
  if (key.startsWith('node:')) return true;
  if (key === 'command:*') return true;
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(key)) return true;
  if (/^[YMDHhmsaAzZT\-/:.\s]+$/.test(key)) return true;
  if (/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?Z?$/.test(key)) return true;
  if (/^\s*[\[{]/.test(key)) return true;
  if (/^\[.+\]\s/.test(key)) return true;
  if (/^[\d\s.,;:!?-]+$/.test(key)) return true;
  if (/^-/.test(key)) return true;
  return false;
};

export const hasPath = (resource, segments) => {
  if (!resource) return false;
  let current = resource;
  for (const segment of segments) {
    if (!Object.prototype.hasOwnProperty.call(current, segment)) {
      return false;
    }
    current = current[segment];
  }
  return true;
};
