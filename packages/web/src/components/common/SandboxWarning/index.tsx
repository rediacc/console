import React, { useEffect, useState } from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { Alert, Flex } from 'antd';
import { useTranslation } from 'react-i18next';
import { configService } from '@/services/api';

const SandboxWarning: React.FC = () => {
  const { t } = useTranslation('common');
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const loadInstanceName = async () => {
      const name = await configService.getInstanceName();
      // Show warning only for sandbox instances
      setIsVisible(name.toLowerCase() === 'sandbox');
    };
    void loadInstanceName();
  }, []);

  useEffect(() => {
    if (isVisible) {
      document.body.classList.add('has-sandbox-banner');
    }
    return () => {
      document.body.classList.remove('has-sandbox-banner');
    };
  }, [isVisible]);

  if (!isVisible) {
    return null;
  }

  return (
    <Alert
      banner
      type="warning"
      showIcon={false}
      closable={false}
      className="sandbox-warning-banner flex items-center justify-center"
      style={{
        position: 'fixed',
        top: 'var(--banner-preview-height, 0px)',
        left: 0,
        right: 0,
        zIndex: 1000,
        minHeight: 40,
      }}
      message={
        <Flex align="center" wrap className="text-center font-medium">
          <ExclamationCircleOutlined />
          <strong>{t('warnings.sandboxEnvironment')}:</strong> {t('warnings.sandboxMessage')}
        </Flex>
      }
      data-testid="sandbox-warning-banner"
    />
  );
};

export default SandboxWarning;
