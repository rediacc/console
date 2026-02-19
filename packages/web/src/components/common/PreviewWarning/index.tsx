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
      className="preview-warning-banner fixed top-0 right-0 left-0 z-[1001] flex min-h-10 items-center justify-center"
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
