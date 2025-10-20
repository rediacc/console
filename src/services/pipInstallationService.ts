/**
 * Pip Installation Service for Rediacc CLI
 * Provides utilities for pip package installation guidance
 */

export interface InstallOptions {
  useUser?: boolean
  useVirtualEnv?: boolean
  version?: string
  upgrade?: boolean
}

export interface PlatformInstructions {
  platform: 'windows' | 'macos' | 'linux'
  pipInstallCommand: string
  pythonCheckCommand: string
  notes: string[]
}

export interface InstallationCommands {
  install: string
  postInstall: string[]
  verify: string[]
}

export type InstallationStatus = 'not-installed' | 'installed' | 'protocol-not-registered' | 'ready'

export type ErrorType = 'pip-not-found' | 'permission-denied' | 'python-version' | 'unknown'

class PipInstallationService {
  /**
   * Generate pip install command based on options
   */
  generateInstallCommand(options: InstallOptions = {}): string {
    const parts = ['pip install']

    if (options.useUser) {
      parts.push('--user')
    }

    if (options.upgrade) {
      parts.push('--upgrade')
    }

    // Package name
    let packageName = 'rediacc'

    // Add version if specified
    if (options.version) {
      packageName += `==${options.version}`
    }

    parts.push(packageName)

    return parts.join(' ')
  }

  /**
   * Generate setup command (includes protocol registration and dependency checks)
   */
  generateSetupCommand(): string {
    return 'rediacc setup'
  }

  /**
   * Generate protocol registration command (for manual registration)
   */
  generateProtocolCommand(): string {
    return 'rediacc protocol register'
  }

  /**
   * Get platform-specific installation instructions
   */
  getPlatformInstructions(): PlatformInstructions {
    const platform = this.detectPlatform()
    
    switch (platform) {
      case 'windows':
        return {
          platform: 'windows',
          pipInstallCommand: 'python -m pip install --upgrade pip',
          pythonCheckCommand: 'python --version',
          notes: [
            'Run PowerShell as Administrator for system-wide installation',
            'Use "py -m pip" if "pip" command is not found',
            'Restart your browser after protocol registration'
          ]
        }
      
      case 'macos':
        return {
          platform: 'macos',
          pipInstallCommand: 'python3 -m pip install --upgrade pip',
          pythonCheckCommand: 'python3 --version',
          notes: [
            'Use "python3" instead of "python" on macOS',
            'You may need to install pip with: python3 -m ensurepip',
            'Grant permission when prompted for protocol handler'
          ]
        }
      
      case 'linux':
        return {
          platform: 'linux',
          pipInstallCommand: 'python3 -m pip install --upgrade pip',
          pythonCheckCommand: 'python3 --version',
          notes: [
            'You may need to install pip: sudo apt install python3-pip',
            'Use --user flag to avoid permission issues',
            'Log out and back in after protocol registration'
          ]
        }
    }
  }

  /**
   * Generate all installation commands
   */
  getInstallationCommands(options: InstallOptions = {}): InstallationCommands {
    const platform = this.detectPlatform()

    return {
      install: this.generateInstallCommand(options),
      postInstall: [
        this.generateSetupCommand(),
        platform === 'windows' ? 'Restart your browser' : 'Restart your browser or log out/in'
      ],
      verify: [
        'rediacc --version',
        'rediacc protocol status'
      ]
    }
  }

  /**
   * Get troubleshooting commands for common errors
   */
  getTroubleshootingCommands(errorType: ErrorType): { description: string; commands: string[] } {
    switch (errorType) {
      case 'pip-not-found': {
        const platform = this.detectPlatform()
        if (platform === 'windows') {
          return {
            description: 'Pip is not installed. Install it with:',
            commands: [
              'python -m ensurepip --upgrade',
              '# Or download get-pip.py from https://pip.pypa.io/en/stable/installation/'
            ]
          }
        } else {
          return {
            description: 'Pip is not installed. Install it with:',
            commands: [
              'python3 -m ensurepip --upgrade',
              '# Or on Ubuntu/Debian: sudo apt install python3-pip',
              '# Or on macOS with Homebrew: brew install python3'
            ]
          }
        }
      }

      case 'permission-denied':
        return {
          description: 'Permission denied. Try one of these approaches:',
          commands: [
            '# Option 1: Install for current user only',
            this.generateInstallCommand({ useUser: true }),
            '',
            '# Option 2: Use virtual environment',
            'python3 -m venv rediacc-env',
            'source rediacc-env/bin/activate  # On Windows: rediacc-env\\Scripts\\activate',
            this.generateInstallCommand()
          ]
        }
      
      case 'python-version':
        return {
          description: 'Python version is too old. Rediacc requires Python 3.7+',
          commands: [
            '# Check your Python version',
            'python --version',
            'python3 --version',
            '',
            '# Update Python from https://www.python.org/downloads/'
          ]
        }
      
      default:
        return {
          description: 'Installation failed. Try these steps:',
          commands: [
            '# 1. Update pip',
            'python -m pip install --upgrade pip',
            '',
            '# 2. Install with verbose output',
            'pip install -v rediacc',
            '',
            '# 3. Check for errors in the output above'
          ]
        }
    }
  }

  /**
   * Get virtual environment setup instructions
   */
  getVirtualEnvInstructions(): { description: string; commands: string[] } {
    const platform = this.detectPlatform()
    const pythonCmd = platform === 'windows' ? 'python' : 'python3'
    const activateCmd = platform === 'windows'
      ? 'rediacc-env\\Scripts\\activate'
      : 'source rediacc-env/bin/activate'

    return {
      description: 'Using a virtual environment (recommended for development):',
      commands: [
        '# Create virtual environment',
        `${pythonCmd} -m venv rediacc-env`,
        '',
        '# Activate virtual environment',
        activateCmd,
        '',
        '# Install Rediacc CLI',
        this.generateInstallCommand(),
        '',
        '# Run setup (checks dependencies and registers protocol)',
        this.generateSetupCommand()
      ]
    }
  }

  /**
   * Get uninstall instructions
   */
  getUninstallInstructions(): { description: string; commands: string[] } {
    return {
      description: 'To uninstall Rediacc CLI:',
      commands: [
        '# Unregister protocol handler first',
        'rediacc protocol unregister',
        '',
        '# Uninstall package',
        'pip uninstall rediacc',
        '',
        '# Remove configuration (optional)',
        '# Linux/macOS: rm -rf ~/.rediacc',
        '# Windows: rmdir /s %USERPROFILE%\\.rediacc'
      ]
    }
  }

  /**
   * Detect the current platform
   */
  private detectPlatform(): 'windows' | 'macos' | 'linux' {
    const userAgent = navigator.userAgent.toLowerCase()
    
    if (userAgent.includes('win')) {
      return 'windows'
    } else if (userAgent.includes('mac')) {
      return 'macos'
    } else {
      return 'linux'
    }
  }

  /**
   * Format commands for display with syntax highlighting hints
   */
  formatCommandsForDisplay(commands: string[]): Array<{ text: string; isCommand: boolean; isComment: boolean }> {
    return commands.map(cmd => {
      const trimmed = cmd.trim()
      const isComment = trimmed.startsWith('#')
      const isCommand = trimmed.length > 0 && !isComment
      
      return {
        text: cmd,
        isCommand,
        isComment
      }
    })
  }
}

// Export singleton instance
export const pipInstallationService = new PipInstallationService()