import { execSync } from 'node:child_process';
import { existsSync, writeFileSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { PROTOCOL_SCHEME } from './parser.js';
import { getPlatform, getHomePath } from '../utils/platform.js';

/**
 * Protocol handler error
 */
export class ProtocolHandlerError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ProtocolHandlerError';
  }
}

/**
 * Protocol registration status
 */
export interface ProtocolStatus {
  registered: boolean;
  userRegistered: boolean;
  systemRegistered: boolean;
  command?: string;
  platform: string;
  supported: boolean;
  error?: string;
}

/**
 * Checks if protocol registration is supported on the current platform
 */
export function isProtocolSupported(): boolean {
  return ['windows', 'linux', 'macos'].includes(getPlatform());
}

/**
 * Electron app paths by platform
 */
const ELECTRON_APP_PATHS: Record<string, () => string[]> = {
  windows: () => [
    join(process.env.LOCALAPPDATA ?? '', 'Programs', 'Rediacc Console', 'Rediacc Console.exe'),
    join(process.env.PROGRAMFILES ?? '', 'Rediacc Console', 'Rediacc Console.exe'),
  ],
  macos: () => ['/Applications/Rediacc Console.app/Contents/MacOS/Rediacc Console'],
  linux: () => [
    '/usr/bin/rediacc-console',
    '/opt/rediacc-console/rediacc-console',
    join(getHomePath(), '.local', 'bin', 'rediacc-console'),
  ],
};

/**
 * Finds the first existing path from a list
 */
function findFirstExistingPath(paths: string[]): string | null {
  for (const p of paths) {
    if (existsSync(p)) return p;
  }
  return null;
}

/**
 * Gets the executable path for the Electron app
 */
export function getElectronExecutablePath(): string | null {
  const platform = getPlatform();
  const pathsGetter = ELECTRON_APP_PATHS[platform];
  return findFirstExistingPath(pathsGetter());
}

/**
 * Windows protocol handler
 */
export class WindowsProtocolHandler {
  private readonly userRegistryRoot = 'HKEY_CURRENT_USER\\Software\\Classes';
  private readonly systemRegistryRoot = 'HKEY_CLASSES_ROOT';

  /**
   * Gets the registry key for the protocol
   */
  private getRegistryKey(systemWide: boolean): string {
    const root = systemWide ? this.systemRegistryRoot : this.userRegistryRoot;
    return `${root}\\${PROTOCOL_SCHEME}`;
  }

  /**
   * Gets the command registry key
   */
  private getCommandKey(systemWide: boolean): string {
    return `${this.getRegistryKey(systemWide)}\\shell\\open\\command`;
  }

