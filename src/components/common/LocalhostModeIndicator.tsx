import React, { useEffect, useState } from 'react'
import { Alert } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { featureFlags } from '@/config/featureFlags'

const LocalhostModeIndicator: React.FC = () => {
  // Initialize state based on localhost check and feature flag
  const [isVisible, setIsVisible] = useState(() => {
    if (typeof window === 'undefined') return false
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    return isLocalhost && featureFlags.isLocalhostModeEnabled()
  })

  useEffect(() => {
    // Check if running on localhost domain
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

    if (!isLocalhost) {
      return
    }

    // Check state changes
    const checkLocalhostMode = () => {
      setIsVisible(featureFlags.isLocalhostModeEnabled())
    }

    // Poll for changes (since we toggle via keyboard shortcut)
    const interval = setInterval(checkLocalhostMode, 500)

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    // Add padding to body when indicator is visible
    if (isVisible) {
      document.body.style.paddingTop = '40px'
    }
    return () => {
      document.body.style.paddingTop = ''
    }
  }, [isVisible])

  if (!isVisible) {
    return null
  }

  return (
    <Alert
      banner
      type="info"
      showIcon={false}
      closable={false}
      message={
        <div style={{ textAlign: 'center', padding: '2px 0' }}>
          <ThunderboltOutlined style={{ marginRight: 8 }} />
          <strong>Localhost Mode:</strong> All features enabled (Press Ctrl+Shift+E to disable)
        </div>
      }
      style={{
        position: 'fixed',
        top: 0,
        left: 200,
        right: 0,
        zIndex: 1001, // Higher than navigation
        borderRadius: 0,
        border: 'none',
        backgroundColor: '#e6f7ff',
        color: '#0050b3',
        borderBottom: '1px solid #91d5ff',
        minHeight: '40px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}
    />
  )
}

export default LocalhostModeIndicator
