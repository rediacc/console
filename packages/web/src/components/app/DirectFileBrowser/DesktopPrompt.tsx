/* eslint-disable no-restricted-syntax, react/forbid-elements */
import React from 'react';
import { DesktopOutlined, DownloadOutlined } from '@ant-design/icons';
import { Button, Result, Typography } from 'antd';
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
      icon={<DesktopOutlined style={{ color: '#1890ff' }} />}
      title={`${featureName} Requires Desktop App`}
      subTitle={
        <Paragraph type="secondary" style={{ maxWidth: 400, margin: '0 auto' }}>
          The {featureName.toLowerCase()} uses secure SSH connections that require the Rediacc
          desktop application.
        </Paragraph>
      }
      extra={[
        <Button type="primary" key="open" icon={<DesktopOutlined />} onClick={handleOpenDesktop}>
          Open in Desktop App
        </Button>,
        <Button key="download" icon={<DownloadOutlined />} onClick={handleDownload}>
          Download Desktop App
        </Button>,
      ]}
    >
      <div style={{ textAlign: 'center' }}>
        <Paragraph type="secondary">
          <Text strong>Why desktop only?</Text>
        </Paragraph>
        <Paragraph type="secondary" style={{ maxWidth: 500, margin: '0 auto' }}>
          Direct file operations require a secure SSH connection from your computer to the remote
          machine. This connection cannot be established from a browser for security reasons.
        </Paragraph>
        {machineName && (
          <Paragraph type="secondary" style={{ marginTop: 16 }}>
            <Text code>Machine: {machineName}</Text>
            {repositoryName && (
              <>
                {' '}
                <Text code>Repository: {repositoryName}</Text>
              </>
            )}
          </Paragraph>
        )}
      </div>
    </Result>
  );
};

export default DesktopPrompt;