  /**
   * Checks if running with admin privileges
   */
  checkAdminPrivileges(): boolean {
    try {
      execSync(
        'reg query "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion" /v ProgramFilesDir',
        {
          stdio: 'pipe',
          timeout: 10000,
        }
      );
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Checks if the protocol is registered
   */
  isRegistered(systemWide = false): boolean {
    try {
      execSync(`reg query "${this.getRegistryKey(systemWide)}"`, {
        stdio: 'pipe',
        timeout: 10000,
      });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Gets the protocol command
   */
  getProtocolCommand(): string {
    const exePath = getElectronExecutablePath();
    if (exePath) {
      return `"${exePath}" --protocol "%1"`;
    }
    throw new ProtocolHandlerError('Could not locate Rediacc Console executable');
  }

  /**
   * Registers the protocol
   */
  register(force = false, systemWide = false): boolean {
    if (!force && this.isRegistered(systemWide)) {
      return true;
    }

    if (systemWide && !this.checkAdminPrivileges()) {
      throw new ProtocolHandlerError(
        'Administrator privileges required for system-wide protocol registration.'
      );
    }

    const registryKey = this.getRegistryKey(systemWide);
    const commandKey = this.getCommandKey(systemWide);
    const command = this.getProtocolCommand();

    try {
      // Create main protocol key
      execSync(`reg add "${registryKey}" /ve /d "URL:Rediacc Desktop" /f`, {
        stdio: 'pipe',
        timeout: 30000,
      });

      // Add URL Protocol value
      execSync(`reg add "${registryKey}" /v "URL Protocol" /t REG_SZ /d "" /f`, {
        stdio: 'pipe',
        timeout: 30000,
      });

      // Add friendly type name
      execSync(`reg add "${registryKey}" /v "FriendlyTypeName" /t REG_SZ /d "Rediacc Desktop" /f`, {
        stdio: 'pipe',
        timeout: 30000,
      });

      // Create command key
      execSync(`reg add "${commandKey}" /ve /d "${command}" /f`, {
        stdio: 'pipe',
        timeout: 30000,
      });

      return true;
    } catch (e) {
      throw new ProtocolHandlerError(`Registry operations failed: ${e}`);
    }
  }

  /**
   * Unregisters the protocol
   */
  unregister(systemWide = false): boolean {
    if (!this.isRegistered(systemWide)) {
      return true;
    }

    if (systemWide && !this.checkAdminPrivileges()) {
      throw new ProtocolHandlerError(
        'Administrator privileges required for system-wide protocol unregistration.'
      );
    }

    try {
      execSync(`reg delete "${this.getRegistryKey(systemWide)}" /f`, {
        stdio: 'pipe',
        timeout: 30000,
      });
      return true;
    } catch (e) {
      throw new ProtocolHandlerError(`Failed to delete registry key: ${e}`);
    }
  }

  /**
   * Gets protocol status
   */
  getStatus(systemWide = false): ProtocolStatus {
    const isRegistered = this.isRegistered(systemWide);
    let command: string | undefined;

    if (isRegistered) {
      try {
        const result = execSync(`reg query "${this.getCommandKey(systemWide)}" /ve`, {
          encoding: 'utf8',
          stdio: 'pipe',
          timeout: 10000,
        });
        const match = /REG_SZ\s+(.+)/.exec(result);
        if (match) {
          command = match[1].trim();
        }
      } catch {
        // Ignore
      }
    }

    return {
      registered: isRegistered,
      userRegistered: !systemWide && isRegistered,
      systemRegistered: systemWide && isRegistered,
      command,
      platform: 'windows',
      supported: true,
    };
  }
}

/**
 * Linux protocol handler using .desktop files
 */
export class LinuxProtocolHandler {
  private readonly desktopFilePath = join(
    getHomePath(),
    '.local',
    'share',
    'applications',
    'rediacc-handler.desktop'
  );

  /**
   * Checks if the protocol is registered
   */
  isRegistered(): boolean {
    return existsSync(this.desktopFilePath);
  }

  /**
   * Gets the protocol command
   */
  getProtocolCommand(): string {
    const exePath = getElectronExecutablePath();
    if (exePath) {
      return `${exePath} --protocol %u`;
    }
    throw new ProtocolHandlerError('Could not locate Rediacc Console executable');
  }

  /**
   * Registers the protocol
   */
  register(force = false): boolean {
    if (!force && this.isRegistered()) {
      return true;
    }

    const command = this.getProtocolCommand();

    const desktopEntry = `[Desktop Entry]
Name=Rediacc Console
Comment=Handle rediacc:// protocol URLs
Exec=${command}
Icon=rediacc-console
Terminal=false
Type=Application
Categories=Development;
MimeType=x-scheme-handler/rediacc;
NoDisplay=true
`;

    try {
      writeFileSync(this.desktopFilePath, desktopEntry, { mode: 0o644 });

      // Register with xdg-mime
      execSync(`xdg-mime default rediacc-handler.desktop x-scheme-handler/rediacc`, {
        stdio: 'pipe',
        timeout: 30000,
      });

      // Update desktop database
      execSync('update-desktop-database ~/.local/share/applications/', {
        stdio: 'pipe',
        timeout: 30000,
      });

      return true;
    } catch (e) {
      throw new ProtocolHandlerError(`Failed to register protocol: ${e}`);
    }
  }

  /**
   * Unregisters the protocol
   */
  unregister(): boolean {
    if (!this.isRegistered()) {
      return true;
    }

    try {
      unlinkSync(this.desktopFilePath);
      // Update desktop database
      execSync('update-desktop-database ~/.local/share/applications/', {
        stdio: 'pipe',
        timeout: 30000,
      });
      return true;
    } catch (e) {
      throw new ProtocolHandlerError(`Failed to unregister protocol: ${e}`);
    }
  }

  /**
   * Gets protocol status
   */
  getStatus(): ProtocolStatus {
    return {
      registered: this.isRegistered(),
      userRegistered: this.isRegistered(),
      systemRegistered: false,
      platform: 'linux',
      supported: true,
    };
  }
}

/**
 * macOS protocol handler
 */
export class MacOSProtocolHandler {
  /**
   * Checks if the protocol is registered
   * Note: macOS apps register protocols via their Info.plist
   * We check if the app bundle exists and has the protocol handler
   */
  isRegistered(): boolean {
    const appPath = '/Applications/Rediacc Console.app';
    return existsSync(appPath);
  }

  /**
   * Registers the protocol
   * Note: On macOS, protocol registration is typically done during app installation
   * via the app's Info.plist. This method ensures the app is the default handler.
   */
  register(_force = false): boolean {
    if (!this.isRegistered()) {
      throw new ProtocolHandlerError(
        'Rediacc Console is not installed. Please install the app first.'
      );
    }

    try {
      // Use lsregister to register the app as handler
      execSync(
        `/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -u "/Applications/Rediacc Console.app"`,
        { stdio: 'pipe', timeout: 30000 }
      );
      execSync(
        `/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister "/Applications/Rediacc Console.app"`,
        { stdio: 'pipe', timeout: 30000 }
      );

      // Use duti if available to set default handler
      try {
        execSync('which duti', { stdio: 'pipe' });
        execSync(`duti -s com.rediacc.console rediacc`, { stdio: 'pipe', timeout: 10000 });
      } catch {
        // duti not available, rely on lsregister
      }

      return true;
    } catch (e) {
      throw new ProtocolHandlerError(`Failed to register protocol: ${e}`);
    }
  }

  /**
   * Unregisters the protocol
   * Note: On macOS, this just unregisters from LaunchServices
   */
  unregister(): boolean {
    try {
      execSync(
        `/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -u "/Applications/Rediacc Console.app"`,
        { stdio: 'pipe', timeout: 30000 }
      );
      return true;
    } catch (e) {
      throw new ProtocolHandlerError(`Failed to unregister protocol: ${e}`);
    }
  }

  /**
   * Gets protocol status
   */
  getStatus(): ProtocolStatus {
    return {
      registered: this.isRegistered(),
      userRegistered: this.isRegistered(),
      systemRegistered: false,
      platform: 'macos',
      supported: true,
    };
  }
}

/**
 * Gets the appropriate protocol handler for the current platform
 */
export function getProtocolHandler():
  | WindowsProtocolHandler
  | LinuxProtocolHandler
  | MacOSProtocolHandler {
  const platform = getPlatform();

  switch (platform) {
    case 'windows':
      return new WindowsProtocolHandler();
    case 'linux':
      return new LinuxProtocolHandler();
    case 'macos':
      return new MacOSProtocolHandler();
    default:
      throw new ProtocolHandlerError(`Unsupported platform: ${platform}`);
  }
}

/**
 * Registers the protocol on the current platform
 */
export function registerProtocol(force = false, systemWide = false): boolean {
  const handler = getProtocolHandler();

  if (handler instanceof WindowsProtocolHandler) {
    return handler.register(force, systemWide);
  }

  return handler.register(force);
}

/**
 * Unregisters the protocol on the current platform
 */
export function unregisterProtocol(systemWide = false): boolean {
  const handler = getProtocolHandler();

  if (handler instanceof WindowsProtocolHandler) {
    return handler.unregister(systemWide);
  }

  return handler.unregister();
}

/**
 * Gets the protocol status on the current platform
 */
export function getProtocolStatus(_systemWide = false): ProtocolStatus {
  if (!isProtocolSupported()) {
    return {
      registered: false,
      userRegistered: false,
      systemRegistered: false,
      platform: getPlatform(),
      supported: false,
      error: `Protocol registration is not supported on ${getPlatform()}`,
    };
  }

  const handler = getProtocolHandler();

  if (handler instanceof WindowsProtocolHandler) {
    const userStatus = handler.getStatus(false);
    const systemStatus = handler.getStatus(true);

    return {
      registered: userStatus.registered || systemStatus.registered,
      userRegistered: userStatus.registered,
      systemRegistered: systemStatus.registered,
      command: userStatus.command ?? systemStatus.command,
      platform: 'windows',
      supported: true,
    };
  }

  return handler.getStatus();
}
