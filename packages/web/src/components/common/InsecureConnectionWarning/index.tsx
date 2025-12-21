import { Alert, Typography } from 'antd';
import React from 'react';
import { LockOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getSecurityContextInfo } from '@/utils/secureContext';

interface InsecureConnectionWarningProps {
  onClose?: () => void;
}

const InsecureConnectionWarning: React.FC<InsecureConnectionWarningProps> = ({ onClose }) => {
  const { t } = useTranslation('auth');
  const securityInfo = getSecurityContextInfo();

  return (
    <div>
      <Alert
        type="error"
        showIcon
        icon={<LockOutlined />}
        closable={!!onClose}
        onClose={onClose}
        message={
          <Typography.Text type="danger" strong>
            {t('login.insecureConnection.title')}
          </Typography.Text>
        }
        description={
          <div style={{ fontSize: 14 }}>
            <p>{t('login.insecureConnection.message')}</p>
            <p style={{ fontSize: 12 }}>
              <strong>{t('login.insecureConnection.howToFix')}:</strong>{' '}
              {securityInfo.suggestion || t('login.insecureConnection.resolution')}
            </p>
          </div>
        }
        data-testid="insecure-connection-warning"
      />
    </div>
  );
};

export default InsecureConnectionWarning;
