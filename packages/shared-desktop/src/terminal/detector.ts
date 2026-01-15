import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { TerminalInfo, TerminalType } from '../types/index.js';
import { getConfigPath, getPlatform, isWSL } from '../utils/platform.js';

/**
 * Cache file location
 */
const CACHE_FILE = join(getConfigPath(), 'cache', 'terminal.json');

/**
 * Cache duration in milliseconds (7 days)
 */
const CACHE_DURATION_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * Terminal detection result
 */
interface DetectionResult {
  success: boolean;
  message: string;
}

/**
 * Cached terminal info
 */
interface CachedInfo {
  method: TerminalType | null;
  workingMethods: TerminalType[];
  timestamp: string;
  platform: string;
}

/**
 * Loads cached terminal detection results
 */
function loadCache(): Record<string, CachedInfo> {
  try {
    if (existsSync(CACHE_FILE)) {
      return JSON.parse(readFileSync(CACHE_FILE, 'utf8'));
    }
  } catch {
    // Ignore cache errors
  }
  return {};
}

/**
 * Saves cache to file
 */
function saveCache(cache: Record<string, CachedInfo>): void {
  try {
    const cacheDir = join(getConfigPath(), 'cache');
    if (!existsSync(cacheDir)) {
      mkdirSync(cacheDir, { recursive: true, mode: 0o700 });
    }
    writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2), { mode: 0o600 });
  } catch {
    // Ignore save errors
  }
}

/**
 * Checks if cached results are still valid
 */
function isCacheValid(cache: Record<string, CachedInfo>, platform: string): boolean {
  const cached = cache[platform] as CachedInfo | undefined;
  if (!cached?.timestamp) return false;

  try {
    const cachedTime = new Date(cached.timestamp).getTime();
    return Date.now() - cachedTime < CACHE_DURATION_MS;
  } catch {
    return false;
  }
}

/**
 * Finds MSYS2 installation path on Windows
 */
export function findMSYS2Installation(): string | null {
  const msys2Paths = [
    process.env.MSYS2_ROOT,
    'C:\\msys64',
    'C:\\msys2',
    join(process.env.USERPROFILE ?? '', 'msys64'),
    join(process.env.USERPROFILE ?? '', 'msys2'),
  ].filter(Boolean) as string[];

  for (const path of msys2Paths) {
    if (existsSync(path)) {
      return path;
    }
  }
  return null;
}

/**
 * Test functions for each terminal type
 */
const testFunctions: Record<TerminalType, () => DetectionResult> = {
  'gnome-terminal': () => {
    try {
      execSync('which gnome-terminal', { stdio: 'pipe' });
      return { success: true, message: 'gnome-terminal is available' };
    } catch {
      return { success: false, message: 'gnome-terminal not found' };
    }
  },

  konsole: () => {
    try {
      execSync('which konsole', { stdio: 'pipe' });
      return { success: true, message: 'konsole is available' };
    } catch {
      return { success: false, message: 'konsole not found' };
    }
  },

  'xfce4-terminal': () => {
    try {
      execSync('which xfce4-terminal', { stdio: 'pipe' });
      return { success: true, message: 'xfce4-terminal is available' };
    } catch {
      return { success: false, message: 'xfce4-terminal not found' };
    }
  },

  xterm: () => {
    try {
      execSync('which xterm', { stdio: 'pipe' });
      return { success: true, message: 'xterm is available' };
    } catch {
      return { success: false, message: 'xterm not found' };
    }
  },

  'mate-terminal': () => {
    try {
      execSync('which mate-terminal', { stdio: 'pipe' });
      return { success: true, message: 'mate-terminal is available' };
    } catch {
      return { success: false, message: 'mate-terminal not found' };
    }
  },

  terminator: () => {
    try {
      execSync('which terminator', { stdio: 'pipe' });
      return { success: true, message: 'terminator is available' };
    } catch {
      return { success: false, message: 'terminator not found' };
    }
  },

  'terminal-app': () => {
    if (getPlatform() !== 'macos') {
      return { success: false, message: 'Not on macOS' };
    }
    // Terminal.app is always available on macOS
    return { success: true, message: 'Terminal.app is available' };
  },

  iterm2: () => {
    if (getPlatform() !== 'macos') {
      return { success: false, message: 'Not on macOS' };
    }
    const itermPath = '/Applications/iTerm.app';
    if (existsSync(itermPath)) {
      return { success: true, message: 'iTerm2 is available' };
    }
    return { success: false, message: 'iTerm2 not found' };
  },

  'windows-terminal': () => {
    if (getPlatform() !== 'windows') {
      return { success: false, message: 'Not on Windows' };
    }
    try {
      execSync('where wt.exe', { stdio: 'pipe' });
      return { success: true, message: 'Windows Terminal is available' };
    } catch {
      return { success: false, message: 'Windows Terminal not found' };
    }
  },

  powershell: () => {
    if (getPlatform() !== 'windows') {
      return { success: false, message: 'Not on Windows' };
    }
    try {
      execSync('powershell.exe -Command "echo test"', { stdio: 'pipe', timeout: 5000 });
      return { success: true, message: 'PowerShell is available' };
    } catch {
      return { success: false, message: 'PowerShell not accessible' };
    }
  },

  cmd: () => {
    if (getPlatform() !== 'windows') {
      return { success: false, message: 'Not on Windows' };
    }
    // cmd.exe is always available on Windows
    return { success: true, message: 'cmd.exe is available' };
  },

  mintty: () => {
    const msys2Path = findMSYS2Installation();
    if (!msys2Path) {
      return { success: false, message: 'MSYS2 not found' };
    }
    const minttyPath = join(msys2Path, 'usr', 'bin', 'mintty.exe');
    if (existsSync(minttyPath)) {
      return { success: true, message: 'mintty is available' };
    }
    return { success: false, message: 'mintty not found' };
  },

  wsl: () => {
    if (!isWSL()) {
      // Check if we can call wsl from Windows
      if (getPlatform() === 'windows') {
        try {
          execSync('wsl.exe --version', { stdio: 'pipe', timeout: 5000 });
          return { success: true, message: 'WSL is available' };
        } catch {
          return { success: false, message: 'WSL not accessible' };
        }
      }
      return { success: false, message: 'Not in WSL environment' };
    }
    return { success: true, message: 'Running in WSL' };
  },
};

