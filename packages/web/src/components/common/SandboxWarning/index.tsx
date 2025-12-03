import React, { useEffect, useState } from 'react'
import { ExclamationCircleOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { configService } from '@/services/configService'
import { SandboxBanner, BannerMessage } from './styles'

const SandboxWarning: React.FC = () => {
  const { t } = useTranslation('common')
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const loadInstanceName = async () => {
      const name = await configService.getInstanceName()
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
    <SandboxBanner
      banner
      type="warning"
      showIcon={false}
      closable={false}
      message={
        <BannerMessage>
          <ExclamationCircleOutlined />
          <strong>{t('warnings.sandboxEnvironment')}:</strong> {t('warnings.sandboxMessage')}
        </BannerMessage>
      }
    />
  )
}

export default SandboxWarning
