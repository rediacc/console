import React, { useEffect } from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { Alert, Flex } from 'antd';
import { useTranslation } from 'react-i18next';

const PreviewWarning: React.FC = () => {
  const { t } = useTranslation('common');

  useEffect(() => {
    document.body.classList.add('has-preview-banner');
    return () => {
      document.body.classList.remove('has-preview-banner');
    };
  }, []);

  return (
    <Alert
      banner
      type="warning"
      showIcon={false}
      closable={false}
      className="preview-warning-banner flex items-center justify-center"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 1001,
        minHeight: 40,
      }}
      message={
        <Flex align="center" wrap className="text-center font-medium">
          <ExclamationCircleOutlined />
          <strong>{t('warnings.previewEnvironment')}:</strong>&nbsp;{t('warnings.previewMessage')}
        </Flex>
      }
      data-testid="preview-warning-banner"
    />
  );
};

export default PreviewWarning;
