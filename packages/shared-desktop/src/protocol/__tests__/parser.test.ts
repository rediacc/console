import { describe, expect, it } from 'vitest';
import {
  buildCliCommand,
  buildProtocolUrl,
  PROTOCOL_SCHEME,
  parseProtocolUrl,
  VALID_ACTIONS,
  validateToken,
} from '../parser.js';

// Valid test token (32+ chars, alphanumeric with dots/dashes/underscores)
const VALID_TOKEN = 'abcdef1234567890abcdef1234567890';
const VALID_TOKEN_WITH_SPECIAL = 'abc-def_123.456-789_abc.def_1234'; // 32 chars

describe('validateToken', () => {
  it('should accept valid 32+ char alphanumeric token', () => {
    expect(validateToken(VALID_TOKEN)).toBe(true);
  });

  it('should accept token with dots, dashes, and underscores', () => {
    expect(validateToken(VALID_TOKEN_WITH_SPECIAL)).toBe(true);
  });

  it('should accept exactly 32 character token', () => {
    expect(validateToken('a'.repeat(32))).toBe(true);
  });

  it('should reject token shorter than 32 chars', () => {
    expect(validateToken('a'.repeat(31))).toBe(false);
  });

  it('should reject empty string', () => {
    expect(validateToken('')).toBe(false);
  });

  it('should reject null/undefined', () => {
    expect(validateToken(null as unknown as string)).toBe(false);
    expect(validateToken(undefined as unknown as string)).toBe(false);
  });

  it('should reject token with special characters', () => {
    expect(validateToken('abcdef1234567890abcdef12345678@#')).toBe(false);
    expect(validateToken('abcdef1234567890abcdef1234567890!')).toBe(false);
  });

  it('should reject token with spaces', () => {
    expect(validateToken('abcdef1234567890abcdef 1234567890')).toBe(false);
  });

  it('should reject token with newlines', () => {
    expect(validateToken('abcdef1234567890abcdef1234567890\n')).toBe(false);
    expect(validateToken('abcdef1234567890abcdef\n1234567890')).toBe(false);
  });
});

describe('parseProtocolUrl - scheme validation', () => {
  it('should throw for non-rediacc scheme', () => {
    expect(() => parseProtocolUrl('http://example.com')).toThrow(
      `Invalid protocol scheme. Expected ${PROTOCOL_SCHEME}://`
    );
  });

  it('should throw for https scheme', () => {
    expect(() => parseProtocolUrl('https://example.com')).toThrow(
      `Invalid protocol scheme. Expected ${PROTOCOL_SCHEME}://`
    );
  });
});

describe('parseProtocolUrl - path format parsing', () => {
  it('should parse basic URL with team and machine', () => {
    const url = `rediacc://${VALID_TOKEN}/MyTeam/MyMachine`;
    const result = parseProtocolUrl(url);

    expect(result.token).toBe(VALID_TOKEN);
    expect(result.teamName).toBe('MyTeam');
    expect(result.machineName).toBe('MyMachine');
    expect(result.repositoryName).toBeUndefined();
    expect(result.action).toBe('desktop');
  });

  it('should parse URL with repository', () => {
    const url = `rediacc://${VALID_TOKEN}/MyTeam/MyMachine/MyRepo`;
    const result = parseProtocolUrl(url);

    expect(result.teamName).toBe('MyTeam');
    expect(result.machineName).toBe('MyMachine');
    expect(result.repositoryName).toBe('MyRepo');
    expect(result.action).toBe('desktop');
  });

  it('should parse URL with explicit action', () => {
    const url = `rediacc://${VALID_TOKEN}/MyTeam/MyMachine/terminal`;
    const result = parseProtocolUrl(url);

    expect(result.teamName).toBe('MyTeam');
    expect(result.machineName).toBe('MyMachine');
    expect(result.repositoryName).toBeUndefined();
    expect(result.action).toBe('terminal');
  });

  it('should parse URL with repository and action', () => {
    const url = `rediacc://${VALID_TOKEN}/MyTeam/MyMachine/MyRepo/sync`;
    const result = parseProtocolUrl(url);

    expect(result.teamName).toBe('MyTeam');
    expect(result.machineName).toBe('MyMachine');
    expect(result.repositoryName).toBe('MyRepo');
    expect(result.action).toBe('sync');
  });

  it('should parse URL with token as hostname', () => {
    const url = `rediacc://${VALID_TOKEN}/MyTeam/MyMachine`;
    const result = parseProtocolUrl(url);

    expect(result.token).toBe(VALID_TOKEN);
    expect(result.teamName).toBe('MyTeam');
    expect(result.machineName).toBe('MyMachine');
  });
});

