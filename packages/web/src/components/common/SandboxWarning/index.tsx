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
    // Add padding to body when warning is visible (additive with PreviewWarning)
    if (isVisible) {
      const current = Number.parseInt(document.body.style.paddingTop || '0', 10);
      document.body.style.paddingTop = `${current + 40}px`;
    }
    return () => {
      if (isVisible) {
        const current = Number.parseInt(document.body.style.paddingTop || '0', 10);
        document.body.style.paddingTop = `${current - 40}px`;
      }
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
      className="flex items-center justify-center"
      // eslint-disable-next-line no-restricted-syntax
      style={{
        position: 'fixed',
        top: 40,
        left: 240,
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
    />
  );
};

export default SandboxWarning;
