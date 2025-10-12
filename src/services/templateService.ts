import { configService } from './configService'
import { CONFIG_URLS } from '@/utils/apiConstants'

interface Template {
  id?: string
  name: string
  readme: string
  category?: string
  tags?: string[]
  difficulty?: 'beginner' | 'intermediate' | 'advanced'
  download_url?: string
}

/**
 * Template Service - Single source of truth for template URLs and fetching
 *
 * This service centralizes all template-related URL generation and data fetching
 * to ensure consistency across the application (Marketplace, Create Repository, etc.)
 */
class TemplateService {
  private templatesCache: Template[] | null = null

  /**
   * Convert UTF-8 string to Base64
   * Handles Unicode characters properly
   */
  private utf8ToBase64(str: string): string {
    // Use TextEncoder for proper UTF-8 encoding (modern browsers)
    const encoder = new TextEncoder()
    const uint8Array = encoder.encode(str)

    // Convert Uint8Array to binary string
    let binaryString = ''
    for (let i = 0; i < uint8Array.length; i++) {
      binaryString += String.fromCharCode(uint8Array[i])
    }

    // Convert binary string to base64
    return btoa(binaryString)
  }

  /**
   * Get the base URL for templates directory
   */
  private getTemplatesBaseUrl(): string {
    return CONFIG_URLS.TEMPLATES_DIR
  }

  /**
   * Get the URL for the templates list (index file)
   */
  async getTemplatesListUrl(): Promise<string> {
    // Use configService for configured templates URL, or default
    return await configService.getTemplatesUrl()
  }

  /**
   * Get the URL for a specific template's data JSON file
   * Handles both id and name fields for backward compatibility
   */
  getTemplateDataUrl(template: { id?: string; name: string; download_url?: string }): string {
    // If download_url is provided, use it (relative to templates directory)
    if (template.download_url) {
      // If download_url already includes the full path, use templates dir directly
      if (template.download_url.startsWith('templates/')) {
        return `${CONFIG_URLS.TEMPLATES_DIR}/${template.download_url.replace('templates/', '')}`
      }
      // Otherwise assume it's relative to configs
      return `${CONFIG_URLS.TEMPLATES_DIR}/${template.download_url}`
    }

    // Prefer id over name
    const identifier = template.id || template.name

    // Standard pattern: templates/{identifier}.json
    return `${this.getTemplatesBaseUrl()}/${identifier}.json`
  }

  /**
   * Fetch the templates list from the configured URL
   * Uses cache to avoid repeated fetches
   */
  async fetchTemplates(forceRefresh: boolean = false): Promise<Template[]> {
    if (this.templatesCache && !forceRefresh) {
      return this.templatesCache
    }

    try {
      const url = await this.getTemplatesListUrl()
      // Use simple CORS request (no preflight needed)
      const response = await fetch(url, {
        method: 'GET',
        mode: 'cors',
        credentials: 'omit',
        cache: forceRefresh ? 'reload' : 'default'
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch templates: ${response.status} ${response.statusText}`)
      }

      const data = await response.json()
      this.templatesCache = data.templates || []
      return this.templatesCache || []
    } catch (error) {
      console.error('Failed to fetch templates:', error)
      throw error
    }
  }

  /**
   * Find a template by ID from the templates list
   * Returns null if template not found
   */
  async findTemplateById(templateId: string): Promise<Template | null> {
    const templates = await this.fetchTemplates()
    return templates.find(t => t.id === templateId || t.name === templateId) || null
  }

  /**
   * Fetch detailed data for a specific template
   */
  async fetchTemplateData(template: { id?: string; name: string; download_url?: string }): Promise<any> {
    try {
      const url = this.getTemplateDataUrl(template)
      // Use simple CORS request (no preflight needed)
      const response = await fetch(url, {
        method: 'GET',
        mode: 'cors',
        credentials: 'omit',
        cache: 'default'
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch template data: ${response.status} ${response.statusText}`)
      }

      return await response.json()
    } catch (error) {
      console.error('Failed to fetch template data:', error)
      throw error
    }
  }

  /**
   * Get Base64-encoded template data for API submission
   */
  async getEncodedTemplateData(template: { id?: string; name: string; download_url?: string }): Promise<string> {
    const templateData = await this.fetchTemplateData(template)
    return this.utf8ToBase64(JSON.stringify(templateData))
  }

  /**
   * Get Base64-encoded template data by template ID
   * Looks up the template from the templates list first
   */
  async getEncodedTemplateDataById(templateId: string): Promise<string> {
    const template = await this.findTemplateById(templateId)
    if (!template) {
      throw new Error(`Template not found: ${templateId}`)
    }
    return this.getEncodedTemplateData(template)
  }
}

export const templateService = new TemplateService()
