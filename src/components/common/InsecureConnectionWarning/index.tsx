import React from 'react'
import { useTranslation } from 'react-i18next'
import { LockOutlined } from '@ant-design/icons'
import { getSecurityContextInfo } from '@/utils/secureContext'
import { WarningAlert, WarningTitle, WarningDescription, ResolutionText } from './styles'

interface InsecureConnectionWarningProps {
  onClose?: () => void
}

const InsecureConnectionWarning: React.FC<InsecureConnectionWarningProps> = ({ onClose }) => {
  const { t } = useTranslation('auth')
  const securityInfo = getSecurityContextInfo()

  return (
    <WarningAlert
      type="error"
      showIcon
      icon={<LockOutlined />}
      closable={!!onClose}
      onClose={onClose}
      message={
        <WarningTitle>
          {t('login.insecureConnection.title')}
        </WarningTitle>
      }
      description={
        <WarningDescription>
          <p>{t('login.insecureConnection.message')}</p>
          <ResolutionText>
            <strong>{t('login.insecureConnection.howToFix')}:</strong>{' '}
            {securityInfo.suggestion || t('login.insecureConnection.resolution')}
          </ResolutionText>
        </WarningDescription>
      }
      data-testid="insecure-connection-warning"
    />
  )
}

export default InsecureConnectionWarning
