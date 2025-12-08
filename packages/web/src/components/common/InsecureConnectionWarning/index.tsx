import React from 'react';
import { LockOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { RediaccAlert, RediaccText } from '@/components/ui';
import { getSecurityContextInfo } from '@/utils/secureContext';
import { ResolutionText, WarningDescription } from './styles';

interface InsecureConnectionWarningProps {
  onClose?: () => void;
}

const InsecureConnectionWarning: React.FC<InsecureConnectionWarningProps> = ({ onClose }) => {
  const { t } = useTranslation('auth');
  const securityInfo = getSecurityContextInfo();

  return (
    <RediaccAlert
      spacing="default"
      variant="error"
      showIcon
      icon={<LockOutlined />}
      closable={!!onClose}
      onClose={onClose}
      message={
        <RediaccText as="span" weight="semibold" color="danger">
          {t('login.insecureConnection.title')}
        </RediaccText>
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
      style={{
        borderRadius: '12px',
        border: '2px solid var(--rediacc-color-error)',
        backgroundColor: 'var(--rediacc-color-bg-error)',
      }}
    />
  );
};

export default InsecureConnectionWarning;
