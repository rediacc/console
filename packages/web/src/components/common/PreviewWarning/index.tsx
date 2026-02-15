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
    const current = Number.parseInt(document.body.style.paddingTop || '0', 10);
    document.body.style.paddingTop = `${current + 40}px`;
    return () => {
      const onUnmount = Number.parseInt(document.body.style.paddingTop || '0', 10);
      document.body.style.paddingTop = `${onUnmount - 40}px`;
    };
  }, []);

  return (
    <Alert
      banner
      type="warning"
      showIcon={false}
      closable={false}
      className={`fixed top-0 right-0 z-[1001] min-h-[40px] flex items-center justify-center ${sidebarOffset > 0 ? 'left-[200px]' : 'left-0'}`}
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