/**
 * Gets the methods to test for each platform
 */
function getMethodsForPlatform(): TerminalType[] {
  const platform = getPlatform();
  const inWSL = isWSL();

  if (platform === 'windows') {
    return ['windows-terminal', 'mintty', 'wsl', 'powershell', 'cmd'];
  }

  if (platform === 'macos') {
    return ['iterm2', 'terminal-app'];
  }

  // Linux
  if (inWSL) {
    // In WSL, prioritize Windows terminals
    return ['wsl', 'gnome-terminal', 'konsole', 'xfce4-terminal', 'xterm'];
  }

  return ['gnome-terminal', 'konsole', 'xfce4-terminal', 'mate-terminal', 'terminator', 'xterm'];
}

/**
 * TerminalDetector - Detects and caches working terminal launch methods
 */
export class TerminalDetector {
  private cache: Record<string, CachedInfo>;

  constructor() {
    this.cache = loadCache();
  }

  /**
   * Detects the best working terminal method
   *
   * @param forceRefresh - Force re-detection even if cache is valid
   * @returns The best working terminal type, or null if none found
   */
  detect(forceRefresh = false): TerminalType | null {
    const platform = getPlatform();

    // Check cache
    if (!forceRefresh && isCacheValid(this.cache, platform)) {
      const cached = this.cache[platform];
      if (cached.method) {
        return cached.method;
      }
    }

    // Get methods for this platform
    const methods = getMethodsForPlatform();
    const workingMethods: TerminalType[] = [];

    // Test each method
    for (const method of methods) {
      const testFn = testFunctions[method];
      const result = testFn();
      if (result.success) {
        workingMethods.push(method);
      }
    }

    // Select the best method (first working one)
    const bestMethod = workingMethods.length > 0 ? workingMethods[0] : null;

    // Update cache
    this.cache[platform] = {
      method: bestMethod,
      workingMethods,
      timestamp: new Date().toISOString(),
      platform,
    };
    saveCache(this.cache);

    return bestMethod;
  }

  /**
   * Gets information about the detected terminal
   */
  getTerminalInfo(): TerminalInfo | null {
    const method = this.detect();
    if (!method) return null;

    return {
      type: method,
      path: this.getTerminalPath(method) ?? '',
      detectedAt: Date.now(),
    };
  }

  /**
   * Gets the path to a terminal executable
   */
  private getTerminalPath(type: TerminalType): string | null {
    switch (type) {
      case 'mintty': {
        const msys2Path = findMSYS2Installation();
        return msys2Path ? join(msys2Path, 'usr', 'bin', 'mintty.exe') : null;
      }
      case 'terminal-app':
        return '/System/Applications/Utilities/Terminal.app';
      case 'iterm2':
        return '/Applications/iTerm.app';
      default:
        return type;
    }
  }

  /**
   * Gets all working terminal methods
   */
  getWorkingMethods(): TerminalType[] {
    const platform = getPlatform();
    const cached = this.cache[platform];
    return cached.workingMethods;
  }

  /**
   * Clears the cache
   */
  clearCache(): void {
    this.cache = {};
    saveCache(this.cache);
  }
}
