export interface SSHTestResult {
  status: string;
  message?: string;
  ssh_key_configured?: boolean;
  known_hosts?: string;
  public_key_deployed?: boolean;
  kernel_compatibility?: {
    os_setup_completed?: boolean;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

type SSHTestResultWrapper = SSHTestResult & { result?: string };

/** Try to parse JSON string safely */
function tryParseJson(content: string): unknown {
  try {
    return JSON.parse(content);
  } catch {
    return null;
  }
}

/** Unwrap a result wrapper if it contains a nested result string */
function unwrapResult(parsed: SSHTestResultWrapper): SSHTestResult | null {
  if (typeof parsed.result === 'string') {
    const inner = tryParseJson(parsed.result);
    return inner as SSHTestResult | null;
  }
  return parsed as SSHTestResult;
}

/** Try to parse an object candidate */
function parseObjectCandidate(candidate: object): SSHTestResult | null {
  const wrapped = candidate as SSHTestResultWrapper;
  if (typeof wrapped.result !== 'string') {
    return wrapped as SSHTestResult;
  }
  const inner = tryParseJson(wrapped.result);
  return inner as SSHTestResult | null;
}

/** Try to parse full JSON content */
function parseFullJson(content: string): SSHTestResult | null {
  const parsed = tryParseJson(content);
  if (!parsed || typeof parsed !== 'object') {
    return null;
  }
  return unwrapResult(parsed as SSHTestResultWrapper);
}

/** Scan lines from end for JSON object */
function scanLinesForJson(content: string): SSHTestResult | null {
  const lines = content
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (line.startsWith('{') && line.endsWith('}')) {
      const parsed = tryParseJson(line);
      if (parsed) {
        return parsed as SSHTestResult;
      }
    }
  }
  return null;
}

/** Try to parse from the last '{' to end of content */
function parseFromLastBrace(content: string): SSHTestResult | null {
  const lastBrace = content.lastIndexOf('{');
  if (lastBrace < 0) {
    return null;
  }
  const tail = content.slice(lastBrace).trim();
  const parsed = tryParseJson(tail);
  return parsed as SSHTestResult | null;
}

function parseCandidate(candidate: unknown): SSHTestResult | null {
  if (!candidate) return null;

  if (typeof candidate === 'object') {
    return parseObjectCandidate(candidate);
  }

  if (typeof candidate !== 'string') return null;

  const content = candidate.trim();
  if (!content) return null;

  // Try full JSON first
  const fullJsonResult = parseFullJson(content);
  if (fullJsonResult) {
    return fullJsonResult;
  }

  // Scan log lines for the last JSON object (renet emits logs + JSON)
  const lineResult = scanLinesForJson(content);
  if (lineResult) {
    return lineResult;
  }

  // Last resort: parse from the final '{' to the end
  return parseFromLastBrace(content);
}

export function parseSshTestResult(params: {
  responseVaultContent?: string | null;
  consoleOutput?: string | null;
}): SSHTestResult | null {
  const fromVault = parseCandidate(params.responseVaultContent);
  if (fromVault) return fromVault;

  return parseCandidate(params.consoleOutput);
}