describe('parseProtocolUrl - action parsing', () => {
  for (const action of VALID_ACTIONS) {
    it(`should parse ${action} action`, () => {
      const url = `rediacc://${VALID_TOKEN}/Team/Machine/${action}`;
      const result = parseProtocolUrl(url);
      expect(result.action).toBe(action);
    });
  }

  it('should default to desktop action when none specified', () => {
    const url = `rediacc://${VALID_TOKEN}/Team/Machine`;
    const result = parseProtocolUrl(url);
    expect(result.action).toBe('desktop');
  });

  it('should throw for invalid action', () => {
    const url = `rediacc://${VALID_TOKEN}/Team/Machine/Repo/invalid-action`;
    expect(() => parseProtocolUrl(url)).toThrow("Invalid action 'invalid-action'");
  });
});

describe('parseProtocolUrl - query parameters', () => {
  it('should parse query parameters', () => {
    const url = `rediacc://${VALID_TOKEN}/Team/Machine/sync?direction=upload&localPath=/home/user`;
    const result = parseProtocolUrl(url);

    expect(result.params).toEqual({
      direction: 'upload',
      localPath: '/home/user',
    });
  });

  it('should return empty object when no params', () => {
    const url = `rediacc://${VALID_TOKEN}/Team/Machine`;
    const result = parseProtocolUrl(url);

    expect(result.params).toEqual({});
  });
});

describe('parseProtocolUrl - URL-encoded components', () => {
  it('should decode URL-encoded team name', () => {
    const url = `rediacc://${VALID_TOKEN}/My%20Team/Machine`;
    const result = parseProtocolUrl(url);
    expect(result.teamName).toBe('My Team');
  });

  it('should decode URL-encoded machine name', () => {
    const url = `rediacc://${VALID_TOKEN}/Team/My%20Machine`;
    const result = parseProtocolUrl(url);
    expect(result.machineName).toBe('My Machine');
  });

  it('should decode URL-encoded repository name', () => {
    const url = `rediacc://${VALID_TOKEN}/Team/Machine/My%20Repo`;
    const result = parseProtocolUrl(url);
    expect(result.repositoryName).toBe('My Repo');
  });
});

describe('parseProtocolUrl - error handling', () => {
  it('should throw for missing team and machine', () => {
    const url = `rediacc://${VALID_TOKEN}`;
    expect(() => parseProtocolUrl(url)).toThrow(
      'URL must contain at least token, team, and machine'
    );
  });

  it('should throw for invalid token', () => {
    const url = 'rediacc://short/Team/Machine';
    expect(() => parseProtocolUrl(url)).toThrow('Invalid or missing authentication token');
  });
});

