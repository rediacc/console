import React, { useEffect, useState } from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { Alert, Flex } from 'antd';
import { useTranslation } from 'react-i18next';
import { configService } from '@/services/configService';

const SandboxWarning: React.FC = () => {
  const { t } = useTranslation('common');
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const loadInstanceName = async () => {
      const name = await configService.getInstanceName();
      // Show warning only for sandbox instances
      setIsVisible(name.toLowerCase() === 'sandbox');
    };
    loadInstanceName();
  }, []);

  useEffect(() => {
    // Add padding to body when warning is visible
    if (isVisible) {
      document.body.style.paddingTop = '40px';
    }
    return () => {
      document.body.style.paddingTop = '';
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
      style={{
        position: 'fixed',
        top: 0,
        left: 240,
        right: 0,
        zIndex: 1000,
        minHeight: 40,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      message={
        <Flex align="center" gap={8} wrap style={{ textAlign: 'center', fontWeight: 500 }}>
          <ExclamationCircleOutlined />
          <strong>{t('warnings.sandboxEnvironment')}:</strong> {t('warnings.sandboxMessage')}
        </Flex>
      }
    />
  );
};

export default SandboxWarning;
