import React from 'react';
import { LockOutlined } from '@ant-design/icons';
import { Alert, Flex, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { getSecurityContextInfo } from '@/utils/secureContext';

interface InsecureConnectionWarningProps {
  onClose?: () => void;
}

const InsecureConnectionWarning: React.FC<InsecureConnectionWarningProps> = ({ onClose }) => {
  const { t } = useTranslation('auth');
  const securityInfo = getSecurityContextInfo();

  return (
    <Flex>
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
          <Flex
            vertical
            // eslint-disable-next-line no-restricted-syntax
            style={{ fontSize: 14 }}
          >
            <Typography.Text>{t('login.insecureConnection.message')}</Typography.Text>
            <Typography.Text
              // eslint-disable-next-line no-restricted-syntax
              style={{ fontSize: 12 }}
            >
              <Typography.Text strong>{t('login.insecureConnection.howToFix')}:</Typography.Text>{' '}
              {securityInfo.suggestion || t('login.insecureConnection.resolution')}
            </Typography.Text>
          </Flex>
        }
        data-testid="insecure-connection-warning"
      />
    </Flex>
  );
};

export default InsecureConnectionWarning;
