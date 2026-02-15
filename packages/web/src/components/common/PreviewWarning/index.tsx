import React, { useEffect } from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { Alert, Flex } from 'antd';
import { useTranslation } from 'react-i18next';

interface PreviewWarningProps {
  sidebarOffset?: number;
}

const PreviewWarning: React.FC<PreviewWarningProps> = ({ sidebarOffset = 0 }) => {
  const { t } = useTranslation('common');

  useEffect(() => {
    document.body.classList.add('has-preview-banner');
    return () => {
      document.body.classList.remove('has-preview-banner');
    };
  }, []);

  useEffect(() => {
    document.documentElement.style.setProperty('--preview-banner-left', `${sidebarOffset}px`);
    return () => {
      document.documentElement.style.removeProperty('--preview-banner-left');
    };
  }, [sidebarOffset]);

  return (
    <Alert
      banner
      type="warning"
      showIcon={false}
      closable={false}
      className="preview-warning-banner flex items-center justify-center"
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
