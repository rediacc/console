/* eslint-disable no-restricted-syntax, react/forbid-elements */
import React from 'react';
import { DesktopOutlined, DownloadOutlined } from '@ant-design/icons';
import { Button, Result, theme, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
const { Paragraph, Text } = Typography;

interface DesktopPromptProps {
  /** Feature name to display */
  featureName?: string;
  /** Machine name for context */
  machineName?: string;
  /** Repository name for context */
  repositoryName?: string;
  /** Initial path for context */
  initialPath?: string;
  /** Callback when user clicks download link */
  onDownloadClick?: () => void;
}

/**
 * Prompt shown when a feature requires the desktop app but user is in browser
 */
export const DesktopPrompt: React.FC<DesktopPromptProps> = ({
  featureName = 'File Browser',
  machineName,
  repositoryName,
  initialPath,
  onDownloadClick,
}) => {
  const { t } = useTranslation('common');
  const { token } = theme.useToken();

  const handleOpenDesktop = () => {
    // Build protocol URL
    const parts = ['rediacc:/'];

    // Add team context if available (placeholder - would need actual team from context)
    // For now, just use machine/repo info
    if (machineName) {
      parts.push(machineName);
    }
    if (repositoryName) {
      parts.push(repositoryName);
    }
    parts.push('browser');

    // Add path as query param if provided
    let url = parts.join('/');
    if (initialPath) {
      url += `?path=${encodeURIComponent(initialPath)}`;
    }

    // Try to open protocol URL
    window.location.href = url;
  };

  const handleDownload = () => {
    if (onDownloadClick) {
      onDownloadClick();
    } else {
      // Default: open downloads page
      window.open('https://rediacc.com/downloads', '_blank');
    }
  };

  return (
    <Result
      icon={<DesktopOutlined style={{ color: token.colorPrimary }} />}
      title={t('desktopPrompt.title', { feature: featureName })}
      subTitle={
        <Paragraph type="secondary" style={{ maxWidth: 400, margin: '0 auto' }}>
          {t('desktopPrompt.subtitle', { feature: featureName.toLowerCase() })}
        </Paragraph>
      }
      extra={[
        <Button type="primary" key="open" icon={<DesktopOutlined />} onClick={handleOpenDesktop}>
          {t('desktopPrompt.openDesktop')}
        </Button>,
        <Button key="download" icon={<DownloadOutlined />} onClick={handleDownload}>
          {t('desktopPrompt.downloadDesktop')}
        </Button>,
      ]}
    >
      <div style={{ textAlign: 'center' }}>
        <Paragraph type="secondary">
          <Text strong>{t('desktopPrompt.whyDesktopOnly')}</Text>
        </Paragraph>
        <Paragraph type="secondary" style={{ maxWidth: 500, margin: '0 auto' }}>
          {t('desktopPrompt.securityExplanation')}
        </Paragraph>
        {machineName && (
          <Paragraph type="secondary" style={{ marginTop: 16 }}>
            <Text code>
              {t('desktopPrompt.machine')}: {machineName}
            </Text>
            {repositoryName && (
              <>
                {' '}
                <Text code>
                  {t('desktopPrompt.repository')}: {repositoryName}
                </Text>
              </>
            )}
          </Paragraph>
        )}
      </div>
    </Result>
  );
};

export default DesktopPrompt;
