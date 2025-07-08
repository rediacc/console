import { useState, useEffect } from 'react'
import { unifiedApiClient } from '@/api/unifiedClient'
import { notification } from 'antd'

export interface DesktopCapabilities {
  isDesktop: boolean
  hasPython: boolean
  pythonVersion: string | null
  hasCli: boolean
  systemInfo: any | null
}

export const useDesktopMode = () => {
  const [capabilities, setCapabilities] = useState<DesktopCapabilities>({
    isDesktop: false,
    hasPython: false,
    pythonVersion: null,
    hasCli: false,
    systemInfo: null
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkCapabilities()
  }, [])

  const checkCapabilities = async () => {
    try {
      setLoading(true)
      
      const isDesktop = await unifiedApiClient.isDesktopMode()
      
      if (!isDesktop) {
        setCapabilities({
          isDesktop: false,
          hasPython: false,
          pythonVersion: null,
          hasCli: false,
          systemInfo: null
        })
        return
      }

      // Check all capabilities in parallel
      const [hasPython, pythonVersion, hasCli, systemInfo] = await Promise.all([
        unifiedApiClient.checkPythonAvailable(),
        unifiedApiClient.getPythonVersion(),
        unifiedApiClient.checkCliAvailable(),
        unifiedApiClient.getSystemInfo()
      ])

      setCapabilities({
        isDesktop,
        hasPython,
        pythonVersion,
        hasCli,
        systemInfo
      })

      // Show warnings if missing requirements
      if (!hasPython) {
        notification.warning({
          message: 'Python Not Found',
          description: 'Python is required for some desktop features. Please install Python 3.6 or later.',
          duration: 10
        })
      }

      if (!hasCli) {
        notification.warning({
          message: 'Rediacc CLI Not Found',
          description: 'The Rediacc CLI tools are required for desktop features. Please install them.',
          duration: 10
        })
      }
    } catch (error) {
      console.error('Failed to check desktop capabilities:', error)
    } finally {
      setLoading(false)
    }
  }

  return {
    ...capabilities,
    loading,
    refresh: checkCapabilities
  }
}