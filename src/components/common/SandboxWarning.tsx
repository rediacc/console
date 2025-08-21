import React, { useEffect, useState } from 'react'
import { Alert } from 'antd'
import { ExclamationCircleOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { configService } from '@/services/configService'

const SandboxWarning: React.FC = () => {
  const { t } = useTranslation('common')
  const [instanceName, setInstanceName] = useState<string>('')
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const loadInstanceName = async () => {
      const name = await configService.getInstanceName()
      console.log('SandboxWarning: Instance name loaded:', name)
      setInstanceName(name)
      // Show warning only for sandbox instances
      setIsVisible(name.toLowerCase() === 'sandbox')
    }
    loadInstanceName()
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
        left: 0,
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