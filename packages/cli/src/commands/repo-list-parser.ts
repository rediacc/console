export function parseRepositoryListOutput(stdout: string): Record<string, unknown>[] {
  const trimmed = stdout.trim();
  const candidates = collectCandidates(trimmed);

  for (const candidate of candidates) {
    const parsed = parseJsonArray(candidate);
    if (parsed) {
      return parsed;
    }
  }

  throw new Error(`Failed to parse repository list JSON from output: ${trimmed.slice(0, 200)}`);
}

function collectCandidates(trimmed: string): string[] {
  const candidates = [trimmed];
  const collected = collectLineDelimitedJson(trimmed);

  if (collected) {
    candidates.unshift(collected);
  }

  const arrayStart = trimmed.indexOf('[{');
  if (arrayStart >= 0) {
    candidates.push(trimmed.slice(arrayStart));
  }

  const emptyArrayStart = trimmed.indexOf('[]');
  if (emptyArrayStart >= 0) {
    candidates.push(trimmed.slice(emptyArrayStart));
  }

  return candidates;
}

function collectLineDelimitedJson(trimmed: string): string | null {
  const lines = trimmed.split('\n').map((line) => line.replace(/^\[[^\]]+\]\s/, '').trimEnd());
  const jsonLines: string[] = [];
  let collecting = false;

  for (const line of lines) {
    const stripped = line.trimStart();
    if (!collecting) {
      const looksLikeJsonArray = stripped === '[' || stripped === '[]' || stripped.startsWith('[{');
      if (!looksLikeJsonArray) {
        continue;
      }
      collecting = true;
    }

    jsonLines.push(stripped);
    const candidate = jsonLines.join('\n');
    if (parseJsonArray(candidate)) {
      return candidate;
    }
  }

  return null;
}

function parseJsonArray(candidate: string): Record<string, unknown>[] | null {
  try {
    const parsed = JSON.parse(candidate) as unknown;
    return Array.isArray(parsed) ? (parsed as Record<string, unknown>[]) : null;
  } catch {
    return null;
  }
}
