import React, { useEffect, useState } from 'react'
import { Alert } from 'antd'
import { ExclamationCircleOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { configService } from '@/services/configService'

const SandboxWarning: React.FC = () => {
  const { t } = useTranslation('common')
  const [isVisible, setIsVisible] = useState(false)
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' ? window.innerWidth < 768 : false)

  useEffect(() => {
    const loadInstanceName = async () => {
      const name = await configService.getInstanceName()
      console.log('SandboxWarning: Instance name loaded:', name)
      // Show warning only for sandbox instances
      setIsVisible(name.toLowerCase() === 'sandbox')
    }
    loadInstanceName()
  }, [])

  // Handle responsive behavior
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768)
    }

    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    // Add padding to body when warning is visible
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
      type="warning"
      showIcon={false}
      closable={false}
      message={
        <div style={{ textAlign: 'center', padding: '2px 0' }}>
          <ExclamationCircleOutlined style={{ marginRight: 8 }} />
          <strong>{t('warnings.sandboxEnvironment')}:</strong> {t('warnings.sandboxMessage')}
        </div>
      }
      style={{
        position: 'fixed',
        top: 0,
        left: isMobile ? 0 : 200, // Start after sidebar on desktop (200px), full width on mobile
        right: 0,
        zIndex: 1001, // Higher than navigation
        borderRadius: 0,
        border: 'none',
        backgroundColor: '#fff3cd',
        color: '#856404',
        borderBottom: '1px solid #ffeaa7',
        minHeight: '40px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}
    />
  )
}

export default SandboxWarning