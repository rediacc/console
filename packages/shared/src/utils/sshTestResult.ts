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

function parseCandidate(candidate: unknown): SSHTestResult | null {
  if (!candidate) return null;

  if (typeof candidate === 'object') {
    const wrapped = candidate as SSHTestResultWrapper;
    if (typeof wrapped.result === 'string') {
      try {
        return JSON.parse(wrapped.result) as SSHTestResult;
      } catch {
        return null;
      }
    }

    return wrapped as SSHTestResult;
  }

  if (typeof candidate !== 'string') return null;

  const content = candidate.trim();
  if (!content) return null;

  // Try full JSON first
  try {
    const parsed = JSON.parse(content) as SSHTestResultWrapper;
    if (typeof parsed.result === 'string') {
      return JSON.parse(parsed.result) as SSHTestResult;
    }
    return parsed as SSHTestResult;
  } catch {
    // Fall through to line scanning
  }

  // Scan log lines for the last JSON object (renet emits logs + JSON)
  const lines = content
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (line.startsWith('{') && line.endsWith('}')) {
      try {
        return JSON.parse(line) as SSHTestResult;
      } catch {
        // Keep scanning
      }
    }
  }

  // Last resort: parse from the final '{' to the end
  const lastBrace = content.lastIndexOf('{');
  if (lastBrace >= 0) {
    const tail = content.slice(lastBrace).trim();
    try {
      return JSON.parse(tail) as SSHTestResult;
    } catch {
      return null;
    }
  }

  return null;
}

export function parseSshTestResult(params: {
  responseVaultContent?: string | null;
  consoleOutput?: string | null;
}): SSHTestResult | null {
  const fromVault = parseCandidate(params.responseVaultContent);
  if (fromVault) return fromVault;

  return parseCandidate(params.consoleOutput);
}