describe('buildCliCommand - sync', () => {
  const baseParsed = {
    token: VALID_TOKEN,
    teamName: 'MyTeam',
    machineName: 'MyMachine',
    params: {},
  };

  it('should build sync download command', () => {
    const parsed = { ...baseParsed, action: 'sync' as const, params: { direction: 'download' } };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('sync');
    expect(cmd).toContain('download');
    expect(cmd).toContain('--team');
    expect(cmd).toContain('MyTeam');
    expect(cmd).toContain('--machine');
    expect(cmd).toContain('MyMachine');
  });

  it('should build sync upload command', () => {
    const parsed = { ...baseParsed, action: 'sync' as const, params: { direction: 'upload' } };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('upload');
  });

  it('should default to download direction', () => {
    const parsed = { ...baseParsed, action: 'sync' as const, params: {} };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('download');
  });

  it('should include localPath when provided', () => {
    const parsed = {
      ...baseParsed,
      action: 'sync' as const,
      params: { direction: 'download', localPath: '/home/user/project' },
    };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('--local');
    expect(cmd).toContain('/home/user/project');
  });

  it('should include mirror flag when true', () => {
    const parsed = {
      ...baseParsed,
      action: 'sync' as const,
      params: { direction: 'download', mirror: 'true' },
    };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('--mirror');
  });

  it('should include verify flag when true', () => {
    const parsed = {
      ...baseParsed,
      action: 'sync' as const,
      params: { direction: 'download', verify: 'true' },
    };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('--verify');
  });

  it('should throw for invalid direction', () => {
    const parsed = {
      ...baseParsed,
      action: 'sync' as const,
      params: { direction: 'invalid' },
    };

    expect(() => buildCliCommand(parsed)).toThrow('Invalid sync direction: invalid');
  });
});

describe('buildCliCommand - terminal', () => {
  const baseParsed = {
    token: VALID_TOKEN,
    teamName: 'MyTeam',
    machineName: 'MyMachine',
    params: {},
  };

  it('should build terminal command', () => {
    const parsed = { ...baseParsed, action: 'terminal' as const };
    const cmd = buildCliCommand(parsed);

    expect(cmd[0]).toBe('term');
    expect(cmd).toContain('--token');
    expect(cmd).toContain('--team');
    expect(cmd).toContain('--machine');
  });

  it('should include repository when provided', () => {
    const parsed = { ...baseParsed, action: 'terminal' as const, repositoryName: 'MyRepo' };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('--repository');
    expect(cmd).toContain('MyRepo');
  });

  it('should include command when provided', () => {
    const parsed = {
      ...baseParsed,
      action: 'terminal' as const,
      params: { command: 'ls -la' },
    };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('--command');
    expect(cmd).toContain('ls -la');
  });

  it('should handle container terminal type', () => {
    const parsed = {
      ...baseParsed,
      action: 'terminal' as const,
      repositoryName: 'MyRepo',
      params: { terminalType: 'container', containerId: 'abc123' },
    };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('--command');
    expect(cmd.join(' ')).toContain('docker exec');
  });
});

describe('buildCliCommand - vscode', () => {
  const baseParsed = {
    token: VALID_TOKEN,
    teamName: 'MyTeam',
    machineName: 'MyMachine',
    params: {},
  };

  it('should build vscode command', () => {
    const parsed = { ...baseParsed, action: 'vscode' as const };
    const cmd = buildCliCommand(parsed);

    expect(cmd[0]).toBe('vscode');
  });

  it('should include path when provided', () => {
    const parsed = {
      ...baseParsed,
      action: 'vscode' as const,
      params: { path: '/src/app' },
    };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('--path');
    expect(cmd).toContain('/src/app');
  });
});

describe('buildCliCommand - desktop', () => {
  const baseParsed = {
    token: VALID_TOKEN,
    teamName: 'MyTeam',
    machineName: 'MyMachine',
    params: {},
  };

  it('should build desktop command', () => {
    const parsed = { ...baseParsed, action: 'desktop' as const };
    const cmd = buildCliCommand(parsed);

    expect(cmd[0]).toBe('desktop');
  });

  it('should include container-id when provided', () => {
    const parsed = {
      ...baseParsed,
      action: 'desktop' as const,
      params: { containerId: 'abc123' },
    };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('--container-id');
    expect(cmd).toContain('abc123');
  });
});

