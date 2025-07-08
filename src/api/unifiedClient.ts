import { apiClient as webApiClient } from './client'
import { desktopApiClient } from './desktopClient'

class UnifiedApiClient {
  private isDesktop = false
  
  constructor() {
    this.detectEnvironment()
  }

  private async detectEnvironment() {
    this.isDesktop = await desktopApiClient.isDesktopMode()
  }

  async post<T = any>(endpoint: string, data?: any) {
    await this.detectEnvironment() // Re-check in case it changed
    
    if (this.isDesktop) {
      return desktopApiClient.post<T>(endpoint, data)
    } else {
      return webApiClient.post<T>(endpoint, data)
    }
  }

  // Desktop-specific methods (return null/throw in web mode)
  async executePythonScript(scriptPath: string, args: string[] = []) {
    if (!this.isDesktop) {
      throw new Error('Python execution is only available in desktop mode')
    }
    return desktopApiClient.executePythonScript(scriptPath, args)
  }

  async syncFiles(
    direction: 'upload' | 'download',
    machine: string,
    repository: string,
    localPath: string,
    options: any = {}
  ) {
    if (!this.isDesktop) {
      throw new Error('File sync is only available in desktop mode')
    }
    return desktopApiClient.syncFiles(direction, machine, repository, localPath, options)
  }

  async executeTerminalCommand(
    machine: string,
    repository: string,
    command: string,
    team?: string
  ) {
    if (!this.isDesktop) {
      throw new Error('Terminal commands are only available in desktop mode')
    }
    return desktopApiClient.executeTerminalCommand(machine, repository, command, team)
  }

  // Environment checks
  async isDesktopMode(): Promise<boolean> {
    return this.isDesktop
  }

  async checkPythonAvailable(): Promise<boolean> {
    if (!this.isDesktop) return false
    return desktopApiClient.checkPythonAvailable()
  }

  async getPythonVersion(): Promise<string | null> {
    if (!this.isDesktop) return null
    try {
      return await desktopApiClient.getPythonVersion()
    } catch {
      return null
    }
  }

  async checkCliAvailable(): Promise<boolean> {
    if (!this.isDesktop) return false
    return desktopApiClient.checkCliAvailable()
  }

  async getSystemInfo(): Promise<any | null> {
    if (!this.isDesktop) return null
    try {
      return await desktopApiClient.getSystemInfo()
    } catch {
      return null
    }
  }
}

// Export a singleton instance
export const unifiedApiClient = new UnifiedApiClient()

// Also export the type for use in other files
export type { CommandResult } from './desktopClient'