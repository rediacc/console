import { invoke } from '@tauri-apps/api/core'
import { ApiResponse } from './client'
import { encryptRequestData, decryptResponseData, hasVaultFields } from './encryptionMiddleware'
import { tokenService } from '@/services/tokenService'

export interface CommandResult {
  success: boolean
  output: string
  error: string
}

interface DesktopApiRequest {
  procedure: string
  params: Record<string, any>
  token?: string
}

class DesktopApiClient {
  private isAvailable = false

  constructor() {
    this.checkAvailability()
  }

  private async checkAvailability() {
    try {
      // Check if we're in Tauri environment
      if (typeof window !== 'undefined' && '__TAURI__' in window) {
        this.isAvailable = true
      }
    } catch (error) {
      this.isAvailable = false
    }
  }

  async isDesktopMode(): Promise<boolean> {
    return this.isAvailable
  }

  async post<T = any>(endpoint: string, data?: any): Promise<ApiResponse<T>> {
    if (!this.isAvailable) {
      throw new Error('Desktop mode not available')
    }

    try {
      // Get current token
      const token = await tokenService.getToken()
      
      // Encrypt vault fields if needed
      const encryptedData = hasVaultFields(data) 
        ? await encryptRequestData(data)
        : data

      // Prepare CLI arguments
      const args = this.buildCliArgs(endpoint, encryptedData, token)
      
      // Execute via Tauri command
      const result: CommandResult = await invoke('execute_rediacc_cli', {
        command: 'api',
        args
      })

      if (!result.success) {
        throw new Error(result.error || 'Command failed')
      }

      // Parse the JSON response
      const response = JSON.parse(result.output)
      
      // Handle token rotation
      if (response.nextRequestCredential) {
        await tokenService.updateToken(response.nextRequestCredential)
      }

      // Decrypt response if needed
      const decryptedResponse = await decryptResponseData(response)
      
      return decryptedResponse
    } catch (error) {
      console.error('Desktop API error:', error)
      throw error
    }
  }

  private buildCliArgs(procedure: string, params: any, token?: string): string[] {
    const args = ['--output', 'json', 'api', procedure]
    
    if (token) {
      args.push('--token', token)
    }

    // Convert params to CLI arguments
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        args.push('--param', `${key}=${JSON.stringify(value)}`)
      })
    }

    return args
  }

  // Python-specific commands
  async executePythonScript(scriptPath: string, args: string[] = []): Promise<CommandResult> {
    if (!this.isAvailable) {
      throw new Error('Desktop mode not available')
    }

    return await invoke('execute_python_command', {
      script: scriptPath,
      args
    })
  }

  // File sync operations
  async syncFiles(
    direction: 'upload' | 'download',
    machine: string,
    repository: string,
    localPath: string,
    options: {
      mirror?: boolean
      verify?: boolean
      team?: string
    } = {}
  ): Promise<CommandResult> {
    if (!this.isAvailable) {
      throw new Error('Desktop mode not available')
    }

    const args = [
      direction,
      '--machine', machine,
      '--repo', repository,
      '--local', localPath
    ]

    if (options.team) {
      args.push('--team', options.team)
    }
    if (options.mirror) {
      args.push('--mirror', '--confirm')
    }
    if (options.verify) {
      args.push('--verify')
    }

    return await invoke('execute_rediacc_cli', {
      command: 'sync',
      args
    })
  }

  // Terminal operations
  async executeTerminalCommand(
    machine: string,
    repository: string,
    command: string,
    team?: string
  ): Promise<CommandResult> {
    if (!this.isAvailable) {
      throw new Error('Desktop mode not available')
    }

    const args = [
      '--machine', machine,
      '--repo', repository,
      '--command', command
    ]

    if (team) {
      args.push('--team', team)
    }

    return await invoke('execute_rediacc_cli', {
      command: 'term',
      args
    })
  }

  // System checks
  async checkPythonAvailable(): Promise<boolean> {
    if (!this.isAvailable) {
      return false
    }

    try {
      return await invoke('check_python_available')
    } catch {
      return false
    }
  }

  async getPythonVersion(): Promise<string> {
    if (!this.isAvailable) {
      throw new Error('Desktop mode not available')
    }

    return await invoke('get_python_version')
  }

  async checkCliAvailable(): Promise<boolean> {
    if (!this.isAvailable) {
      return false
    }

    try {
      return await invoke('check_rediacc_cli_available')
    } catch {
      return false
    }
  }

  async getSystemInfo(): Promise<any> {
    if (!this.isAvailable) {
      throw new Error('Desktop mode not available')
    }

    return await invoke('get_system_info')
  }
}

export const desktopApiClient = new DesktopApiClient()