describe('buildCliCommand - common parameters', () => {
  const baseParsed = {
    token: VALID_TOKEN,
    teamName: 'MyTeam',
    machineName: 'MyMachine',
    params: {},
  };

  it('should include apiUrl for all commands', () => {
    const parsed = {
      ...baseParsed,
      action: 'terminal' as const,
      params: { apiUrl: 'https://api.example.com' },
    };
    const cmd = buildCliCommand(parsed);

    expect(cmd).toContain('--api-url');
    expect(cmd).toContain('https://api.example.com');
  });
});

describe('buildProtocolUrl', () => {
  it('should build basic URL with token, team, and machine', () => {
    const url = buildProtocolUrl({
      token: VALID_TOKEN,
      teamName: 'MyTeam',
      machineName: 'MyMachine',
    });

    expect(url).toBe(`rediacc://${VALID_TOKEN}/MyTeam/MyMachine`);
  });

  it('should include repository when provided', () => {
    const url = buildProtocolUrl({
      token: VALID_TOKEN,
      teamName: 'MyTeam',
      machineName: 'MyMachine',
      repositoryName: 'MyRepo',
    });

    expect(url).toBe(`rediacc://${VALID_TOKEN}/MyTeam/MyMachine/MyRepo`);
  });

  it('should include action when not desktop', () => {
    const url = buildProtocolUrl({
      token: VALID_TOKEN,
      teamName: 'MyTeam',
      machineName: 'MyMachine',
      action: 'terminal',
    });

    expect(url).toBe(`rediacc://${VALID_TOKEN}/MyTeam/MyMachine/terminal`);
  });

  it('should not include action when desktop (default)', () => {
    const url = buildProtocolUrl({
      token: VALID_TOKEN,
      teamName: 'MyTeam',
      machineName: 'MyMachine',
      action: 'desktop',
    });

    expect(url).toBe(`rediacc://${VALID_TOKEN}/MyTeam/MyMachine`);
  });

  it('should include query parameters', () => {
    const url = buildProtocolUrl({
      token: VALID_TOKEN,
      teamName: 'MyTeam',
      machineName: 'MyMachine',
      action: 'sync',
      params: { direction: 'upload', localPath: '/home/user' },
    });

    expect(url).toContain('?');
    expect(url).toContain('direction=upload');
    expect(url).toContain('localPath=');
  });

  it('should URL-encode special characters in team name', () => {
    const url = buildProtocolUrl({
      token: VALID_TOKEN,
      teamName: 'My Team',
      machineName: 'MyMachine',
    });

    expect(url).toContain('My%20Team');
  });

  it('should URL-encode special characters in machine name', () => {
    const url = buildProtocolUrl({
      token: VALID_TOKEN,
      teamName: 'MyTeam',
      machineName: 'My Machine',
    });

    expect(url).toContain('My%20Machine');
  });

  it('should URL-encode special characters in repository name', () => {
    const url = buildProtocolUrl({
      token: VALID_TOKEN,
      teamName: 'MyTeam',
      machineName: 'MyMachine',
      repositoryName: 'My Repo',
    });

    expect(url).toContain('My%20Repo');
  });

  it('should produce URL that can be parsed back', () => {
    const original = {
      token: VALID_TOKEN,
      teamName: 'MyTeam',
      machineName: 'MyMachine',
      repositoryName: 'MyRepo',
      action: 'sync' as const,
      params: { direction: 'upload' },
    };

    const url = buildProtocolUrl(original);
    const parsed = parseProtocolUrl(url);

    expect(parsed.token).toBe(original.token);
    expect(parsed.teamName).toBe(original.teamName);
    expect(parsed.machineName).toBe(original.machineName);
    expect(parsed.repositoryName).toBe(original.repositoryName);
    expect(parsed.action).toBe(original.action);
    expect(parsed.params?.direction).toBe(original.params.direction);
  });
});
