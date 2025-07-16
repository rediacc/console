
interface AppConfig {
  apiUrl: string
  domain: string
  httpPort: number
  environment: 'development' | 'production'
}

class ConfigService {
  private config: AppConfig | null = null



  async getConfig(): Promise<AppConfig> {
    if (this.config) {
      return this.config
    }

    // Use Vite environment variables
    this.config = {
      apiUrl: import.meta.env.VITE_API_URL || this.getDefaultConfig().apiUrl,
      domain: import.meta.env.VITE_SYSTEM_DOMAIN || 'localhost',
      httpPort: parseInt(import.meta.env.VITE_HTTP_PORT || '7322'),
      environment: import.meta.env.MODE as 'development' | 'production'
    }

    return this.config
  }


  private getDefaultConfig(): AppConfig {
    return {
      apiUrl: 'http://localhost:7322/api',
      domain: 'localhost',
      httpPort: 7322,
      environment: 'production'
    }
  }

  // Get specific config values
  async getApiUrl(): Promise<string> {
    const config = await this.getConfig()
    return config.apiUrl
  }

  async getDomain(): Promise<string> {
    const config = await this.getConfig()
    return config.domain
  }

  async getHttpPort(): Promise<number> {
    const config = await this.getConfig()
    return config.httpPort
  }

  // Update config
  async updateConfig(newConfig: Partial<AppConfig>): Promise<void> {
    const currentConfig = await this.getConfig()
    this.config = { ...currentConfig, ...newConfig }
  }
}

export const configService = new ConfigService()