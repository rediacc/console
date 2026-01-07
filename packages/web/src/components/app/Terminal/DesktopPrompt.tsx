/* eslint-disable no-restricted-syntax, react/forbid-elements */
import { DesktopOutlined, DownloadOutlined } from '@ant-design/icons';
import { Button, Result, theme, Typography } from 'antd';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

/**
 * Props for the DesktopPrompt component
 */
export interface DesktopPromptProps {
  /** Title to display */
  title?: string;
  /** Subtitle/description to display */
  subtitle?: string;
  /** Feature name that requires desktop app */
  featureName?: string;
  /** Machine name for protocol URL */
  machineName?: string;
  /** Team name for protocol URL */
  teamName?: string;
  /** Repository name for protocol URL */
  repositoryName?: string;
  /** Additional CSS class name */
  className?: string;
  /** Additional inline styles */
  style?: React.CSSProperties;
}

/**
 * Component displayed when a feature requires the desktop app
 *
 * Shows a friendly message explaining that the feature requires
 * the Electron desktop app and provides a button to open it.
 *
 * @example
 * ```tsx
 * <DesktopPrompt
 *   featureName="Terminal"
 *   machineName="production-server"
 *   repositoryName="webapp"
 * />
 * ```
 */
export function DesktopPrompt({
  title,
  subtitle,
  featureName = 'This feature',
  machineName,
  teamName,
  repositoryName,
  className,
  style,
}: DesktopPromptProps): React.ReactElement {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  const handleOpenDesktop = (): void => {
    // Build protocol URL
    let protocolUrl = 'rediacc://';

    // Add placeholder token (will be replaced by app)
    protocolUrl += 'open';

    // Add path components
    if (teamName) protocolUrl += `/${teamName}`;
    if (machineName) protocolUrl += `/${machineName}`;
    if (repositoryName) protocolUrl += `/${repositoryName}`;

    // Add action
    protocolUrl += '/terminal';

    // Try to open the protocol URL
    window.location.href = protocolUrl;
  };

  const handleDownload = (): void => {
    // Open downloads page
    window.open('https://www.rediacc.com/downloads', '_blank');
  };

  const displayTitle = title ?? t('desktop.prompt.title', { feature: featureName });
  const displaySubtitle =
    subtitle ??
    t('desktop.prompt.subtitle', {
      feature: featureName,
      defaultValue: `${featureName} requires a secure SSH connection that only works in the desktop application.`,
    });

  return (
    <div className={className} style={style}>
      <Result
        icon={<DesktopOutlined style={{ color: token.colorPrimary }} />}
        title={displayTitle}
        subTitle={displaySubtitle}
        extra={
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center' }}>
            {machineName && (
              <Button
                type="primary"
                size="large"
                icon={<DesktopOutlined />}
                onClick={handleOpenDesktop}
              >
                {t('desktop.prompt.openButton', { defaultValue: 'Open in Desktop App' })}
              </Button>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Text type="secondary">
                {t('desktop.prompt.noApp', { defaultValue: "Don't have the app?" })}
              </Text>
              <Button type="link" icon={<DownloadOutlined />} onClick={handleDownload}>
                {t('desktop.prompt.downloadButton', { defaultValue: 'Download' })}
              </Button>
            </div>
          </div>
        }
      />
    </div>
  );
}
